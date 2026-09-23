# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Hold goods for a customer and let them pay over time.

Three things have to be true at once, and each is handled by the document that
is meant for it:

- the GOODS are reserved, so another till cannot sell the last one: a Sales
  Order, ERPNext's own reservation.
- the MONEY is in the drawer and on the Z-report the moment it is taken: each
  instalment is a real POS sale of one line, the deposit item, which posts to
  the Customer Deposits liability account (see lumenpos/deposits.py). It is not
  revenue: the shop is holding someone else's money.
- the SHOP can see what is held, for whom, and what is left: the POS Layaway
  document, whose totals are derived from the two above.

Handing over posts the sale of the real goods and settles what was already
paid, so the liability clears and the drawer only ever sees the balance. How it
settles depends on how the shop taxes a deposit: an untaxed deposit is spent as
the "Deposit" tender (the goods are taxed in full), a taxed one comes off as a
NEGATIVE line carrying the same tax, so the tax declared on the advance is
deducted instead of charged twice.

Cancelling refunds every instalment through the ordinary return path, so the
refund method rules a shop already set apply here too, and closes the order so
the goods go back on the shelf.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from lumenpos import deposits, erpnext_compat
from lumenpos.api import permissions, sales


def _require_layaway():
    if not permissions.can_hold_goods():
        frappe.throw(_("You are not allowed to hold goods for a customer"), frappe.PermissionError)


def _load(name):
    doc = frappe.get_doc("POS Layaway", name)
    return doc


def _profile(pos_profile):
    return frappe.get_cached_doc("POS Profile", pos_profile)


def _post_sale(profile, customer, lines, payments, note, with_taxes, tax_included=False):
    """Post a POS sale with the rates GIVEN, not the ones the price list has
    today.

    A hold fixes its prices the day it is made, and a deposit is an amount,
    not a product, so neither may go through the normal pricing engine. This is
    the same builder a gift card sale uses: explicit lines, the shop's tender
    rows, one invoice tied to the open shift, so the drawer and the Z-report
    see it like any other sale."""
    session = sales._open_session(profile.name)
    warehouse = sales._company_warehouse(profile)
    invoice = erpnext_compat.new_doc(sales._sale_doctype(profile))
    invoice.update(
        {
            "is_pos": 1,
            "pos_profile": profile.name,
            "company": profile.company,
            "customer": customer,
            "selling_price_list": profile.selling_price_list,
            "ignore_pricing_rule": 1,
            "set_warehouse": warehouse,
            "taxes_and_charges": profile.taxes_and_charges if with_taxes else None,
            "remarks": note,
        }
    )
    sales._set_custom(invoice, ("lumenpos_session",), session["name"])
    sales._set_custom(invoice, ("lumenpos_note",), note)
    for line in lines:
        row = dict(line)
        row.setdefault("warehouse", warehouse)
        invoice.append("items", row)
    invoice.set_missing_values()
    if not with_taxes:
        invoice.taxes = []
    elif tax_included:
        # A deposit is the amount the customer HANDS OVER. Where an advance is
        # taxable, the tax is carved out of that amount, never added on top:
        # asking for 50 plus tax is not what "a 50 deposit" means to anyone.
        for row in invoice.taxes or []:
            row.included_in_print_rate = 1
    invoice.set("set_warehouse", warehouse)
    for row in invoice.items:
        row.warehouse = warehouse

    for payment in payments or []:
        amount = flt(payment.get("amount"))
        if amount:
            sales._set_payment(invoice, payment["mode_of_payment"], amount)
    sales._reconcile_payment(invoice, profile)
    sales._drop_empty_payments(invoice)
    sales._apply_payment_references(invoice, payments)

    sales._lock_open_session(session["name"])
    invoice.insert()
    invoice.submit()
    return sales.get_receipt(invoice.name)


def _deposit_line(profile, amount, negative=False, taxable=None):
    """One line, the deposit item, posting to the liability account.

    When the shop does not tax deposits the line carries a zero-rate item tax
    template, because emptying the invoice's tax table does not survive
    validate: ERPNext refills it from the POS Profile."""
    liability, code = deposits.ensure_setup(profile.company)
    rate = -abs(flt(amount)) if negative else abs(flt(amount))
    row = {
        "item_code": code,
        "qty": 1,
        "rate": rate,
        "price_list_rate": rate,
        "income_account": liability,
    }
    if not (deposits.taxed() if taxable is None else taxable):
        zero = deposits.zero_tax_template(profile.company, profile.taxes_and_charges)
        if zero:
            row["item_tax_template"] = zero
    return row


def _take_deposit(doc, profile, amount, payments, note=None):
    """Post the instalment as a real POS sale and record it on the hold."""
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Enter the amount the customer is paying"))
    if amount > flt(doc.balance) + 0.005:
        frappe.throw(
            _("That is more than the {0} still owed on this hold.").format(flt(doc.balance, 2))
        )
    receipt = _post_sale(
        profile,
        doc.customer,
        [_deposit_line(profile, amount)],
        payments,
        note or _("Deposit for hold {0}").format(doc.name),
        with_taxes=deposits.taxed(),
        tax_included=True,
    )
    doc.append(
        "payments",
        {
            "paid_at": now_datetime(),
            "amount": amount,
            "mode_of_payment": ", ".join(
                p.get("mode_of_payment") for p in payments if flt(p.get("amount"))
            ),
            "invoice": receipt["name"],
            "recorded_by": frappe.session.user,
        },
    )
    return receipt


def _net_deposited(doc):
    """What the deposit invoices actually declared, before tax. Read from the
    invoices themselves so it can never drift from what was posted."""
    total = 0.0
    for row in doc.payments or []:
        if row.refunded or not row.invoice:
            continue
        doctype = "POS Invoice" if frappe.db.exists("POS Invoice", row.invoice) else "Sales Invoice"
        total += flt(frappe.db.get_value(doctype, row.invoice, "net_total"))
    return flt(total, 2)


def _reserve(doc, profile, items):
    """A Sales Order, so ERPNext shows the quantity as reserved and no other
    till sells the last one. Best-effort: a shop that cannot raise orders (no
    permission, an item that needs details a till does not ask for) still gets
    the hold, just without the reservation."""
    if not frappe.db.get_single_value("LumenPOS Settings", "layaway_reserve_stock"):
        return None
    try:
        order = frappe.new_doc("Sales Order")
        order.update(
            {
                "customer": doc.customer,
                "company": profile.company,
                "transaction_date": nowdate(),
                "delivery_date": doc.expiry_date or nowdate(),
                "selling_price_list": profile.selling_price_list,
                "order_type": "Sales",
            }
        )
        if profile.get("warehouse"):
            order.set("set_warehouse", profile.warehouse)
        for row in items:
            order.append(
                "items",
                {
                    "item_code": row["item_code"],
                    "qty": flt(row["qty"]),
                    "rate": flt(row["rate"]),
                    "delivery_date": doc.expiry_date or nowdate(),
                    "warehouse": profile.get("warehouse"),
                },
            )
        order.insert(ignore_permissions=True)
        order.submit()
        return order.name
    except Exception:
        frappe.log_error(title="LumenPOS layaway reservation", message=frappe.get_traceback())
        return None


def _release(doc, reason):
    """Stop the order reserving stock, whether the goods went out or the hold
    was cancelled."""
    if not doc.sales_order or not frappe.db.exists("Sales Order", doc.sales_order):
        return
    try:
        order = frappe.get_doc("Sales Order", doc.sales_order)
        if order.docstatus == 1 and order.status not in ("Closed", "Completed"):
            order.add_comment("Comment", reason)
            order.update_status("Closed")
    except Exception:
        frappe.log_error(title="LumenPOS layaway release", message=frappe.get_traceback())


@frappe.whitelist()
def create_layaway(payload):
    """Start a hold: reserve the goods, take the first instalment.

    payload = {pos_profile, customer, items:[{item_code, qty, rate}],
               payments:[{mode_of_payment, amount}], expiry_date?, note?}
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    _require_layaway()

    profile = _profile(payload["pos_profile"])
    customer = payload.get("customer")
    if not customer:
        frappe.throw(_("A hold needs a customer, so the shop knows whose goods these are"))
    items = payload.get("items") or []
    if not items:
        frappe.throw(_("Add the goods being held"))

    days = frappe.db.get_single_value("LumenPOS Settings", "layaway_days") or 0
    doc = frappe.new_doc("POS Layaway")
    doc.update(
        {
            "customer": customer,
            "customer_name": frappe.db.get_value("Customer", customer, "customer_name"),
            "pos_profile": profile.name,
            "company": profile.company,
            "status": "Open",
            "expiry_date": payload.get("expiry_date")
            or (frappe.utils.add_days(nowdate(), int(days)) if days else None),
            "note": payload.get("note"),
        }
    )
    for row in items:
        qty = flt(row.get("qty")) or 1
        rate = flt(row.get("rate"))
        doc.append(
            "items",
            {
                "item_code": row["item_code"],
                "item_name": row.get("item_name")
                or frappe.db.get_value("Item", row["item_code"], "item_name"),
                "qty": qty,
                "rate": rate,
                "amount": flt(qty * rate, 2),
            },
        )
    doc.insert(ignore_permissions=True)

    minimum = flt(frappe.db.get_single_value("LumenPOS Settings", "layaway_min_percent"))
    paid_now = flt(sum(flt(p.get("amount")) for p in (payload.get("payments") or [])))
    if minimum and paid_now + 0.005 < flt(doc.total) * minimum / 100:
        frappe.throw(
            _("This shop asks for at least {0}% down, which is {1}.").format(
                flt(minimum, 2), flt(flt(doc.total) * minimum / 100, 2)
            )
        )

    receipt = None
    if paid_now:
        receipt = _take_deposit(doc, profile, paid_now, payload.get("payments") or [])
    doc.sales_order = _reserve(doc, profile, items)
    doc.save(ignore_permissions=True)
    return {"layaway": get_layaway(doc.name), "receipt": receipt}


@frappe.whitelist()
def add_instalment(layaway, payments):
    """Take another payment against an open hold."""
    if isinstance(payments, str):
        payments = json.loads(payments)
    _require_layaway()
    doc = _load(layaway)
    if doc.status != "Open":
        frappe.throw(_("This hold is {0}").format(_(doc.status)))
    profile = _profile(doc.pos_profile)
    amount = flt(sum(flt(p.get("amount")) for p in payments))
    receipt = _take_deposit(doc, profile, amount, payments)
    doc.save(ignore_permissions=True)
    return {"layaway": get_layaway(doc.name), "receipt": receipt}


@frappe.whitelist()
def complete_layaway(layaway, payments=None):
    """Hand the goods over: the real sale, less what is already paid.

    The deposit comes off as a negative line of the SAME item that took it, so
    the liability clears and, when a shop taxes deposits, the tax already
    declared is deducted instead of charged twice."""
    if isinstance(payments, str):
        payments = json.loads(payments or "[]")
    _require_layaway()
    doc = _load(layaway)
    if doc.status != "Open":
        frappe.throw(_("This hold is {0}").format(_(doc.status)))
    profile = _profile(doc.pos_profile)

    lines = [
        {
            "item_code": row.item_code,
            "qty": flt(row.qty),
            "rate": flt(row.rate),
            "price_list_rate": flt(row.rate),
        }
        for row in (doc.items or [])
    ]
    held = flt(doc.paid)
    tenders = list(payments or [])
    if held > 0:
        if deposits.taxed():
            # The deposit was already invoiced WITH tax carved out of it, so
            # what comes off here is the NET that was declared, and the tax on
            # it comes off with it. Putting the gross back as a tender would
            # tax the same money twice.
            inclusive = deposits.template_is_inclusive(profile.taxes_and_charges)
            deduct = held if inclusive else _net_deposited(doc)
            lines.append(_deposit_line(profile, deduct, negative=True))
        else:
            # The deposit carried no tax, so the goods are taxed in full and
            # what the customer already paid settles the invoice as a tender.
            deposits.ensure_mode_of_payment(profile.company)
            tenders = [{"mode_of_payment": deposits.MODE_OF_PAYMENT, "amount": held}] + tenders

    receipt = _post_sale(
        profile,
        doc.customer,
        lines,
        tenders,
        _("Hold {0} handed over").format(doc.name),
        with_taxes=True,
    )
    doc.status = "Completed"
    doc.completed_invoice = receipt["name"]
    doc.completed_at = now_datetime()
    _release(doc, _("Goods handed over on {0}").format(receipt["name"]))
    doc.save(ignore_permissions=True)
    return {"layaway": get_layaway(doc.name), "receipt": receipt}


@frappe.whitelist()
def cancel_layaway(layaway, refund_mode=None, refund_payments=None, reason=None):
    """Give the money back and put the goods on the shelf.

    Every instalment is refunded through the ordinary return, so the refund
    methods a shop configured apply here as well."""
    if isinstance(refund_payments, str):
        refund_payments = json.loads(refund_payments or "[]")
    _require_layaway()
    doc = _load(layaway)
    if doc.status != "Open":
        frappe.throw(_("This hold is {0}").format(_(doc.status)))

    refunds = []
    for row in doc.payments or []:
        if row.refunded or not row.invoice:
            continue
        credit = sales.create_return(
            invoice=row.invoice,
            items={deposits.item_code(): 1},
            refund_mode=refund_mode or "Cash",
            return_reason=reason or _("Hold cancelled"),
            pos_profile=doc.pos_profile,
            refund_payments=refund_payments or None,
        )
        row.refunded = 1
        refunds.append(credit["name"])

    doc.status = "Cancelled"
    if reason:
        doc.note = "\n".join(part for part in [doc.note, reason] if part)
    _release(doc, _("Hold cancelled"))
    doc.save(ignore_permissions=True)
    return {"layaway": get_layaway(doc.name), "refunds": refunds}


@frappe.whitelist()
def get_layaway(name):
    doc = _load(name)
    return {
        "name": doc.name,
        "customer": doc.customer,
        "customer_name": doc.customer_name,
        "pos_profile": doc.pos_profile,
        "status": doc.status,
        "expiry_date": str(doc.expiry_date) if doc.expiry_date else None,
        "sales_order": doc.sales_order,
        "total": flt(doc.total, 2),
        "paid": flt(doc.paid, 2),
        "balance": flt(doc.balance, 2),
        "note": doc.note,
        "completed_invoice": doc.completed_invoice,
        "items": [
            {
                "item_code": row.item_code,
                "item_name": row.item_name,
                "qty": flt(row.qty),
                "rate": flt(row.rate, 2),
                "amount": flt(row.amount, 2),
            }
            for row in (doc.items or [])
        ],
        "payments": [
            {
                "paid_at": str(row.paid_at) if row.paid_at else None,
                "amount": flt(row.amount, 2),
                "mode_of_payment": row.mode_of_payment,
                "invoice": row.invoice,
                "refunded": bool(row.refunded),
            }
            for row in (doc.payments or [])
        ],
    }


@frappe.whitelist()
def list_layaways(pos_profile=None, status="Open", search=None, limit=50):
    """The holds screen: what this outlet is holding, newest first."""
    filters = {}
    if status and status != "All":
        filters["status"] = status
    if pos_profile and pos_profile != "__all__":
        filters["pos_profile"] = pos_profile
    or_filters = None
    if (search or "").strip():
        term = f"%{search.strip()}%"
        or_filters = {"name": ["like", term], "customer_name": ["like", term], "customer": ["like", term]}
    rows = frappe.get_all(
        "POS Layaway",
        filters=filters,
        or_filters=or_filters,
        fields=[
            "name", "customer", "customer_name", "pos_profile", "status",
            "total", "paid", "balance", "expiry_date", "modified",
        ],
        order_by="modified desc",
        limit_page_length=int(limit),
    )
    for row in rows:
        row["expiry_date"] = str(row["expiry_date"]) if row.get("expiry_date") else None
        row["modified"] = str(row["modified"])
        row["overdue"] = bool(
            row.get("expiry_date") and row["status"] == "Open" and row["expiry_date"] < nowdate()
        )
    return {"layaways": rows}
