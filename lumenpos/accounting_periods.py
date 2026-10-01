# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""ERPNext's Accounting Periods, as a shop meets them at the till (0.58.1).

An Accounting Period LOCKS the documents ticked Closed in it, on the dates it
covers, and ERPNext's own form ticks every one of them (Sales Invoice, Journal
Entry, Stock Entry...). A POS Invoice is never among them, so a shop that made
a period ahead of time "to open" a month sells all day and then cannot close
the shift: the close posts the shift's sales as a Sales Invoice, which ERPNext
refuses ("You cannot create a Sales Invoice within the closed Accounting Period
...", the Zimbabwe shop on 2026-10-01). ERPNext 15 and 16 refuse to save a
period that ends after today, so one made ahead cannot even be edited until it
ends: deleting it is the way out.

lock() answers as ERPNext decides (validate_accounting_period_on_doc_save from
14, the ledger check on 13): the company, a document type ticked Closed, the
date inside the period, and on 16 a period not disabled and a role it exempts.
hint() finds the period a failed close names: ERPNext names it in its refusal
on every version and in any language (a name is never translated), so the name
in the error is the proof, not a guess from dates. LumenPOS Settings, General,
"Warn about locked accounting periods" (ships ON) shows both in the till, and
the system check lists such periods whatever the switch says.
"""

from __future__ import annotations

import html
import re

import frappe
from frappe.utils import getdate, nowdate

# What LumenPOS posts itself: a shift's sales at the close (and every sale of a
# Sales Invoice outlet), and Journal Entries for cashback and group balances.
POSTED = ("Sales Invoice", "Journal Entry")

_BREAK = re.compile(r"<br\s*/?>", re.IGNORECASE)
# A tag starts with its name right after "<", so "x < 5 and y > 3" stays.
_TAG = re.compile(r"</?[a-zA-Z][a-zA-Z0-9-]*(\s[^<>]*)?/?>")


def plain(text, length=None):
    """An error as a person reads it. ERPNext's messages carry HTML (the name of
    the period in <strong>), which the till shows as text, tags and all."""
    if text is None:
        return None
    out = html.unescape(_TAG.sub("", _BREAK.sub("\n", str(text)))).strip()
    return out[:length] if length else out


def switch():
    """LumenPOS Settings.warn_locked_periods: on unless the shop switched it off."""
    from lumenpos.api.settings import offline_switch

    return offline_switch("warn_locked_periods")


def periods(companies, doctypes=POSTED, on=None, until=None):
    """The Accounting Periods of `companies` that lock any of `doctypes`, each
    with the types it locks: those covering the date `on`, or, with `until`,
    every one still running or still to come on that date. A disabled period
    (ERPNext 16) locks nothing."""
    if isinstance(companies, str):
        companies = [companies]
    companies = [c for c in companies or [] if c]
    if not companies or not frappe.db.table_exists("Accounting Period"):
        return []
    rows = frappe.db.sql(
        """select ap.*, cd.document_type as locked_type
        from `tabAccounting Period` ap
        join `tabClosed Document` cd on cd.parent = ap.name
        where ap.company in %(companies)s and cd.closed = 1 and cd.document_type in %(doctypes)s
        order by ap.start_date, ap.name""",
        {"companies": tuple(companies), "doctypes": tuple(doctypes)},
        as_dict=True,
    )
    day = getdate(on) if on else None
    after = getdate(until) if until else None
    out = {}
    for r in rows:
        if r.get("disabled") or not r.start_date or not r.end_date:
            continue
        start, end = getdate(r.start_date), getdate(r.end_date)
        if day and not start <= day <= end:
            continue
        if after and end < after:
            continue
        p = out.setdefault(
            r.name,
            frappe._dict(name=r.name, company=r.company, start_date=start, end_date=end,
                         exempted_role=r.get("exempted_role") or None, doctypes=[]),
        )
        if r.locked_type not in p.doctypes:
            p.doctypes.append(r.locked_type)
    return list(out.values())


def public(p):
    """What the till shows: the period, its dates, and whether it has ended (one
    that has not cannot be edited on ERPNext 15 and 16, only deleted)."""
    end = getdate(p.end_date) if p.get("end_date") else None
    return {
        "period": p.name,
        "from": str(p.start_date or ""),
        "to": str(p.end_date or ""),
        "ended": 1 if end and end < getdate(nowdate()) else 0,
    }


def lock(company, on=None, doctype="Sales Invoice", user=None):
    """The period that refuses a `doctype` of `company` dated `on` (today) to
    `user` (the session's), as ERPNext decides it, or None."""
    roles = None
    for p in periods(company, (doctype,), on=on or nowdate()):
        if p.exempted_role:
            if roles is None:
                roles = set(frappe.get_roles(user))
            if p.exempted_role in roles:
                continue
        return public(p)
    return None


def hint(company, error):
    """The Accounting Period a failed close names, or None."""
    text = plain(error)
    if not company or not text or not frappe.db.table_exists("Accounting Period"):
        return None
    for p in frappe.get_all("Accounting Period", filters={"company": company},
                            fields=["name", "start_date", "end_date"], order_by="start_date desc"):
        if p.name and p.name in text:
            return public(p)
    return None


def till_lock(company):
    """For the till: what locks a shift's close today at this company, when the
    shop has the warning on."""
    return lock(company) if switch() else None


def till_hint(company, error):
    """For the till: the period that stopped a close, when the shop has the
    warning on."""
    return hint(company, error) if error and switch() else None
