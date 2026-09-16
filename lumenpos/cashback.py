# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Cashback: a per-customer wallet (POS Cashback Entry) that a sale earns and a
later sale spends, backed by a real liability account so the GL stays correct.

Unlike store credit, cashback expires. Each Earn row carries its own window
(usable from `valid_from`, expiring on `expiry_date`) and its own `remaining`,
the unspent, unexpired part still available:

- Earn    (a qualifying sale)      -> a new Earn row, remaining = amount.
- Redeem  (paying with cashback)   -> consumes the live Earn rows soonest to
  expire first, decrements their remaining, and writes a Redeem row. Pays out
  through the "Cashback" mode of payment (debits the liability).
- Reverse (a return of the earning sale) -> gives back the UNSPENT remainder of
  that sale's Earn rows; the part already spent is gone.
- Expire  (the nightly job)        -> writes off the remainder of a row past
  its expiry.

The balance is the sum of `remaining` over Earn rows that are live right now, so
it is always correct without walking every Redeem and Expire.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, now_datetime

MODE_OF_PAYMENT = "Cashback"
ACCOUNT_NAME = "Cashback"
LEDGER = "POS Cashback Entry"


def get_balance(customer, when=None):
    """The customer's spendable cashback right now: the remaining on every Earn
    row that has become usable and has not expired."""
    if not customer:
        return 0.0
    when = when or now_datetime()
    row = frappe.db.sql(
        """
        select sum(remaining) from `tabPOS Cashback Entry`
        where customer = %(customer)s
          and entry_type = 'Earn'
          and remaining > 0
          and (valid_from is null or valid_from <= %(when)s)
          and (expiry_date is null or expiry_date > %(when)s)
        """,
        {"customer": customer, "when": when},
    )
    return flt(row[0][0] if row and row[0][0] else 0.0, 2)


def _reference_doctype(reference_invoice):
    for doctype in ("POS Invoice", "Sales Invoice"):
        if frappe.db.exists(doctype, reference_invoice):
            return doctype
    return None


def earn(customer, amount, rule=None, reference_invoice=None, company=None,
         validity_days=0, activation_delay_days=0, reference_doctype=None):
    """Grant cashback to a customer. No-op for a blank customer or amount."""
    amount = flt(amount, 2)
    if not customer or amount <= 0:
        return None
    now = now_datetime()
    valid_from = add_to_date(now, days=cint_(activation_delay_days)) if activation_delay_days else now
    expiry = add_to_date(valid_from, days=cint_(validity_days)) if validity_days else None
    if reference_invoice and not reference_doctype:
        reference_doctype = _reference_doctype(reference_invoice)
    doc = frappe.get_doc(
        {
            "doctype": LEDGER,
            "customer": customer,
            "entry_type": "Earn",
            "amount": amount,
            "remaining": amount,
            "cashback_rule": rule,
            "valid_from": valid_from,
            "expiry_date": expiry,
            "company": company,
            "reference_doctype": reference_doctype if reference_invoice else None,
            "reference_invoice": reference_invoice,
            "posting_datetime": now,
        }
    ).insert(ignore_permissions=True)
    return doc.name


def redeem(customer, amount, reference_invoice=None, company=None, reference_doctype=None):
    """Spend `amount` of cashback, consuming the live Earn rows soonest to
    expire first. Raises if the balance is short."""
    amount = flt(amount, 2)
    if amount <= 0:
        return 0.0
    when = now_datetime()
    if get_balance(customer, when) + 0.005 < amount:
        frappe.throw(_("Cashback balance is too low to redeem {0}").format(amount))

    live = frappe.get_all(
        LEDGER,
        filters={
            "customer": customer,
            "entry_type": "Earn",
            "remaining": [">", 0],
        },
        fields=["name", "remaining", "valid_from", "expiry_date"],
        order_by="ifnull(expiry_date, '2999-12-31') asc, creation asc",
    )
    left = amount
    for row in live:
        if left <= 0.005:
            break
        if row.valid_from and row.valid_from > when:
            continue
        if row.expiry_date and row.expiry_date <= when:
            continue
        take = min(flt(row.remaining), left)
        frappe.db.set_value(LEDGER, row.name, "remaining", flt(row.remaining) - take,
                            update_modified=False)
        left -= take

    if reference_invoice and not reference_doctype:
        reference_doctype = _reference_doctype(reference_invoice)
    frappe.get_doc(
        {
            "doctype": LEDGER,
            "customer": customer,
            "entry_type": "Redeem",
            "amount": amount,
            "remaining": 0,
            "company": company,
            "reference_doctype": reference_doctype if reference_invoice else None,
            "reference_invoice": reference_invoice,
            "posting_datetime": when,
        }
    ).insert(ignore_permissions=True)
    return amount


def reverse_for_sale(reference_doctype, reference_invoice):
    """A return of a sale gives back the UNSPENT part of the cashback that sale
    earned. Whatever the customer already spent is not clawed back."""
    earns = frappe.get_all(
        LEDGER,
        filters={
            "entry_type": "Earn",
            "reference_doctype": reference_doctype,
            "reference_invoice": reference_invoice,
            "remaining": [">", 0],
        },
        fields=["name", "customer", "remaining", "company"],
    )
    reversed_total = 0.0
    now = now_datetime()
    for row in earns:
        give_back = flt(row.remaining, 2)
        if give_back <= 0:
            continue
        frappe.db.set_value(LEDGER, row.name, "remaining", 0, update_modified=False)
        frappe.get_doc(
            {
                "doctype": LEDGER,
                "customer": row.customer,
                "entry_type": "Reverse",
                "amount": give_back,
                "remaining": 0,
                "company": row.company,
                "reference_doctype": reference_doctype,
                "reference_invoice": reference_invoice,
                "posting_datetime": now,
            }
        ).insert(ignore_permissions=True)
        reversed_total += give_back
    return flt(reversed_total, 2)


def expire_due(batch=500):
    """Nightly: write off the remainder of every Earn row that has passed its
    expiry. Scheduled from hooks.py."""
    now = now_datetime()
    due = frappe.get_all(
        LEDGER,
        filters={
            "entry_type": "Earn",
            "remaining": [">", 0],
            "expiry_date": ["<=", now],
        },
        fields=["name", "customer", "remaining", "company"],
        limit=batch,
    )
    for row in due:
        lost = flt(row.remaining, 2)
        frappe.db.set_value(LEDGER, row.name, "remaining", 0, update_modified=False)
        frappe.get_doc(
            {
                "doctype": LEDGER,
                "customer": row.customer,
                "entry_type": "Expire",
                "amount": lost,
                "remaining": 0,
                "company": row.company,
                "posting_datetime": now,
            }
        ).insert(ignore_permissions=True)
    if due:
        # Scheduled-job checkpoint, so a crash mid-run keeps the write-offs
        # already made. Not a request, so nothing commits it for us.
        frappe.db.commit()  # nosemgrep
    return len(due)


def ensure_mode_of_payment(company):
    """Make sure the Cashback mode of payment exists with a liability account for
    this company, creating both on first use. Mirrors store credit."""
    from lumenpos.internal_accounts import fill_required_custom_fields

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
        return account

    mop = frappe.get_doc("Mode of Payment", MODE_OF_PAYMENT)
    row = next((r for r in mop.accounts if r.company == company), None)
    if row is None:
        mop.append("accounts", {"company": company, "default_account": account})
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.save(ignore_permissions=True)
    elif row.default_account != account:
        row.default_account = account
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.save(ignore_permissions=True)
    return account


def _get_or_create_account(company):
    abbr = frappe.get_cached_value("Company", company, "abbr")
    account_name = "{0} - {1}".format(ACCOUNT_NAME, abbr)
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
        "Account",
        {"company": company, "root_type": "Liability", "is_group": 1},
        "name",
    )
    if not parent:
        frappe.throw(
            _("No liability account group found for {0}; create a 'Cashback' liability account manually").format(company)
        )

    account = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": ACCOUNT_NAME,
            "parent_account": parent,
            "company": company,
            "root_type": "Liability",
            "account_currency": frappe.get_cached_value("Company", company, "default_currency"),
        }
    ).insert(ignore_permissions=True)
    return account.name


def cint_(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
