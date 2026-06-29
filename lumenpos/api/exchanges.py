"""Warranty/damage exchanges in one atomic operation.

A customer brings a damaged item (under warranty) and takes a replacement.
LumenPOS creates the SAME two documents the team makes by hand today, but in one
click and with the cash netted:

  - Damaged item  -> a return POS Invoice (is_return=1, is_exchange=1) against
    the original sale. Posts to the normal warehouse; the site's hourly script
    moves is_return+is_exchange stock to the damage warehouse.
  - Replacement   -> a sale POS Invoice (is_exchange=1) at the current price.

Only the NET difference touches real tender. The matched portion is settled
through an auto-provisioned "Exchange Credit" mode of payment backed by a
clearing account that nets to zero across the two documents, so the drawer
shows exactly what the customer paid or was refunded — nothing gross.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate

from lumenpos.api import sales as sales_api
from lumenpos.api.catalog import warranty_field
from lumenpos.install import EXCHANGE_RETURN_REASON
from lumenpos.internal_accounts import fill_required_custom_fields
from lumenpos.price_books import effective_prices, resolve_price_list

MODE_OF_PAYMENT = "Exchange Credit"
ACCOUNT_NAME = "Exchange Clearing"


def _enabled():
    return bool(frappe.db.get_single_value("LumenPOS Settings", "exchanges_enabled"))


def _item_warranty_days(item_code):
    """Warranty length for an item, in days, from its warranty field."""
    wf = warranty_field()
    if not wf:
        return 0
    return int(frappe.db.get_value("Item", item_code, wf) or 0)


def ensure_exchange_mode(company):
    account = _get_or_create_account(company)
    if not frappe.db.exists("Mode of Payment", MODE_OF_PAYMENT):
        mop = frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": MODE_OF_PAYMENT,
                "type": "General",
                "enabled": 1,
                "accounts": [{"company": company, "default_account": account}],
            }
        )
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.insert(ignore_permissions=True)
        return
    mop = frappe.get_doc("Mode of Payment", MODE_OF_PAYMENT)
    if not any(r.company == company and r.default_account for r in mop.accounts):
        mop.append("accounts", {"company": company, "default_account": account})
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.save(ignore_permissions=True)


def _get_or_create_account(company):
    abbr = frappe.get_cached_value("Company", company, "abbr")
    account_name = f"{ACCOUNT_NAME} - {abbr}"
    if frappe.db.exists("Account", account_name):
        return account_name
    parent = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "root_type": "Liability",
            "is_group": 1,
            "account_name": ["in", ["Current Liabilities", "Current Liability"]],
        },
        "name",
    ) or frappe.db.get_value(
        "Account", {"company": company, "root_type": "Liability", "is_group": 1}, "name"
    )
    if not parent:
        frappe.throw(_("No liability account group found for {0}").format(company))
    return (
        frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": ACCOUNT_NAME,
                "parent_account": parent,
                "company": company,
                "root_type": "Liability",
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


@frappe.whitelist()
def lookup(pos_profile, search):
    """Find the original sale for a warranty exchange. Searches submitted POS
    Invoices by invoice no / customer / mobile / serial, and returns each
    exchangeable line with its own warranty status (per the item's warranty
    days, counted from the sale date)."""
    if not _enabled():
        frappe.throw(_("Exchanges are turned off in LumenPOS Settings"))
    search = (search or "").strip()
    # Require a few characters — 1-2 chars match thousands of invoices and make
    # the per-invoice warranty computation crawl.
    if len(search) < 3:
        return []

    like = f"%{search}%"
    CAP = 8
    names, seen = [], set()

    def add(name):
        if name and name not in seen:
            seen.add(name)
            names.append(name)

    # Invoice no / customer name (both live on POS Invoice — one indexed query).
    for inv in frappe.get_all(
        "POS Invoice",
        filters={"docstatus": 1, "is_return": 0},
        or_filters={"name": ["like", like], "customer_name": ["like", like]},
        pluck="name",
        order_by="creation desc",
        limit_page_length=CAP,
    ):
        add(inv)

    # By mobile: resolve matching customers first (smaller table), then their
    # invoices — avoids a leading-wildcard join across all POS Invoices.
    if len(names) < CAP:
        customers = frappe.get_all(
            "Customer", filters={"mobile_no": ["like", like]}, pluck="name", limit_page_length=10
        )
        if customers:
            for inv in frappe.get_all(
                "POS Invoice",
                filters={"customer": ["in", customers], "docstatus": 1, "is_return": 0},
                pluck="name",
                order_by="creation desc",
                limit_page_length=CAP,
            ):
                add(inv)

    # By serial number.
    if len(names) < CAP and frappe.db.exists("Serial No", search.upper()):
        for parent in frappe.get_all(
            "POS Invoice Item",
            filters={"serial_no": ["like", f"%{search.upper()}%"], "docstatus": 1},
            pluck="parent",
            limit_page_length=CAP,
        ):
            add(parent)

    names = names[:CAP]
    if not names:
        return []

    today = getdate(nowdate())

    # --- batched lookups (a handful of queries for ALL candidates, instead of a
    # full get_doc + per-serial query per invoice) ---

    # Sold lines, aggregated per (invoice, item_code). LumenPOS writes serials onto
    # the item row's serial_no (use_serial_batch_fields), so they come for free.
    sold = {}
    for r in frappe.get_all(
        "POS Invoice Item",
        filters={"parent": ["in", names]},
        fields=["parent", "item_code", "item_name", "qty", "rate", "serial_no"],
    ):
        agg = sold.setdefault(
            (r.parent, r.item_code),
            {"item_name": r.item_name, "qty": 0.0, "rate": r.rate, "serials": []},
        )
        agg["qty"] += flt(r.qty)
        if r.serial_no:
            agg["serials"] += [s.strip() for s in r.serial_no.split("\n") if s.strip()]

    # Already-returned qty per (original invoice, item_code).
    returned = {}
    returns = frappe.get_all(
        "POS Invoice",
        filters={"return_against": ["in", names], "docstatus": 1, "is_return": 1},
        fields=["name", "return_against"],
    )
    if returns:
        ret_map = {r.name: r.return_against for r in returns}
        for r in frappe.get_all(
            "POS Invoice Item",
            filters={"parent": ["in", list(ret_map)]},
            fields=["parent", "item_code", "qty"],
        ):
            key = (ret_map[r.parent], r.item_code)
            returned[key] = returned.get(key, 0.0) + abs(flt(r.qty))

    # Warranty days + serialization for every distinct item, in one query.
    item_meta = {}
    item_codes = list({ic for (_, ic) in sold})
    if item_codes:
        wf = warranty_field()
        fields = ["name", "has_serial_no"] + ([wf] if wf else [])
        for it in frappe.get_all("Item", filters={"name": ["in", item_codes]}, fields=fields):
            item_meta[it.name] = (int(it.get(wf) or 0) if wf else 0, cint(it.has_serial_no))

    # Which sold serials are still Delivered (returnable), in one query.
    delivered = set()
    all_serials = list({s for agg in sold.values() for s in agg["serials"]})
    if all_serials:
        delivered = set(
            frappe.get_all(
                "Serial No",
                filters={"name": ["in", all_serials], "status": "Delivered"},
                pluck="name",
            )
        )

    inv_meta = {
        d.name: d
        for d in frappe.get_all(
            "POS Invoice",
            filters={"name": ["in", names]},
            fields=[
                "name", "posting_date", "customer", "customer_name",
                "lumenpos_warranty_start_date",
            ],
        )
    }

    results = []
    for name in names:
        meta = inv_meta.get(name)
        if not meta:
            continue
        posting_date = meta.posting_date
        # Warranty counts from the original purchase date — for a prior
        # replacement that's the chained start, not its (later) posting date.
        warranty_start = meta.get("lumenpos_warranty_start_date") or posting_date
        lines = []
        for (parent, item_code), agg in sold.items():
            if parent != name:
                continue
            already = min(returned.get((name, item_code), 0.0), agg["qty"])
            returnable_qty = flt(agg["qty"] - already)
            if returnable_qty <= 0:
                continue
            warranty_days, has_serial = item_meta.get(item_code, (0, 0))
            if warranty_days > 0:
                expiry = add_days(getdate(warranty_start), warranty_days)
                in_warranty = today <= expiry
                warranty_expiry = str(expiry)
            else:
                in_warranty = False
                warranty_expiry = None
            lines.append(
                {
                    "item_code": item_code,
                    "item_name": agg["item_name"],
                    "qty": agg["qty"],
                    "rate": agg["rate"],
                    "returnable_qty": returnable_qty,
                    "has_serial_no": has_serial,
                    "returnable_serials": [s for s in agg["serials"] if s in delivered]
                    if has_serial
                    else [],
                    "warranty_days": warranty_days,
                    "warranty_expiry": warranty_expiry,
                    "in_warranty": in_warranty,
                }
            )
        if not lines:
            continue
        results.append(
            {
                "name": name,
                "customer": meta.customer,
                "customer_name": meta.customer_name,
                "posting_date": str(posting_date),
                "any_in_warranty": any(l["in_warranty"] for l in lines),
                "items": lines,
            }
        )
    results.sort(key=lambda r: r["posting_date"], reverse=True)
    return results


@frappe.whitelist()
def submit_exchange(payload):
    """Atomic warranty exchange. payload = {
        pos_profile, original_invoice,
        returned_items: [{item_code, qty, serial_nos}],
        replacement_items: [{item_code, qty, serial_nos}],
        settle_mode: a real Mode of Payment for the net (collect or refund),
        note,
    }"""
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not _enabled():
        frappe.throw(_("Exchanges are turned off in LumenPOS Settings"))

    profile = frappe.get_cached_doc("POS Profile", payload["pos_profile"])
    session = sales_api._open_session(profile.name)
    ensure_exchange_mode(profile.company)

    original = frappe.get_doc("POS Invoice", payload["original_invoice"])
    if original.docstatus != 1 or original.is_return:
        frappe.throw(_("{0} is not a valid original sale").format(payload["original_invoice"]))

    returned = {
        code: flt(qty)
        for code, qty in (
            (i["item_code"], i.get("qty")) for i in payload.get("returned_items", [])
        )
        if flt(qty) > 0
    }
    if not returned:
        frappe.throw(_("Select the damaged item(s) being returned"))

    # Strict, per-item warranty: each damaged item must be within its own
    # warranty window (item warranty days, counted from the sale date).
    # Warranty is counted from the ORIGINAL purchase date — for a replacement that
    # is itself being exchanged, that date chains back via lumenpos_warranty_start_date.
    warranty_start = original.get("lumenpos_warranty_start_date") or original.posting_date
    today = getdate(nowdate())
    for code in returned:
        days = _item_warranty_days(code)
        if days <= 0:
            frappe.throw(_("{0} has no warranty period set — it cannot be exchanged").format(code))
        expiry = add_days(getdate(warranty_start), days)
        if today > expiry:
            frappe.throw(
                _("{0}'s warranty expired on {1} — no longer exchangeable").format(code, expiry)
            )

    serials_in = {
        i["item_code"]: i.get("serial_nos") or []
        for i in payload.get("returned_items", [])
    }

    # ---- damaged return (is_return=1, is_exchange=1) ----
    return_reason = (payload.get("return_reason") or "").strip() or EXCHANGE_RETURN_REASON
    return_doc, credit_value = _build_damaged_return(
        original, returned, serials_in, session, return_reason
    )

    # ---- replacement sale (is_exchange=1) ----
    replacement_value = 0.0
    replacement_doc = None
    if payload.get("replacement_items"):
        replacement_doc, replacement_value = _build_replacement_sale(
            profile, original.customer, payload, session
        )

    net = flt(replacement_value - credit_value, 2)  # >0 collect, <0 refund
    settle_mode = payload.get("settle_mode")
    clearing = min(credit_value, replacement_value)

    # Return invoice payments: -clearing via Exchange Credit, plus refund of
    # any excess (credit beyond replacement) in real tender.
    return_doc.payments = []
    sales_api._set_payment(return_doc, MODE_OF_PAYMENT, -clearing)
    if credit_value > replacement_value:
        refund = flt(credit_value - replacement_value, 2)
        if not settle_mode:
            frappe.throw(_("Choose how to refund the {0} difference").format(refund))
        sales_api._set_payment(return_doc, settle_mode, -refund)
    return_doc.write_off_amount = 0
    # paid_amount must equal the netted payment rows, not the original sale's
    # (make_return_doc copies the original's, which calc keeps for returns).
    sales_api._sync_return_paid_amount(return_doc)
    return_doc.run_method("calculate_taxes_and_totals")
    sales_api._drop_empty_payments(return_doc)
    return_doc.insert()
    return_doc.submit()

    if replacement_doc:
        replacement_doc.payments = []
        sales_api._set_payment(replacement_doc, MODE_OF_PAYMENT, clearing)
        if replacement_value > credit_value:
            collect = flt(replacement_value - credit_value, 2)
            if not settle_mode:
                frappe.throw(_("Choose how the customer pays the {0} difference").format(collect))
            sales_api._set_payment(replacement_doc, settle_mode, collect)
        replacement_doc.write_off_amount = 0
        replacement_doc.run_method("calculate_taxes_and_totals")
        sales_api._drop_empty_payments(replacement_doc)
        replacement_doc.insert()
        replacement_doc.submit()

    receipt = sales_api.get_receipt(return_doc.name)
    receipt["exchange"] = {
        "original_invoice": original.name,
        "credit_value": flt(credit_value, 2),
        "replacement_value": flt(replacement_value, 2),
        "net": net,
        "return_invoice": return_doc.name,
        "replacement_invoice": replacement_doc.name if replacement_doc else None,
    }
    if replacement_doc:
        receipt["replacement_receipt"] = sales_api.get_receipt(replacement_doc.name)
    return receipt


def _build_damaged_return(original, returned, serials_in, session, return_reason=None):
    from erpnext.controllers.sales_and_purchase_return import make_return_doc

    returnable = {
        row["item_code"]: row
        for row in sales_api.get_returnable(original.name)["items"]
    }
    for code, qty in returned.items():
        avail = returnable.get(code, {}).get("returnable_qty", 0)
        if qty > avail + 0.005:
            frappe.throw(_("Only {0} x {1} can still be exchanged").format(avail, code))

    return_doc = make_return_doc("POS Invoice", original.name)
    kept, seen = [], set()
    for row in return_doc.items:
        if row.item_code in returned and row.item_code not in seen:
            kept.append(row)
            seen.add(row.item_code)
    return_doc.items = kept
    if not return_doc.items:
        frappe.throw(_("Damaged items were not found on the original sale"))

    sold = sales_api._sold_serials(original)
    credit_value = 0.0
    for row in return_doc.items:
        row.qty = -returned[row.item_code]
        if row.get("stock_qty"):
            row.stock_qty = row.qty * flt(row.conversion_factor or 1)
        credit_value += abs(flt(row.qty)) * flt(row.rate)
        row_serials = sales_api._validate_return_serials(
            row.item_code, returned[row.item_code], serials_in.get(row.item_code), sold
        )
        if row_serials:
            row.serial_and_batch_bundle = None
            row.use_serial_batch_fields = 1
            row.serial_no = "\n".join(row_serials)

    sales_api._set_custom(return_doc, ("lumenpos_session",), session["name"])
    sales_api._set_custom(return_doc, ("is_exchange", "custom_is_exchange"), 1)
    sales_api._set_custom(
        return_doc,
        ("exchange_against_invoice", "custom_exchange_against_invoice"),
        original.name,
    )
    if (return_reason or "").strip():
        sales_api._set_custom(return_doc, ("lumenpos_return_reason",), return_reason.strip())
    return_doc.run_method("set_missing_values")
    return_doc.run_method("calculate_taxes_and_totals")
    # Net the exchange against the value ERPNext validates the credit note on
    # (rounded_total when rounding is on), so the netted payments match exactly.
    credit_value = abs(
        flt(return_doc.rounded_total or return_doc.grand_total, return_doc.precision("grand_total"))
    )
    return return_doc, credit_value


def _build_replacement_sale(profile, customer, payload, session):
    customer_group = frappe.db.get_value("Customer", customer, "customer_group")
    price_list = resolve_price_list(profile, customer_group)
    items = payload["replacement_items"]
    codes = [i["item_code"] for i in items]
    details = {
        d.name: d
        for d in frappe.get_all(
            "Item",
            filters={"name": ["in", codes]},
            fields=["name", "stock_uom", "has_serial_no"],
        )
    }
    price_map = effective_prices(
        profile, codes, customer_group, None, {c: d.stock_uom for c, d in details.items()}
    )

    invoice = frappe.new_doc("POS Invoice")
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
            "ignore_pricing_rule": 1,
            "remarks": _("Warranty exchange replacement against {0}").format(
                payload["original_invoice"]
            ),
        }
    )
    sales_api._set_custom(invoice, ("lumenpos_session",), session["name"])
    sales_api._set_custom(invoice, ("is_exchange", "custom_is_exchange"), 1)
    sales_api._set_custom(
        invoice,
        ("exchange_against_invoice", "custom_exchange_against_invoice"),
        payload["original_invoice"],
    )
    # The replacement's warranty runs from the ORIGINAL purchase date (chained
    # from the original's own start if it was itself a replacement), so the
    # customer only keeps the remaining warranty — not a fresh full term.
    orig = frappe.db.get_value(
        "POS Invoice",
        payload["original_invoice"],
        ["lumenpos_warranty_start_date", "posting_date"],
        as_dict=True,
    )
    if orig:
        sales_api._set_custom(
            invoice,
            ("lumenpos_warranty_start_date",),
            orig.lumenpos_warranty_start_date or orig.posting_date,
        )

    seen_serials = set()
    for row in items:
        detail = details.get(row["item_code"])
        if not detail:
            frappe.throw(_("Unknown item {0}").format(row["item_code"]))
        line = {
            "item_code": row["item_code"],
            "qty": flt(row.get("qty")) or 1,
            "uom": detail.stock_uom,
            "warehouse": profile.warehouse,
        }
        if detail.has_serial_no:
            serials = [s.strip() for s in (row.get("serial_nos") or []) if s and s.strip()]
            from lumenpos.api.catalog import _check_serial

            if len(serials) != int(line["qty"]):
                frappe.throw(
                    _("{0} is serialized: scan {1} serial(s)").format(
                        row["item_code"], int(line["qty"])
                    )
                )
            for s in serials:
                if s in seen_serials:
                    frappe.throw(_("Serial {0} is scanned twice").format(s))
                seen_serials.add(s)
                check = _check_serial(row["item_code"], s, profile.warehouse)
                if not check["valid"]:
                    frappe.throw(check["message"])
            line.update({"use_serial_batch_fields": 1, "serial_no": "\n".join(serials)})
        invoice.append("items", line)

    invoice.set_missing_values()
    overridden = False
    for i, item_row in enumerate(invoice.items):
        # A manual price override (e.g. giving a pricier item at the same price)
        # comes through as `rate` on the payload line; otherwise price it from
        # the server price list (authoritative).
        override = items[i].get("rate") if i < len(items) else None
        if override is not None:
            item_row.price_list_rate = flt(override)
            overridden = True
        else:
            item_row.price_list_rate = flt(price_map.get(item_row.item_code, 0))
        item_row.discount_percentage = 0
        item_row.discount_amount = 0
        item_row.rate = 0
    if overridden:
        invoice.remarks = (invoice.remarks or "") + _("\n(manual exchange price)")
    invoice.run_method("calculate_taxes_and_totals")
    value = flt(invoice.rounded_total or invoice.grand_total, invoice.precision("grand_total"))
    return invoice, value
