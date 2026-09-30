# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Thin shims over the Frappe/ERPNext internals LumenPOS calls directly.

LumenPOS supports Frappe/ERPNext **v13 through v16** from one branch. Almost all
of it uses public Frappe APIs, but four things need ERPNext's own code: loyalty
points, POS-invoice consolidation, and the return builder. Those live at module
paths that a major release is allowed to move.

Importing them here means a moved API produces ONE clear, actionable message
naming the app, the ERPNext version and what broke, instead of an ImportError
stack trace from the middle of a sale. It also gives us a single place to add a
version fallback if v16 ever relocates one of them.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt


def _fail(what, exc):
    frappe.log_error(
        title=f"LumenPOS: incompatible ERPNext API ({what})",
        message=f"{what}\n\nERPNext: {_erpnext_version()}\n\n{frappe.get_traceback()}",
    )
    frappe.throw(
        _(
            "LumenPOS could not use ERPNext's {0} on this version of ERPNext ({1}). "
            "This usually means the site is running an ERPNext release LumenPOS "
            "has not been updated for yet, please report it to "
            "hello@lumen-solutions.co with this message."
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


def settle_points_outstanding(doc, method=None):
    """POS Invoice before_submit (hooks.py), after ERPNext's own.

    ERPNext 16 works out what a POS Invoice still owes as its total less
    paid_amount (POSInvoice.set_outstanding_amount, new in 16), and paid_amount
    is the payment rows alone (SalesInvoice.before_save). So a sale paid partly
    with loyalty points posts "Partly Paid" with the points still owing, though
    ERPNext's Sales Invoice counts points as paid (calculate_paid_amount) and so
    does the invoice ERPNext merges the shift into: the books are right, only
    the POS Invoice's own figure is not. For LumenPOS's own sales (they carry a
    lumenpos_session), the points count here as they did up to ERPNext 15. The
    sale is refused before this if points and payments do not cover it."""
    if doc.get("is_return") or not doc.get("lumenpos_session"):
        return
    if not (doc.get("redeem_loyalty_points") and flt(doc.get("loyalty_amount"))):
        return
    total = flt(doc.get("rounded_total")) or flt(doc.get("grand_total"))
    owed = flt(total - flt(doc.get("paid_amount")) - flt(doc.loyalty_amount), doc.precision("outstanding_amount"))
    doc.outstanding_amount = owed if owed > 0 else 0


def one_open_shift_per_outlet():
    """ERPNext 16 checks, on every POS Invoice (sales and returns alike), that
    its outlet has exactly one open POS Opening Entry and that it was opened
    today (SalesInvoice.validate_pos_opening_entry, new in 16). Up to 15 an
    outlet could hold several, and one could run past midnight."""
    try:
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
    except Exception:  # pragma: no cover - version guard
        return False
    return hasattr(SalesInvoice, "validate_pos_opening_entry")


def pos_invoice_refused():
    """The reason ERPNext refuses POS Invoices on this site, or None.

    ERPNext 16 makes the POS create either Sales Invoices or POS Invoices for
    the whole site (POS Settings, Invoice Type Created via POS Screen), and
    refuses a POS Invoice when it is set to Sales Invoice. A site upgraded from
    15 is set to POS Invoice by ERPNext's own patch; a NEW v16 site starts on
    Sales Invoice."""
    try:
        if not frappe.get_meta("POS Settings").has_field("invoice_type"):
            return None
        kind = frappe.db.get_single_value("POS Settings", "invoice_type")
    except Exception:
        return None
    if kind != "Sales Invoice":
        return None
    return _(
        "ERPNext is set to make Sales Invoices from the POS (POS Settings, Invoice Type Created via "
        "POS Screen), so it refuses the POS Invoices this outlet makes. Set it to POS Invoice, or set "
        "the outlet to Sales Invoice (POS Profile, LumenPOS)."
    )


def change_gl_setting():
    """The single doctype holding ERPNext's "Create Ledger Entries for Change
    Amount" (post_change_gl_entries): POS Settings from ERPNext 16, Accounts
    Settings before. None where a site has neither."""
    for doctype in ("POS Settings", "Accounts Settings"):
        try:
            if frappe.get_meta(doctype).has_field("post_change_gl_entries"):
                return doctype
        except Exception:
            continue
    return None


def change_gl_entries_on():
    """True when ERPNext books change as its own ledger entry, out of the
    change account. Off, it takes change off the payment made INTO that account
    instead (SalesInvoice.make_pos_gl_entries), in local money only: it cannot
    give change from one drawer for money paid into another, and it reduces
    only the local value of a drawer in another currency."""
    doctype = change_gl_setting()
    if not doctype:
        return True
    return bool(cint(frappe.db.get_single_value(doctype, "post_change_gl_entries")))


def ensure_change_gl_entries():
    """Selling in other currencies needs change booked as its own entry (see
    change_gl_entries_on). On by default up to ERPNext 15; a NEW ERPNext 16
    site starts with it off (a site upgraded from 15 keeps its value). Turns it
    on; True when it changed."""
    doctype = change_gl_setting()
    if not doctype or change_gl_entries_on():
        return False
    frappe.db.set_single_value(doctype, "post_change_gl_entries", 1)
    return True


def _erpnext_major():
    try:
        return int(str(_erpnext_version()).split(".")[0])
    except ValueError:
        return 99  # a development build: the newest rules


def merge_posts_sales_when_sold():
    """When ERPNext posts a shift's merged invoices. 15 and 16 give the merged
    Sales Invoice the posting time of its last sale (POSInvoiceMergeLog.
    merge_pos_invoice_into) and the credit note the close's. 13 and 14 post
    both at the close, the credit note first."""
    return _erpnext_major() >= 15


def returns_held_until_posted():
    """ERPNext 13 and 14 give a returned item back to the shelf only once the
    return is posted: their stock check (POSInvoice.validate_stock_availablility,
    through get_pos_reserved_qty) takes every POS sale not posted yet off the
    shelf and none of its returns. 15 and 16 count the returns (and a bundle's
    Packed Item rows, get_pos_reserved_qty_from_table)."""
    return _erpnext_major() < 15


def consolidate_pos_invoices(rows):
    """ERPNext's own posting of chosen POS Invoices without a shift close
    (pos_invoice_merge_log.consolidate_pos_invoices, closing_entry None): one
    merge per customer, a Sales Invoice for the sales and a credit note for the
    returns, as the close would post them. `rows` are shaped like a POS Closing
    Entry's invoice rows. It commits, and rolls back what is not committed yet
    when it fails."""
    try:
        from erpnext.accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log import (
            consolidate_pos_invoices as consolidate,
        )
    except Exception as exc:  # pragma: no cover - version guard
        _fail("POS invoice consolidation", exc)
    return consolidate(pos_invoices=rows)


def closing_invoice_table():
    """The POS Closing Entry table that lists the shift's POS Invoices:
    `pos_transactions` up to ERPNext 15, renamed `pos_invoices` in ERPNext 16
    (which also added `sales_invoices` beside it). Consolidation reads it."""
    meta = frappe.get_meta("POS Closing Entry")
    return "pos_invoices" if meta.has_field("pos_invoices") else "pos_transactions"


def pos_reserved_serials(item_code, warehouse=None):
    """The serials ERPNext itself holds for POS Invoices, by the rule of this
    version, so the till refuses exactly what ERPNext would refuse at submit.

    ERPNext 15 and 16 (Serial and Batch Bundle): get_reserved_serial_nos_for_pos,
    every submitted POS Invoice not consolidated yet, less what a POS return
    gave back. It counts a sale's serial once from its bundle AND once from its
    serial_no text, while a return gives it back only once, so a line that
    carries both (use_serial_batch_fields, as every LumenPOS sale does) stays
    held after a return in the same shift, until the shift close consolidates
    the sale. ERPNext 13 and 14: get_pos_reserved_serial_nos, every submitted POS
    Invoice in the warehouse less its POS returns."""
    try:
        from erpnext.stock.doctype.serial_and_batch_bundle.serial_and_batch_bundle import (
            get_reserved_serial_nos_for_pos,
        )
    except ImportError:
        get_reserved_serial_nos_for_pos = None
    if get_reserved_serial_nos_for_pos:
        return list(
            get_reserved_serial_nos_for_pos(
                frappe._dict(item_code=item_code, warehouse=warehouse, ignore_voucher_nos=[""])
            )
            or []
        )
    try:
        from erpnext.stock.doctype.serial_no.serial_no import get_pos_reserved_serial_nos
    except Exception as exc:  # pragma: no cover - version guard
        _fail("reserved serial numbers", exc)
    if not warehouse:
        return []
    return list(get_pos_reserved_serial_nos({"item_code": item_code, "warehouse": warehouse}) or [])


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

    That difference broke the register close on v13, the Z-report accumulators
    scan `payment_reconciliation` looking for an existing row before adding one.
    Rather than reorder every accumulator, normalise the document here so all
    supported versions behave the same way.
    """
    doc = frappe.new_doc(doctype)
    for df in doc.meta.get_table_fields():
        if doc.get(df.fieldname) is None:
            doc.set(df.fieldname, [])
    return doc
