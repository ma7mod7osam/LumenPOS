# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Selling in other currencies (LumenPOS Settings, General, Other currencies).

ERPNext bills a customer in their Billing Currency (Customer, Currency and
Price List): a POS Invoice follows it, on every validate. Until 0.51.0 LumenPOS
ignored that and posted the shelf numbers as foreign money. This module makes
such a sale right instead, the way ERPNext expects it, and keeps the rules
ERPNext's own code imposes (read in its source and proved on v13, v14 and v15
before any of this was written):

- The sale's currency is the customer's Billing Currency, else the outlet's.
  A walk-in who wants to pay in dollars is sold to that currency's walk-in
  customer ("Walk-in USD"), so ONE customer never mixes currencies in a shift:
  ERPNext consolidates a shift per customer and copies the last invoice's
  currency and rate onto the merged invoice.
- The exchange rate is fixed for the shift the first time the shift sells in
  that currency (POS Session Rate), for the same reason.
- LumenPOS keeps pricing in the outlet's currency, exactly as before: price
  books, bundles, offers and basket discounts are untouched. Only the invoice
  rows, the service charge and the display are converted, by one factor.
- The receivable is in the sale's currency (a provisioned "Debtors USD" when
  the customer has none), so the consolidated Sales Invoice passes ERPNext's
  party account check.
- A tender is accepted when its account is in the company currency (dirham
  cash on a dollar sale) or in the sale's currency (Cash USD). ERPNext refuses
  a dollar account on a dirham invoice at the shift close, so the till never
  offers one.
- Change always comes back in local money from the outlet's change account,
  as in ERPNext's own POS: the close merges a customer's invoices and books
  all their change from ONE account (the last invoice's), so a drawer in
  another currency takes money in and never pays change out.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate

SETTINGS = "LumenPOS Settings"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def enabled():
    try:
        return bool(cint(frappe.db.get_single_value(SETTINGS, "enable_multi_currency")))
    except Exception:
        return False  # a site that has not migrated yet


def currency_rows():
    """{currency: row} of the currencies the till sells in."""
    try:
        doc = frappe.get_cached_doc(SETTINGS)
    except Exception:
        return {}
    return {r.currency: r for r in (doc.get("sale_currencies") or []) if r.currency}


def company_currency(company):
    return frappe.get_cached_value("Company", company, "default_currency")


def list_currency(price_list):
    return frappe.get_cached_value("Price List", price_list, "currency") if price_list else None


# ---------------------------------------------------------------------------
# Rates
# ---------------------------------------------------------------------------

def current_rate(from_currency, to_currency, date=None):
    """ERPNext's own selling rate (Currency Exchange, then its fallbacks)."""
    if not from_currency or from_currency == to_currency:
        return 1.0
    from erpnext.setup.utils import get_exchange_rate

    return flt(get_exchange_rate(from_currency, to_currency, date or nowdate(), "for_selling"), 9)


def shift_rate(session_name, currency, company, pin=False):
    """The rate this shift sells `currency` at, to the company currency. Fixed
    the first time the shift needs it (pin=True, on a sale) and read back ever
    after, so every invoice of the shift, and so the one ERPNext merges per
    customer at the close, carries the same rate."""
    ccy = company_currency(company)
    if not currency or currency == ccy:
        return 1.0
    if session_name:
        fixed = frappe.db.get_value(
            "POS Session Rate",
            {"parent": session_name, "parenttype": "POS Register Session", "currency": currency},
            "exchange_rate",
        )
        if flt(fixed):
            return flt(fixed)
    rate = current_rate(currency, ccy)
    if not rate:
        frappe.throw(
            _("There is no exchange rate from {0} to {1}. Set it in LumenPOS Settings, General, Other currencies.").format(
                currency, ccy
            ),
            title=_("Exchange rate"),
        )
    if pin and session_name:
        idx = frappe.db.count("POS Session Rate", {"parent": session_name, "parenttype": "POS Register Session"})
        frappe.get_doc(
            {
                "doctype": "POS Session Rate",
                "parent": session_name,
                "parenttype": "POS Register Session",
                "parentfield": "currency_rates",
                "idx": idx + 1,
                "currency": currency,
                "exchange_rate": rate,
                "pinned_at": now_datetime(),
            }
        ).db_insert()
    return rate


# ---------------------------------------------------------------------------
# What a sale is in
# ---------------------------------------------------------------------------

def own_price_list(customer, currency):
    """The customer's own selling price list, or their group's, when it is in
    the sale's currency. ERPNext honours it, and so does the till."""
    if not customer:
        return None
    price_list, group = frappe.get_cached_value("Customer", customer, ["default_price_list", "customer_group"])
    group_list = frappe.get_cached_value("Customer Group", group, "default_price_list") if group else None
    for candidate in (price_list, group_list):
        if (
            candidate
            and list_currency(candidate) == currency
            and cint(frappe.get_cached_value("Price List", candidate, "selling"))
        ):
            return candidate
    return None


def own_list_prices(ctx, item_codes, uom_map=None):
    """{item_code: price in the OUTLET's terms} for the items the customer's own
    price list (in the sale's currency) prices, so offers, bundles and
    discounts keep working on one currency. An item that list does not price
    is left out: it keeps the outlet's price and is converted like any other.
    (Until 0.51.1 such an item fell back to its outlet NUMBER read as the
    sale's currency: a US$5 item sold for ZWG 5 instead of ZWG 175.)"""
    if not ctx or not ctx.get("own_list") or not item_codes:
        return {}
    from lumenpos.price_books import get_price_map

    own = get_price_map(item_codes, ctx.own_list, uom_map)
    return {code: flt(rate) / ctx.factor for code, rate in own.items() if flt(rate) > 0}


def sale_context(profile, customer, price_list, session_name=None, pin=False):
    """What a sale to `customer` at this outlet is in.

    `price_list` is the list LumenPOS prices from (the outlet's, a delivery
    app's). Returns a dict: currency, company_currency, outlet_currency, rate
    (sale currency to company currency), list_rate (outlet list currency to
    company currency), factor (outlet price x factor = sale price), foreign,
    own_list. Refuses a customer the till cannot sell to, with a plain reason."""
    ccy = company_currency(profile.company)
    outlet = list_currency(price_list) or profile.get("currency") or ccy
    billed = frappe.get_cached_value("Customer", customer, "default_currency") if customer else None
    ctx = frappe._dict(
        company_currency=ccy,
        outlet_currency=outlet,
        currency=outlet,
        rate=None,
        list_rate=None,
        factor=1.0,
        foreign=False,
        price_list=price_list,
        own_list=None,
    )
    if not billed or billed == outlet:
        return ctx
    name = frappe.get_cached_value("Customer", customer, "customer_name") or customer
    if not enabled():
        frappe.throw(
            _(
                "{0} is billed in {1}, but this till sells in {2}. Switch on Other currencies in "
                "LumenPOS Settings, choose another customer, or clear the customer's Billing Currency in "
                "ERPNext (Customer, Currency and Price List)."
            ).format(name, billed, outlet),
            title=_("Customer currency"),
        )
    if billed not in currency_rows():
        frappe.throw(
            _(
                "{0} is billed in {1}, which this till does not sell in. Add {1} in LumenPOS Settings, "
                "General, Other currencies, or change the customer's Billing Currency."
            ).format(name, billed),
            title=_("Customer currency"),
        )
    rate = shift_rate(session_name, billed, profile.company, pin)
    list_rate = shift_rate(session_name, outlet, profile.company, pin)
    # A plain dict: v13's frappe._dict.update takes no keyword arguments.
    ctx.update(
        {
            "currency": billed,
            "rate": rate,
            "list_rate": list_rate,
            "factor": list_rate / rate,
            "foreign": True,
            "own_list": own_price_list(customer, billed),
        }
    )
    return ctx


def public(ctx):
    """The part of a sale context the till needs."""
    return {
        "currency": ctx.currency,
        "outlet_currency": ctx.outlet_currency,
        "company_currency": ctx.company_currency,
        "rate": flt(ctx.rate or 1, 9),
        "factor": flt(ctx.factor, 12),
        "foreign": 1 if ctx.foreign else 0,
    }


def apply_to_invoice(invoice, ctx):
    """After set_missing_values: the header of a sale in another currency.
    LumenPOS sets every field ERPNext would otherwise fetch, so nothing is
    re-fetched at a different rate later in the shift."""
    if not ctx.foreign:
        return
    invoice.currency = ctx.currency
    invoice.conversion_rate = ctx.rate
    if ctx.own_list:
        invoice.selling_price_list = ctx.own_list
        invoice.price_list_currency = ctx.currency
        invoice.plc_conversion_rate = ctx.rate
    else:
        invoice.selling_price_list = ctx.price_list
        invoice.price_list_currency = ctx.outlet_currency
        invoice.plc_conversion_rate = ctx.list_rate
    receivable = invoice.get("debit_to")
    if not receivable or frappe.get_cached_value("Account", receivable, "account_currency") != ctx.currency:
        invoice.debit_to = receivable_account(invoice.company, ctx.currency)


def assert_local(ctx, what):
    """Features whose ledgers hold one currency (holds, gift cards, store
    credit, cashback, points, exchanges) stay in the outlet's currency."""
    if ctx.foreign:
        frappe.throw(
            _("{0} are in {1} only, and this customer buys in {2}.").format(what, ctx.outlet_currency, ctx.currency),
            title=_("Customer currency"),
        )


# ---------------------------------------------------------------------------
# Tenders
# ---------------------------------------------------------------------------

def mode_currency(mode, company):
    """A payment method's currency is its account's for this company."""
    account = frappe.db.get_value(
        "Mode of Payment Account", {"parent": mode, "company": company}, "default_account"
    )
    return (frappe.get_cached_value("Account", account, "account_currency") if account else None) or company_currency(
        company
    )


def check_tenders(ctx, company, payments):
    """Every tender must sit in an account ERPNext accepts for this sale at the
    close: the company currency, or the sale's own. A dollar account on a
    dirham sale fails there, hours later, so it is refused here."""
    for row in payments or []:
        if not flt(row.get("amount")):
            continue
        currency = mode_currency(row.get("mode_of_payment"), company)
        if currency in (ctx.company_currency, ctx.currency):
            continue
        frappe.throw(
            _("{0} takes {1} only, and this sale is in {2}.").format(
                row.get("mode_of_payment"), currency, ctx.currency
            ),
            title=_("Payment"),
        )


def amount_in_account_currency(row, invoice, company):
    """What a tender row put into its account, in that account's currency:
    the row amount when the account is in the invoice's currency (Cash USD on
    a dollar sale, or any row of a local sale), its base amount when the
    account is in the company currency (dirham cash on a dollar sale). This is
    what the drawer really holds."""
    if invoice.currency == company_currency(company):
        return flt(row.amount)
    if mode_currency(row.mode_of_payment, company) == invoice.currency:
        return flt(row.amount)
    return flt(row.get("base_amount")) or flt(row.amount) * flt(invoice.conversion_rate)


# ---------------------------------------------------------------------------
# Setting a currency up
# ---------------------------------------------------------------------------

def _companies():
    return sorted(set(frappe.get_all("POS Profile", filters={"disabled": 0}, pluck="company")))


def _account(company, name, account_type, currency, parent):
    from lumenpos.internal_accounts import fill_required_custom_fields

    abbr = frappe.get_cached_value("Company", company, "abbr")
    full = f"{name} - {abbr}"
    if frappe.db.exists("Account", full):
        return full
    if not parent:
        frappe.throw(
            _("No account group found for {0} in {1}. Create the account '{0}' in {2} by hand.").format(
                name, company, currency
            )
        )
    doc = frappe.get_doc(
        {
            "doctype": "Account",
            "account_name": name,
            "parent_account": parent,
            "company": company,
            "account_type": account_type,
            "account_currency": currency,
            "is_group": 0,
        }
    )
    fill_required_custom_fields(doc, name)
    return doc.insert(ignore_permissions=True).name


def receivable_account(company, currency):
    existing = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Receivable", "account_currency": currency, "is_group": 0, "disabled": 0},
        "name",
    )
    if existing:
        return existing
    base = frappe.get_cached_value("Company", company, "default_receivable_account")
    parent = frappe.db.get_value("Account", base, "parent_account") if base else None
    return _account(company, f"Debtors {currency}", "Receivable", currency, parent)


def cash_account(company, currency):
    existing = frappe.db.get_value(
        "Account",
        {"company": company, "account_type": "Cash", "account_currency": currency, "is_group": 0, "disabled": 0},
        "name",
    )
    if existing:
        return existing
    base = frappe.get_cached_value("Company", company, "default_cash_account") or frappe.db.get_value(
        "Mode of Payment Account", {"parent": "Cash", "company": company}, "default_account"
    )
    parent = frappe.db.get_value("Account", base, "parent_account") if base else None
    return _account(company, f"Cash {currency}", "Cash", currency, parent)


def _ensure_cash_mode(currency, company, account):
    from lumenpos.internal_accounts import fill_required_custom_fields

    name = f"Cash {currency}"
    if not frappe.db.exists("Mode of Payment", name):
        doc = frappe.get_doc(
            {
                "doctype": "Mode of Payment",
                "mode_of_payment": name,
                "type": "Cash",
                "enabled": 1,
                "accounts": [{"company": company, "default_account": account}],
            }
        )
        fill_required_custom_fields(doc, name)
        doc.insert(ignore_permissions=True)
        return name
    doc = frappe.get_doc("Mode of Payment", name)
    row = next((r for r in doc.accounts if r.company == company), None)
    if row is None:
        doc.append("accounts", {"company": company, "default_account": account})
    elif not row.default_account:
        row.default_account = account
    else:
        return name
    fill_required_custom_fields(doc, name)
    doc.save(ignore_permissions=True)
    return name


def _ensure_walk_in(currency, receivables):
    """The customer a walk-in paying in `currency` is billed to: that billing
    currency, and a receivable in it for every company with a till."""
    from lumenpos.internal_accounts import fill_required_custom_fields

    label = f"Walk-in {currency}"
    name = frappe.db.get_value("Customer", {"customer_name": label})
    if name:
        doc = frappe.get_doc("Customer", name)
    else:
        default_customer = frappe.db.get_value(
            "POS Profile", {"disabled": 0, "customer": ["is", "set"]}, "customer"
        )
        group, territory = (
            frappe.get_cached_value("Customer", default_customer, ["customer_group", "territory"])
            if default_customer
            else (None, None)
        )
        # A group v15 accepts: it refuses a group node ("Cannot select a Group
        # type Customer Group"), and an outlet's default customer often sits in
        # "All Customer Groups", so the currency was never set up there.
        from lumenpos.api.catalog import _customer_group

        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": label,
                "customer_type": "Individual",
                "customer_group": _customer_group(
                    "Individual", group, frappe.db.get_single_value("Selling Settings", "customer_group")
                ),
                "territory": territory or frappe.db.get_single_value("Selling Settings", "territory"),
            }
        )
    doc.default_currency = currency
    have = {r.company for r in (doc.get("accounts") or [])}
    for company, account in receivables.items():
        if company not in have:
            doc.append("accounts", {"company": company, "account": account})
    fill_required_custom_fields(doc, label)
    doc.flags.ignore_permissions = True
    if doc.is_new():
        doc.insert()
    else:
        doc.save()
    return doc.name


def _add_to_profiles(mode, company):
    for name in frappe.get_all("POS Profile", filters={"company": company, "disabled": 0}, pluck="name"):
        profile = frappe.get_doc("POS Profile", name)
        if any(r.mode_of_payment == mode for r in profile.payments):
            continue
        profile.append("payments", {"mode_of_payment": mode})
        profile.flags.ignore_permissions = True
        profile.save()


def setup_currency(currency):
    """Everything a sale in `currency` needs, for every company with a till:
    a receivable and a cash account in that currency, "Cash <currency>" on
    every outlet, and the walk-in customer. Idempotent, ERPNext records only."""
    receivables = {}
    mode = None
    for company in _companies():
        if currency == company_currency(company):
            continue
        receivables[company] = receivable_account(company, currency)
        mode = _ensure_cash_mode(currency, company, cash_account(company, currency))
        _add_to_profiles(mode, company)
    walk_in = _ensure_walk_in(currency, receivables) if receivables else None
    return {"walk_in_customer": walk_in, "cash_mode": mode}


SETUP_ERRORS = "lumenpos_currency_setup_errors"


def setup_errors():
    """{currency: reason} of the currencies whose last setup failed."""
    try:
        found = frappe.cache().hgetall(SETUP_ERRORS) or {}
    except Exception:
        return {}
    # Redis hands the field names back as bytes.
    return {(k.decode() if isinstance(k, bytes) else k): v for k, v in found.items()}


def ensure_setup():
    """After a migrate, and after saving Settings: set up every currency row
    that is not set up yet. Never blocks a migrate. A currency is set up whole
    or not at all (no drawer without its walk-in customer), and why it failed
    is kept for the Settings screen, which used to say "Set up when you save"
    forever. Returns {currency: reason} for the ones that failed."""
    if not enabled():
        return {}
    doc = frappe.get_single(SETTINGS)
    changed = False
    failed = {}
    for row in doc.get("sale_currencies") or []:
        if not row.currency or (row.walk_in_customer and row.cash_mode):
            continue
        frappe.db.savepoint("lumenpos_currency_setup")
        try:
            made = setup_currency(row.currency)
        except Exception as exc:
            frappe.db.rollback(save_point="lumenpos_currency_setup")
            failed[row.currency] = frappe.utils.strip_html(str(exc)).strip() or type(exc).__name__
            frappe.log_error(
                title=f"LumenPOS: setting up {row.currency} failed", message=frappe.get_traceback()
            )
            continue
        row.walk_in_customer = row.walk_in_customer or made["walk_in_customer"]
        row.cash_mode = row.cash_mode or made["cash_mode"]
        changed = True
    try:
        cache = frappe.cache()
        cache.delete_key(SETUP_ERRORS)
        for code, reason in failed.items():
            cache.hset(SETUP_ERRORS, code, reason)
    except Exception:
        pass
    if changed:
        doc.flags.ignore_permissions = True
        doc.save()
    return failed


# ---------------------------------------------------------------------------
# The till's side
# ---------------------------------------------------------------------------

def client_config(profile, session_name=None):
    """What the till needs at start: the currencies, their walk-in customer and
    cash drawer, and the rate the shift sells at (fixed or, before the first
    sale, today's)."""
    ccy = company_currency(profile.company)
    outlet = list_currency(profile.selling_price_list) or profile.get("currency") or ccy
    out = {
        "enabled": 1 if enabled() else 0,
        "company_currency": ccy,
        "outlet_currency": outlet,
        "outlet_rate": 1.0,
        "currencies": [],
    }
    if not out["enabled"]:
        return out
    try:
        out["outlet_rate"] = shift_rate(session_name, outlet, profile.company)
    except Exception:
        out["outlet_rate"] = 0
    for currency, row in currency_rows().items():
        if currency == outlet:
            continue
        try:
            rate = shift_rate(session_name, currency, profile.company)
        except Exception:
            rate = 0
        walk_in = (
            frappe.db.get_value(
                "Customer", row.walk_in_customer, ["customer_name", "customer_group"], as_dict=True
            )
            if row.walk_in_customer
            else None
        ) or {}
        out["currencies"].append(
            {
                "currency": currency,
                "symbol": frappe.get_cached_value("Currency", currency, "symbol") or currency,
                "walk_in_customer": row.walk_in_customer,
                "walk_in_name": walk_in.get("customer_name") or row.walk_in_customer,
                "walk_in_group": walk_in.get("customer_group"),
                "cash_mode": row.cash_mode,
                "show_equivalent": 1 if cint(row.show_equivalent) else 0,
                "rate": rate,
            }
        )
    return out


@frappe.whitelist()
def sale_info(pos_profile, customer=None):
    """What a sale to this customer would be in, for the till to show before
    anything is rung up. Read only: it never fixes a rate."""
    from lumenpos.api.sales import _require_sell
    from lumenpos.api.session import get_open_session
    from lumenpos.price_books import resolve_price_list

    _require_sell()
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    customer = customer or profile.customer
    group = frappe.get_cached_value("Customer", customer, "customer_group") if customer else None
    session = get_open_session(pos_profile)
    ctx = sale_context(
        profile, customer, resolve_price_list(profile, group), (session or {}).get("name")
    )
    return public(ctx)


def _require_settings():
    if not frappe.has_permission(SETTINGS, "write"):
        frappe.throw(_("Only someone who manages LumenPOS Settings can change exchange rates."), frappe.PermissionError)


@frappe.whitelist()
def get_rates():
    """Today's selling rate of every currency the till sells in, to each
    company currency with a till."""
    _require_settings()
    return rates()


def rates():
    """get_rates for the Settings screen: anyone who may see Settings sees the
    rates (only changing one needs the right to manage them; they used to
    vanish behind "Save the currencies first"). ERPNext's lookup can pop up
    "Unable to find exchange rate" for a currency it cannot fetch, which is
    exactly the one to set here, so its message is muted."""
    out = []
    muted = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        for currency in currency_rows():
            for ccy in sorted({company_currency(c) for c in _companies()}):
                if currency == ccy:
                    continue
                out.append({"currency": currency, "company_currency": ccy, "rate": current_rate(currency, ccy)})
    finally:
        frappe.flags.mute_messages = muted
    return out


@frappe.whitelist()
def set_rate(currency, company_currency, rate):
    """A new selling rate from today, as ERPNext keeps them: a Currency
    Exchange record. A shift already selling in that currency keeps the rate
    it started with (see shift_rate)."""
    _require_settings()
    rate = flt(rate, 9)
    if rate <= 0:
        frappe.throw(_("The rate must be more than 0."))
    filters = {"from_currency": currency, "to_currency": company_currency, "date": nowdate(), "for_selling": 1}
    name = frappe.db.get_value("Currency Exchange", filters, "name")
    if name:
        frappe.db.set_value("Currency Exchange", name, "exchange_rate", rate)
    else:
        frappe.get_doc(
            {
                "doctype": "Currency Exchange",
                "from_currency": currency,
                "to_currency": company_currency,
                "date": nowdate(),
                "exchange_rate": rate,
                "for_selling": 1,
                "for_buying": 0,
            }
        ).insert(ignore_permissions=True)
    return {"currency": currency, "company_currency": company_currency, "rate": rate}
