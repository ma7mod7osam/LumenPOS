"""Gift cards, retail best practice:

- SELLING a card is a real sale: the POS Invoice carries a non-stock
  GIFT-CARD item whose income account is the 'Gift Cards' LIABILITY account —
  cash comes in, liability goes up, no revenue yet (and no tax: tax applies
  when the card is spent).
- REDEEMING pays via the 'Gift Card' mode of payment backed by the same
  liability account — liability goes down against the sale.
- Balances live on POS Gift Card with an entry ledger for the audit trail.
"""

import frappe
from frappe import _
from frappe.utils import flt, getdate, now_datetime, nowdate

# Defaults LumenPOS provisions when the admin hasn't mapped its own in LumenPOS
# Settings → Gift cards.
DEFAULT_MODE_OF_PAYMENT = "Gift Card"
DEFAULT_ACCOUNT_NAME = "Gift Cards"
DEFAULT_ITEM_CODE = "GIFT-CARD"


def _setting(field):
    value = frappe.db.get_single_value("LumenPOS Settings", field)
    return value.strip() if isinstance(value, str) and value.strip() else None


def mode_of_payment():
    """The gift-card Mode of Payment — the one mapped in LumenPOS Settings, else the
    default 'Gift Card'."""
    return _setting("gift_card_mode_of_payment") or DEFAULT_MODE_OF_PAYMENT


def item_code():
    """The gift-card Item — mapped in LumenPOS Settings, else the default."""
    return _setting("gift_card_item") or DEFAULT_ITEM_CODE


def ensure_setup(company):
    """Provision (or reuse the mapped) liability account, mode of payment and
    gift-card item on first use."""
    from lumenpos.internal_accounts import fill_required_custom_fields

    account = _account(company)
    mop_name = mode_of_payment()
    code = item_code()

    if not frappe.db.exists("Mode of Payment", mop_name):
        mop = frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": mop_name,
                "type": "General",
                "enabled": 1,
                "accounts": [{"company": company, "default_account": account}],
            }
        )
        fill_required_custom_fields(mop, mop_name)
        mop.insert(ignore_permissions=True)
    else:
        mop = frappe.get_doc("Mode of Payment", mop_name)
        row = next((r for r in mop.accounts if r.company == company), None)
        if row is None:
            mop.append("accounts", {"company": company, "default_account": account})
            fill_required_custom_fields(mop, mop_name)
            mop.save(ignore_permissions=True)
        elif row.default_account != account:
            # Correct a stale/wrong account (e.g. a party account that would make
            # redemption post to Receivable and fail). `account` already honours a
            # valid per-company override, so this reflects the intended account.
            row.default_account = account
            fill_required_custom_fields(mop, mop_name)
            mop.save(ignore_permissions=True)

    if not frappe.db.exists("Item", code):
        item_group = frappe.db.get_value(
            "Item Group", {"is_group": 0}, "name"
        )
        item = frappe.get_doc(
            {
                "doctype": "Item",
                "item_code": code,
                "item_name": "Gift Card",
                "item_group": item_group,
                "is_stock_item": 0,
                "is_sales_item": 1,
                "include_item_in_manufacturing": 0,
                # Preset our OWN item default so ERPNext does not copy the Item
                # Group's defaults on insert — those can carry a wrong-company
                # default warehouse that fails validation on a multi-company site
                # (update_defaults_from_item_group only copies when item_defaults
                # is empty). No warehouse: a non-stock gift card needs none.
                "item_defaults": [{"company": company, "income_account": account}],
            }
        )
        fill_required_custom_fields(item, "Gift Card")
        item.insert(ignore_permissions=True)

    # A non-stock gift card never needs a stock warehouse, but ERPNext validates
    # every item_default's default_warehouse against THAT row's company whenever
    # the Item is SAVED (validate_item_default_company_links). A stray warehouse —
    # copied from the Item Group's defaults, or the global Stock Settings default —
    # that points at another company throws "Row #1: Warehouse … doesn't belong to
    # Company …". This fails inside ensure_setup, before an invoice is ever built,
    # and simply re-saving the doc to blank the field does NOT hold (ERPNext
    # re-derives it during validate, before the check runs). So we do not re-save
    # the Item at all: scrub the stray warehouse STRAIGHT IN THE DB (bypassing
    # document validation). The sale posts income via the invoice line (see
    # sell_gift_card), so it never depends on these item defaults.
    strays = frappe.get_all(
        "Item Default",
        filters={
            "parent": code,
            "parenttype": "Item",
            "default_warehouse": ["is", "set"],
        },
        pluck="name",
    )
    for name in strays:
        frappe.db.set_value(
            "Item Default", name, "default_warehouse", None, update_modified=False
        )
    return account


def _account(company):
    """The mapped gift-card liability account, else auto-create the default.

    Honours a per-company override (LumenPOS Settings → Company Accounts) and
    only uses a configured account that ACTUALLY belongs to this company — so on
    a multi-company site a global account set for one company is never posted to
    another's GL (it auto-creates the right one instead)."""
    from lumenpos.api.settings import company_setting

    configured = company_setting(company, "gift_card_account") or _setting("gift_card_account")
    if (
        configured
        and frappe.db.exists("Account", configured)
        and frappe.db.get_value("Account", configured, "company") == company
        # A gift card is a LIABILITY we owe the holder. It must never be a party
        # account (Receivable/Payable) — redeeming would post the payment to it
        # WITHOUT a party and fail "Customer is required against Receivable …".
        and frappe.db.get_value("Account", configured, "account_type")
        not in ("Receivable", "Payable")
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
        frappe.throw(_("No liability account group found for {0}").format(company))
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


def new_card_no():
    while True:
        card_no = "GC-" + frappe.generate_hash(length=10).upper()
        if not frappe.db.exists("POS Gift Card", card_no):
            return card_no


def issue_card(card_no, amount, company, expiry_date=None, customer=None, invoice=None):
    card_no = (card_no or "").strip().upper() or new_card_no()
    if frappe.db.exists("POS Gift Card", card_no):
        frappe.throw(_("Gift card {0} already exists").format(card_no))
    card = frappe.get_doc(
        {
            "doctype": "POS Gift Card",
            "card_no": card_no,
            "status": "Active",
            "initial_amount": flt(amount),
            "balance": flt(amount),
            "expiry_date": expiry_date,
            "customer": customer,
            "company": company,
            "issued_invoice": invoice,
        }
    ).insert(ignore_permissions=True)
    _add_entry(card.name, "Load", flt(amount), invoice)
    return card


def check_redeem(card_no, amount):
    """Validate a redemption; returns the card doc or a clear error."""
    card_no = (card_no or "").strip().upper()
    if not frappe.db.exists("POS Gift Card", card_no):
        frappe.throw(_("Gift card {0} not found").format(card_no))
    card = frappe.get_doc("POS Gift Card", card_no)
    if card.status != "Active":
        frappe.throw(_("Gift card {0} is {1}").format(card_no, card.status))
    if card.expiry_date and getdate(card.expiry_date) < getdate(nowdate()):
        frappe.throw(_("Gift card {0} expired on {1}").format(card_no, card.expiry_date))
    if flt(amount) > flt(card.balance) + 0.005:
        frappe.throw(
            _("Gift card {0} has {1} left, cannot redeem {2}").format(
                card_no, card.balance, amount
            )
        )
    return card


def redeem(card_no, amount, invoice=None):
    card = check_redeem(card_no, amount)
    new_balance = flt(card.balance) - flt(amount)
    frappe.db.set_value("POS Gift Card", card.name, "balance", new_balance)
    if new_balance <= 0.005:
        frappe.db.set_value("POS Gift Card", card.name, "status", "Used")
    _add_entry(card.name, "Redeem", flt(amount), invoice)


def _add_entry(card, entry_type, amount, invoice=None):
    frappe.get_doc(
        {
            "doctype": "POS Gift Card Entry",
            "card": card,
            "entry_type": entry_type,
            "amount": flt(amount),
            "invoice": invoice,
            "posting_datetime": now_datetime(),
        }
    ).insert(ignore_permissions=True)
