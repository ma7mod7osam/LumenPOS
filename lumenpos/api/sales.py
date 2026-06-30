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


def _table_doctype(pos_profile):
    """Sale doctype for a profile's history queries (defaults to POS Invoice)."""
    if pos_profile and frappe.db.get_value(
        "POS Profile", pos_profile, "lumenpos_invoice_mode"
    ) == "Sales Invoice":
        return "Sales Invoice"
    return "POS Invoice"


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

    # ERPNext Pricing Rules are bypassed by default (LumenPOS runs its own
    # promotion engine); a POS Profile can opt back into them.
    ignore_pricing_rule = 0 if profile.get("lumenpos_ignore_pricing_rules") == 0 else 1

    invoice = frappe.new_doc(_sale_doctype(profile))
    invoice.update(
        {
            "is_pos": 1,
            "pos_profile": profile.name,
            "company": profile.company,
            "customer": customer,
            "selling_price_list": price_list,
            "update_stock": profile.update_stock,
            "set_warehouse": profile.warehouse,
            "taxes_and_charges": profile.taxes_and_charges,
            "ignore_pricing_rule": ignore_pricing_rule,
            "remarks": _build_remarks(payload.get("note"), discount_approver),
        }
    )
    _set_custom(invoice, ("lumenpos_promotions",), json.dumps(promo_result["applied"]))
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
    account = settings.get("service_charge_account")
    if not account:
        frappe.throw(
            _("Set a Service charge account in LumenPOS Settings → Features before charging it.")
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

    _require_sell()
    profile = frappe.get_cached_doc("POS Profile", payload["pos_profile"])
    session = _open_session(profile.name)

    invoice, customer = _build_sale_invoice(profile, payload)
    _set_custom(invoice, ("lumenpos_session",), session["name"])

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
            store_credit.ensure_mode_of_payment(profile.company)
            store_credit_used += amount
        if payment["mode_of_payment"] == gift_cards.mode_of_payment():
            gift_cards.ensure_setup(profile.company)
            gift_card_total += amount
        _set_payment(invoice, payment["mode_of_payment"], amount)
        paid_total += amount
    if abs(gift_card_total - sum(c["amount"] for c in redeem_cards)) > 0.005:
        frappe.throw(_("Gift card payments don't match the scanned cards"))
    if not paid_total and not invoice.get("redeem_loyalty_points"):
        frappe.throw(_("At least one payment is required"))

    _reconcile_payment(invoice, profile)
    _drop_empty_payments(invoice)

    _lock_open_session(session["name"])
    invoice.insert()
    invoice.submit()

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

    return get_receipt(invoice.name)


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
    session = _open_session(profile.name)
    amount = flt(payload.get("amount"))
    if amount <= 0:
        frappe.throw(_("Enter the gift card amount"))

    gift_cards.ensure_setup(profile.company)
    customer = payload.get("customer") or profile.customer
    if not customer:
        frappe.throw(_("Select a customer (or set a default customer on the POS Profile)"))

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
        },
    )
    if payload.get("sales_person"):
        invoice.append(
            "sales_team",
            {"sales_person": payload["sales_person"], "allocated_percentage": 100},
        )
    invoice.set_missing_values()
    invoice.taxes = []

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
    from lumenpos.api.session import get_open_session

    session = get_open_session(pos_profile)
    if not session:
        frappe.throw(_("No open register session. Open the register first."))
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
        return result if isinstance(result, str) else None

    # 2) An approved discount request (approver was elsewhere). Validated here;
    #    submit_sale consumes it after the invoice posts.
    if allow_request and payload.get("discount_request"):
        from lumenpos.api import approval_requests

        return approval_requests.validate_discount(payload["discount_request"], worst)

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


def _first_column(candidates, doctype=INVOICE_DOCTYPE):
    """First of the candidate fieldnames that actually exists as a column on the
    given sale doctype (so history search uses the site's real fields), or None
    if none exist."""
    for fieldname in candidates:
        if frappe.db.has_column(doctype, fieldname):
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
def get_receipt(invoice):
    doc = frappe.get_doc(_doctype_of(invoice), invoice)
    doc.check_permission("read")
    earned_points = frappe.db.get_value(
        "Loyalty Point Entry",
        {"invoice": doc.name, "loyalty_points": [">", 0]},
        "loyalty_points",
    )
    return {
        "name": doc.name,
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

    app_field = _first_column(("custom_app_type", "lumenpos_app_type"), doctype)
    order_field = _first_column(("pick_order_no", "custom_order_id", "lumenpos_order_id"), doctype)
    online_field = _first_column(("online_order", "custom_online_order", "is_online_order"), doctype)
    exchange_field = _first_column(("is_exchange", "custom_is_exchange"), doctype)

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
        params["search"] = f"%{f.search.strip()}%"
        order_clause = f" or pi.{order_field} like %(search)s" if order_field else ""
        conds.append(
            f"(pi.name like %(search)s or pi.customer_name like %(search)s"
            f" or pi.customer like %(search)s or c.mobile_no like %(search)s"
            f"{order_clause})"
        )

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
    rows = frappe.db.sql(
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
    items = []
    for row in doc.items:
        already = min(returned.get(row.item_code, 0), row.qty)
        returned[row.item_code] = returned.get(row.item_code, 0) - already
        has_serial = frappe.get_cached_value("Item", row.item_code, "has_serial_no")
        returnable_serials = []
        if has_serial:
            # A sold serial is returnable while its status is still Delivered
            # (a prior return flips it back to Active)
            for serial in sold_serials.get(row.item_code, []):
                if frappe.db.get_value("Serial No", serial, "status") == "Delivered":
                    returnable_serials.append(serial)
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
    allowed.add(store_credit.MODE_OF_PAYMENT)
    return sorted(allowed)


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
def create_return(invoice, items, refund_mode, serials=None, return_reason=None, return_request=None):
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
    if allowed_modes is not None and refund_mode not in allowed_modes:
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

    session = _open_session(original.pos_profile)

    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    return_doc = make_return_doc(sale_doctype, invoice)
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
    for row in return_doc.items:
        row.qty = -items[row.item_code]
        if row.get("stock_qty"):
            row.stock_qty = row.qty * flt(row.conversion_factor or 1)
        row_serials = _validate_return_serials(
            row.item_code, items[row.item_code], serials.get(row.item_code), sold
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
    if refund_mode == store_credit.MODE_OF_PAYMENT:
        store_credit.ensure_mode_of_payment(original.company)
    for row in return_doc.payments:
        row.amount = 0
    _set_payment(return_doc, refund_mode, refund_amount)
    return_doc.write_off_amount = 0
    _sync_return_paid_amount(return_doc)  # paid_amount must equal the rows, not the original sale
    return_doc.run_method("calculate_taxes_and_totals")
    _drop_empty_payments(return_doc)

    if return_approver:
        # Stamp the late-return approval onto the credit note for the audit trail.
        return_doc.remarks = "\n".join(
            filter(None, [return_doc.get("remarks"), _("Late return approved by {0}").format(return_approver)])
        )

    _lock_open_session(session["name"])
    return_doc.insert()
    return_doc.submit()

    if refund_mode == store_credit.MODE_OF_PAYMENT:
        store_credit.add_entry(
            original.customer,
            "Issue",
            abs(refund_amount),
            return_doc.name,
            original.company,
        )
    # Consume the single-use late-return approval the credit note was built with.
    if return_request and return_approver:
        from lumenpos.api import approval_requests

        approval_requests.consume(return_request, return_doc.name)

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


def _validate_return_serials(item_code, qty, serial_nos, sold):
    """STRICT: returning a serialized item requires picking exactly which
    sold serials are coming back."""
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
        if frappe.db.get_value("Serial No", serial, "status") != "Delivered":
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
