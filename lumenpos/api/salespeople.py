# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Salespeople at the till (0.57.0).

The till records who sold on the invoice's Sales Team at 100%, and ERPNext
works out the commission itself on every version (13 to 16, checked
2026-10-01): `incentives` is the commission at the Sales Person's commission
rate, on the items that grant commission, and a return carries the same row
negative. A person's sales are their share of each invoice's NET total in the
company currency (`allocated_percentage`), so the rows, the sales nobody was
named on included, add up to the outlet's net sales.

ERPNext's own Sales Person reports cannot show a POS outlet's salespeople: the
close merges a shift into a Sales Invoice without its Sales Team, and those
reports read Sales Order, Delivery Note and Sales Invoice only. So this module
reads the till's own documents: the POS Invoices, and the Sales Invoices of an
outlet that posts them directly (never a consolidated one, which holds the
same sales a second time).

LumenPOS Settings, "Salesperson at the till": Optional (the default, the
behaviour before 0.57.0), Required (a sale without one is refused on the
server), or Off (the till asks for nobody and records nobody).
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from lumenpos.api import permissions

MODES = ("Optional", "Required", "Off")


def mode():
    """Salesperson at the till: Optional, Required or Off."""
    try:
        value = frappe.db.get_single_value("LumenPOS Settings", "salesperson_mode")
    except Exception:
        value = None  # a site that pulled the code without migrating
    return value if value in MODES else "Optional"


def for_sale(payload, enforce=True):
    """The salesperson to record on a sale, or None.

    Off records nobody. Required refuses a sale without one, but not a sale the
    till queued without a connection: it was made under the till's rules of
    that moment and the money has changed hands, so refusing it at upload would
    only lose a real sale. `enforce` is False for a quote, which only prices.
    A name sent must be an enabled salesperson, not a group."""
    current = mode()
    if current == "Off":
        return None
    name = (payload.get("sales_person") or "").strip()
    if not name:
        if enforce and current == "Required" and not cint(payload.get("queued_offline")):
            frappe.throw(_("Pick the salesperson for this sale."), title=_("Salesperson required"))
        return None
    row = frappe.db.get_value("Sales Person", name, ["enabled", "is_group"], as_dict=True)
    if not row or not cint(row.enabled) or cint(row.is_group):
        frappe.throw(_("{0} is not an active salesperson.").format(name))
    return name


def _number_field():
    meta = frappe.get_meta("Sales Person")
    return next((f for f in ("sales_person_no", "custom_sales_person_no") if meta.has_field(f)), None)


def _rows(doctype, condition, params):
    """One row per invoice and salesperson. `doctype` and `condition` are fixed
    text from this module, never user input."""
    extra = " and inv.is_pos = 1 and inv.is_consolidated = 0" if doctype == "Sales Invoice" else ""
    return frappe.db.sql(  # nosemgrep
        f"""
        select inv.name, inv.is_return, inv.base_net_total, st.sales_person,
               st.allocated_percentage, st.incentives
        from `tab{doctype}` inv
        left join `tabSales Team` st on st.parent = inv.name and st.parenttype = %(doctype)s
        where inv.docstatus = 1{extra} and {condition}
        """,
        dict(params, doctype=doctype),
        as_dict=True,
    )


def _summarise(rows, with_commission):
    """Per salesperson: sales and returns (count and net amount), the net, the
    commission. Sales nobody was named on come last as one row ("")."""
    by = {}
    for r in rows:
        key = r.sales_person or ""
        entry = by.setdefault(
            key,
            {"sales_person": key, "sales": 0, "sales_amount": 0.0, "returns": 0, "returns_amount": 0.0,
             "commission": 0.0},
        )
        amount = flt(r.base_net_total) * (flt(r.allocated_percentage) / 100 if r.sales_person else 1)
        if cint(r.is_return):
            entry["returns"] += 1
            entry["returns_amount"] += amount
        else:
            entry["sales"] += 1
            entry["sales_amount"] += amount
        entry["commission"] += flt(r.incentives)

    names = [k for k in by if k]
    people = {}
    if names:
        fields = ["name", "sales_person_name", "commission_rate"]
        number = _number_field()
        if number:
            fields.append(f"{number} as sales_person_no")
        people = {p.name: p for p in frappe.get_all("Sales Person", filters={"name": ["in", names]}, fields=fields)}

    out = []
    for key, entry in by.items():
        person = people.get(key) or {}
        row = {
            "sales_person": key,
            "name": (person.get("sales_person_name") or key) if key else "",
            "number": (person.get("sales_person_no") or "") if key else "",
            "sales": entry["sales"],
            "sales_amount": flt(entry["sales_amount"], 2),
            "returns": entry["returns"],
            "returns_amount": flt(entry["returns_amount"], 2),
            "net": flt(entry["sales_amount"] + entry["returns_amount"], 2),
        }
        if with_commission:
            row["commission_rate"] = flt(person.get("commission_rate")) if key else 0
            row["commission"] = flt(entry["commission"], 2) if key else 0
        out.append(row)
    out.sort(key=lambda r: (not r["sales_person"], -r["net"], r["name"]))
    return out


def _totals(rows, with_commission):
    keys = ["sales", "sales_amount", "returns", "returns_amount", "net"] + (["commission"] if with_commission else [])
    return {k: flt(sum(flt(r.get(k)) for r in rows), 2) for k in keys}


def shift_rows(session_name, sale_doctype):
    """The shift report's lines (X and Z): per salesperson, for this shift only.
    Empty when the till does not ask for salespeople or nobody was named. The
    commission shows only to whoever may see the salesperson report."""
    if mode() == "Off" or not frappe.db.has_column(sale_doctype, "lumenpos_session"):
        return []
    rows = _rows(sale_doctype, "inv.lumenpos_session = %(session)s", {"session": session_name})
    data = _summarise(rows, permissions.can_see_sales_by_person())
    return data if any(r["sales_person"] for r in data) else []


def _outlets(pos_profile, company):
    """The outlets a report covers: the one asked for, or every outlet of one
    company this person may work at."""
    from lumenpos.api import session as session_api

    if pos_profile:
        permissions.assert_outlet(pos_profile)
        return [pos_profile], frappe.get_cached_value("POS Profile", pos_profile, "company")
    if not company:
        frappe.throw(_("Pick an outlet or a company."))
    allowed = permissions.allowed_companies()
    if allowed is not None and company not in allowed:
        frappe.throw(_("You're not allowed to see {0}.").format(company), frappe.PermissionError)
    mine = set(session_api._user_profiles() or [])
    outlets = [
        p for p in frappe.get_all("POS Profile", filters={"company": company, "disabled": 0}, pluck="name")
        if p in mine and permissions.can_use_outlet(p)
    ]
    return outlets, company


@frappe.whitelist()
def report(from_date: str | None = None, to_date: str | None = None, pos_profile: str | None = None, company: str | None = None):
    """Sales by salesperson over a period, for one outlet or every outlet of a
    company: count and net amount of sales and of returns, the net, and the
    commission ERPNext worked out. Amounts are before tax, in the company
    currency. For whoever may "See sales by salesperson" (managers always)."""
    if not permissions.can_see_sales_by_person():
        frappe.throw(_("You're not allowed to see sales by salesperson."), frappe.PermissionError)
    start = getdate(from_date or nowdate())
    end = getdate(to_date or from_date or nowdate())
    if end < start:
        start, end = end, start
    if (end - start).days > 370:
        frappe.throw(_("Pick a period of one year or less."))
    outlets, company = _outlets(pos_profile, company)
    rows = []
    if outlets:
        params = {"outlets": tuple(outlets), "start": start, "end": end}
        condition = "inv.pos_profile in %(outlets)s and inv.posting_date between %(start)s and %(end)s"
        rows = _rows("POS Invoice", condition, params) + _rows("Sales Invoice", condition, params)
    data = _summarise(rows, True)
    from lumenpos import currency

    return {
        "from_date": str(start),
        "to_date": str(end),
        "company": company,
        "currency": currency.company_currency(company),
        "outlets": outlets,
        "mode": mode(),
        "rows": data,
        "totals": _totals(data, True),
    }
