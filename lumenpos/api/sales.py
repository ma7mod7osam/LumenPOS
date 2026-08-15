import json

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, now_datetime, nowdate

from lumenpos import coupons, gift_cards, store_credit
from lumenpos.price_books import effective_prices, resolve_price_list, standard_prices
from lumenpos.promotions.engine import evaluate
from lumenpos.promotions.loader import get_active_promotions

INVOICE_DOCTYPE = "POS Invoice"


def _sale_doctype(profile):
    """The document a sale posts as for this POS Profile: a **POS Invoice**
    (default — consolidated into a Sales Invoice at register close) or a **Sales
    Invoice** (posted directly, GL immediately, no consolidation)."""
    return (
        "Sales Invoice"
        if profile.get("lumenpos_invoice_mode") == "Sales Invoice"
        else "POS Invoice"
    )


def _doctype_of(name):
    """The sale doctype an existing invoice name belongs to (works in either
    backend — names are unique per doctype)."""
    return "Sales Invoice" if frappe.db.exists("Sales Invoice", name) else "POS Invoice"


def _company_warehouse(profile):
    """A warehouse that BELONGS to the profile's company: the profile's own if it
    matches, else any non-group company warehouse (fallback for a misconfigured
    profile), else None. Used so a sale never posts a wrong-company warehouse
    (which ERPNext rejects even for non-stock lines)."""
    wh = profile.get("warehouse")
    if wh and frappe.db.get_value("Warehouse", wh, "company") == profile.company:
        return wh
    return frappe.db.get_value(
        "Warehouse", {"company": profile.company, "is_group": 0}, "name"
    )


def _find_by_idempotency_key(key):
    """A non-cancelled sale already posted under this client idempotency key, or
    None. Checks both backends (POS Invoice + Sales Invoice)."""
    for dt in ("POS Invoice", "Sales Invoice"):
        try:
            if not frappe.get_meta(dt).has_field("lumenpos_idempotency_key"):
                continue
            name = frappe.db.get_value(
                dt, {"lumenpos_idempotency_key": key, "docstatus": ["!=", 2]}, "name"
            )
            if name:
                return name
        except Exception:
            pass
    return None


def _table_doctype(pos_profile):
    """Sale doctype for a profile's history queries (defaults to POS Invoice)."""
    if pos_profile and frappe.db.get_value(
        "POS Profile", pos_profile, "lumenpos_invoice_mode"
    ) == "Sales Invoice":
        return "Sales Invoice"
    return "POS Invoice"


def _ensure_ignore_pricing_rule(profile):
    """LumenPOS prices every sale itself (price books + its own promotion engine)
    and never applies ERPNext Pricing Rules — so a rule ERPNext re-applies on
    submit would diverge from what the till charged and land the invoice
    "Partly Paid". We already set `ignore_pricing_rule` on the invoice, but
    ERPNext's POS flow (`set_pos_fields`) re-reads that flag from the POS Profile
    on every save and flips ours back to the profile's value. So mirror
    LumenPOS's always-ignore behaviour onto the profile itself: set the POS
    Profile's "Ignore Pricing Rule" to 1 once, idempotently. (No-op if the field
    isn't present or is already set.)"""
    if not frappe.get_meta("POS Profile").has_field("ignore_pricing_rule"):
        return
    if not profile.get("ignore_pricing_rule"):
        frappe.db.set_value("POS Profile", profile.name, "ignore_pricing_rule", 1)
        profile.ignore_pricing_rule = 1
        frappe.clear_document_cache("POS Profile", profile.name)


def _build_sale_invoice(profile, payload, *, validate_serials=True, check_passcode=True):
    """Build a fully-priced, fully-taxed but NOT-yet-inserted POS Invoice from
    the cart. Shared by submit_sale (which then attaches payments and submits)
    and quote_sale (which only reads the authoritative totals so the till can
    charge exactly what the posted invoice will show — no phantom rounding
    'change'). Prices and promotions are ALWAYS resolved server-side; the
    client's math is display-only. Returns (invoice, customer). Does NOT set
    lumenpos_session (the caller does that on submit)."""
    customer = payload.get("customer") or profile.customer
    if not customer:
        frappe.throw(_("Select a customer (or set a default customer on the POS Profile)"))
    customer_group = frappe.db.get_value("Customer", customer, "customer_group")

    app = _resolve_delivery_app(payload)
    price_list = resolve_price_list(
        profile, customer_group, app.get("price_list") if app else None
    )
    if check_passcode:
        _check_price_edit_permission(payload)
    discount_approver = _check_discount_passcode(payload) if check_passcode else None

    lines = _build_lines(
        payload["items"], profile, customer_group, app.get("price_list") if app else None
    )
    bundle_discounts, bundle_applied = _apply_bundles(payload["items"], lines)

    # Promotions never touch bundle lines — bundle pricing is final.
    non_bundle_idx = [
        i for i, row in enumerate(payload["items"]) if not row.get("bundle_key")
    ]
    active_promos = get_active_promotions(profile.name, include_coupon=True)
    # A valid bulk-coupon code unlocks its promotion just like a legacy single
    # code (sets that promo's coupon_code to the provided code for the engine).
    coupons.apply_to_promotions(active_promos, payload.get("coupon_codes") or [])
    promo_raw = evaluate(
        {
            "customer_group": customer_group,
            "pos_profile": profile.name,
            "coupon_codes": [
                str(c).strip().upper() for c in (payload.get("coupon_codes") or [])
            ],
            "items": [lines[i] for i in non_bundle_idx],
        },
        active_promos,
        now_datetime(),
    )
    promo_line_discounts = [0.0] * len(lines)
    for k, orig in enumerate(non_bundle_idx):
        promo_line_discounts[orig] = promo_raw["line_discounts"][k]
    promo_result = {
        "line_discounts": promo_line_discounts,
        "basket_discount": promo_raw["basket_discount"],
        "applied": promo_raw["applied"] + bundle_applied,
    }

    # LumenPOS owns POS pricing (price books + its own promotion engine), and the
    # till/cart NEVER applies ERPNext Pricing Rules — so POS sales always ignore
    # them. Otherwise the posted invoice would diverge from what the till charged
    # and land "Partly Paid". (ERPNext Pricing Rules still apply to non-POS docs.)
    ignore_pricing_rule = 1

    # Some ERPNext versions don't carry `update_stock` on the POS Profile, so a
    # direct attribute access throws ('POSProfile' object has no attribute
    # 'update_stock') and kills the sale. Read it defensively: honour the
    # profile's setting when present, otherwise default to 1 — a POS reduces
    # stock at the point of sale (and Sales-Invoice-direct mode needs it to move
    # stock at all, since there is no consolidation step).
    _update_stock = profile.get("update_stock")
    update_stock = 1 if _update_stock is None else cint(_update_stock)

    # Make ERPNext's POS flow agree with LumenPOS: always ignore Pricing Rules.
    # (Sets POS Profile → Ignore Pricing Rule so the flag survives submit.)
    _ensure_ignore_pricing_rule(profile)

    invoice = frappe.new_doc(_sale_doctype(profile))
    invoice.update(
        {
            "is_pos": 1,
            "pos_profile": profile.name,
            "company": profile.company,
            "customer": customer,
            "selling_price_list": price_list,
            "update_stock": update_stock,
            "set_warehouse": profile.warehouse,
            "taxes_and_charges": profile.taxes_and_charges,
            "ignore_pricing_rule": ignore_pricing_rule,
            "remarks": _build_remarks(payload.get("note"), discount_approver),
        }
    )
    _set_custom(invoice, ("lumenpos_promotions",), json.dumps(promo_result["applied"]))
    _set_custom(invoice, ("lumenpos_note",), payload.get("note"))
    if app:
        # Use the site's existing channel fields: pick_customer (the checkbox
        # that reveals the app fields), custom_app_type (Select) and
        # pick_order_no (Data). The app name must match a custom_app_type
        # option in ERPNext.
        _set_custom(invoice, ("pick_customer",), 1)
        _set_custom(invoice, ("custom_app_type", "lumenpos_app_type"), app["app_name"])
        _set_custom(invoice, ("pick_order_no", "custom_order_id"), payload.get("order_id"))
    if cint(payload.get("is_exchange")):
        _set_custom(invoice, ("is_exchange", "custom_is_exchange"), 1)

    # Total per-unit discount per line: promotion + bundle + a proportional
    # share of any basket discount + manual %. Folding the basket discount
    # into the lines (instead of invoice-level apply_discount_on) keeps the
    # math correct under VAT-inclusive pricing.
    per_unit_discounts = _line_discounts(payload, lines, promo_result, bundle_discounts)

    return_groups = _compute_return_groups(
        payload["items"], lines, non_bundle_idx, active_promos, promo_result["applied"]
    )

    seen_serials = set()
    for i, line in enumerate(lines):
        row = {
            "item_code": line["item_code"],
            "qty": line["qty"],
            "uom": line["stock_uom"],
            "warehouse": profile.warehouse,
        }
        if return_groups[i]:
            row["lumenpos_return_group"] = return_groups[i]
        if validate_serials:
            serials = _validate_line_serials(
                line, payload["items"][i].get("serial_nos"), profile, seen_serials
            )
            if serials:
                row.update({"use_serial_batch_fields": 1, "serial_no": "\n".join(serials)})
        invoice.append("items", row)

    if payload.get("sales_person"):
        invoice.append(
            "sales_team",
            {"sales_person": payload["sales_person"], "allocated_percentage": 100},
        )

    invoice.set_missing_values()

    # Every line keeps the profile's warehouse (set in the row build above) — it
    # belongs to the profile's company. Do NOT clear it for non-stock lines:
    # clearing lets ERPNext fall back to the GLOBAL default warehouse, which on a
    # multi-company site can be another company's ("Warehouse … doesn't belong to
    # Company …"). A warehouse on a non-stock line is harmless (no stock moves).

    # Apply discounts AFTER set_missing_values (it resets them otherwise).
    # CRITICAL: with Pricing Rules off, ERPNext's calculate_taxes_and_totals
    # honours ONLY discount_percentage (it recomputes discount_amount from
    # it). Setting discount_amount alone is silently ignored and the full
    # price is posted. So express every discount as a percentage and clear
    # rate so ERPNext recalculates it from the percentage on each pass.
    for i, item_row in enumerate(invoice.items):
        price = flt(lines[i]["price"])
        per_unit = flt(per_unit_discounts[i])
        item_row.price_list_rate = price
        item_row.margin_type = ""
        item_row.margin_rate_or_amount = 0
        item_row.rate_with_margin = 0
        item_row.rate = 0  # force recompute from discount_percentage
        # LumenPOS prices (price books + its own promotion engine) are
        # authoritative. set_missing_values can stamp an ERPNext Pricing Rule on
        # the row; if left, ERPNext RE-APPLIES it on submit and overrides the
        # price book — the till already collected the LumenPOS price, so the
        # posted invoice diverges and lands "Partly Paid". Clear the stamp so the
        # price we set is what posts.
        item_row.pricing_rules = ""
        item_row.is_free_item = 0
        if price > 0 and per_unit > 0:
            item_row.discount_percentage = flt(min(per_unit, price) / price * 100, 6)
        else:
            item_row.discount_percentage = 0
        item_row.discount_amount = 0

    _apply_service_charge(invoice, profile, lines, per_unit_discounts)

    invoice.run_method("calculate_taxes_and_totals")
    return invoice, customer


def _apply_service_charge(invoice, profile, lines, per_unit_discounts):
    """Optional flat-percent service charge / tip (LumenPOS Settings → Features).
    Posted as a FINAL non-taxed 'Actual' charge so it lands in the grand total
    exactly as the till displayed it. The percent is server-authoritative — read
    from Settings, never the cart — and the base is the discounted, VAT-inclusive
    line total so it mirrors the client's `serviceCharge` getter. No-op on
    returns (negative qty) and when the feature/percent is off."""
    settings = frappe.get_cached_doc("LumenPOS Settings")
    if not settings.get("enable_service_charge"):
        return
    pct = flt(settings.get("service_charge_percent"))
    if pct <= 0:
        return
    base = sum(
        (flt(lines[i]["price"]) - flt(per_unit_discounts[i])) * (lines[i]["qty"] or 0)
        for i in range(len(lines))
    )
    amount = flt(base * pct / 100.0, invoice.precision("grand_total"))
    if amount <= 0:
        return
    from lumenpos.api.settings import company_setting

    account = company_setting(profile.company, "service_charge_account") or settings.get(
        "service_charge_account"
    )
    if not account:
        frappe.throw(
            _("Set a Service charge account for {0} in LumenPOS Settings → Company Accounts (or the global default).").format(profile.company)
        )
    invoice.append(
        "taxes",
        {
            "charge_type": "Actual",
            "account_head": account,
            "description": _("Service charge ({0}%)").format(pct),
            "tax_amount": amount,
            "cost_center": profile.get("cost_center"),
        },
    )


@frappe.whitelist()
def quote_sale(payload):
    """Authoritative pre-payment totals for the current cart — the SAME server
    computation submit_sale uses, so the till charges exactly what the posted
    invoice will show (a VAT-inclusive promo line can round a couple of halalas
    differently from the client, which would otherwise surface as phantom
    'change'). Display-only: no register session, no serial scan, no manager
    passcode, nothing inserted."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    _require_sell()
    profile = frappe.get_cached_doc("POS Profile", payload["pos_profile"])
    invoice, _customer = _build_sale_invoice(
        profile, payload, validate_serials=False, check_passcode=False
    )
    prec = invoice.precision("grand_total")
    # What the till should collect: ERPNext validates payment against
    # `rounded_total or grand_total`, so quote the same.
    payable = invoice.rounded_total or invoice.grand_total
    return {
        "payable": flt(payable, prec),
        "grand_total": flt(invoice.grand_total, prec),
        "rounded_total": flt(invoice.rounded_total, prec),
        "net_total": flt(invoice.net_total, prec),
        "total_taxes": flt(invoice.total_taxes_and_charges, prec),
    }


@frappe.whitelist()
def submit_sale(payload):
    """Create and submit a POS Invoice (consolidated into Sales Invoices by
    ERPNext when the register closes).

    The client sends its cart and chosen payments. Promotions and prices are
    ALWAYS re-resolved server-side — the client's math is display-only.

    payload = {
        "pos_profile", "customer",
        "items": [{"item_code", "qty", "manual_discount_percent", "serial_nos"}],
        "payments": [{"mode_of_payment", "amount"}],
        "redeem_loyalty_points", "coupon_codes", "sales_person",
        "app_type", "order_id", "is_exchange",
        "discount_passcode", "discount_request", "note",
    }
    """
    if isinstance(payload, str):
        payload = json.loads(payload)

    _started = _perf_now()
    _require_sell()
    # Idempotency: a queued OFFLINE sale whose server ACK was lost gets retried
    # on the next flush — if it already posted, return the existing receipt
    # instead of creating a duplicate invoice.
    key = (payload.get("idempotency_key") or "").strip()
    if key:
        existing = _find_by_idempotency_key(key)
        if existing:
            return get_receipt(existing)
    profile = frappe.get_cached_doc("POS Profile", payload["pos_profile"])
    session = _open_session(profile.name)

    invoice, customer = _build_sale_invoice(profile, payload)
    _set_custom(invoice, ("lumenpos_session",), session["name"])
    if key:
        _set_custom(invoice, ("lumenpos_idempotency_key",), key)

    _apply_loyalty_redemption(invoice, customer, profile.company, payload)

    redeem_cards = [
        {"card_no": (c.get("card_no") or "").strip().upper(), "amount": flt(c.get("amount"))}
        for c in (payload.get("gift_cards") or [])
        if flt(c.get("amount")) > 0
    ]
    for card in redeem_cards:
        gift_cards.check_redeem(card["card_no"], card["amount"])

    store_credit_used = 0.0
    gift_card_total = 0.0
    gc_account = None
    sc_account = None
    paid_total = 0.0
    for payment in payload.get("payments", []):
        amount = flt(payment.get("amount"))
        if not amount:
            continue
        if payment["mode_of_payment"] == store_credit.MODE_OF_PAYMENT:
            balance = store_credit.get_balance(customer)
            if store_credit_used + amount > balance + 0.005:
                frappe.throw(
                    _("Store credit balance is {0}, cannot redeem {1}").format(balance, amount)
                )
            sc_account = store_credit.ensure_mode_of_payment(profile.company)
            store_credit_used += amount
        if payment["mode_of_payment"] == gift_cards.mode_of_payment():
            gc_account = gift_cards.ensure_setup(profile.company)
            gift_card_total += amount
        _set_payment(invoice, payment["mode_of_payment"], amount)
        paid_total += amount
    if abs(gift_card_total - sum(c["amount"] for c in redeem_cards)) > 0.005:
        frappe.throw(_("Gift card payments don't match the scanned cards"))
    if not paid_total and not invoice.get("redeem_loyalty_points"):
        frappe.throw(_("At least one payment is required"))

    _reconcile_payment(invoice, profile)
    _drop_empty_payments(invoice)
    # Shop rules on HOW this basket may be paid — re-checked server-side so a
    # stale tab, a queued offline sale or a direct API call can't bypass them.
    from lumenpos import payment_restrictions

    payment_restrictions.assert_allowed(
        _restriction_items(invoice), payload.get("payments"), profile.name
    )
    _apply_payment_references(invoice, payload.get("payments"))
    # Pin liability-backed tenders (gift card, store credit) to THEIR liability
    # account so ERPNext can't resolve them to the company Receivable (debtors):
    # a payment leg on a Receivable account posts WITHOUT a party and fails
    # "Customer is required against Receivable account …". Redeeming reduces the
    # liability we owe the holder, not debtors.
    pin_accounts = {}
    if gc_account:
        pin_accounts[gift_cards.mode_of_payment()] = gc_account
    if sc_account:
        pin_accounts[store_credit.MODE_OF_PAYMENT] = sc_account
    if pin_accounts:
        for row in invoice.payments:
            if row.mode_of_payment in pin_accounts:
                row.account = pin_accounts[row.mode_of_payment]

    _lock_open_session(session["name"])
    t_build = _perf_now()
    invoice.insert()
    t_insert = _perf_now()
    invoice.submit()
    t_submit = _perf_now()

    if store_credit_used:
        store_credit.add_entry(
            customer, "Redeem", store_credit_used, invoice.name, profile.company
        )
    for card in redeem_cards:
        gift_cards.redeem(card["card_no"], card["amount"], invoice.name)
    # Spend any single-use bulk coupons that were entered on this sale.
    coupons.consume(payload.get("coupon_codes") or [], invoice.name)
    # Consume the over-limit discount approval (single-use) the sale was built with.
    if payload.get("discount_request"):
        from lumenpos.api import approval_requests

        approval_requests.consume(payload["discount_request"], invoice.name)

    receipt = get_receipt(invoice.name)
    _log_slow_sale(
        invoice.name,
        started=_started,
        build=t_build,
        insert=t_insert,
        submit=t_submit,
        done=_perf_now(),
        lines=len(invoice.items or []),
    )
    return receipt


@frappe.whitelist()
def sell_gift_card(payload):
    """Sell/load a gift card as a real POS sale: the GIFT-CARD item posts to
    the gift-card liability account (no revenue, no tax until the card is
    spent). payload = {pos_profile, amount, card_no?, expiry_date?,
    customer?, payments:[{mode_of_payment, amount}], sales_person?}"""
    if isinstance(payload, str):
        payload = json.loads(payload)

    _require_sell()
    profile = frappe.get_cached_doc("POS Profile", payload["pos_profile"])
    _ensure_ignore_pricing_rule(profile)
    session = _open_session(profile.name)
    amount = flt(payload.get("amount"))
    if amount <= 0:
        frappe.throw(_("Enter the gift card amount"))

    gift_card_account = gift_cards.ensure_setup(profile.company)
    customer = payload.get("customer") or profile.customer
    if not customer:
        frappe.throw(_("Select a customer (or set a default customer on the POS Profile)"))

    # A gift card is non-stock, but ERPNext STILL validates the line/default
    # warehouse against the company even for a POS sale. Its warehouse resolver
    # (get_item_warehouse) reads the header `set_warehouse` FIRST, then item
    # defaults, then the GLOBAL default warehouse — which on a multi-company site
    # belongs to the wrong company ("Warehouse … doesn't belong to Company …").
    # So we pin a company-owned warehouse UP FRONT (in the header + on the row),
    # exactly like regular sales do — setting it after set_missing_values is too
    # late, the row was already defaulted to the global warehouse by then.
    warehouse = _company_warehouse(profile)
    if not warehouse:
        frappe.throw(
            _(
                "No warehouse belongs to company {0}. Set a Default Warehouse on "
                "the POS Profile (or create a warehouse for this company) before "
                "selling gift cards."
            ).format(profile.company)
        )

    invoice = frappe.new_doc(_sale_doctype(profile))
    invoice.update(
        {
            "is_pos": 1,
            "pos_profile": profile.name,
            "company": profile.company,
            "customer": customer,
            "selling_price_list": profile.selling_price_list,
            "update_stock": 0,
            "ignore_pricing_rule": 1,
            "set_warehouse": warehouse,
            # no taxes: gift card sales are a liability swap, tax applies on use
        }
    )
    _set_custom(invoice, ("lumenpos_session",), session["name"])
    invoice.append(
        "items",
        {
            "item_code": gift_cards.item_code(),
            "qty": 1,
            "rate": amount,
            "price_list_rate": amount,
            "warehouse": warehouse,
            # Post to the gift-card LIABILITY account explicitly, so it never
            # depends on item-default resolution (revenue would be wrong).
            "income_account": gift_card_account,
        },
    )
    if payload.get("sales_person"):
        invoice.append(
            "sales_team",
            {"sales_person": payload["sales_person"], "allocated_percentage": 100},
        )
    invoice.set_missing_values()
    invoice.taxes = []

    # Belt-and-suspenders: re-assert the company warehouse in case
    # set_missing_values re-defaulted a row back to the global default.
    invoice.set("set_warehouse", warehouse)
    for row in invoice.items:
        row.warehouse = warehouse

    paid_total = 0.0
    for payment in payload.get("payments", []):
        pay_amount = flt(payment.get("amount"))
        if pay_amount:
            if payment["mode_of_payment"] == gift_cards.mode_of_payment():
                frappe.throw(_("A gift card cannot pay for a gift card"))
            _set_payment(invoice, payment["mode_of_payment"], pay_amount)
            paid_total += pay_amount
    if paid_total < amount - 0.005:
        frappe.throw(_("Payment must cover the gift card amount"))

    _lock_open_session(session["name"])
    invoice.insert()
    invoice.submit()

    expiry_days = frappe.db.get_single_value("LumenPOS Settings", "gift_card_expiry_days") or 0
    expiry_date = payload.get("expiry_date") or (
        frappe.utils.add_days(nowdate(), int(expiry_days)) if expiry_days else None
    )
    card = gift_cards.issue_card(
        payload.get("card_no"),
        amount,
        profile.company,
        expiry_date=expiry_date,
        customer=payload.get("customer"),
        invoice=invoice.name,
    )

    receipt = get_receipt(invoice.name)
    receipt["gift_card_no"] = card.card_no
    receipt["gift_card_balance"] = card.balance
    receipt["gift_card_expiry"] = str(card.expiry_date) if card.expiry_date else None
    return receipt


@frappe.whitelist()
def gift_card_info(card_no):
    """Balance lookup for the payment screen."""
    card_no = (card_no or "").strip().upper()
    if not frappe.db.exists("POS Gift Card", card_no):
        frappe.throw(_("Gift card {0} not found").format(card_no))
    card = frappe.get_doc("POS Gift Card", card_no)
    return {
        "card_no": card.card_no,
        "status": card.status,
        "balance": card.balance,
        "expiry_date": str(card.expiry_date) if card.expiry_date else None,
    }


def _require_sell():
    if not frappe.has_permission(INVOICE_DOCTYPE, "create"):
        frappe.throw(_("You are not permitted to make sales"), frappe.PermissionError)


def _lock_open_session(session_name):
    """Row-lock the session and re-assert it's still Open immediately before an
    invoice is committed. This serializes against close_register's flip to
    'Closing', so a sale (or correction) can never land on a shift that's being
    closed — which would otherwise leave a submitted invoice that the closing
    snapshot missed and nothing ever consolidates."""
    status = frappe.db.get_value(
        "POS Register Session", session_name, "status", for_update=True
    )
    if status != "Open":
        frappe.throw(
            _("This register is being closed. Reopen it (or wait for the close to finish) before ringing up this sale.")
        )


def _open_session(pos_profile):
    """THE chokepoint for every sale, return and gift-card sale — so the
    shift-ownership rule is enforced here once, for all of them."""
    from lumenpos.api.session import get_open_session, shift_scope

    session = get_open_session(pos_profile)
    if not session:
        frappe.throw(_("No open register session. Open the register first."))
    # "Per cashier" scope: the takings land in the drawer of whoever OPENED the
    # shift, so only that cashier may ring one up. Deliberately no manager
    # bypass — selling is operational, not supervisory (supervision, i.e. cash
    # in/out and closing, keeps its own owner-or-manager check). Handover is
    # close + reopen, which is instant.
    if shift_scope() == "Per cashier":
        owner = session.get("opened_by")
        if owner and owner != frappe.session.user:
            frappe.throw(
                _(
                    "This shift belongs to {0}. Only the cashier who opened the register "
                    "can sell on it — close that shift and open your own."
                ).format(frappe.utils.get_fullname(owner)),
                frappe.PermissionError,
            )
    return session


def _resolve_delivery_app(payload):
    """A sale can come through a delivery app (Jahez, HungerStation, ...).
    The app row decides whether an order ID is mandatory and which price
    list applies."""
    app_name = (payload.get("app_type") or "").strip()
    if not app_name:
        return None
    settings = frappe.get_cached_doc("LumenPOS Settings")
    row = next(
        (r for r in (settings.delivery_apps or []) if r.app_name == app_name), None
    )
    if not row:
        frappe.throw(_("Unknown delivery app {0} — add it in LumenPOS Settings").format(app_name))
    if row.require_order_id and not (payload.get("order_id") or "").strip():
        frappe.throw(_("Order ID is required for {0} sales").format(app_name))
    return {"app_name": row.app_name, "price_list": row.price_list}


def _check_price_edit_permission(payload):
    """Block manual discounts / price edits for staff without the edit-price role
    (LumenPOS Settings → Permissions). A no-op when no discount is applied or no
    role is configured."""
    worst = max(
        flt(payload.get("order_discount_percent")),
        max(
            (flt(i.get("manual_discount_percent")) for i in payload.get("items", [])),
            default=0,
        ),
    )
    if worst <= 0:
        return
    from lumenpos.api import permissions

    if not permissions.can_edit_price():
        frappe.throw(
            _("You're not allowed to edit prices or apply discounts on a sale."),
            frappe.PermissionError,
        )


def _check_discount_passcode(payload):
    """Authorize manual discounts above the configured limit. Per LumenPOS Settings
    → over-limit approval method the cashier clears it with a manager passcode
    (any named approver's PIN or the master passcode) and/or an approved POS
    Discount Request. Returns the approver name for the invoice audit trail."""
    settings = frappe.get_cached_doc("LumenPOS Settings")
    limit = flt(settings.get("discount_limit_percent"))
    if limit <= 0:
        return None
    worst = max(
        flt(payload.get("order_discount_percent")),
        max(
            (flt(i.get("manual_discount_percent")) for i in payload.get("items", [])),
            default=0,
        ),
    )
    if worst <= limit:
        return None

    mode = settings.get("discount_approval_mode") or "Passcode only"
    allow_passcode = mode in ("Passcode only", "Passcode or request")
    allow_request = mode in ("Request only", "Passcode or request")

    # 1) Manager passcode (a manager is at the till)
    if allow_passcode and payload.get("discount_passcode"):
        from lumenpos.api.settings import check_passcode

        result = check_passcode(payload.get("discount_passcode"))
        if not result:
            frappe.throw(
                _("Wrong approver passcode for the {0}% discount.").format(worst)
            )
        approver = result if isinstance(result, str) else None
        from lumenpos.api import audit

        audit.log(
            audit.OVER_LIMIT_DISCOUNT,
            detail=_("{0}% discount cleared by passcode").format(worst)
            + (f" ({approver})" if approver else ""),
            pos_profile=payload.get("pos_profile"),
        )
        return approver

    # 2) An approved discount request (approver was elsewhere). Validated here;
    #    submit_sale consumes it after the invoice posts.
    if allow_request and payload.get("discount_request"):
        from lumenpos.api import approval_requests, audit

        approver = approval_requests.validate_discount(payload["discount_request"], worst)
        audit.log(
            audit.OVER_LIMIT_DISCOUNT,
            detail=_("{0}% discount cleared by approved request {1}").format(
                worst, payload["discount_request"]
            ),
            pos_profile=payload.get("pos_profile"),
        )
        return approver

    if mode == "Request only":
        frappe.throw(
            _("A manual discount of {0}% exceeds the {1}% limit — send an approval request.").format(worst, limit)
        )
    if mode == "Passcode or request":
        frappe.throw(
            _("A manual discount of {0}% exceeds the {1}% limit — enter the manager passcode or send an approval request.").format(worst, limit)
        )
    frappe.throw(
        _("A manual discount of {0}% exceeds the {1}% limit — approver passcode required").format(worst, limit)
    )


def _apply_bundles(payload_items, lines):
    """Validate and price bundle instances. Items arrive as separate lines
    tagged with bundle_key ('BNDL-0001#2'); each instance must contain
    exactly the bundle's components, and the saving (natural total minus
    bundle price) is split across the lines cent-correct — so every line
    stays individually returnable at its discounted rate."""
    groups = {}
    for i, row in enumerate(payload_items):
        key = row.get("bundle_key")
        if key:
            groups.setdefault(key, []).append(i)

    discounts = [0.0] * len(lines)
    applied = []
    for key, idxs in groups.items():
        bundle_name = key.split("#")[0]
        if not frappe.db.exists("POS Bundle", bundle_name):
            frappe.throw(_("Bundle {0} does not exist").format(bundle_name))
        bundle = frappe.get_doc("POS Bundle", bundle_name)
        if bundle.status != "Active":
            frappe.throw(_("Bundle {0} is inactive").format(bundle.title))

        expected = {row.item_code: flt(row.qty) for row in bundle.items}
        actual = {}
        for i in idxs:
            actual[lines[i]["item_code"]] = actual.get(lines[i]["item_code"], 0) + flt(
                lines[i]["qty"]
            )
        if actual != expected:
            frappe.throw(
                _("Bundle {0} is incomplete — it needs exactly: {1}").format(
                    bundle.title,
                    ", ".join(f"{int(q)} x {c}" for c, q in expected.items()),
                )
            )

        natural = sum(lines[i]["price"] * lines[i]["qty"] for i in idxs)
        saving = flt(natural - flt(bundle.bundle_price), 2)
        allocations = {
            row.item_code: flt(row.allocated_amount)
            for row in bundle.items
            if row.get("allocated_amount")
        }
        if len(allocations) == len(bundle.items):
            # Manager-defined split: each line is discounted down (or up) to
            # its allocated share of the bundle price
            for i in idxs:
                discounts[i] += flt(
                    lines[i]["price"] * lines[i]["qty"]
                    - allocations.get(lines[i]["item_code"], 0),
                    2,
                )
        elif saving > 0:
            shares = {
                i: round(saving * (lines[i]["price"] * lines[i]["qty"]) / natural, 2)
                for i in idxs
            }
            delta = round(saving - sum(shares.values()), 2)
            if delta:
                biggest = max(shares, key=lambda i: shares[i])
                shares[biggest] = round(shares[biggest] + delta, 2)
            for i, share in shares.items():
                discounts[i] += share
        applied.append(
            {
                "name": bundle.name,
                "title": bundle.title,
                "promotion_type": "Bundle",
                "savings": max(saving, 0),
            }
        )
    return discounts, applied


def _compute_return_groups(payload_items, lines, non_bundle_idx, active_promos, applied):
    """Tag each line with a return-group id so a regular return can require the
    whole linked set back together (bundles, and Buy X Get Y promos). Bundle
    lines group by their bundle_key; lines bound by an APPLIED Buy X Get Y promo
    group by that promotion. Returns a list aligned with `lines` (None = the
    line is returnable on its own). Exchanges don't use this."""
    from lumenpos.promotions import engine

    groups = [None] * len(lines)
    for i, row in enumerate(payload_items):
        if row.get("bundle_key"):
            groups[i] = "BUNDLE:" + row["bundle_key"]

    applied_bxgy = {
        a.get("name") for a in applied if a.get("promotion_type") == "Buy X Get Y"
    }
    if applied_bxgy:
        cart = {"items": [lines[i] for i in non_bundle_idx]}
        by_name = {p["name"]: p for p in active_promos}
        for name in applied_bxgy:
            promo = by_name.get(name)
            if not promo:
                continue
            involved = set(engine._matching_indexes(cart, promo, role="Buy")) | set(
                engine._matching_indexes(cart, promo, role="Get")
            )
            for pos in involved:
                orig = non_bundle_idx[pos]
                if groups[orig] is None:  # bundle membership wins if somehow both
                    groups[orig] = "PROMO:" + name
    return groups


def _build_remarks(note, discount_approver):
    parts = []
    if note:
        parts.append(note)
    if discount_approver:
        parts.append(_("Discount approved by {0}").format(discount_approver))
    return "\n".join(parts) or None


def _set_custom(doc, candidate_fields, value):
    """Write to the site's own custom field when it exists (e.g.
    custom_app_type), otherwise fall back to the lumenpos_* field.

    Boolean flags are coerced to the target field's type: some sites model
    is_exchange / pick_customer as a Yes/No **Select** instead of a Check, where
    writing a raw 1 is rejected ("Is Exchange ... should be one of Yes, No")."""
    for fieldname in candidate_fields:
        df = doc.meta.get_field(fieldname)
        if df:
            doc.set(fieldname, _coerce_custom_value(df, value))
            return


def _coerce_custom_value(df, value):
    if df.fieldtype == "Check":
        return 1 if value else 0
    # A boolean flag (0/1) written to a Yes/No Select field.
    if df.fieldtype == "Select" and value in (0, 1):
        options = {
            o.strip().lower(): o.strip()
            for o in (df.options or "").split("\n")
            if o.strip()
        }
        if "yes" in options and "no" in options:
            return options["yes"] if value else options["no"]
    return value


def _get_custom(doc, candidate_fields):
    for fieldname in candidate_fields:
        if doc.meta.has_field(fieldname):
            return doc.get(fieldname)
    return None


def _truthy_custom(value):
    """Read a boolean flag stored as a Check (1/0) OR a Yes/No Select."""
    if isinstance(value, str):
        return 1 if value.strip().lower() in ("yes", "1", "true") else 0
    return cint(value)


def _split_tags(value):
    """ERPNext stores _user_tags as a comma-joined string with a leading comma
    (e.g. ",vip,electronics"). Return a clean list of tag names."""
    return [t.strip() for t in (value or "").split(",") if t.strip()]


# Field kinds for host-site detection. A marketplace app lands on sites it has
# never seen, and the SAME field name can mean different things: a site may have
# `online_order` holding the marketplace order NUMBER while we assume it is the
# boolean "is this an online order" flag. Matching on the name alone then makes
# the Yes/No filter compare an order number to 1 (matching nothing) and renders
# a number where a flag belongs — silently, with no error. So a candidate must
# match on TYPE as well as name.
_BOOL_FIELDTYPES = {"Check", "Select"}   # Select only when it looks like Yes/No
_TEXT_FIELDTYPES = {
    "Data", "Small Text", "Text", "Long Text", "Select", "Link", "Read Only", "Int",
}


def _is_boolean_field(df):
    """A field that can hold a 0/1 flag: a Check, or a Yes/No Select."""
    if df.fieldtype == "Check":
        return True
    if df.fieldtype == "Select":
        options = {o.strip().lower() for o in (df.options or "").split("\n") if o.strip()}
        return "yes" in options and "no" in options
    return False


def _first_column(candidates, doctype=INVOICE_DOCTYPE, kind=None):
    """First of the candidate fieldnames that actually exists as a column on the
    given sale doctype (so history search uses the site's real fields), or None.

    `kind` ("bool" | "text") additionally requires the field to BE that kind on
    this site — see the note above on same-name/different-meaning collisions.
    Appended as a third parameter on purpose: existing callers pass `doctype`
    positionally, and reordering would silently bind the doctype into the new
    argument."""
    meta = None
    if kind:
        try:
            meta = frappe.get_meta(doctype)
        except Exception:
            meta = None
    for fieldname in candidates:
        if not frappe.db.has_column(doctype, fieldname):
            continue
        if kind and meta:
            df = meta.get_field(fieldname)
            if not df:
                continue  # a real column with no docfield — can't verify, skip
            if kind == "bool" and not _is_boolean_field(df):
                continue
            if kind == "text" and (df.fieldtype not in _TEXT_FIELDTYPES or _is_boolean_field(df)):
                continue
        return fieldname
    return None


def _validate_line_serials(line, serial_nos, profile, seen_serials):
    """STRICT: serialized items cannot be sold without exactly qty serials,
    each one Active stock in the register's warehouse. No auto-pick."""
    if not line.get("has_serial_no"):
        return []
    from lumenpos.api.catalog import _check_serial

    qty = line["qty"]
    if abs(qty - round(qty)) > 1e-6:
        frappe.throw(_("{0} is serialized; quantity must be a whole number").format(line["item_code"]))
    serials = [s.strip() for s in (serial_nos or []) if s and s.strip()]
    if len(serials) != int(qty):
        frappe.throw(
            _("{0} is serialized: scan {1} serial number(s), got {2}").format(
                line["item_code"], int(qty), len(serials)
            )
        )
    for serial in serials:
        if serial in seen_serials:
            frappe.throw(_("Serial {0} is scanned twice in this sale").format(serial))
        seen_serials.add(serial)
        check = _check_serial(line["item_code"], serial, profile.warehouse)
        if not check["valid"]:
            frappe.throw(check["message"])
    return serials


def _line_discounts(payload, lines, promo_result, bundle_discounts):
    """Per-unit discount for each line: promotion + bundle + a proportional
    share of any basket discount, with the manual % applied on top of the
    discounted unit price. Returned as a per-unit amount (ERPNext multiplies
    by qty)."""
    n = len(lines)
    whole = [0.0] * n  # whole-line (qty-total) discount before manual %

    for i in range(n):
        whole[i] = flt(promo_result["line_discounts"][i]) + flt(bundle_discounts[i])

    # Spread the basket discount across non-bundle lines by their net amount
    basket = flt(promo_result.get("basket_discount"))
    if basket > 0:
        eligible = [
            i for i in range(n) if not payload["items"][i].get("bundle_key")
        ]
        net = {
            i: lines[i]["price"] * lines[i]["qty"] - whole[i] for i in eligible
        }
        total_net = sum(v for v in net.values() if v > 0)
        if total_net > 0:
            spread = 0.0
            for i in eligible:
                if net[i] <= 0:
                    continue
                share = flt(basket * net[i] / total_net, 2)
                whole[i] += share
                spread += share
            # park any rounding remainder on the largest eligible line
            remainder = flt(basket - spread, 2)
            if remainder and eligible:
                biggest = max(eligible, key=lambda i: net[i])
                whole[biggest] += remainder

    # Whole-cart discount stacks on top of every line-level discount. Bundles
    # are priced as a fixed package and never participate.
    order_pct = flt(payload.get("order_discount_percent"))
    per_unit = [0.0] * n
    for i in range(n):
        qty = lines[i]["qty"] or 1
        promo_per_unit = whole[i] / qty
        is_bundle = bool(payload["items"][i].get("bundle_key"))
        manual_pct = (
            0 if is_bundle else flt(payload["items"][i].get("manual_discount_percent"))
        )
        manual_per_unit = (lines[i]["price"] - promo_per_unit) * manual_pct / 100.0
        unit_discount = promo_per_unit + manual_per_unit
        if order_pct and not is_bundle:
            net_after_line = lines[i]["price"] - unit_discount
            unit_discount += net_after_line * order_pct / 100.0
        per_unit[i] = max(0.0, unit_discount)
    return per_unit


def _reconcile_payment(invoice, profile):
    """Guarantee the payment settles the invoice so ERPNext never rejects it
    as a partial POS payment. The server total is authoritative; tiny gaps
    (cent rounding) are absorbed onto the largest payment row, while a large
    shortfall means a real config mismatch and is surfaced with both numbers
    instead of ERPNext's cryptic error."""
    invoice.run_method("calculate_taxes_and_totals")
    target = flt(invoice.rounded_total or invoice.grand_total, 2)
    loyalty = flt(invoice.loyalty_amount) if invoice.get("redeem_loyalty_points") else 0
    paid = flt(sum(flt(p.amount) for p in invoice.payments), 2)
    shortfall = flt(target - paid - loyalty, 2)
    if shortfall <= 0:
        return  # fully covered (cash over-tender becomes change)

    tolerance = flt(profile.get("lumenpos_payment_tolerance")) or 1.0
    if shortfall > tolerance:
        frappe.throw(
            _(
                "This sale was rung up as {0} but ERPNext calculated {1} (short by {2}). "
                "This is usually a price-list or VAT mismatch — check that every item is "
                "priced on the active price list and that the VAT template's "
                "'included in rate' flag matches your shelf prices (Settings → Status)."
            ).format(flt(paid + loyalty, 2), target, shortfall)
        )

    rows = [row for row in invoice.payments if flt(row.amount)]
    if rows:
        biggest = max(rows, key=lambda row: flt(row.amount))
        biggest.amount = flt(biggest.amount + shortfall, 2)
        invoice.run_method("calculate_taxes_and_totals")


def _restriction_items(doc):
    """Cart lines as {item_code, item_group, brand, tags} for payment-restriction
    matching. Read from the built invoice so it reflects exactly what will post."""
    codes = list({r.item_code for r in (doc.items or []) if r.item_code})
    if not codes:
        return []
    rows = frappe.get_all(
        "Item",
        filters={"name": ["in", codes]},
        fields=["name", "item_group", "brand", "_user_tags"],
    )
    return [
        {
            "item_code": r.name,
            "item_group": r.item_group,
            "brand": r.brand,
            "tags": _split_tags(r.get("_user_tags")),
        }
        for r in rows
    ]


def _payment_rules():
    """{mode: {require_reference, reference_label}} from LumenPOS Settings."""
    try:
        doc = frappe.get_cached_doc("LumenPOS Settings")
    except Exception:
        return {}
    out = {}
    for row in doc.get("payment_method_rules") or []:
        if row.mode_of_payment:
            out[row.mode_of_payment] = {
                "require_reference": 1 if row.get("require_reference") else 0,
                "reference_label": row.get("reference_label") or "",
            }
    return out


def _apply_payment_references(doc, payments):
    """Stamp each tender's transaction reference onto its payment row, and
    enforce the ones configured as required — a card payment with no approval
    code can't be traced back to the terminal when a customer disputes it."""
    rules = _payment_rules()
    if not rules:
        return
    supplied = {}
    for p in payments or []:
        mode = p.get("mode_of_payment")
        if mode and (p.get("reference_no") or "").strip():
            supplied[mode] = str(p["reference_no"]).strip()
    for row in doc.payments:
        rule = rules.get(row.mode_of_payment)
        if not rule:
            continue
        ref = supplied.get(row.mode_of_payment)
        if ref and doc.meta.has_field("payments") and hasattr(row, "reference_no"):
            row.reference_no = ref
        if rule["require_reference"] and flt(row.amount) and not ref:
            frappe.throw(
                _("{0} needs a {1} before this sale can be completed.").format(
                    row.mode_of_payment, rule["reference_label"] or _("transaction reference")
                )
            )


def _set_payment(invoice, mode_of_payment, amount):
    """set_missing_values pre-fills zero-amount rows for every mode on the
    POS Profile; fill those instead of appending duplicates."""
    for row in invoice.payments:
        if row.mode_of_payment == mode_of_payment:
            row.amount = flt(row.amount) + amount
            return
    invoice.append("payments", {"mode_of_payment": mode_of_payment, "amount": amount})


def _drop_empty_payments(doc):
    """ERPNext pre-fills a zero-amount row for EVERY Mode of Payment on the POS
    Profile (set_missing_values). Keep only the tenders actually used, so the
    invoice records — and history shows — the real payment method(s) instead of
    all eleven. No-op if nothing was used (e.g. a loyalty-only sale)."""
    used = [p for p in doc.payments if flt(p.amount)]
    if used and len(used) != len(doc.payments):
        doc.payments = used


def _sync_return_paid_amount(doc):
    """make_return_doc copies the ORIGINAL sale's paid_amount onto the credit
    note, and calculate_taxes_and_totals does NOT recompute it for returns — so
    paid_amount keeps the full original figure (e.g. -274.50) while the payment
    rows we set total only the returned value (e.g. -137.24). That mismatch trips
    POS validate_pos ("Paid amount + Write Off Amount can not be greater than
    Grand Total"). Force paid_amount / base_paid_amount to equal the rows."""
    paid = sum(flt(p.amount) for p in doc.payments)
    doc.paid_amount = flt(paid, doc.precision("paid_amount"))
    doc.base_paid_amount = flt(
        paid * (doc.conversion_rate or 1), doc.precision("base_paid_amount")
    )


def _apply_loyalty_redemption(invoice, customer, company, payload):
    points = cint(payload.get("redeem_loyalty_points"))
    if points <= 0:
        return
    from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
        get_loyalty_program_details_with_points,
    )

    details = get_loyalty_program_details_with_points(
        customer, company=company, silent=True, include_expired_entry=False
    )
    if not details or not details.get("loyalty_program"):
        frappe.throw(_("Customer {0} is not enrolled in a loyalty program").format(customer))
    if points > cint(details.loyalty_points):
        frappe.throw(
            _("Customer has {0} loyalty points, cannot redeem {1}").format(
                cint(details.loyalty_points), points
            )
        )
    invoice.redeem_loyalty_points = 1
    invoice.loyalty_program = details.loyalty_program
    invoice.loyalty_points = points
    invoice.loyalty_amount = flt(points * flt(details.conversion_factor), 2)
    invoice.loyalty_redemption_account = details.expense_account
    invoice.loyalty_redemption_cost_center = details.cost_center


def _build_lines(items, profile, customer_group=None, app_price_list=None):
    """Resolve server-side prices and attributes for the engine. Client
    prices are ignored. `price` is the effective unit price (price-book
    overrides / delivery-app list applied); `standard_price` is the plain
    selling price the 'Standard Price' promo basis discounts from."""
    if not items:
        frappe.throw(_("Cart is empty"))
    codes = [row["item_code"] for row in items]
    details = {
        d.name: d
        for d in frappe.get_all(
            "Item",
            filters={"name": ["in", codes]},
            fields=[
                "name",
                "item_name",
                "item_group",
                "brand",
                "stock_uom",
                "has_serial_no",
                "_user_tags",
            ],
        )
    }
    uom_map = {code: d.stock_uom for code, d in details.items()}
    price_map = effective_prices(profile, codes, customer_group, app_price_list, uom_map)
    standard_map = standard_prices(profile, codes, uom_map)

    lines = []
    for row in items:
        detail = details.get(row["item_code"])
        if not detail:
            frappe.throw(_("Unknown item {0}").format(row["item_code"]))
        qty = flt(row.get("qty"))
        if qty <= 0:
            frappe.throw(_("Quantity for {0} must be positive").format(detail.item_name))
        price = flt(price_map.get(detail.name, 0))
        lines.append(
            {
                "item_code": detail.name,
                "item_group": detail.item_group,
                "brand": detail.brand,
                "tags": _split_tags(detail.get("_user_tags")),
                "stock_uom": detail.stock_uom,
                "has_serial_no": detail.has_serial_no,
                "qty": qty,
                "price": price,
                "standard_price": flt(standard_map.get(detail.name) or price),
            }
        )
    return lines


@frappe.whitelist()
def email_receipt(invoice, email=None):
    """Email a copy of the receipt to the customer (Settings → Features → Email
    receipt). Uses the explicit address, else the invoice contact, else the
    customer's email. Attaches the POS Profile's Print Format if one is set.
    Requires an outgoing Email Account on the site."""
    settings = frappe.get_cached_doc("LumenPOS Settings")
    if not settings.get("enable_email_receipt"):
        frappe.throw(_("Email receipts are turned off (Settings → Features)."))
    doctype = _doctype_of(invoice)
    if not doctype:
        frappe.throw(_("Sale {0} not found").format(invoice))
    doc = frappe.get_doc(doctype, invoice)
    doc.check_permission("read")

    recipient = (email or "").strip() or doc.get("contact_email")
    if not recipient and doc.get("customer"):
        recipient = frappe.db.get_value("Customer", doc.customer, "email_id")
    if not recipient:
        frappe.throw(_("No email address — add one to the customer or type it in."))

    print_format = frappe.db.get_value("POS Profile", doc.get("pos_profile"), "print_format")
    attachment = None
    try:
        attachment = frappe.attach_print(doctype, invoice, print_format=print_format or None)
    except Exception:
        # Fall back to a plain-text message if the print format can't render.
        frappe.clear_last_message()
    frappe.sendmail(
        recipients=[recipient],
        subject=_("Your receipt from {0} — {1}").format(doc.get("company") or "", invoice),
        message=_("Thank you for your purchase. Your receipt {0} is attached.").format(invoice),
        attachments=[attachment] if attachment else None,
        reference_doctype=doctype,
        reference_name=invoice,
    )
    from lumenpos.api import audit

    audit.log(
        "Email receipt",
        detail=f"Receipt emailed to {recipient}",
        reference_doctype=doctype,
        reference_name=invoice,
        pos_profile=doc.get("pos_profile"),
    )
    return {"sent": True, "email": recipient}


@frappe.whitelist()
def get_receipt(invoice):
    doc = frappe.get_doc(_doctype_of(invoice), invoice)
    doc.check_permission("read")
    earned_points = frappe.db.get_value(
        "Loyalty Point Entry",
        {"invoice": doc.name, "loyalty_points": [">", 0]},
        "loyalty_points",
    )
    # Barcodes for the receipt (optional column, gated client-side).
    barcode_map = {}
    codes = [row.item_code for row in doc.items]
    if codes:
        for b in frappe.get_all(
            "Item Barcode",
            filters={"parent": ["in", codes]},
            fields=["parent", "barcode"],
            order_by="idx asc",
        ):
            barcode_map.setdefault(b.parent, b.barcode)
    from lumenpos.api.settings import resolve_receipt_custom_fields

    return {
        "name": doc.name,
        "doctype": doc.doctype,  # so the client prints the right doc via a Print Format
        "custom_fields": resolve_receipt_custom_fields(doc),
        "note": _get_custom(doc, ("lumenpos_note",)) or "",
        "is_return": doc.is_return,
        "return_against": doc.return_against,
        "loyalty_points_earned": cint(earned_points),
        "loyalty_points_redeemed": cint(doc.loyalty_points) if doc.get("redeem_loyalty_points") else 0,
        "loyalty_amount": flt(doc.loyalty_amount) if doc.get("redeem_loyalty_points") else 0,
        "sales_person": doc.sales_team[0].sales_person if doc.get("sales_team") else None,
        "app_type": _get_custom(doc, ("custom_app_type", "lumenpos_app_type")),
        "order_id": _get_custom(doc, ("pick_order_no", "custom_order_id", "lumenpos_order_id")),
        "is_exchange": _truthy_custom(_get_custom(doc, ("is_exchange", "custom_is_exchange"))),
        "posting_date": str(doc.posting_date),
        "posting_time": str(doc.posting_time),
        "customer": doc.customer,
        "customer_name": doc.customer_name,
        "company": doc.company,
        "currency": doc.currency,
        "items": [
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": row.qty,
                "price_list_rate": row.price_list_rate,
                "rate": row.rate,
                "amount": row.amount,
                "discount_amount": row.discount_amount,
                "barcode": barcode_map.get(row.item_code),
                "serial_no": (row.get("serial_no") or "").strip() or None,
            }
            for row in doc.items
        ],
        "total": doc.total,
        "net_total": doc.net_total,
        "discount_amount": doc.discount_amount,
        "total_taxes_and_charges": doc.total_taxes_and_charges,
        "taxes": [
            {"description": t.description, "tax_amount": t.tax_amount}
            for t in (doc.taxes or [])
        ],
        "grand_total": doc.grand_total,
        "rounded_total": doc.rounded_total,
        "paid_amount": doc.paid_amount,
        "change_amount": doc.change_amount,
        "payments": [
            {"mode_of_payment": p.mode_of_payment, "amount": p.amount}
            for p in (doc.payments or [])
            if p.amount
        ],
        "applied_promotions": json.loads(
            _get_custom(doc, ("lumenpos_promotions",)) or "[]"
        ),
    }


@frappe.whitelist()
def recent_sales(pos_profile, limit=50):
    return search_sales({"pos_profile": pos_profile, "limit": limit})


SEARCH_PROBE_CAP = 1000

# A sale slower than this writes ONE Error Log entry with a phase breakdown.
# Without it "the POS is slow" is unfalsifiable; with it, the first real capture
# tells you whether the time is in this app or in ERPNext's own submit.
SLOW_SALE_MS = 2500


def _perf_now():
    import time

    return time.monotonic()


def _log_slow_sale(invoice_name, *, started, build, insert, submit, done, lines):
    """Best-effort: never let instrumentation break a sale."""
    try:
        total_ms = (done - started) * 1000
        if total_ms < SLOW_SALE_MS:
            return
        frappe.log_error(
            title="LumenPOS slow sale",
            message=(
                f"invoice: {invoice_name}\n"
                f"lines:   {lines}\n"
                f"total:   {total_ms:.0f} ms\n"
                f"  build (price/promo/validate): {(build - started) * 1000:.0f} ms\n"
                f"  insert:                       {(insert - build) * 1000:.0f} ms\n"
                f"  submit (ERPNext):             {(submit - insert) * 1000:.0f} ms\n"
                f"  post (loyalty/gc/receipt):    {(done - submit) * 1000:.0f} ms\n"
            ),
        )
    except Exception:
        pass


def _search_probe_names(doctype, term, order_field=None, cap=SEARCH_PROBE_CAP):
    """Free-text sales search as SLIM, SINGLE-PREDICATE PROBES.

    One wide OR over invoice-no / customer / customer-name / mobile / order-id —
    each a leading-wildcard LIKE, one of them across a JOIN — gives the query
    planner a choice between an index merge and a full table scan. That is why
    the same search is instant one minute and times out the next once the table
    is large. Every probe below can use exactly ONE index; we merge the names
    here, most-precise first, and the caller then filters by primary key so the
    wide display columns never sit on a scan path.

    A bounded contains-scan runs LAST and only if the precise probes came back
    thin, so the expensive case is the exception rather than the rule."""
    term = (term or "").strip()
    if not term:
        return []

    names, seen = [], set()

    def add(rows):
        for row in rows:
            name = row[0]
            if name not in seen:
                seen.add(name)
                names.append(name)

    def q(sql, args):
        if len(names) >= cap:
            return []
        try:
            return frappe.db.sql(sql, args)  # nosemgrep
        except Exception:
            return []

    tbl = f"tab{doctype}"
    prefix = f"{term}%"
    anywhere = f"%{term}%"
    remaining = lambda: max(0, cap - len(names))  # noqa: E731

    # 1) exact invoice number — primary key, instant
    add(q(f"select name from `{tbl}` where name = %s limit 1", (term,)))
    # 2) invoice-number prefix — primary-key range
    add(q(f"select name from `{tbl}` where name like %s limit %s", (prefix, remaining())))
    # 3) customer id prefix — indexed foreign key
    add(q(f"select name from `{tbl}` where customer like %s limit %s", (prefix, remaining())))
    # 4) customer-name prefix — indexed on most sites
    add(q(f"select name from `{tbl}` where customer_name like %s limit %s", (prefix, remaining())))
    # 5) mobile: resolve customers first (their own index), then invoices by FK
    if remaining():
        customers = q(
            "select name from `tabCustomer` where mobile_no like %s limit 200", (prefix,)
        )
        if customers:
            add(
                q(
                    f"select name from `{tbl}` where customer in %s limit %s",
                    (tuple(c[0] for c in customers), remaining()),
                )
            )
    # 6) order id / marketplace number prefix
    if order_field and remaining():
        add(
            q(
                f"select name from `{tbl}` where `{order_field}` like %s limit %s",
                (prefix, remaining()),
            )
        )
    # 7) last resort — bounded contains scans, only when the precise probes were
    # thin (a cashier searching a mid-string fragment).
    if len(names) < 50:
        add(q(f"select name from `{tbl}` where customer_name like %s limit %s", (anywhere, 200)))
        if order_field:
            add(
                q(
                    f"select name from `{tbl}` where `{order_field}` like %s limit %s",
                    (anywhere, 200),
                )
            )
    return names[:cap]


@frappe.whitelist()
def search_sales(filters=None):
    """Sales-history search. filters = {
        search: free text (invoice no, customer, mobile, order id),
        pos_profile, all_profiles: 1, date_from, date_to,
        status, docstatus: Submitted|Draft|Cancelled|All,
        app_type: "Walk-in" | app name, online_order: "1"|"0",
        item, serial_no, total_min, total_max, limit
    }"""
    if isinstance(filters, str):
        filters = json.loads(filters)
    f = frappe._dict(filters or {})
    # Which backend's table to read (POS Invoice by default; Sales Invoice when
    # the profile posts directly). The client always passes pos_profile so the
    # mode is known even when listing across profiles.
    doctype = _table_doctype(f.get("pos_profile"))
    if not frappe.has_permission(doctype, "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)

    # kind= makes these resolve by TYPE as well as name: a site whose
    # `online_order` holds the marketplace order NUMBER must not be treated as
    # the boolean online flag (and vice-versa) — see _first_column.
    app_field = _first_column(("custom_app_type", "lumenpos_app_type"), doctype, kind="text")
    # `online_order` is last: on a site where it is a Data field it holds the
    # marketplace order NUMBER, and without this the number is invisible to
    # search. Where it's a real Check it fails the "text" kind and is skipped.
    order_field = _first_column(
        ("pick_order_no", "custom_order_id", "lumenpos_order_id", "online_order"),
        doctype,
        kind="text",
    )
    online_field = _first_column(
        ("online_order", "custom_online_order", "is_online_order"), doctype, kind="bool"
    )
    exchange_field = _first_column(("is_exchange", "custom_is_exchange"), doctype, kind="bool")

    conds, params = [], {}

    if f.pos_profile and not cint(f.all_profiles):
        conds.append("pi.pos_profile = %(pos_profile)s")
        params["pos_profile"] = f.pos_profile

    docstatus = f.get("docstatus") or "Submitted"
    if docstatus == "Submitted":
        conds.append("pi.docstatus = 1")
    elif docstatus == "Draft":
        conds.append("pi.docstatus = 0")
    elif docstatus == "Cancelled":
        conds.append("pi.docstatus = 2")
    # "All" adds no condition
    if doctype == "Sales Invoice":
        conds.append("pi.is_pos = 1")  # POS sales only, not desk Sales Invoices

    if f.get("customer"):
        conds.append("pi.customer = %(customer)s")
        params["customer"] = f.customer
    if f.get("is_return") in ("1", 1, True):
        conds.append("pi.is_return = 1")
    elif f.get("is_return") in ("0", 0):
        conds.append("pi.is_return = 0")
    if f.status:
        conds.append("pi.status = %(status)s")
        params["status"] = f.status
    if f.date_from:
        conds.append("pi.posting_date >= %(date_from)s")
        params["date_from"] = f.date_from
    if f.date_to:
        conds.append("pi.posting_date <= %(date_to)s")
        params["date_to"] = f.date_to
    if f.get("total_min") not in (None, ""):
        conds.append("abs(pi.grand_total) >= %(total_min)s")
        params["total_min"] = flt(f.total_min)
    if f.get("total_max") not in (None, ""):
        conds.append("abs(pi.grand_total) <= %(total_max)s")
        params["total_max"] = flt(f.total_max)

    if app_field and f.app_type == "Walk-in":
        conds.append(f"coalesce(pi.{app_field}, '') = ''")
    elif app_field and f.app_type:
        conds.append(f"pi.{app_field} = %(app_type)s")
        params["app_type"] = f.app_type

    online = f.get("online_order")
    if online_field and online in ("1", 1, True):
        conds.append(f"coalesce(pi.{online_field}, 0) = 1")
    elif online_field and online in ("0", 0):
        conds.append(f"coalesce(pi.{online_field}, 0) = 0")

    if f.search:
        # Resolve the free text to a bounded set of invoice names FIRST (slim,
        # single-index probes — see _search_probe_names), then filter by primary
        # key. The old single wide OR mixed leading-wildcard LIKEs across a JOIN,
        # which let the optimizer pick a full table scan: instant on a small
        # site, a 504 on a large one.
        probe = _search_probe_names(doctype, f.search.strip(), order_field)
        if not probe:
            return []
        conds.append("pi.name in %(probe_names)s")
        params["probe_names"] = tuple(probe)

    if f.item:
        params["item"] = f"%{f.item.strip()}%"
        conds.append(
            f"exists (select 1 from `tab{doctype} Item` pii"
            " where pii.parent = pi.name"
            " and (pii.item_code like %(item)s or pii.item_name like %(item)s))"
        )

    if f.serial_no:
        params["serial_like"] = f"%{f.serial_no.strip()}%"
        params["serial_exact"] = f.serial_no.strip()
        conds.append(
            f"(exists (select 1 from `tab{doctype} Item` pis"
            "   where pis.parent = pi.name and pis.serial_no like %(serial_like)s)"
            " or exists (select 1 from `tabSerial and Batch Bundle` b"
            "   join `tabSerial and Batch Entry` e on e.parent = b.name"
            "   where b.voucher_no = pi.name and e.serial_no = %(serial_exact)s))"
        )

    if f.get("payment_mode"):
        conds.append(
            "exists (select 1 from `tabSales Invoice Payment` sip"
            f" where sip.parent = pi.name and sip.parenttype = '{doctype}'"
            " and sip.mode_of_payment = %(payment_mode)s)"
        )
        params["payment_mode"] = f.payment_mode

    where = " and ".join(conds) if conds else "1=1"
    params["limit"] = min(cint(f.get("limit") or 100), 200)
    params["start"] = cint(f.get("start") or 0)

    app_select = f"pi.{app_field} as app_type" if app_field else "null as app_type"
    order_select = f"pi.{order_field} as order_id" if order_field else "null as order_id"
    online_select = f"pi.{online_field} as online_order" if online_field else "0 as online_order"
    exchange_select = (
        f"pi.{exchange_field} as is_exchange" if exchange_field else "0 as is_exchange"
    )
    pay_modes_select = (
        "(select group_concat(distinct sip.mode_of_payment separator ', ')"
        " from `tabSales Invoice Payment` sip"
        f" where sip.parent = pi.name and sip.parenttype = '{doctype}'"
        " and sip.amount != 0) as payment_modes"
    )
    # Interpolated names are all fixed/validated: `doctype` is POS Invoice /
    # Sales Invoice; the *_select and `where` fragments come from a column
    # allowlist (_first_column) and constant strings, with every user value bound
    # as a %(...)s param. Safe despite the f-string.
    rows = frappe.db.sql(  # nosemgrep
        f"""
        select pi.name, pi.customer, pi.customer_name, c.mobile_no, pi.pos_profile,
               pi.grand_total, pi.currency, pi.posting_date, pi.posting_time,
               pi.status, pi.docstatus, pi.is_return, pi.owner, u.full_name as owner_name,
               {app_select}, {order_select}, {online_select}, {exchange_select},
               {pay_modes_select}
        from `tab{doctype}` pi
        left join `tabCustomer` c on c.name = pi.customer
        left join `tabUser` u on u.name = pi.owner
        where {where}
        order by pi.creation desc
        limit %(start)s, %(limit)s
        """,
        params,
        as_dict=True,
    )
    # is_exchange may be stored as a Yes/No Select on some sites — normalise to 1/0.
    for row in rows:
        row["is_exchange"] = _truthy_custom(row.get("is_exchange"))
        row["owner_name"] = row.get("owner_name") or row.get("owner")
    return rows


# ---------------------------------------------------------------------------
# Returns / refunds
# ---------------------------------------------------------------------------

@frappe.whitelist()
def get_returnable(invoice):
    """Per-line quantity still eligible for return (original minus prior returns)."""
    doctype = _doctype_of(invoice)
    doc = frappe.get_doc(doctype, invoice)
    doc.check_permission("read")
    if doc.is_return or doc.docstatus != 1:
        return {"items": []}

    returned = {}
    return_names = frappe.get_all(
        doctype,
        filters={"return_against": invoice, "docstatus": 1, "is_return": 1},
        pluck="name",
    )
    if return_names:
        for row in frappe.get_all(
            f"{doctype} Item",
            filters={"parent": ["in", return_names]},
            fields=["item_code", "sum(qty) as qty"],
            group_by="item_code",
        ):
            returned[row.item_code] = abs(flt(row.qty))

    sold_serials = _sold_serials(doc)
    # Which serials have ALREADY come back on a prior credit note — read from our
    # own return documents, not from Serial No.status.
    #
    # ERPNext v15 routes serials through the Serial and Batch Bundle and no
    # longer reliably marks a sold serial "Delivered", so keying returnability
    # off that status made every serialized item show NOTHING to pick — the item
    # was un-returnable at the till. Our own records are authoritative here.
    already_returned = _returned_serials(doctype, return_names)
    items = []
    for row in doc.items:
        already = min(returned.get(row.item_code, 0), row.qty)
        returned[row.item_code] = returned.get(row.item_code, 0) - already
        has_serial = frappe.get_cached_value("Item", row.item_code, "has_serial_no")
        returnable_serials = []
        if has_serial:
            returnable_serials = [
                s for s in sold_serials.get(row.item_code, []) if s not in already_returned
            ]
        items.append(
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": row.qty,
                "rate": row.rate,
                "returnable_qty": flt(row.qty - already),
                "has_serial_no": has_serial,
                "returnable_serials": returnable_serials,
                "return_group": row.get("lumenpos_return_group"),
            }
        )
    return {
        "items": items,
        "customer": doc.customer,
        "customer_name": doc.customer_name,
        "allowed_refund_modes": _allowed_refund_modes(doc),
        "return_window": _return_window(doc),
    }


def _return_window(original):
    """Whether this sale is still inside the regular-return window. Controlled by
    LumenPOS Settings → restrict_returns_to_window + return_window_days. When the
    restriction is off (or the period is 0) every sale is `within`. An over-window
    return needs an approved Return request to proceed."""
    settings = frappe.get_cached_doc("LumenPOS Settings")
    restrict = bool(settings.get("restrict_returns_to_window"))
    days = cint(settings.get("return_window_days"))
    age = date_diff(nowdate(), original.posting_date)
    within = (not restrict) or days <= 0 or age <= days
    return {"restrict": restrict, "window_days": days, "age_days": age, "within": within}


def _refund_splits(refund_payments, refund_amount, default_mode, allowed_modes):
    """Normalise the refund tenders into [{mode_of_payment, amount(neg), reference_no}].

    Splitting a refund matters when the customer paid two ways — but DIRECTION
    matters too: collecting money may use any tender, whereas REFUNDING is
    restricted to the configured refund rules. So every requested tender is
    validated here, not just the first.

    Falls back to the legacy single `refund_mode` when no split is supplied."""
    if isinstance(refund_payments, str):
        refund_payments = json.loads(refund_payments or "[]")
    rows = [
        {
            "mode_of_payment": (r.get("mode_of_payment") or "").strip(),
            "amount": abs(flt(r.get("amount"))),
            "reference_no": (r.get("reference_no") or "").strip() or None,
        }
        for r in (refund_payments or [])
        if (r.get("mode_of_payment") or "").strip() and abs(flt(r.get("amount"))) > 0
    ]
    if not rows:
        rows = [{"mode_of_payment": default_mode, "amount": abs(refund_amount), "reference_no": None}]

    total = flt(sum(r["amount"] for r in rows), 2)
    if abs(total - abs(refund_amount)) > 0.005:
        frappe.throw(
            _("The refund split adds up to {0} but the refund is {1}.").format(
                total, abs(refund_amount)
            )
        )
    if allowed_modes is not None:
        bad = [r["mode_of_payment"] for r in rows if r["mode_of_payment"] not in allowed_modes]
        if bad:
            frappe.throw(
                _("{0} can't be used to refund this sale. Allowed: {1}.").format(
                    ", ".join(sorted(set(bad))), ", ".join(allowed_modes)
                )
            )
    # amounts on a credit note are negative
    for r in rows:
        r["amount"] = -r["amount"]
    return rows


def _allowed_refund_modes(original):
    """The refund tenders permitted for this sale: every mode the customer
    actually paid with, expanded by the configured per-mode rules (e.g. paid
    Mada -> also allow Cash), plus Store Credit (keeping the value on account
    is always allowed). Returns None when the restriction is switched off."""
    settings = frappe.get_cached_doc("LumenPOS Settings")
    if not settings.get("restrict_refund_to_paid_mode"):
        return None
    paid = {p.mode_of_payment for p in (original.payments or []) if flt(p.amount) > 0}
    allowed = set(paid)
    for rule in settings.get("refund_rules") or []:
        if rule.paid_mode in paid and rule.refund_mode:
            allowed.add(rule.refund_mode)
    # Refunding onto the customer's account used to be hard-wired as always
    # allowed, so a cashier could park a refund on credit against shop policy.
    # It's a switch now — with ONE carve-out: credit the customer actually SPENT
    # on this sale can always go back to credit (capped at what they spent),
    # because otherwise a credit-paid sale would have no refund method at all.
    if settings.get("allow_store_credit_refund") or store_credit.MODE_OF_PAYMENT in paid:
        allowed.add(store_credit.MODE_OF_PAYMENT)
    return sorted(allowed)


def _returned_serials(doctype, return_names):
    """Set of serials already returned on the given credit notes.

    Batched on purpose: the previous approach asked Serial No for a status ONE
    QUERY PER SERIAL, so a serialized invoice crawled. Two queries total now.
    """
    if not return_names:
        return set()
    out = set()
    rows = frappe.get_all(
        f"{doctype} Item",
        filters={"parent": ["in", return_names]},
        fields=["serial_no", "serial_and_batch_bundle"],
    )
    bundles = [r.serial_and_batch_bundle for r in rows if r.get("serial_and_batch_bundle")]
    for r in rows:
        if r.get("serial_no"):
            out.update(s.strip() for s in str(r.serial_no).split("\n") if s.strip())
    if bundles:
        out.update(
            frappe.get_all(
                "Serial and Batch Entry",
                filters={"parent": ["in", bundles]},
                pluck="serial_no",
            )
        )
    return {s for s in out if s}


def _sold_serials(invoice_doc):
    """Serials that went out on this invoice, per item code (reads the v15
    Serial and Batch Bundle, falling back to the legacy serial_no field)."""
    result = {}
    for row in invoice_doc.items:
        serials = []
        if row.get("serial_and_batch_bundle"):
            serials = frappe.get_all(
                "Serial and Batch Entry",
                filters={"parent": row.serial_and_batch_bundle},
                pluck="serial_no",
            )
        elif row.get("serial_no"):
            serials = [s.strip() for s in str(row.serial_no).split("\n") if s.strip()]
        if serials:
            result.setdefault(row.item_code, []).extend(serials)
    return result


@frappe.whitelist()
def create_return(
    invoice,
    items,
    refund_mode,
    serials=None,
    return_reason=None,
    return_request=None,
    pos_profile=None,
    refund_payments=None,
):
    """Create a POS return (credit note) against a submitted POS sale.

    items = {"ITEM-001": 2, ...} quantities to return (positive numbers).
    serials = {"ITEM-001": ["SN-1", "SN-2"]} — REQUIRED for serialized items;
    each serial must have been sold on the original invoice and still be
    marked Delivered.
    refund_mode = a Mode of Payment; use "Store Credit" to keep the value on
    the customer's account instead of handing money back.
    return_reason = free text (a picked reason or a typed "Other" reason),
    recorded on the credit note.
    return_request = an approved POS Approval Request (type Return) that
    authorizes a return made AFTER the configured return window has passed.
    """
    _require_sell()
    from lumenpos.api import permissions

    if not permissions.can_return():
        frappe.throw(
            _("You're not allowed to make returns."), frappe.PermissionError
        )
    if isinstance(items, str):
        items = json.loads(items)
    if isinstance(serials, str):
        serials = json.loads(serials)
    serials = serials or {}
    items = {code: flt(qty) for code, qty in items.items() if flt(qty) > 0}
    if not items:
        frappe.throw(_("Select at least one item to return"))

    sale_doctype = _doctype_of(invoice)
    original = frappe.get_doc(sale_doctype, invoice)
    if original.docstatus != 1 or original.is_return:
        frappe.throw(_("{0} cannot be returned").format(invoice))

    # Regular returns are allowed only inside the configured window. Past it, a
    # holder of the "exceed return window" role (or a manager) may return
    # directly; everyone else needs an approved Return request.
    window = _return_window(original)
    return_approver = None
    if not window["within"] and not permissions.can_exceed_return_window():
        if not return_request:
            frappe.throw(
                _("Returns are allowed within {0} days — this invoice is {1} days old. Send a return approval request to continue.").format(
                    window["window_days"], window["age_days"]
                )
            )
        from lumenpos.api import approval_requests

        return_approver = approval_requests.validate_return(return_request, invoice)
    # A consolidated original (its shift was closed, so it was merged into a
    # Sales Invoice) is STILL returnable from the till: we create the credit
    # note as a POS Invoice return against the original POS Invoice, tied to the
    # CURRENT open shift, so the refund comes from the current drawer. ERPNext's
    # consolidation links/merges this return into a credit-note Sales Invoice at
    # the next close — no desk trip needed.

    allowed_modes = _allowed_refund_modes(original)
    # With a split refund every tender is validated in _refund_splits below, so
    # only check the single legacy mode when no split was supplied.
    if allowed_modes is not None and not refund_payments and refund_mode not in allowed_modes:
        paid_modes = [p.mode_of_payment for p in original.payments if flt(p.amount) > 0]
        frappe.throw(
            _("This sale was paid by {0}, so it can only be refunded to: {1}. Adjust the refund methods in LumenPOS Settings if needed.").format(
                ", ".join(paid_modes) or _("(no recorded payment)"),
                ", ".join(allowed_modes),
            )
        )

    returnable_items = get_returnable(invoice)["items"]
    returnable = {row["item_code"]: row["returnable_qty"] for row in returnable_items}
    for code, qty in items.items():
        if qty > returnable.get(code, 0) + 0.005:
            frappe.throw(
                _("Only {0} x {1} can still be returned").format(returnable.get(code, 0), code)
            )
    # Bundle / buy-x-get-y sets must come back together on a regular return.
    _enforce_return_groups(returnable_items, items)

    # The return posts on the outlet HANDLING it, not the one that made the sale.
    # ERPNext's return builder copies everything from the original, so a branch
    # returning (say) an online order would post on the E-Commerce profile: the
    # refund left the branch's drawer but under another outlet's name, and
    # profile-filtered closings/reports missed it entirely.
    handling_profile_name = pos_profile or original.pos_profile
    handling_profile = frappe.get_cached_doc("POS Profile", handling_profile_name)
    if handling_profile.company != original.company:
        frappe.throw(
            _(
                "{0} was sold by {1}, but this till belongs to {2}. A return must be "
                "processed by a till in the same company."
            ).format(invoice, original.company, handling_profile.company)
        )
    session = _open_session(handling_profile_name)

    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    return_doc = make_return_doc(sale_doctype, invoice)
    # Re-stamp the copied header onto THIS till.
    return_doc.pos_profile = handling_profile.name
    if handling_profile.get("warehouse"):
        return_doc.set("set_warehouse", handling_profile.warehouse)
    if handling_profile.get("cost_center"):
        return_doc.cost_center = handling_profile.cost_center
    if handling_profile.get("selling_price_list"):
        return_doc.selling_price_list = handling_profile.selling_price_list
    # Keep one row per returned item code (a quantity may span duplicate
    # lines on the original; the aggregate returnable check above still holds)
    kept, seen = [], set()
    for row in return_doc.items:
        if row.item_code in items and row.item_code not in seen:
            kept.append(row)
            seen.add(row.item_code)
    return_doc.items = kept
    if not return_doc.items:
        frappe.throw(_("Selected items were not found on the original sale"))
    sold = _sold_serials(original)
    # Serials already returned on a previous credit note (our own record — see
    # _returned_serials on why Serial No.status can't be trusted on v15).
    prior_returns = frappe.get_all(
        sale_doctype,
        filters={"return_against": invoice, "docstatus": 1, "is_return": 1},
        pluck="name",
    )
    already_returned = _returned_serials(sale_doctype, prior_returns)
    for row in return_doc.items:
        # Lines carry the ORIGINAL outlet's warehouse / cost center too — stock
        # would come back into the selling branch instead of the one taking it.
        if handling_profile.get("warehouse"):
            row.warehouse = handling_profile.warehouse
        if handling_profile.get("cost_center"):
            row.cost_center = handling_profile.cost_center
        row.qty = -items[row.item_code]
        if row.get("stock_qty"):
            row.stock_qty = row.qty * flt(row.conversion_factor or 1)
        row_serials = _validate_return_serials(
            row.item_code,
            items[row.item_code],
            serials.get(row.item_code),
            sold,
            already_returned,
        )
        if row_serials:
            row.serial_and_batch_bundle = None
            row.use_serial_batch_fields = 1
            row.serial_no = "\n".join(row_serials)

    return_doc.payments = []
    _set_custom(return_doc, ("lumenpos_session",), session["name"])
    if (return_reason or "").strip():
        _set_custom(return_doc, ("lumenpos_return_reason",), return_reason.strip())
    return_doc.run_method("set_missing_values")
    return_doc.run_method("calculate_taxes_and_totals")

    # Refund EXACTLY what ERPNext validates a return against. POS Invoice's
    # validate_pos checks `abs(paid) + abs(write_off) - abs(rounded_total or
    # grand_total)`; it uses rounded_total when rounding is on (POS Invoice has
    # no disable_rounded_total field, so we can't turn that off). Paying that
    # exact figure and forcing write_off to 0 makes the difference 0 — so a
    # tax-inclusive half-cent can never trip "Paid amount + Write Off Amount can
    # not be greater than Grand Total".
    invoice_total = return_doc.rounded_total or return_doc.grand_total
    refund_amount = flt(invoice_total, return_doc.precision("grand_total"))  # negative
    splits = _refund_splits(refund_payments, refund_amount, refund_mode, allowed_modes)
    if any(r["mode_of_payment"] == store_credit.MODE_OF_PAYMENT for r in splits):
        store_credit.ensure_mode_of_payment(original.company)
    for row in return_doc.payments:
        row.amount = 0
    for r in splits:
        _set_payment(return_doc, r["mode_of_payment"], r["amount"])
    _apply_payment_references(
        return_doc,
        [{"mode_of_payment": r["mode_of_payment"], "reference_no": r["reference_no"]} for r in splits],
    )
    return_doc.write_off_amount = 0
    _sync_return_paid_amount(return_doc)  # paid_amount must equal the rows, not the original sale
    return_doc.run_method("calculate_taxes_and_totals")
    _drop_empty_payments(return_doc)

    if return_approver:
        # Stamp the late-return approval onto the credit note for the audit trail.
        return_doc.remarks = "\n".join(
            part
            for part in [return_doc.get("remarks"), _("Late return approved by {0}").format(return_approver)]
            if part
        )

    _lock_open_session(session["name"])
    return_doc.insert()
    return_doc.submit()

    credit_amount = flt(
        sum(
            abs(r["amount"]) for r in splits
            if r["mode_of_payment"] == store_credit.MODE_OF_PAYMENT
        ),
        2,
    )
    if credit_amount:
        store_credit.add_entry(
            original.customer,
            "Issue",
            credit_amount,
            return_doc.name,
            original.company,
        )
    # Consume the single-use late-return approval the credit note was built with.
    if return_request and return_approver:
        from lumenpos.api import approval_requests

        approval_requests.consume(return_request, return_doc.name)

    from lumenpos.api import audit

    detail = _("Refund as {0}").format(
        ", ".join(f'{r["mode_of_payment"]} {abs(r["amount"]):.2f}' for r in splits)
    )
    if return_reason:
        detail += f" · {return_reason}"
    if return_approver:
        detail += f" · {_('late return approved by {0}').format(return_approver)}"
    audit.log(
        audit.RETURN,
        detail=detail,
        amount=abs(refund_amount),
        reference_doctype=return_doc.doctype,
        reference_name=return_doc.name,
        pos_profile=original.get("pos_profile"),
    )

    return get_receipt(return_doc.name)


def _enforce_return_groups(returnable_items, items):
    """Items sold together as a bundle or a Buy X Get Y set must be returned as a
    whole on a REGULAR return — every member at its full remaining quantity, or
    none. Exchanges are exempt (they never call this)."""
    members = {}  # group -> {item_code: total_returnable_qty}
    group_of = {}
    for r in returnable_items:
        g = r.get("return_group")
        if not g:
            continue
        members.setdefault(g, {})
        members[g][r["item_code"]] = members[g].get(r["item_code"], 0) + flt(r["returnable_qty"])
        group_of[r["item_code"]] = g

    touched = {group_of[c] for c in items if c in group_of}
    for g in touched:
        for code, full_qty in members[g].items():
            if abs(flt(items.get(code, 0)) - flt(full_qty)) > 0.005:
                names = ", ".join(sorted(members[g]))
                frappe.throw(
                    _("These items were sold together (bundle/offer) and must be returned together: {0}. Use Exchange for a partial swap.").format(names)
                )


def _validate_return_serials(item_code, qty, serial_nos, sold, already_returned=None):
    """STRICT: returning a serialized item requires picking exactly which
    sold serials are coming back.

    `already_returned` is OUR record of serials that came back on a previous
    credit note. It replaces a Serial No.status check: ERPNext v15 no longer
    reliably marks a sold serial "Delivered", so that check rejected every
    genuine serialized return."""
    if not frappe.get_cached_value("Item", item_code, "has_serial_no"):
        return []
    serial_list = [s.strip() for s in (serial_nos or []) if s and s.strip()]
    if len(serial_list) != int(qty):
        frappe.throw(
            _("{0} is serialized: select {1} serial number(s) to return, got {2}").format(
                item_code, int(qty), len(serial_list)
            )
        )
    sold_for_item = set(sold.get(item_code, []))
    seen = set()
    for serial in serial_list:
        if serial in seen:
            frappe.throw(_("Serial {0} is selected twice").format(serial))
        seen.add(serial)
        if serial not in sold_for_item:
            frappe.throw(_("Serial {0} was not sold on this invoice").format(serial))
        if already_returned and serial in already_returned:
            frappe.throw(_("Serial {0} was already returned").format(serial))
    return serial_list


# ---------------------------------------------------------------------------
# Parked sales
# ---------------------------------------------------------------------------

@frappe.whitelist()
def park_sale(pos_profile, cart, customer=None, customer_name=None, note=None):
    if isinstance(cart, (dict, list)):
        cart = json.dumps(cart)
    doc = frappe.get_doc(
        {
            "doctype": "POS Parked Sale",
            "pos_profile": pos_profile,
            "customer": customer,
            "customer_name": customer_name,
            "note": note,
            "cart": cart,
            "status": "Parked",
            "parked_at": now_datetime(),
        }
    ).insert()
    return doc.name


@frappe.whitelist()
def list_parked(pos_profile):
    return frappe.get_all(
        "POS Parked Sale",
        filters={"pos_profile": pos_profile, "status": "Parked"},
        fields=["name", "customer", "customer_name", "note", "parked_at"],
        order_by="parked_at desc",
        limit_page_length=50,
    )


@frappe.whitelist()
def retrieve_parked(name):
    doc = frappe.get_doc("POS Parked Sale", name)
    doc.check_permission("write")
    cart = json.loads(doc.cart or "{}")
    doc.status = "Retrieved"
    doc.save()
    return {"customer": doc.customer, "customer_name": doc.customer_name, "cart": cart}


@frappe.whitelist()
def discard_parked(name):
    doc = frappe.get_doc("POS Parked Sale", name)
    doc.check_permission("delete")
    doc.delete()
