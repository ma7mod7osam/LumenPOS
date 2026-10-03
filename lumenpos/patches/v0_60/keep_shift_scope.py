# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""v0.60.1: "Per cashier" is the default shift scope, and a site that already
has shifts keeps the way it worked.

Until 0.60.1 a site that never saved "A shift belongs to" ran "Per outlet"
(the old default, read through a fallback in the code). Switching such a shop
to "Per cashier" with an update would stop every cashier but the one who
opened the shift from selling on it, and on ERPNext 16, where an outlet sells
on one open shift at a time, keep the others from opening their own. So where
nothing is stored and the site has shifts, "Per outlet" is written down once.
A new site (no shifts yet) gets the new default, and a stored choice is never
touched."""

import frappe

DOCTYPE = "LumenPOS Settings"


def _stored():
    row = frappe.db.sql(
        "select value from tabSingles where doctype=%s and field='shift_scope'", DOCTYPE
    )
    return row[0][0] if row else None


def _has_shifts():
    if not frappe.db.table_exists("POS Register Session"):
        return False
    return bool(frappe.db.sql("select name from `tabPOS Register Session` limit 1"))


def execute():
    if _stored():
        return
    if not _has_shifts():
        return
    frappe.db.sql(
        "delete from tabSingles where doctype=%s and field='shift_scope'", DOCTYPE
    )
    frappe.db.sql(
        "insert into tabSingles (doctype, field, value) values (%s, 'shift_scope', 'Per outlet')",
        DOCTYPE,
    )
    frappe.clear_cache(doctype=DOCTYPE)
