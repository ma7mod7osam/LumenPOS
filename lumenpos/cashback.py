# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Cashback: a per-customer wallet (POS Cashback Entry) that a sale earns and a
later sale spends, booked to two accounts each company chooses.

Unlike store credit, cashback expires. Each Earn row carries its own window
(usable from `valid_from`, expiring on `expiry_date`) and its own `remaining`,
the unspent, unexpired part still available:

- Earn    (a qualifying sale)      -> a new Earn row, remaining = amount.
- Redeem  (paying with cashback)   -> consumes the live Earn rows soonest to
  expire first, decrements their remaining, and writes a Redeem row. Pays out
  through the "Cashback" mode of payment, whose account is the liability.
- Reverse (a return of the earning sale) -> gives back the UNSPENT remainder of
  that sale's Earn rows. The part already spent is gone.
- Expire  (the nightly job)        -> writes off the remainder of a row past
  its expiry.

The balance is the sum of `remaining` over Earn rows that are live right now, so
it is always correct without walking every Redeem and Expire.

Accounting (full accrual). Per company, LumenPOS Settings > Company Accounts
names a cashback LIABILITY account and a cashback EXPENSE account (both created
automatically when left empty):

- Earn:            Dr expense   Cr liability   (booked by post_to_gl)
- Redeem:          Dr liability Cr debtors     (the sale's own payment row)
- Expire, Reverse: Dr liability Cr expense     (booked by post_to_gl)

post_to_gl books Earn, Expire and Reverse rows as ONE summary Journal Entry per
company, day and cost center (the outlet's), never one per sale. Every row it
books is stamped with that Journal Entry, so nothing is ever booked twice. The
nightly job books the days that have ended, and a manager can book everything
up to now from the Cashback settings tab. Once rows are booked and the shifts are
closed, the liability account equals what customers still hold.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, flt, get_datetime, getdate, now_datetime, nowdate

MODE_OF_PAYMENT = "Cashback"
ACCOUNT_NAME = "Cashback"
EXPENSE_ACCOUNT_NAME = "Cashback Expense"
LEDGER = "POS Cashback Entry"
POSTABLE = ("Earn", "Expire", "Reverse")
LIABILITY_FIELD = "cashback_liability_account"
EXPENSE_FIELD = "cashback_expense_account"


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


def _cost_center(company, pos_profile=None):
    """The outlet's cost center, else the company default."""
    cost_center = None
    if pos_profile:
        cost_center = frappe.get_cached_value("POS Profile", pos_profile, "cost_center")
    return cost_center or frappe.get_cached_value("Company", company, "cost_center")


def earn(customer, amount, rule=None, reference_invoice=None, company=None,
         validity_days=0, activation_delay_days=0, reference_doctype=None, pos_profile=None):
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
            "pos_profile": pos_profile,
            "cost_center": _cost_center(company, pos_profile) if company else None,
            "reference_doctype": reference_doctype if reference_invoice else None,
            "reference_invoice": reference_invoice,
            "posting_datetime": now,
        }
    ).insert(ignore_permissions=True)
    return doc.name


def redeem(customer, amount, reference_invoice=None, company=None, reference_doctype=None,
           pos_profile=None):
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
            "pos_profile": pos_profile,
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
        fields=["name", "customer", "remaining", "company", "pos_profile", "cost_center"],
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
                "pos_profile": row.pos_profile,
                "cost_center": row.cost_center,
                "reference_doctype": reference_doctype,
                "reference_invoice": reference_invoice,
                "posting_datetime": now,
            }
        ).insert(ignore_permissions=True)
        reversed_total += give_back
    return flt(reversed_total, 2)


def expire_due(batch=500, commit=True):
    """Write off the remainder of every Earn row that has passed its expiry."""
    now = now_datetime()
    due = frappe.get_all(
        LEDGER,
        filters={
            "entry_type": "Earn",
            "remaining": [">", 0],
            "expiry_date": ["<=", now],
        },
        fields=["name", "customer", "remaining", "company", "pos_profile", "cost_center"],
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
                "pos_profile": row.pos_profile,
                "cost_center": row.cost_center,
                "posting_datetime": now,
            }
        ).insert(ignore_permissions=True)
    if due and commit:
        # Scheduled-job checkpoint, so a crash mid-run keeps the write-offs
        # already made. Not a request, so nothing commits it for us.
        frappe.db.commit()  # nosemgrep
    return len(due)


def nightly():
    """Scheduled from hooks.py at 00:30: write off expired cashback, then book
    the days that have ended to the accounts."""
    expire_due()
    post_to_gl(include_today=False, commit_each=True)


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def account_problem(account, company, kind):
    """Why `account` cannot take cashback postings for `company`, or None when
    it can. `kind` is "liability" or "expense". Used when settings are saved and
    again whenever an account is resolved."""
    if not account:
        return None
    row = frappe.db.get_value(
        "Account", account, ["company", "is_group", "root_type", "account_type", "disabled"], as_dict=True
    )
    if not row:
        return _("Account {0} does not exist").format(account)
    if row.company != company:
        return _("Account {0} belongs to {1}, not {2}").format(account, row.company, company)
    if cint(row.is_group):
        return _("Account {0} is a group account. Pick an account under it").format(account)
    if cint(row.get("disabled")):
        return _("Account {0} is disabled").format(account)
    if kind == "liability":
        if row.root_type != "Liability":
            return _("The cashback liability account must be a Liability account, and {0} is {1}").format(
                account, _(row.root_type or "")
            )
        if row.account_type in ("Receivable", "Payable"):
            # A party account needs a customer or supplier on every line, and
            # the cashback postings carry none.
            return _("Account {0} is a {1} account, which cashback cannot post to").format(
                account, _(row.account_type)
            )
    elif row.root_type != "Expense":
        return _("The cashback expense account must be an Expense account, and {0} is {1}").format(
            account, _(row.root_type or "")
        )
    return None


def _configured(company, field):
    from lumenpos.api.settings import company_setting

    return company_setting(company, field)


def liability_account(company):
    """The company's cashback liability account: the one chosen in settings
    when it is usable, else "Cashback" under Current Liabilities (created on
    first use)."""
    configured = _configured(company, LIABILITY_FIELD)
    if configured and not account_problem(configured, company, "liability"):
        return configured
    return _get_or_create_account(company)


def expense_account(company):
    """The company's cashback expense account: the one chosen in settings when
    it is usable, else "Cashback Expense" under Indirect Expenses (created on
    first use)."""
    configured = _configured(company, EXPENSE_FIELD)
    if configured and not account_problem(configured, company, "expense"):
        return configured
    return _get_or_create_expense_account(company)


def ensure_mode_of_payment(company):
    """Make sure the Cashback mode of payment exists and pays out of this
    company's liability account, creating either on first use. Mirrors store
    credit. Changing the account in settings re-points the mode of payment on
    the next sale."""
    from lumenpos.internal_accounts import fill_required_custom_fields

    account = liability_account(company)
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


def _default_account_name(company, account_name):
    abbr = frappe.get_cached_value("Company", company, "abbr")
    return "{0} - {1}".format(account_name, abbr)


def _get_or_create_account(company):
    account_name = _default_account_name(company, ACCOUNT_NAME)
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
            _("No liability account group found for {0}. Create a cashback liability account and choose it in LumenPOS Settings").format(company)
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


def _get_or_create_expense_account(company):
    account_name = _default_account_name(company, EXPENSE_ACCOUNT_NAME)
    if frappe.db.exists("Account", account_name):
        return account_name

    parent = frappe.db.get_value(
        "Account",
        {
            "company": company,
            "root_type": "Expense",
            "is_group": 1,
            "account_name": ["in", ["Indirect Expenses", "Expenses"]],
        },
        "name",
    ) or frappe.db.get_value(
        "Account",
        {"company": company, "root_type": "Expense", "is_group": 1},
        "name",
    )
    if not parent:
        frappe.throw(
            _("No expense account group found for {0}. Create a cashback expense account and choose it in LumenPOS Settings").format(company)
        )

    account = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": EXPENSE_ACCOUNT_NAME,
            "parent_account": parent,
            "company": company,
            "root_type": "Expense",
            "account_currency": frappe.get_cached_value("Company", company, "default_currency"),
        }
    ).insert(ignore_permissions=True)
    return account.name


# ---------------------------------------------------------------------------
# Booking to the accounts
# ---------------------------------------------------------------------------


def post_to_gl(include_today=False, commit_each=False, limit=5000):
    """Book unbooked Earn, Expire and Reverse rows as one summary Journal Entry
    per company, day and cost center.

    `include_today` False books only days that have ended (the nightly job).
    True books everything up to now (the manager's button). `commit_each`
    commits after every Journal Entry, for the scheduled job only. A group that
    fails (a frozen period, a mandatory accounting dimension) rolls back on its
    own, is logged, and leaves its rows for the next run."""
    filters = [
        ["entry_type", "in", list(POSTABLE)],
        ["journal_entry", "is", "not set"],
        ["amount", ">", 0],
    ]
    if not include_today:
        filters.append(["posting_datetime", "<", get_datetime(nowdate())])
    rows = frappe.get_all(
        LEDGER,
        filters=filters,
        fields=["name", "entry_type", "amount", "company", "pos_profile", "cost_center", "posting_datetime"],
        order_by="posting_datetime asc",
        limit=limit,
    )

    groups = {}
    for row in rows:
        if not row.company:
            continue
        cost_center = row.cost_center or _cost_center(row.company, row.pos_profile)
        key = (row.company, getdate(row.posting_datetime), cost_center)
        groups.setdefault(key, []).append(row)

    posted, failed = [], []
    for (company, day, cost_center), group in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1])):
        frappe.db.savepoint("lumenpos_cashback_gl")
        try:
            journal_entry = _book_group(company, day, cost_center, group)
            frappe.db.sql(
                "update `tabPOS Cashback Entry` set journal_entry = %(je)s where name in %(names)s",
                {"je": journal_entry, "names": tuple(r.name for r in group)},
            )
            posted.append(
                {"company": company, "date": str(day), "cost_center": cost_center,
                 "journal_entry": journal_entry, "rows": len(group)}
            )
            if commit_each:
                # Scheduled-job checkpoint: keep every day that booked cleanly
                # even if a later one fails. Not a request, so nothing commits
                # it for us.
                frappe.db.commit()  # nosemgrep
        except Exception as exc:
            frappe.db.rollback(save_point="lumenpos_cashback_gl")
            clear = getattr(frappe, "clear_last_message", None)
            if clear:
                clear()
            frappe.log_error(title="LumenPOS: cashback booking failed", message=frappe.get_traceback())
            failed.append(
                {"company": company, "date": str(day), "cost_center": cost_center,
                 "rows": len(group), "error": str(exc)}
            )
    return {"posted": posted, "failed": failed, "more": len(rows) >= limit}


def _book_group(company, day, cost_center, rows):
    earned = flt(sum(flt(r.amount) for r in rows if r.entry_type == "Earn"), 2)
    given_back = flt(sum(flt(r.amount) for r in rows if r.entry_type != "Earn"), 2)
    earned_count = sum(1 for r in rows if r.entry_type == "Earn")
    back_count = len(rows) - earned_count
    liability = liability_account(company)
    expense = expense_account(company)

    def line(account, debit=0.0, credit=0.0):
        row = {
            "account": account,
            "debit_in_account_currency": debit,
            "credit_in_account_currency": credit,
        }
        # Every line carries the outlet's cost center. Left empty, ERPNext fills
        # the company default into the liability lines (seen on v13, v14 and
        # v15), which would split one entry across two cost centers.
        if cost_center:
            row["cost_center"] = cost_center
        return row

    lines = []
    if earned > 0:
        lines += [line(expense, debit=earned), line(liability, credit=earned)]
    if given_back > 0:
        lines += [line(liability, debit=given_back), line(expense, credit=given_back)]

    remark = _("LumenPOS cashback for {0} ({1}): {2} earned on {3} sales, {4} expired or returned on {5} entries.").format(
        day, cost_center or company, earned, earned_count, given_back, back_count
    )
    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "voucher_type": "Journal Entry",
            "company": company,
            "posting_date": day,
            "user_remark": remark,
            "accounts": lines,
        }
    )
    journal_entry.flags.ignore_permissions = True
    journal_entry.insert()
    journal_entry.submit()
    return journal_entry.name


def accounting_status():
    """What the Cashback settings tab shows per company: the accounts in use
    (and why a chosen one is not), what is still waiting to be booked, what
    customers hold, and the liability account's balance to compare against."""
    companies = set(
        r[0] for r in frappe.db.sql("select distinct company from `tabPOS Cashback Entry` where company is not null")
    )
    doc = frappe.get_cached_doc("LumenPOS Settings")
    for row in doc.get("company_settings") or []:
        if row.get(LIABILITY_FIELD) or row.get(EXPENSE_FIELD):
            companies.add(row.company)
    out = []
    for company in sorted(c for c in companies if c):
        liability, liability_state, liability_problem = _account_in_use(company, "liability")
        expense, expense_state, expense_problem = _account_in_use(company, "expense")
        pending = {r[0]: {"count": cint(r[1]), "amount": flt(r[2], 2), "oldest": r[3]} for r in frappe.db.sql(
            """
            select entry_type, count(*), sum(amount), min(posting_datetime)
            from `tabPOS Cashback Entry`
            where company = %s and entry_type in ('Earn', 'Expire', 'Reverse')
              and (journal_entry is null or journal_entry = '') and amount > 0
            group by entry_type
            """,
            (company,),
        )}
        outstanding = frappe.db.sql(
            "select sum(remaining) from `tabPOS Cashback Entry` where company = %s and entry_type = 'Earn' and remaining > 0",
            (company,),
        )[0][0]
        gl_balance = None
        if frappe.db.exists("Account", liability):
            gl_balance = flt(frappe.db.sql(
                "select sum(credit) - sum(debit) from `tabGL Entry` where account = %s and is_cancelled = 0",
                (liability,),
            )[0][0], 2)
        oldest = [p["oldest"] for p in pending.values() if p["oldest"]]
        last = frappe.get_all(
            LEDGER,
            filters=[["company", "=", company], ["journal_entry", "is", "set"]],
            fields=["journal_entry", "posting_datetime"],
            order_by="posting_datetime desc",
            limit=1,
        )
        out.append({
            "company": company,
            "liability_account": liability,
            "liability_state": liability_state,
            "liability_problem": liability_problem,
            "expense_account": expense,
            "expense_state": expense_state,
            "expense_problem": expense_problem,
            "pending_count": sum(p["count"] for p in pending.values()),
            "pending_earned": flt(pending.get("Earn", {}).get("amount"), 2),
            "pending_given_back": flt(
                flt(pending.get("Expire", {}).get("amount")) + flt(pending.get("Reverse", {}).get("amount")), 2
            ),
            "pending_since": str(getdate(min(oldest))) if oldest else None,
            "outstanding": flt(outstanding, 2),
            "liability_balance": gl_balance,
            "last_journal_entry": last[0].journal_entry if last else None,
        })
    return out


def _account_in_use(company, kind):
    """The account cashback posts to for this company, a state code the screen
    translates, and the reason a chosen account is not usable. States: None
    (in use), "not_created_yet" (the default is made on first use) and
    "chosen_unusable" (the chosen account is refused, the default is used)."""
    field = LIABILITY_FIELD if kind == "liability" else EXPENSE_FIELD
    default = _default_account_name(company, ACCOUNT_NAME if kind == "liability" else EXPENSE_ACCOUNT_NAME)
    configured = _configured(company, field)
    if configured:
        problem = account_problem(configured, company, kind)
        if problem:
            return default, "chosen_unusable", problem
        return configured, None, None
    if frappe.db.exists("Account", default):
        return default, None, None
    return default, "not_created_yet", None


def cint_(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
