# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""v0.61.0: cash in and cash out are two permissions (lumenpos.cash_out).

Each rule a shop wrote on the old "Cash in / out" becomes one rule on "Cash in"
and one on "Cash out", for the same role or person, so nobody gains or loses
anything by the update. Until this runs (an update that did not migrate),
permissions._cash_allowed still reads the old rows."""

import frappe

OLD = "Cash in / out"


def execute():
    if not frappe.db.table_exists("POS Capability Rule"):
        return
    rows = frappe.db.sql(
        "select name, parent, parenttype, parentfield, role, `user` from `tabPOS Capability Rule` where capability=%s",
        OLD,
        as_dict=True,
    )
    for row in rows:
        frappe.db.set_value("POS Capability Rule", row.name, "capability", "Cash in", update_modified=False)
        top = frappe.db.sql(
            "select coalesce(max(idx), 0) from `tabPOS Capability Rule` where parent=%s", row.parent
        )[0][0]
        frappe.get_doc(
            {
                "doctype": "POS Capability Rule",
                "parent": row.parent,
                "parenttype": row.parenttype,
                "parentfield": row.parentfield,
                "idx": int(top) + 1,
                "capability": "Cash out",
                "role": row.role,
                "user": row.user,
            }
        ).db_insert()
    if rows:
        frappe.clear_cache(doctype="LumenPOS Settings")
