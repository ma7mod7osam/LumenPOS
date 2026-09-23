# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Capability checks for till actions that a store may want to restrict to
certain staff: editing price (manual discounts), making returns, and returning
past the return window without approval.

Each capability is governed by an OPTIONAL role configured in LumenPOS Settings.
A System / LumenPOS Manager always passes. The checks are enforced server-side
(here) and mirrored to the UI via session.get_user_permissions, so the frontend
can hide/disable controls, but the server is always the authority.
"""

import frappe

MANAGER_ROLES = {"System Manager", "LumenPOS Manager"}


def _roles(user=None):
    return set(frappe.get_roles(user) if user else frappe.get_roles())


def is_manager(user=None):
    return bool(MANAGER_ROLES & _roles(user))


def _role_setting(field):
    """A role configured in LumenPOS Settings, or None.

    Tolerates a field the site has not migrated yet: Frappe Cloud sometimes
    updates a site by pulling the code WITHOUT running migrate, and a capability
    check that raised "Invalid field name" there would take the whole till down
    instead of falling back to "nobody is restricted"."""
    try:
        return frappe.db.get_single_value("LumenPOS Settings", field)
    except Exception:
        return None


def can_edit_price(user=None):
    """Apply a manual discount / price edit on a sale line. Empty role = anyone."""
    role = _role_setting("price_edit_role")
    if not role:
        return True
    return is_manager(user) or role in _roles(user)


def can_return(user=None):
    """Create a return (credit note). Empty role = anyone with sell access."""
    role = _role_setting("return_role")
    if not role:
        return True
    return is_manager(user) or role in _roles(user)


def can_exchange(user=None):
    """Swap goods in one step (a return and a new sale settled together).

    An exchange is a return plus a sale, so whoever may do it must be allowed
    to make returns first. On top of that a shop can name its own role: blank
    means anyone who may return may also exchange."""
    if not can_return(user):
        return False
    role = _role_setting("exchange_role")
    if not role:
        return True
    return is_manager(user) or role in _roles(user)


def can_exceed_return_window(user=None):
    """Return a sale PAST the return window without an approval request. Empty
    role = nobody bypasses (everyone uses the request flow); managers always do."""
    if is_manager(user):
        return True
    role = _role_setting("return_exceed_role")
    return bool(role and role in _roles(user))
