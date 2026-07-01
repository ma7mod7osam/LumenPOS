"""Store credit: a simple per-customer ledger (POS Store Credit Entry) backed
by a real liability account so the GL stays correct.

- Refund to store credit  -> return invoice pays out via the "Store Credit"
  mode of payment (credits the liability) + an Issue ledger entry.
- Pay with store credit   -> sale invoice payment row in the same mode
  (debits the liability) + a Redeem ledger entry.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

MODE_OF_PAYMENT = "Store Credit"
ACCOUNT_NAME = "Store Credit"


def get_balance(customer):
    if not customer:
        return 0.0
    rows = frappe.get_all(
        "POS Store Credit Entry",
        filters={"customer": customer},
        fields=["entry_type", "sum(amount) as total"],
        group_by="entry_type",
    )
    balance = 0.0
    for row in rows:
        balance += flt(row.total) if row.entry_type == "Issue" else -flt(row.total)
    return flt(balance, 2)


def add_entry(customer, entry_type, amount, reference_invoice=None, company=None):
    frappe.get_doc(
        {
            "doctype": "POS Store Credit Entry",
            "customer": customer,
            "entry_type": entry_type,
            "amount": flt(amount, 2),
            "reference_invoice": reference_invoice,
            "company": company,
            "posting_datetime": now_datetime(),
        }
    ).insert(ignore_permissions=True)


def ensure_mode_of_payment(company):
    """Make sure the Store Credit mode of payment exists and has a liability
    account for this company, creating both on first use."""
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
        # Correct a stale/wrong account so redemption can't post to Receivable.
        row.default_account = account
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.save(ignore_permissions=True)
    return account


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
        "Account",
        {"company": company, "root_type": "Liability", "is_group": 1},
        "name",
    )
    if not parent:
        frappe.throw(
            _("No liability account group found for {0}; create a 'Store Credit' liability account manually").format(company)
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
