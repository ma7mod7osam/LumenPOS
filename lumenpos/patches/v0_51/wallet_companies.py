# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""v0.51.0: every customer balance entry names its company.

Balances can now be shared by a group of companies or kept separate per
company (lumenpos.inter_company), which reads the company of each store credit
entry, cashback entry and gift card. Older entries could leave it empty: fill
it from the sale the entry points at, or, on a site with one company, with
that company. Anything still unknown is left alone and counts as the spending
company's own."""

import frappe


def _company_of(doctype, name):
    if not doctype or not name:
        return None
    try:
        return frappe.db.get_value(doctype, name, "company")
    except Exception:
        return None


def execute():
    companies = frappe.get_all("Company", pluck="name")
    only = companies[0] if len(companies) == 1 else None
    for ledger in ("POS Store Credit Entry", "POS Cashback Entry"):
        if not frappe.db.exists("DocType", ledger):
            continue
        for row in frappe.get_all(
            ledger,
            filters={"company": ["in", ["", None]]},
            fields=["name", "reference_doctype", "reference_invoice"],
        ):
            company = _company_of(row.reference_doctype, row.reference_invoice) or only
            if company:
                frappe.db.set_value(ledger, row.name, "company", company, update_modified=False)
    if frappe.db.exists("DocType", "POS Gift Card"):
        for card in frappe.get_all(
            "POS Gift Card", filters={"company": ["in", ["", None]]}, fields=["name", "issued_invoice"]
        ):
            sold_on = card.issued_invoice or (
                frappe.db.get_value(
                    "POS Gift Card Entry", {"card": card.name, "invoice": ["is", "set"]}, "invoice", order_by="creation asc"
                )
                if frappe.db.exists("DocType", "POS Gift Card Entry")
                else None
            )
            company = None
            for doctype in ("POS Invoice", "Sales Invoice"):
                company = company or _company_of(doctype, sold_on)
            company = company or only
            if company:
                frappe.db.set_value("POS Gift Card", card.name, "company", company, update_modified=False)
