# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""The clearing tender an exchange settles through.

An exchange is two ERPNext documents: a credit note for what came back and a
sale for what the customer took instead. Only the DIFFERENCE between them ever
touches the drawer, so the matched part has to settle somewhere that is not
cash and not a card, or the Z-report would show a refund and a collection that
never happened and the card terminal would never agree.

That somewhere is a clearing Mode of Payment, "Exchange", backed by a liability
account. The credit note pays into it, the new sale pays out of it, and the two
cancel inside the same transaction: the account is back to zero the moment the
exchange finishes. Anything left over (the customer took something cheaper) is
refunded by the normal refund rules instead, it never sits in the clearing
account.

Provisioned on first use, exactly like gift cards and store credit.
"""

import frappe
from frappe import _

MODE_OF_PAYMENT = "Exchange"
ACCOUNT_NAME = "POS Exchange Clearing"


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
        frappe.throw(
            _("No liability account group found for {0}, create a '{1}' liability account manually").format(
                company, ACCOUNT_NAME
            )
        )
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


def ensure_setup(company):
    """The Exchange mode of payment, mapped to this company's clearing account."""
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
    elif not row.default_account:
        row.default_account = account
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.save(ignore_permissions=True)
    return account
