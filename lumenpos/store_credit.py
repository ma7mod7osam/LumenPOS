# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
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


def get_balance(customer, company=None):
    """What the customer may spend at an outlet of `company`: every company's
    credit when balances are shared by the group (same currency only), its own
    when separate (lumenpos.inter_company). No company: all of it."""
    if not customer:
        return 0.0
    from lumenpos import inter_company

    balance = sum(balances_by_company(customer, company).values())
    if company and not inter_company.shared():
        # Separate balances on a site that shared them before: credit issued
        # here but already spent at another company was recorded THERE, so
        # this company's own figure can overstate it. Never more than the
        # customer holds in all.
        balance = min(balance, sum(balances_by_company(customer).values()))
    return flt(max(balance, 0) if company else balance, 2)


def balances_by_company(customer, company=None):
    """{company: balance} of the credit an outlet of `company` accepts. An
    entry without a company (made before companies were recorded) counts as
    the spending company's own."""
    from lumenpos import inter_company

    allowed = inter_company.companies_for(company)
    rows = frappe.get_all(
        "POS Store Credit Entry",
        filters={"customer": customer},
        fields=["company", "entry_type", "sum(amount) as total"],
        group_by="company, entry_type",
    )
    out = {}
    for row in rows:
        owner = row.company or company or ""
        if allowed is not None and owner not in allowed:
            continue
        out[owner] = out.get(owner, 0.0) + (flt(row.total) if row.entry_type == "Issue" else -flt(row.total))
    return {k: flt(v, 2) for k, v in out.items()}


def redeem(customer, amount, reference_invoice=None, company=None, reference_doctype=None):
    """Spend store credit at an outlet of `company`: its own customers' credit
    first, then other companies of the group (largest first). Each company's
    part is its own Redeem entry, and a part issued by another company is
    recorded for the Inter Company Journal Entry that settles it."""
    from lumenpos import inter_company

    amount = flt(amount, 2)
    per = balances_by_company(customer, company)
    order = sorted(per, key=lambda c: (c != (company or ""), -per[c]))
    left = amount
    for owner in order:
        take = flt(min(max(per[owner], 0), left), 2)
        if take <= 0:
            continue
        add_entry(customer, "Redeem", take, reference_invoice, owner or company, reference_doctype)
        if company and owner and owner != company:
            inter_company.record("Store Credit", owner, company, take, customer, reference_doctype, reference_invoice)
        left = flt(left - take, 2)
        if left <= 0:
            break
    if left > 0.005:
        frappe.throw(_("Store credit balance is too low to redeem {0}").format(amount))
    return amount


def add_entry(
    customer,
    entry_type,
    amount,
    reference_invoice=None,
    company=None,
    reference_doctype=None,
):
    """Record one movement on a customer's store credit.

    `reference_doctype` says WHICH sale doctype `reference_invoice` names. It
    matters because LumenPOS posts POS Invoices by default but a profile can be
    set to post Sales Invoices, and the reference is a Dynamic Link. Left blank
    it is inferred from the document that actually exists, so older callers keep
    working.
    """
    if reference_invoice and not reference_doctype:
        for doctype in ("POS Invoice", "Sales Invoice"):
            if frappe.db.exists(doctype, reference_invoice):
                reference_doctype = doctype
                break
    frappe.get_doc(
        {
            "doctype": "POS Store Credit Entry",
            "customer": customer,
            "entry_type": entry_type,
            "amount": flt(amount, 2),
            "reference_doctype": reference_doctype if reference_invoice else None,
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
            _("No liability account group found for {0}, create a 'Store Credit' liability account manually").format(company)
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
