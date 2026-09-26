# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Who may do what at the till.

A shop restricts an action by adding rows to **Who can do what** in LumenPOS
Settings. A row names a ROLE or a PERSON, and any matching row passes, so
"the shift supervisors plus Fatima" is two rows, not a special role invented
for one person. A capability with no rows at all is open to everyone (the one
exception is returning past the window, which stays shut unless someone is
named). A System / LumenPOS Manager always passes.

Every check is enforced HERE, server-side, and mirrored to the UI through
session.get_user_permissions so the till can hide what a cashier may not do.
The UI copy is a convenience, this module is the authority.

The four single-role fields that came before (price_edit_role, return_role,
return_exceed_role, exchange_role) are still read as a fallback, so a site that
has not migrated its settings yet keeps exactly the behaviour it had.
"""

import frappe

MANAGER_ROLES = {"System Manager", "LumenPOS Manager"}

# The stored label of each capability (the Select on POS Capability Rule) and
# the legacy single-role field it replaced.
PRICE_EDIT = "Edit price / discount"
RETURN = "Make returns"
RETURN_EXCEED = "Return past the window"
EXCHANGE = "Exchange goods"
CASH_MOVEMENT = "Cash in / out"
REPRINT = "Reprint a receipt"
OPEN_REGISTER = "Open the register"
CLOSE_REGISTER = "Close the register"
HOLD_GOODS = "Hold goods for a customer"

LEGACY_FIELD = {
    PRICE_EDIT: "price_edit_role",
    RETURN: "return_role",
    RETURN_EXCEED: "return_exceed_role",
    EXCHANGE: "exchange_role",
}

# Capabilities nobody holds until someone is named. Everything else is open
# until a shop decides otherwise, so installing LumenPOS never locks a till.
CLOSED_BY_DEFAULT = {RETURN_EXCEED}


def _roles(user=None):
    return set(frappe.get_roles(user) if user else frappe.get_roles())


def allowed_companies(user=None):
    """The companies ERPNext's User Permissions hold this user to, or None
    when there is no such permission (every company)."""
    user = user or frappe.session.user
    if user == "Administrator":
        return None
    companies = frappe.get_all("User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value")
    return set(companies) or None


def can_use_outlet(pos_profile, user=None):
    """Whether this user may work at this outlet: its company allowed by the
    user's permissions, and the user a manager, assigned to the outlet
    (Applicable for Users), or at a shop that assigns nobody."""
    user = user or frappe.session.user
    if not pos_profile:
        return False
    if user == "Administrator":
        return True
    company = frappe.get_cached_value("POS Profile", pos_profile, "company")
    companies = allowed_companies(user)
    if companies is not None and company not in companies:
        return False
    if is_manager(user):
        return True
    assigned = frappe.get_all("POS Profile User", filters={"user": user, "parenttype": "POS Profile"}, pluck="parent")
    return not assigned or pos_profile in assigned


def assert_outlet(pos_profile):
    if not can_use_outlet(pos_profile):
        frappe.throw(
            frappe._("You are not assigned to outlet {0}. Ask an administrator to add you under Applicable for Users.").format(
                pos_profile
            ),
            frappe.PermissionError,
        )


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


def _rules(capability):
    """The rows naming who may do this, plus the legacy single role if the site
    still has one set and has not written any row for this capability."""
    rows = []
    try:
        settings = frappe.get_cached_doc("LumenPOS Settings")
        rows = [
            r
            for r in (settings.get("capability_rules") or [])
            if (r.get("capability") or "") == capability and (r.get("role") or r.get("user"))
        ]
    except Exception:
        rows = []  # not migrated yet
    if rows:
        return rows
    legacy = LEGACY_FIELD.get(capability)
    role = _role_setting(legacy) if legacy else None
    return [frappe._dict({"capability": capability, "role": role, "user": None})] if role else []


def allowed(capability, user=None):
    """Is this person allowed to do it?"""
    if is_manager(user):
        return True
    rows = _rules(capability)
    if not rows:
        return capability not in CLOSED_BY_DEFAULT
    who = user or frappe.session.user
    roles = _roles(user)
    return any((r.get("user") and r.get("user") == who) or (r.get("role") and r.get("role") in roles) for r in rows)


def can_edit_price(user=None):
    """Apply a manual discount / price edit on a sale line."""
    return allowed(PRICE_EDIT, user)


def can_return(user=None):
    """Create a return (credit note)."""
    return allowed(RETURN, user)


def can_exchange(user=None):
    """Swap goods in one step (a return and a new sale settled together).

    An exchange is a return plus a sale, so whoever does it must be allowed to
    make returns first, whatever the exchange rows say."""
    return can_return(user) and allowed(EXCHANGE, user)


def can_exceed_return_window(user=None):
    """Return a sale PAST the return window without an approval request. Nobody
    does unless a shop names them, managers always do."""
    return allowed(RETURN_EXCEED, user)


def can_hold_goods(user=None):
    """Put goods aside for a customer who pays over time, take an instalment,
    hand the goods over or cancel the hold."""
    return allowed(HOLD_GOODS, user)


def can_move_cash(user=None):
    """Put money in the drawer or take it out mid-shift."""
    return allowed(CASH_MOVEMENT, user)


def can_reprint(user=None):
    """Print a receipt again after the sale."""
    return allowed(REPRINT, user)


def can_open_register(user=None):
    """Open a shift. ERPNext's own document permissions still apply on top."""
    return allowed(OPEN_REGISTER, user)


def can_close_register(user=None):
    """Close a shift and count the drawer. ERPNext's own document permissions
    still apply on top."""
    return allowed(CLOSE_REGISTER, user)
