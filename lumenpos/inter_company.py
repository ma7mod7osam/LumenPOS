# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Customer balances across the companies of a group (LumenPOS Settings,
General, Companies): gift cards, cashback and store credit.

- Shared by the group (the default, and how LumenPOS always behaved): a
  balance is spendable at any outlet of any company of the group that keeps
  its books in the same currency. The company whose outlet takes it as payment
  spends its own customers' balance first.
- Separate per company: a balance is spendable only at the company that
  issued it.

When a shared balance issued by company A is spent at company B, B's outlet
posts the payment against B's own liability account (as every sale always
did), and a settlement line is recorded. Once a day, or when a manager asks,
the lines of each day, pair of companies and balance are booked as ONE
Inter Company Journal Entry pair, ERPNext's own mechanism (two entries, the
second referencing the first):

    at B (spent at):  Dr Due from group companies   Cr B's balance liability
    at A (issued by): Dr A's balance liability      Cr Due to group companies

so B's liability is back to what its own customers hold, A's liability goes
down by what its customer spent, and A owes B the goods B handed over. Before
this, A's liability never went down and B's went negative.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

SETTINGS = "LumenPOS Settings"
SETTLEMENT = "POS Inter Company Settlement"
SHARED = "Shared by the group"
SEPARATE = "Separate per company"
WALLETS = ("Gift Card", "Store Credit", "Cashback")


# ---------------------------------------------------------------------------
# Which companies' balances a till may spend
# ---------------------------------------------------------------------------

def mode():
    try:
        value = frappe.db.get_single_value(SETTINGS, "balances_across_companies")
    except Exception:
        value = None  # a site that has not migrated yet
    return value if value in (SHARED, SEPARATE) else SHARED


def shared():
    return mode() == SHARED


def _currency(company):
    return frappe.get_cached_value("Company", company, "default_currency")


def companies_for(company):
    """The companies whose customer balances an outlet of `company` accepts:
    itself alone when balances are separate, else every company of the group
    in the same currency (a riyal balance never pays a dirham bill)."""
    if not company:
        return None
    if not shared():
        return [company]
    currency = _currency(company)
    return sorted(c for c in frappe.get_all("Company", pluck="name") if _currency(c) == currency)


def usable_here(issuer, company):
    """Whether a balance issued by `issuer` may be spent at `company`."""
    if not issuer or not company or issuer == company:
        return True
    return issuer in (companies_for(company) or [])


# ---------------------------------------------------------------------------
# Settlement lines
# ---------------------------------------------------------------------------

def record(wallet, from_company, to_company, amount, customer=None, reference_doctype=None, reference_invoice=None):
    """A balance issued by `from_company` spent at `to_company`: to be settled."""
    amount = flt(amount, 2)
    if amount <= 0 or not from_company or not to_company or from_company == to_company:
        return None
    return frappe.get_doc(
        {
            "doctype": SETTLEMENT,
            "posting_date": nowdate(),
            "wallet": wallet,
            "from_company": from_company,
            "to_company": to_company,
            "amount": amount,
            "customer": customer,
            "reference_doctype": reference_doctype if reference_invoice else None,
            "reference_invoice": reference_invoice,
            "status": "Pending",
        }
    ).insert(ignore_permissions=True).name


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

def wallet_account(wallet, company):
    """The liability account a balance of this kind sits in, for a company."""
    if wallet == "Gift Card":
        from lumenpos import gift_cards

        return gift_cards.ensure_setup(company)
    if wallet == "Store Credit":
        from lumenpos import store_credit

        return store_credit.ensure_mode_of_payment(company)
    from lumenpos import cashback

    return cashback.liability_account(company)


def _configured(company, field):
    from lumenpos.api.settings import company_setting

    account = company_setting(company, field)
    if account and frappe.db.get_value("Account", account, "company") == company:
        return account
    return None


def _group_account(company, name, root_type, sibling):
    """An untyped account (no party needed on any version) beside the
    company's receivable or payable account, created once."""
    from lumenpos.internal_accounts import fill_required_custom_fields

    abbr = frappe.get_cached_value("Company", company, "abbr")
    full = f"{name} - {abbr}"
    if frappe.db.exists("Account", full):
        return full
    base = frappe.get_cached_value("Company", company, sibling)
    parent = frappe.db.get_value("Account", base, "parent_account") if base else None
    if not parent:
        parent = frappe.db.get_value("Account", {"company": company, "root_type": root_type, "is_group": 1}, "name")
    if not parent:
        frappe.throw(_("No {0} account group found for {1}. Create '{2}' by hand.").format(root_type, company, name))
    doc = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": name,
            "parent_account": parent,
            "company": company,
            "root_type": root_type,
            "is_group": 0,
            "account_currency": _currency(company),
        }
    )
    fill_required_custom_fields(doc, name)
    return doc.insert(ignore_permissions=True).name


def due_from_account(company):
    return _configured(company, "group_receivable_account") or _group_account(
        company, "Due from Group Companies", "Asset", "default_receivable_account"
    )


def due_to_account(company):
    return _configured(company, "group_payable_account") or _group_account(
        company, "Due to Group Companies", "Liability", "default_payable_account"
    )


# ---------------------------------------------------------------------------
# Posting: one Inter Company Journal Entry pair per day, pair and balance
# ---------------------------------------------------------------------------

def _journal_entry(company, posting_date, lines, remark, reference=None):
    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Inter Company Journal Entry"
    je.company = company
    je.posting_date = posting_date
    je.user_remark = remark
    if reference:
        je.inter_company_journal_entry_reference = reference
    # Every line on the company's own cost center: left empty, ERPNext fills
    # the default in anyway, and one entry must never straddle two.
    cost_center = frappe.get_cached_value("Company", company, "cost_center")
    for account, debit, credit in lines:
        je.append(
            "accounts",
            {
                "account": account,
                "debit_in_account_currency": debit,
                "credit_in_account_currency": credit,
                "cost_center": cost_center,
            },
        )
    je.flags.ignore_permissions = True
    je.insert()
    je.submit()
    return je.name


def post_pair(from_company, to_company, wallet, amount, posting_date):
    """Book one settlement: the entry at the company that took the balance,
    then the one at the company that issued it, referencing the first
    (submitting it links the first back, ERPNext's own way)."""
    remark = _("{0} issued by {1} and spent at {2}").format(_(wallet), from_company, to_company)
    at_spender = _journal_entry(
        to_company,
        posting_date,
        [(due_from_account(to_company), amount, 0), (wallet_account(wallet, to_company), 0, amount)],
        remark,
    )
    at_issuer = _journal_entry(
        from_company,
        posting_date,
        [(wallet_account(wallet, from_company), amount, 0), (due_to_account(from_company), 0, amount)],
        remark,
        reference=at_spender,
    )
    return at_spender, at_issuer


def post_pending(upto=None, commit=True, companies=None):
    """Book every pending line up to a date (all of them when None), grouped
    by day, pair of companies and balance. A group that fails keeps its lines
    pending with the reason, and the next run tries again. With `companies`,
    only groups whose two companies are both in it. Returns the number of
    lines booked."""
    filters = {"status": "Pending"}
    if upto:
        filters["posting_date"] = ["<=", getdate(upto)]
    lines = frappe.get_all(
        SETTLEMENT,
        filters=filters,
        fields=["name", "posting_date", "wallet", "from_company", "to_company", "amount"],
        order_by="posting_date asc, creation asc",
    )
    groups = defaultdict(list)
    for line in lines:
        groups[(line.posting_date, line.from_company, line.to_company, line.wallet)].append(line)
    booked = 0
    for (day, issuer, spender, wallet), rows in groups.items():
        if companies is not None and not (issuer in companies and spender in companies):
            continue
        names = [r.name for r in rows]
        amount = flt(sum(flt(r.amount) for r in rows), 2)
        # A savepoint per group: a pair that fails is undone on its own (no
        # half pair, no draft entry left behind) and the others stand.
        frappe.db.savepoint("lumenpos_ic")
        try:
            at_spender, at_issuer = post_pair(issuer, spender, wallet, amount, day)
            for name in names:
                frappe.db.set_value(
                    SETTLEMENT,
                    name,
                    {"status": "Posted", "to_journal_entry": at_spender, "from_journal_entry": at_issuer, "error": None},
                    update_modified=False,
                )
            booked += len(names)
            if commit:
                # One committed pair per group, so a later failure keeps it.
                frappe.db.commit()  # nosemgrep
        except Exception as exc:
            frappe.db.rollback(save_point="lumenpos_ic")
            message = str(exc)[:500]
            for name in names:
                frappe.db.set_value(SETTLEMENT, name, "error", message, update_modified=False)
            frappe.log_error(title="LumenPOS: inter-company settlement failed", message=frappe.get_traceback())
            if commit:
                frappe.db.commit()  # nosemgrep
    return booked


def nightly():
    """Book the days that have ended (today's lines wait for tonight, so a
    busy day is one entry pair, not one per sale)."""
    try:
        post_pending(upto=frappe.utils.add_days(nowdate(), -1))
    except Exception:
        frappe.log_error(title="LumenPOS: inter-company settlement run failed", message=frappe.get_traceback())


# ---------------------------------------------------------------------------
# Settings screen
# ---------------------------------------------------------------------------

def _require_manager():
    if not frappe.has_permission(SETTINGS, "write"):
        frappe.throw(_("Only someone who manages LumenPOS Settings can do this."), frappe.PermissionError)


@frappe.whitelist()
def status():
    """What the Companies card shows: the setting, what waits to be booked
    (per pair and balance), and the latest entry pairs."""
    if not frappe.has_permission(SETTLEMENT, "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    from lumenpos.api.permissions import allowed_companies

    # A user held to some companies (ERPNext User Permissions) sees only the
    # lines one of them is part of.
    companies = allowed_companies()
    where, values = "", {}
    if companies is not None:
        where = " and (from_company in %(companies)s or to_company in %(companies)s)"
        values["companies"] = tuple(companies)
    # where is a fixed string, the values are bound.
    pending = frappe.db.sql(  # nosemgrep
        f"""
        select from_company, to_company, wallet, count(*) as line_count, sum(amount) as amount,
               min(posting_date) as since, max(error) as error
        from `tabPOS Inter Company Settlement`
        where status = 'Pending'{where}
        group by from_company, to_company, wallet
        order by since asc
        """,
        values,
        as_dict=True,
    )
    recent = frappe.db.sql(  # nosemgrep
        f"""
        select posting_date, from_company, to_company, wallet, sum(amount) as amount,
               to_journal_entry, from_journal_entry
        from `tabPOS Inter Company Settlement`
        where status = 'Posted'{where}
        group by posting_date, from_company, to_company, wallet, to_journal_entry, from_journal_entry
        order by posting_date desc
        limit 10
        """,
        values,
        as_dict=True,
    )
    for row in pending + recent:
        row["amount"] = flt(row["amount"], 2)
        for key in ("since", "posting_date"):
            if row.get(key):
                row[key] = str(row[key])
    return {
        "mode": mode(),
        # Each company's currency, to show an amount in the issuer's money.
        "companies": {c.name: c.default_currency for c in frappe.get_all("Company", fields=["name", "default_currency"])},
        "pending": pending,
        "recent": recent,
    }


@frappe.whitelist()
def post_now():
    """Book everything waiting, today's lines included: for a manager held to
    some companies, only what passes between two of them."""
    _require_manager()
    from lumenpos.api.permissions import allowed_companies

    booked = post_pending(companies=allowed_companies())
    return {"booked": booked, **status()}
