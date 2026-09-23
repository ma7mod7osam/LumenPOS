# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Money a customer has paid against goods they have not taken yet.

A deposit is not revenue. The shop is holding someone else's money until the
goods are handed over, so it posts to a LIABILITY account ("Customer Deposits")
exactly the way a gift card does, and the drawer still sees it because it is
taken on a real POS sale: one line, the deposit item, priced at what was paid.

Handing the goods over posts the sale in full and puts the SAME item on it as a
NEGATIVE line, which clears the liability and leaves only the balance to
collect. One mechanism, and it works whichever way the shop treats tax:

- deposits without tax (the default): the deposit line carries no tax, and the
  full VAT is charged on the goods at hand-over.
- deposits with tax (Settings, for places where an advance against a known
  supply is taxable the moment it is received): the deposit line is taxed, and
  the negative line at hand-over carries the same tax, so the VAT already
  declared is deducted instead of charged twice.
"""

import frappe
from frappe import _

DEFAULT_ACCOUNT_NAME = "Customer Deposits"
DEFAULT_ITEM_CODE = "LUMENPOS-DEPOSIT"
ITEM_NAME = "Customer Deposit"
# The tender that spends a deposit when the goods are handed over. It moves
# nothing in the drawer: it debits the liability the instalments credited, so
# the sale is settled and only the balance is actually collected.
MODE_OF_PAYMENT = "Deposit"


def _setting(field):
    try:
        value = frappe.db.get_single_value("LumenPOS Settings", field)
    except Exception:
        return None
    return value.strip() if isinstance(value, str) and value.strip() else None


def item_code():
    """The deposit Item, the one mapped in LumenPOS Settings, else the default."""
    return _setting("deposit_item") or DEFAULT_ITEM_CODE


def taxed():
    """Does a deposit carry tax the moment it is taken? Off by default: the
    goods are taxed in full when they are handed over."""
    try:
        return bool(frappe.db.get_single_value("LumenPOS Settings", "deposit_with_tax"))
    except Exception:
        return False


def account(company):
    """The mapped deposit liability account, else auto-create the default.

    Never a party account (Receivable/Payable): posting a deposit there would
    need a party on every line and fail, and it would read as a debt owed BY
    the customer instead of money the shop is holding FOR them."""
    from lumenpos.api.settings import company_setting

    configured = company_setting(company, "deposit_account") or _setting("deposit_account")
    if (
        configured
        and frappe.db.exists("Account", configured)
        and frappe.db.get_value("Account", configured, "company") == company
        and frappe.db.get_value("Account", configured, "account_type") not in ("Receivable", "Payable")
    ):
        return configured
    return _get_or_create_account(company)


def _get_or_create_account(company):
    abbr = frappe.get_cached_value("Company", company, "abbr")
    account_name = f"{DEFAULT_ACCOUNT_NAME} - {abbr}"
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
                company, DEFAULT_ACCOUNT_NAME
            )
        )
    return (
        frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": DEFAULT_ACCOUNT_NAME,
                "parent_account": parent,
                "company": company,
                "root_type": "Liability",
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def ensure_setup(company):
    """Provision the liability account and the deposit item on first use.
    Returns (account, item_code)."""
    from lumenpos.internal_accounts import fill_required_custom_fields

    liability = account(company)
    code = item_code()
    if not frappe.db.exists("Item", code):
        item_group = frappe.db.get_value("Item Group", {"is_group": 0}, "name")
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": ITEM_NAME,
                "item_group": item_group,
                "is_stock_item": 0,
                "is_sales_item": 1,
                "include_item_in_manufacturing": 0,
                # Our own defaults, so ERPNext does not copy an item group's
                # (possibly wrong-company) warehouse on insert.
                "item_defaults": [{"company": company, "income_account": liability}],
            }
        )
        fill_required_custom_fields(item, ITEM_NAME)
        item.insert(ignore_permissions=True)
    ensure_mode_of_payment(company, liability)
    return liability, code


def zero_tax_template(company, taxes_and_charges=None):
    """An Item Tax Template that charges nothing, for the deposit line.

    Clearing an invoice's taxes does not hold: ERPNext re-applies the POS
    Profile's tax template on every validate (set_pos_fields refills them when
    the table is empty), so a deposit that must not be taxed has to say so on
    the LINE. The template zeroes exactly the accounts the outlet's own tax
    template uses, so nothing else about the invoice changes.

    Returns None when the outlet charges no tax anyway, or when the accounts
    cannot be read: there is nothing to suppress then."""
    if not taxes_and_charges:
        return None
    try:
        accounts = frappe.get_all(
            "Sales Taxes and Charges",
            filters={"parent": taxes_and_charges},
            pluck="account_head",
        )
        accounts = [a for a in dict.fromkeys(accounts) if a]
        if not accounts:
            return None
        abbr = frappe.get_cached_value("Company", company, "abbr")
        name = f"LumenPOS Zero Tax - {abbr}"
        if frappe.db.exists("Item Tax Template", name):
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Item Tax Template",
                "title": "LumenPOS Zero Tax",
                "company": company,
                "taxes": [{"tax_type": account, "tax_rate": 0} for account in accounts],
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(title="LumenPOS deposit zero tax", message=frappe.get_traceback())
        return None


def template_is_inclusive(taxes_and_charges):
    """Does this outlet quote prices WITH tax in them? It decides how an
    advance comes off the final invoice: on tax-inclusive prices the deduction
    is what the customer handed over, on tax-exclusive prices it is the net,
    because that is the number the rest of the lines are expressed in."""
    if not taxes_and_charges:
        return False
    try:
        return bool(
            frappe.db.exists(
                "Sales Taxes and Charges",
                {"parent": taxes_and_charges, "included_in_print_rate": 1},
            )
        )
    except Exception:
        return False


def ensure_mode_of_payment(company, liability=None):
    """The "Deposit" tender, backed by the same liability account, so handing
    the goods over spends what the customer already paid instead of asking for
    it twice."""
    from lumenpos.internal_accounts import fill_required_custom_fields

    liability = liability or account(company)
    if not frappe.db.exists("Mode of Payment", MODE_OF_PAYMENT):
        mop = frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": MODE_OF_PAYMENT,
                "type": "General",
                "enabled": 1,
                "accounts": [{"company": company, "default_account": liability}],
            }
        )
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.insert(ignore_permissions=True)
        return liability

    mop = frappe.get_doc("Mode of Payment", MODE_OF_PAYMENT)
    row = next((r for r in mop.accounts if r.company == company), None)
    if row is None:
        mop.append("accounts", {"company": company, "default_account": liability})
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.save(ignore_permissions=True)
    elif not row.default_account:
        row.default_account = liability
        fill_required_custom_fields(mop, MODE_OF_PAYMENT)
        mop.save(ignore_permissions=True)
    return liability
