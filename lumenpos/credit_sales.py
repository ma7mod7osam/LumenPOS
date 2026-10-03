# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Sales on account (0.60.0).

Asked by the Zimbabwe shop (2026-10-02, "Allow Credit Sale") and approved by the
owner on 2026-10-03: "خلينا نضيف البيع بالاجل", then "ليش ما يكون نقاط بيع زي كل
العمليات": a sale on account is a POS Invoice like every other sale.

How it works. The part the customer does not pay now is paid on the invoice by a
LumenPOS tender, "Credit Sale", whose account is a clearing account. In the same
request LumenPOS books the customer's debt with a Journal Entry: Dr the
customer's receivable (party = the customer), Cr the clearing account. When the
shift closes, the merged invoice's "Credit Sale" payment debits the clearing
account, which is back to zero; what stays is the debt on the customer's
account, one entry per sale, from the moment of the sale. A Payment Entry, at
the till (receive_payment) or in ERPNext, settles it.

Why not a POS Invoice left unpaid, ERPNext 15/16's "Allow Partial Payment": proven
on all four versions (scratchpad probe_credit.py, 2026-10-03), ERPNext 16 refuses
a POS Invoice with nothing paid ("At least one mode of payment is required"),
ERPNext 13 and 14 refuse a POS return that does not refund in full, and ERPNext
checks the credit limit only when the shift's invoices are merged, so a sale over
the limit failed the whole close. With a tender, every version takes any amount
paid now (none included), a return comes off the debt first (book_return), and
the limit is checked at the sale.

Rules (LumenPOS Settings, General, Sales on account):
- credit_sales_enabled: off by default.
- credit_customers: "Customers allowed on their card" (the default: the Customer's
  lumenpos_allow_credit) or "Any named customer". Never an outlet's walk-in.
- the limit: ERPNext's own (Customer, then Customer Group, then Company credit
  limit, erpnext get_credit_limit), else credit_default_limit, else none (0).
  Owed is ERPNext's own figure (get_customer_outstanding: the customer's ledger,
  unbilled Sales Orders and Delivery Notes), so ERPNext's check at the close sees
  what the till saw.
- who: the capabilities "Sell on account", "Take customer payments" and "Set a
  customer's credit" (api.permissions), nobody but a manager until named.
- in the company's currency only, and never offline.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

MODE_OF_PAYMENT = "Credit Sale"
ACCOUNT_NAME = "POS Credit Sale Clearing"
ALLOWED_ONLY = "Customers allowed on their card"
ANY_NAMED = "Any named customer"
WHO = (ALLOWED_ONLY, ANY_NAMED)
EPSILON = 0.005


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def _setting(field):
    try:
        return frappe.db.get_single_value("LumenPOS Settings", field)
    except Exception:
        return None  # a site that pulled the code without migrating


def enabled():
    return bool(cint(_setting("credit_sales_enabled")))


def who():
    value = _setting("credit_customers")
    return value if value in WHO else ALLOWED_ONLY


def default_limit():
    return max(flt(_setting("credit_default_limit")), 0.0)


def client_facts():
    """What the till needs before it asks anything (session bootstrap and
    get_settings)."""
    return {
        "credit_sales_enabled": 1 if enabled() else 0,
        "credit_customers": who(),
        "credit_default_limit": default_limit(),
        "credit_mode": MODE_OF_PAYMENT,
    }


# ---------------------------------------------------------------------------
# The tender and its clearing account
# ---------------------------------------------------------------------------


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
    ) or frappe.db.get_value("Account", {"company": company, "root_type": "Liability", "is_group": 1}, "name")
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
                "account_currency": frappe.get_cached_value("Company", company, "default_currency"),
            }
        )
        .insert(ignore_permissions=True)
        .name
    )


def ensure_setup(company):
    """The Credit Sale mode of payment, mapped to this company's clearing
    account, made on first use like the gift card and exchange tenders. A
    payment method of that name the shop made itself, on another account, is
    never taken over: the shop is told to rename it."""
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
    elif not row.default_account:
        row.default_account = account
    elif row.default_account != account:
        frappe.throw(
            _(
                "The payment method {0} already exists, and its account for {1} is {2}. LumenPOS needs its own "
                "for sales on account: rename yours in ERPNext (Mode of Payment, Rename) and save again."
            ).format(MODE_OF_PAYMENT, company, row.default_account),
            title=_("Sales on account"),
        )
    else:
        if not cint(mop.enabled):
            mop.enabled = 1
        else:
            return account
    fill_required_custom_fields(mop, MODE_OF_PAYMENT)
    mop.save(ignore_permissions=True)
    return account


def clearing_account(company):
    return frappe.db.get_value(
        "Mode of Payment Account", {"parent": MODE_OF_PAYMENT, "company": company}, "default_account"
    ) or f"{ACCOUNT_NAME} - {frappe.get_cached_value('Company', company, 'abbr')}"


# ---------------------------------------------------------------------------
# Who may buy, and how much
# ---------------------------------------------------------------------------


def walk_ins():
    """Customers that stand for whoever walks in: every outlet's default
    customer and each currency's walk-in (lumenpos.currency). A debt on them
    has nobody to collect it from."""
    names = set(frappe.get_all("POS Profile", filters={"customer": ["is", "set"]}, pluck="customer"))
    try:
        from lumenpos import currency

        labels = [f"Walk-in {code}" for code in currency.currency_rows()]
        if labels:
            names.update(frappe.get_all("Customer", filters={"customer_name": ["in", labels]}, pluck="name"))
    except Exception:
        pass
    return names


def credit_limit(customer, company):
    """(limit, where it comes from). ERPNext's own first (the customer, its
    group, the company), then LumenPOS's default. 0 is no limit."""
    from erpnext.selling.doctype.customer.customer import get_credit_limit

    own = flt(get_credit_limit(customer, company))
    if own > 0:
        return own, "erpnext"
    fallback = default_limit()
    if fallback > 0:
        return fallback, "default"
    return 0.0, None


def owed(customer, company):
    """What ERPNext counts against the customer's limit, in the company
    currency: the customer's ledger (every debt on account included, from the
    moment of its sale), plus unbilled Sales Orders and Delivery Notes."""
    from erpnext.selling.doctype.customer.customer import get_customer_outstanding

    return flt(get_customer_outstanding(customer, company), 2)


def customer_allowed(customer):
    return bool(cint(frappe.db.get_value("Customer", customer, "lumenpos_allow_credit")))


def refusal(customer, company):
    """Why this customer cannot buy on account at all (not the amount), or
    None."""
    if not enabled():
        return _("Sales on account are switched off in LumenPOS Settings.")
    if not customer or customer in walk_ins():
        return _("Choose the customer: a sale on account needs a named customer, not the walk-in customer.")
    if frappe.db.get_value("Customer", customer, "disabled"):
        return _("This customer is disabled.")
    if who() == ALLOWED_ONLY and not customer_allowed(customer):
        return _("This customer is not allowed to buy on account. Allow it on their card in Customers.")
    return None


def facts(customer, company, user=None):
    """What the till shows: may this customer buy on account here, how much is
    owed, the limit and what is left. Amounts in the company currency."""
    from lumenpos.api import permissions

    out = {
        "enabled": 1 if enabled() else 0,
        "mode": MODE_OF_PAYMENT,
        "can_sell": 1 if permissions.can_sell_on_account(user) else 0,
        "can_take_payment": 1 if permissions.can_take_customer_payments(user) else 0,
        "can_set": 1 if permissions.can_set_customer_credit(user) else 0,
        "currency": frappe.get_cached_value("Company", company, "default_currency") if company else None,
        "allowed_on_card": 1 if customer and customer_allowed(customer) else 0,
        "who": who(),
    }
    if not out["enabled"] or not customer or not company:
        out.update(allowed=0, reason=refusal(customer, company), owed=0.0, limit=0.0, available=None)
        return out
    limit, source = credit_limit(customer, company)
    owes = owed(customer, company)
    out.update(
        {
            "reason": refusal(customer, company),
            "owed": owes,
            "limit": limit,
            "limit_source": source,
            "erpnext_limit": flt(_erpnext_own_limit(customer, company)),
            "available": max(flt(limit - owes, 2), 0.0) if limit > 0 else None,
        }
    )
    out["allowed"] = 0 if out["reason"] else 1
    return out


def _erpnext_own_limit(customer, company):
    """The limit on the customer's own card for this company (not its group's
    or the company's), the one a manager edits from the till."""
    return frappe.db.get_value(
        "Customer Credit Limit", {"parent": customer, "parenttype": "Customer", "company": company}, "credit_limit"
    )


def assert_sale(customer, company, amount_base, invoice_currency, company_currency):
    """Refuse a sale on account the shop's rules do not allow, before anything
    posts. `amount_base` is the part put on account, in the company currency."""
    from lumenpos.api import permissions

    if not permissions.can_sell_on_account():
        frappe.throw(_("You are not allowed to sell on account."), frappe.PermissionError, title=_("Sales on account"))
    why = refusal(customer, company)
    if why:
        frappe.throw(why, title=_("Sales on account"))
    if invoice_currency != company_currency:
        frappe.throw(
            _("A sale on account is made in {0}, the company's currency.").format(company_currency),
            title=_("Sales on account"),
        )
    limit, _source = credit_limit(customer, company)
    if limit > 0:
        owes = owed(customer, company)
        if flt(owes + amount_base, 2) > flt(limit, 2) + EPSILON:
            from frappe.utils import fmt_money

            frappe.throw(
                _(
                    "{0} owes {1} of a limit of {2}, so at most {3} can go on account. Take more now, or ask a "
                    "manager to raise the limit."
                ).format(
                    frappe.db.get_value("Customer", customer, "customer_name") or customer,
                    fmt_money(owes, currency=company_currency),
                    fmt_money(limit, currency=company_currency),
                    fmt_money(max(limit - owes, 0), currency=company_currency),
                ),
                title=_("Credit limit"),
            )


# ---------------------------------------------------------------------------
# Booking
# ---------------------------------------------------------------------------


def _dimensions(doc):
    """The accounting dimensions the sale carries (Branch, Region...): a site
    that makes one mandatory refuses an entry without it."""
    try:
        from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import get_accounting_dimensions

        names = get_accounting_dimensions() or []
    except Exception:
        names = []
    return {name: doc.get(name) for name in names if doc.get(name)}


def _cost_center(doc):
    return (
        doc.get("cost_center")
        or (doc.get("pos_profile") and frappe.get_cached_value("POS Profile", doc.pos_profile, "cost_center"))
        or frappe.get_cached_value("Company", doc.company, "cost_center")
    )


def _journal_entry(doc, kind, amount, against=None):
    """Dr the customer / Cr the clearing account for a sale (`kind` Sale), the
    other way round for a return, which settles against the sale's own entry
    (`against`) so that entry owes less. Every line on the outlet's cost
    center: left empty, ERPNext fills the company's in (trap in CLAUDE.md)."""
    amount = flt(amount, 2)
    receivable = doc.debit_to
    clearing = clearing_account(doc.company)
    cost_center = _cost_center(doc)
    dims = _dimensions(doc)
    party = {"party_type": "Customer", "party": doc.customer}

    def line(account, debit=0.0, credit=0.0, **extra):
        row = {
            "account": account,
            "debit_in_account_currency": debit,
            "credit_in_account_currency": credit,
            "cost_center": cost_center,
            **dims,
            **extra,
        }
        return row

    if kind == "Sale":
        lines = [line(receivable, debit=amount, **party), line(clearing, credit=amount)]
        remark = _("{0} put on account at {1}: {2}").format(doc.name, doc.get("pos_profile") or doc.company, amount)
    else:
        lines = [
            line(clearing, debit=amount),
            line(
                receivable,
                credit=amount,
                **party,
                **({"reference_type": "Journal Entry", "reference_name": against} if against else {}),
            ),
        ]
        remark = _("{0} takes {1} off what is owed on account").format(doc.name, amount)
    je = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "company": doc.company,
            "posting_date": doc.posting_date or nowdate(),
            "user_remark": remark,
            "accounts": lines,
            "lumenpos_credit_kind": kind,
            "lumenpos_credit_invoice": doc.name,
            "lumenpos_credit_customer": doc.customer,
        }
    )
    je.flags.ignore_permissions = True
    je.insert()
    je.submit()
    return je.name


def on_account_part(doc):
    """What the Credit Sale tender carries on this invoice (negative on a
    return), in the invoice's currency."""
    return flt(sum(flt(p.amount) for p in (doc.payments or []) if p.mode_of_payment == MODE_OF_PAYMENT), 2)


def book_sale(invoice):
    """The customer's debt for the part of `invoice` put on account."""
    amount = on_account_part(invoice)
    if amount <= 0:
        return None
    name = _journal_entry(invoice, "Sale", amount)
    invoice.db_set("lumenpos_credit_entry", name, update_modified=False)
    return name


def entry_outstanding(entry, customer):
    """What is still owed on one sale's entry: its debit, less every payment,
    credit note or return allocated against it. From the ledger itself, the
    same on every version (13 has no Payment Ledger Entry)."""
    if not entry:
        return 0.0
    value = frappe.db.sql(
        """
        select coalesce(sum(debit_in_account_currency - credit_in_account_currency), 0)
        from `tabGL Entry`
        where party_type = 'Customer' and party = %(party)s and is_cancelled = 0
          and (
            (voucher_type = 'Journal Entry' and voucher_no = %(entry)s and coalesce(against_voucher, '') = '')
            or (against_voucher_type = 'Journal Entry' and against_voucher = %(entry)s)
          )
        """,
        {"party": customer, "entry": entry},
    )[0][0]
    return max(flt(value, 2), 0.0)


def owed_on_sale(sale):
    """What is still owed on this sale's part on account (0 when none)."""
    entry = sale.get("lumenpos_credit_entry")
    if not entry:
        return 0.0
    return entry_outstanding(entry, sale.customer)


def book_return(return_doc, original):
    """Take a return's part on account off the debt of the sale it returns."""
    amount = abs(on_account_part(return_doc))
    if amount <= 0:
        return None
    name = _journal_entry(return_doc, "Return", amount, against=original.get("lumenpos_credit_entry"))
    return_doc.db_set("lumenpos_credit_entry", name, update_modified=False)
    return name


def debt_part(original, refund_value):
    """How much of a return of `refund_value` comes off what the customer still
    owes on `original` (the rest goes back to them as money)."""
    return flt(min(flt(refund_value), owed_on_sale(original)), 2)


def refuse_tender(payments, what):
    """Gift cards and holds are paid with money, never on account."""
    if any(flt(p.get("amount")) and p.get("mode_of_payment") == MODE_OF_PAYMENT for p in payments or []):
        frappe.throw(_("{0} cannot be put on account.").format(what), title=_("Sales on account"))


def assert_no_debt(original, action):
    """Refuse `action` on a sale that still owes something on account."""
    owes = owed_on_sale(original)
    if owes > EPSILON:
        frappe.throw(
            _("{0} still has {1} on account. {2}").format(original.name, owes, action),
            title=_("Sales on account"),
        )


# ---------------------------------------------------------------------------
# What a customer owes, item by item
# ---------------------------------------------------------------------------


def open_items(customer, company):
    """Every debt of this customer at this company the till can take a payment
    for, oldest first: each sale on account (its entry) and each Sales Invoice
    still unpaid. Amounts in the company currency."""
    items = []
    entries = frappe.db.sql(
        """
        select je.name, je.posting_date, je.lumenpos_credit_invoice as invoice, jea.account,
               jea.debit_in_account_currency as amount
        from `tabJournal Entry` je
        join `tabJournal Entry Account` jea on jea.parent = je.name and jea.party_type = 'Customer'
             and jea.party = %(customer)s and jea.debit_in_account_currency > 0
        where je.docstatus = 1 and je.company = %(company)s and je.lumenpos_credit_kind = 'Sale'
          and je.lumenpos_credit_customer = %(customer)s
        order by je.posting_date, je.creation
        """,
        {"customer": customer, "company": company},
        as_dict=True,
    )
    for row in entries:
        left = entry_outstanding(row.name, customer)
        if left > EPSILON:
            items.append(
                {
                    "doctype": "Journal Entry",
                    "name": row.name,
                    "invoice": row.invoice,
                    "posting_date": str(row.posting_date),
                    "amount": flt(row.amount, 2),
                    "outstanding": left,
                    "account": row.account,
                }
            )
    for row in frappe.get_all(
        "Sales Invoice",
        filters={"customer": customer, "company": company, "docstatus": 1, "outstanding_amount": [">", 0]},
        fields=["name", "posting_date", "grand_total", "rounded_total", "outstanding_amount", "debit_to", "currency"],
        order_by="posting_date asc, creation asc",
    ):
        if row.currency != frappe.get_cached_value("Company", company, "default_currency"):
            continue
        items.append(
            {
                "doctype": "Sales Invoice",
                "name": row.name,
                "invoice": row.name,
                "posting_date": str(row.posting_date),
                "amount": flt(row.rounded_total or row.grand_total, 2),
                "outstanding": flt(row.outstanding_amount, 2),
                "account": row.debit_to,
            }
        )
    items.sort(key=lambda item: item["posting_date"])
    return items


def receipt_facts(doc):
    """For the receipt: the part on account, what is still owed on this sale
    and in all."""
    part = on_account_part(doc)
    if not part:
        return None
    out = {"mode": MODE_OF_PAYMENT, "amount": part}
    if not doc.get("is_return"):
        out["owed_on_sale"] = owed_on_sale(doc)
    try:
        out["owed_total"] = owed(doc.customer, doc.company)
    except Exception:
        pass
    return out
