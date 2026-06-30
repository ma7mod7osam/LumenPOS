"""Lightweight audit trail of sensitive till actions.

`log()` is best-effort: gated by the Settings → Features toggle, it never raises
and never blocks the action it records (a failed write is swallowed so a sale is
never lost to an audit problem). Reads are manager-only.
"""

import frappe
from frappe.utils import cint, flt

# Actions worth recording. Free-form strings — these are just the common ones.
SALE = "Sale"
RETURN = "Return"
OVER_LIMIT_DISCOUNT = "Over-limit discount"
PRICE_EDIT = "Price edit"
REGISTER_OPEN = "Register open"
REGISTER_CLOSE = "Register close"
SETTINGS_CHANGE = "Settings change"
TILL_UNLOCK = "Till unlock"


def _enabled():
    try:
        return bool(frappe.get_cached_doc("LumenPOS Settings").get("enable_audit_log"))
    except Exception:
        return False


def log(
    action,
    detail=None,
    reference_doctype=None,
    reference_name=None,
    amount=None,
    pos_profile=None,
    user=None,
):
    """Record one sensitive action. Silent no-op when the feature is off or the
    write fails — auditing must never break the till."""
    if not _enabled():
        return
    try:
        doc = frappe.get_doc(
            {
                "doctype": "LumenPOS Audit Log",
                "action": action,
                "user": user or frappe.session.user,
                "pos_profile": pos_profile,
                "amount": flt(amount) if amount is not None else None,
                "reference_doctype": reference_doctype,
                "reference_name": reference_name,
                "detail": (detail or "")[:1000] or None,
            }
        )
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "LumenPOS audit log")


@frappe.whitelist()
def list_logs(action=None, user=None, from_date=None, to_date=None, start=0, limit=50):
    """Manager-only reader for the Settings → Audit log viewer."""
    from lumenpos.api import permissions

    if not permissions.is_manager():
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

    filters = {}
    if action:
        filters["action"] = action
    if user:
        filters["user"] = user
    if from_date and to_date:
        filters["creation"] = ["between", [from_date, to_date + " 23:59:59"]]
    elif from_date:
        filters["creation"] = [">=", from_date]
    elif to_date:
        filters["creation"] = ["<=", to_date + " 23:59:59"]

    rows = frappe.get_all(
        "LumenPOS Audit Log",
        filters=filters,
        fields=[
            "name", "action", "user", "pos_profile", "amount",
            "reference_doctype", "reference_name", "detail", "creation",
        ],
        order_by="creation desc",
        start=cint(start),
        page_length=cint(limit),
    )
    return rows
