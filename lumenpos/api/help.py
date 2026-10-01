# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Help in the till (0.58.0): what each person has already seen.

The help itself lives in the till: the "?" button with each screen's help, the
short tours over the real buttons, the welcome card and "What's new" after an
update. The server keeps, per user, the last version whose news they saw and
the tours they finished, in ERPNext's own user defaults, so a cashier who took
the tour on one till is not offered it again on another.

LumenPOS Settings, General, "Help for staff": three switches that ship ON
(install.HELP_SWITCHES, written once): the help in the till, the tour offered
to someone who has not seen it, and "What's new" after an update."""

from __future__ import annotations

import re

import frappe
from frappe import _

SWITCHES = ("help_in_till", "help_offer_tour", "help_whats_new")
SEEN_KEY = "lumenpos_help_seen_version"
TOURS_KEY = "lumenpos_help_tours_done"
# A release ("0.58.0") or a test bench's build of one ("0.58.0-r42").
VERSION_RE = re.compile(r"\d{1,4}(\.\d{1,4}){1,3}(-r\d{1,5})?")
TOUR_RE = re.compile(r"[a-z0-9-]{1,40}")
MAX_TOURS = 40


def switch(field):
    """On unless the shop switched it off. A site updated without its migrate
    has no such field yet: on, as it ships."""
    from lumenpos.api.settings import offline_switch

    return offline_switch(field)


def _require_till():
    """The same door as the till itself (session.get_bootstrap)."""
    if frappe.session.user == "Guest" or not frappe.has_permission("POS Invoice", "read"):
        frappe.throw(
            _("You do not have access to the POS. Ask an administrator to grant you the LumenPOS Cashier role (or POS Invoice access)."),
            frappe.PermissionError,
        )


def _tours(user):
    raw = frappe.defaults.get_user_default(TOURS_KEY, user) or ""
    return [tour for tour in str(raw).split(",") if TOUR_RE.fullmatch(tour)]


def state():
    """The three switches and what the person at the till has seen, for the
    bootstrap."""
    user = frappe.session.user
    seen = frappe.defaults.get_user_default(SEEN_KEY, user) or ""
    return {
        "in_till": 1 if switch("help_in_till") else 0,
        "offer_tour": 1 if switch("help_offer_tour") else 0,
        "whats_new": 1 if switch("help_whats_new") else 0,
        "seen_version": seen if VERSION_RE.fullmatch(str(seen)) else "",
        "tours_done": _tours(user),
    }


@frappe.whitelist()
def mark(seen_version: str | None = None, tour_done: str | None = None):
    """Remember, for the person at the till, the news they have seen (the
    version) and a tour they finished. Only ever their own."""
    _require_till()
    user = frappe.session.user
    if seen_version:
        if not VERSION_RE.fullmatch(str(seen_version)):
            frappe.throw(_("Not a LumenPOS version: {0}").format(seen_version))
        frappe.defaults.set_user_default(SEEN_KEY, str(seen_version), user)
    if tour_done:
        if not TOUR_RE.fullmatch(str(tour_done)):
            frappe.throw(_("Not a LumenPOS tour: {0}").format(tour_done))
        tours = [tour for tour in _tours(user) if tour != tour_done] + [str(tour_done)]
        frappe.defaults.set_user_default(TOURS_KEY, ",".join(tours[-MAX_TOURS:]), user)
    return state()
