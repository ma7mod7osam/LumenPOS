"""Capability checks for till actions that a store may want to restrict to
certain staff: editing price (manual discounts), making returns, and returning
past the return window without approval.

Each capability is governed by an OPTIONAL role configured in LumenPOS Settings.
A System / LumenPOS Manager always passes. The checks are enforced server-side
(here) and mirrored to the UI via session.get_user_permissions, so the frontend
can hide/disable controls — but the server is always the authority.
"""

import frappe

MANAGER_ROLES = {"System Manager", "LumenPOS Manager"}


def _roles(user=None):
    return set(frappe.get_roles(user) if user else frappe.get_roles())


def is_manager(user=None):
    return bool(MANAGER_ROLES & _roles(user))


def _role_setting(field):
    return frappe.db.get_single_value("LumenPOS Settings", field)


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


def can_exceed_return_window(user=None):
    """Return a sale PAST the return window without an approval request. Empty
    role = nobody bypasses (everyone uses the request flow); managers always do."""
    if is_manager(user):
        return True
    role = _role_setting("return_exceed_role")
    return bool(role and role in _roles(user))
