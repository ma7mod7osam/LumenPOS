"""Thin shims over the ERPNext internals LumenPOS calls directly.

LumenPOS supports Frappe/ERPNext **v15 and v16** from one branch. Almost all of
it uses public Frappe APIs, but four things need ERPNext's own code: loyalty
points, POS-invoice consolidation, and the return builder. Those live at module
paths that a major release is allowed to move.

Importing them here means a moved API produces ONE clear, actionable message
naming the app, the ERPNext version and what broke — instead of an ImportError
stack trace from the middle of a sale. It also gives us a single place to add a
version fallback if v16 ever relocates one of them.
"""

import frappe
from frappe import _


def _fail(what, exc):
    frappe.log_error(
        title=f"LumenPOS: incompatible ERPNext API ({what})",
        message=f"{what}\n\nERPNext: {_erpnext_version()}\n\n{frappe.get_traceback()}",
    )
    frappe.throw(
        _(
            "LumenPOS could not use ERPNext's {0} on this version of ERPNext ({1}). "
            "This usually means the site is running an ERPNext release LumenPOS "
            "has not been updated for yet — please report it to "
            "support@lumen-solutions.co with this message."
        ).format(what, _erpnext_version())
    )


def _erpnext_version():
    try:
        import erpnext

        return getattr(erpnext, "__version__", "unknown")
    except Exception:
        return "not installed"


def loyalty_details(customer, company, silent=True, include_expired_entry=False):
    """Customer's loyalty program + point balance."""
    try:
        from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
            get_loyalty_program_details_with_points,
        )
    except Exception as exc:  # pragma: no cover - version guard
        _fail("loyalty program details", exc)
    return get_loyalty_program_details_with_points(
        customer,
        company=company,
        silent=silent,
        include_expired_entry=include_expired_entry,
    )


def merge_log_api():
    """(create_merge_logs, get_invoice_customer_map) for POS consolidation."""
    try:
        from erpnext.accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log import (
            create_merge_logs,
            get_invoice_customer_map,
        )
    except Exception as exc:  # pragma: no cover - version guard
        _fail("POS invoice consolidation", exc)
    return create_merge_logs, get_invoice_customer_map


def make_return_doc(doctype, name):
    """ERPNext's credit-note builder."""
    try:
        from erpnext.controllers.sales_and_purchase_return import (
            make_return_doc as _make_return_doc,
        )
    except Exception as exc:  # pragma: no cover - version guard
        _fail("return document builder", exc)
    return _make_return_doc(doctype, name)
