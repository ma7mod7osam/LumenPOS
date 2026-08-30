"""Thin shims over the Frappe/ERPNext internals LumenPOS calls directly.

LumenPOS supports Frappe/ERPNext **v13 through v16** from one branch. Almost all
of it uses public Frappe APIs, but four things need ERPNext's own code: loyalty
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
    """Customer's loyalty program + point balance, or None if they have none.

    The program has to be resolved HERE and passed in. ERPNext's
    get_loyalty_program_details_with_points resolves it internally for its own
    lookup, but then re-reads the *argument* to load the program document:

        lp_details = get_loyalty_program_details(customer, loyalty_program, ...)
        loyalty_program = frappe.get_doc("Loyalty Program", loyalty_program)

    so a caller that leaves the argument out gets
    "Loyalty Program None not found" every time, even for a customer who is
    properly enrolled. Its own callers all pass the program, so this matches
    them. Verified against ERPNext v13, v14 and v15.
    """
    try:
        from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
            get_loyalty_program_details_with_points,
        )
        from erpnext.selling.doctype.customer.customer import get_loyalty_programs
    except Exception as exc:  # pragma: no cover - version guard
        _fail("loyalty program details", exc)

    program = frappe.db.get_value("Customer", customer, "loyalty_program")
    if not program:
        # Not explicitly enrolled: fall back to any auto opt-in program whose
        # customer group and territory match, exactly as ERPNext does.
        try:
            available = get_loyalty_programs(frappe.get_doc("Customer", customer))
        except Exception:
            available = []
        program = available[0] if available else None
    if not program:
        return None

    return get_loyalty_program_details_with_points(
        customer,
        loyalty_program=program,
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


def new_doc(doctype):
    """frappe.new_doc with every child table initialised to an empty list.

    Frappe v14 and later set Table fields to [] on a new document, so code can
    read a child table before it has appended anything to it. Frappe v13 does
    not: the attribute simply isn't there, and the first read raises
    `AttributeError: 'X' object has no attribute 'y'`.

    That difference broke the register close on v13 — the Z-report accumulators
    scan `payment_reconciliation` looking for an existing row before adding one.
    Rather than reorder every accumulator, normalise the document here so all
    supported versions behave the same way.
    """
    doc = frappe.new_doc(doctype)
    for df in doc.meta.get_table_fields():
        if doc.get(df.fieldname) is None:
            doc.set(df.fieldname, [])
    return doc
