# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Where a rule applies: promotions, cashback rules, bundles and price books.

A rule applies to the whole group (no company, no outlets), to one company
(every outlet of it), or to outlets chosen by name. Chosen outlets win; a
company with outlets chosen must own them. One rule for all four, so a
promotion and the bundle beside it never disagree about an outlet."""

import frappe
from frappe import _


def applies_to(company, outlets, pos_profile):
    """Whether a rule scoped to (company, outlets) applies at this outlet."""
    if not pos_profile:
        return True
    if outlets:
        return pos_profile in outlets
    if company:
        return frappe.get_cached_value("POS Profile", pos_profile, "company") == company
    return True


def validate(doc):
    """Chosen outlets must belong to the rule's company, when it has one."""
    company = doc.get("company")
    if not company:
        return
    for row in doc.get("pos_profiles") or []:
        owner = frappe.get_cached_value("POS Profile", row.pos_profile, "company")
        if owner != company:
            frappe.throw(
                _("Outlet {0} belongs to {1}, not {2}. Choose outlets of {2}, or clear the company.").format(
                    row.pos_profile, owner, company
                ),
                title=_("Where it applies"),
            )
