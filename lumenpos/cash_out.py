# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Taking money out of the drawer (0.61.0).

The owner, 2026-10-03, on the Register page's cash in / out: "عشان ما يصير كل
احد يسحب من الصندوق بكيفه", and he picked all three: cash out apart from cash in
(two permissions, lumenpos.api.permissions), a reason for every cash out, and a
manager's approval for it, by their passcode at the till or a request from the
Approvals tray, the way discounts and returns are approved.

LumenPOS Settings (General, Approvals and access, Cash out):
- cash_out_reason_required: Check, ON on install and update (written once).
- cash_out_approval: Off (the default, nothing changes) / Above an amount /
  Always.
- cash_out_approval_amount: Above an amount asks only past it, in the company
  currency (a drawer in another currency valued at the shift's rate).

A manager (LumenPOS or System Manager) is the authority and needs nobody's
approval. Whoever approved is kept on the cash movement and in the audit log."""

import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money

SETTINGS = "LumenPOS Settings"
MODES = ("Off", "Above an amount", "Always")
EPSILON = 0.005


def _settings():
    return frappe.get_cached_doc(SETTINGS)


def mode():
    value = _settings().get("cash_out_approval") or "Off"
    return value if value in MODES else "Off"


def threshold():
    return max(flt(_settings().get("cash_out_approval_amount")), 0.0)


def reason_required():
    return bool(cint(_settings().get("cash_out_reason_required")))


def client_facts():
    """What the till needs (bootstrap and get_settings)."""
    return {
        "cash_out_approval": mode(),
        "cash_out_approval_amount": threshold(),
        "cash_out_reason_required": 1 if reason_required() else 0,
    }


def _is_manager(user=None):
    from lumenpos.api.permissions import is_manager

    return is_manager(user)


def company_value(session_doc, amount, drawer=None):
    """`amount` taken from `drawer` (empty: the main drawer), valued in the
    company currency at the shift's rate for a drawer in another currency."""
    from lumenpos.api.register import _foreign_drawers, _in_company_currency

    code = _foreign_drawers(session_doc.pos_profile).get(drawer) if drawer else None
    return flt(_in_company_currency(session_doc, amount, code), 2)


def money(session_doc, amount, drawer=None):
    """An amount of a drawer written with its money ("SAR 60.00"), for the
    audit log and the refusals: the drawer's own currency for a drawer in
    another currency, the company's for the main one."""
    from lumenpos import currency
    from lumenpos.api.register import _foreign_drawers

    code = _foreign_drawers(session_doc.pos_profile).get(drawer) if drawer else None
    if not code:
        company = frappe.get_cached_value("POS Profile", session_doc.pos_profile, "company")
        code = currency.company_currency(company)
    return fmt_money(flt(amount, 2), currency=code)


def needs_approval(session_doc, amount, drawer=None, user=None):
    """Does this cash out need a manager's approval? Never for a manager."""
    current = mode()
    if current == "Off" or _is_manager(user):
        return False
    if current == "Always":
        return True
    return abs(company_value(session_doc, amount, drawer)) > threshold() + EPSILON


def approve(session_doc, amount, drawer=None, passcode=None, request=None):
    """Who approved this cash out and the request it used: (None, None) when
    none is needed. Raises when one is needed and missing or wrong."""
    if not needs_approval(session_doc, amount, drawer):
        return None, None
    if passcode:
        from lumenpos.api.settings import check_passcode

        result = check_passcode(passcode)
        if not result:
            frappe.throw(_("Wrong approver passcode."), title=_("Cash out"))
        return (result if isinstance(result, str) else _("the master passcode")), None
    if request:
        from lumenpos.api import approval_requests

        approver = approval_requests.validate_cash_out(request, session_doc.name, amount, drawer)
        return approver, request
    frappe.throw(
        _("Taking this much out of the drawer needs a manager's approval: their passcode, or a request they approve."),
        title=_("Cash out"),
    )
