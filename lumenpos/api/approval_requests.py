"""POS approval requests — a generic, role-approved request used for two cases:

- **Discount**: a manual discount above LumenPOS Settings → Discount Limit, when the
  approval method allows requests.
- **Return**: a regular return after the configured return window has passed.

In both cases the cashier drops a request that a user holding the configured
**Approver Role** approves while the cashier's register is still OPEN. A request
is single-use: it is consumed by the sale / credit note it authorizes, and it
expires if the register closes before it's approved.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, get_fullname, now_datetime, nowdate

REQUEST_DOCTYPE = "POS Approval Request"
SESSION_DOCTYPE = "POS Register Session"
INVOICE_DOCTYPE = "POS Invoice"

REQUEST_TYPES = ("Discount", "Return")


def _settings():
    return frappe.get_cached_doc("LumenPOS Settings")


def approval_mode():
    """Discount over-limit method: Passcode only | Request only | Passcode or
    request (default Passcode only, so untouched sites keep today's behavior)."""
    return _settings().get("discount_approval_mode") or "Passcode only"


def _approver_role():
    return _settings().get("approver_role")


def _is_manager(user=None):
    roles = set(frappe.get_roles(user) if user else frappe.get_roles())
    return bool({"System Manager", "LumenPOS Manager"} & roles)


def can_approve(user=None):
    """True if the user may approve requests: a LumenPOS/System Manager, or a holder
    of the configured approver role."""
    if _is_manager(user):
        return True
    role = _approver_role()
    roles = set(frappe.get_roles(user) if user else frappe.get_roles())
    return bool(role and role in roles)


def _require_approver():
    if not can_approve():
        frappe.throw(
            _("You are not allowed to approve requests."), frappe.PermissionError
        )


@frappe.whitelist()
def create_request(
    request_type,
    pos_profile,
    reason=None,
    customer=None,
    customer_name=None,
    discount_percent=0,
    cart_total=0,
    return_invoice=None,
):
    """Cashier drops an approval request tied to the open register session.
    request_type is 'Discount' or 'Return'. Returns {name, status}."""
    request_type = (request_type or "").strip().title()
    if request_type not in REQUEST_TYPES:
        frappe.throw(_("Unknown request type {0}").format(request_type))

    settings = _settings()
    age = None
    if request_type == "Discount":
        if approval_mode() == "Passcode only":
            frappe.throw(
                _("Discount requests are turned off — ask a manager for the passcode.")
            )
        discount_percent = flt(discount_percent)
        limit = flt(settings.get("discount_limit_percent"))
        if limit > 0 and discount_percent <= limit:
            frappe.throw(
                _("This discount is within the {0}% limit — no approval needed.").format(limit)
            )
    else:  # Return
        if not settings.get("restrict_returns_to_window"):
            frappe.throw(_("Return approval isn't required — returns are open."))
        if not return_invoice:
            frappe.throw(_("Select the invoice to return."))
        posting = frappe.db.get_value(INVOICE_DOCTYPE, return_invoice, "posting_date")
        if posting:
            age = date_diff(nowdate(), posting)

    session = frappe.db.get_value(
        SESSION_DOCTYPE, {"pos_profile": pos_profile, "status": "Open"}, "name"
    )
    if not session:
        frappe.throw(_("Open the register before requesting approval."))

    doc = frappe.new_doc(REQUEST_DOCTYPE)
    doc.update(
        {
            "request_type": request_type,
            "register_session": session,
            "pos_profile": pos_profile,
            "cashier": frappe.session.user,
            "cashier_name": get_fullname(frappe.session.user),
            "customer": customer or None,
            "customer_name": customer_name or None,
            "discount_percent": flt(discount_percent) if request_type == "Discount" else 0,
            "cart_total": flt(cart_total),
            "return_invoice": return_invoice if request_type == "Return" else None,
            "invoice_age_days": age,
            "reason": (reason or "").strip() or None,
            "status": "Pending",
        }
    )
    doc.insert(ignore_permissions=True)
    frappe.publish_realtime(
        "lumenpos_approval_request", {"pos_profile": pos_profile}, after_commit=True
    )
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def request_status(name):
    """Poll a request — the cashier who raised it (or any approver) may read."""
    doc = frappe.get_doc(REQUEST_DOCTYPE, name)
    if doc.cashier != frappe.session.user and not can_approve():
        frappe.throw(_("Request not found."), frappe.PermissionError)
    return {
        "name": doc.name,
        "request_type": doc.request_type,
        "status": doc.status,
        "approver_name": doc.approver_name,
        "decision_note": doc.decision_note,
        "discount_percent": doc.discount_percent,
    }


@frappe.whitelist()
def cancel_request(name):
    """Cashier withdraws their own still-pending request."""
    doc = frappe.get_doc(REQUEST_DOCTYPE, name)
    if doc.cashier != frappe.session.user and not can_approve():
        frappe.throw(_("Not allowed."), frappe.PermissionError)
    if doc.status == "Pending":
        doc.status = "Expired"
        doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def pending_requests(pos_profile=None):
    """Requests an approver can act on right now — Pending and whose register
    session is still Open. Returns the list (its length is the badge count)."""
    _require_approver()
    filters = {"status": "Pending"}
    if pos_profile:
        filters["pos_profile"] = pos_profile
    rows = frappe.get_all(
        REQUEST_DOCTYPE,
        filters=filters,
        fields=[
            "name", "request_type", "register_session", "pos_profile", "cashier",
            "cashier_name", "customer_name", "discount_percent", "cart_total",
            "return_invoice", "invoice_age_days", "reason", "creation",
        ],
        order_by="creation asc",
        limit_page_length=50,
    )
    open_sessions = set(
        frappe.get_all(SESSION_DOCTYPE, filters={"status": "Open"}, pluck="name")
    )
    return [r for r in rows if r.register_session in open_sessions]


@frappe.whitelist()
def approve_request(name):
    return _decide(name, "Approved")


@frappe.whitelist()
def reject_request(name, note=None):
    return _decide(name, "Rejected", note)


def _decide(name, status, note=None):
    _require_approver()
    doc = frappe.get_doc(REQUEST_DOCTYPE, name)
    if doc.status != "Pending":
        frappe.throw(_("This request was already {0}.").format(_(doc.status.lower())))
    # Only while the cashier's register session is still open.
    if frappe.db.get_value(SESSION_DOCTYPE, doc.register_session, "status") != "Open":
        doc.status = "Expired"
        doc.save(ignore_permissions=True)
        frappe.throw(_("The cashier's register has closed — this request has expired."))
    # Separation of duties: a role-only approver can't clear their own request.
    # A manager (the authority) may — this is a manager override, and it also
    # lets a single owner test the flow end-to-end.
    if doc.cashier == frappe.session.user and not _is_manager():
        frappe.throw(_("You can't approve your own request — another approver must."))
    doc.status = status
    doc.approved_by = frappe.session.user
    doc.approver_name = get_fullname(frappe.session.user)
    doc.decided_at = now_datetime()
    doc.decision_note = (note or "").strip() or None
    doc.save(ignore_permissions=True)
    frappe.publish_realtime(
        "lumenpos_approval_decided",
        {"name": doc.name, "status": status, "cashier": doc.cashier},
        after_commit=True,
    )
    return {"name": doc.name, "status": doc.status, "approver_name": doc.approver_name}


def _validate(request_name, request_type):
    """Shared submit-time checks: belongs to this cashier, Approved, unconsumed,
    right type, and on a still-open session. Returns the doc."""
    doc = frappe.get_doc(REQUEST_DOCTYPE, request_name)
    if doc.request_type != request_type:
        frappe.throw(_("This approval is for a {0}, not a {1}.").format(
            _(doc.request_type), _(request_type)))
    if doc.cashier != frappe.session.user:
        frappe.throw(_("This approval was issued to another cashier."))
    if doc.status != "Approved":
        frappe.throw(_("The approval is {0}, not approved.").format(_(doc.status.lower())))
    if doc.consumed:
        frappe.throw(_("This approval was already used."))
    if frappe.db.get_value(SESSION_DOCTYPE, doc.register_session, "status") != "Open":
        frappe.throw(_("The approval's register session has closed."))
    return doc


def validate_discount(request_name, discount_percent):
    """Submit-time check for a Discount request; returns the approver name."""
    doc = _validate(request_name, "Discount")
    if flt(doc.discount_percent) + 0.001 < flt(discount_percent):
        frappe.throw(
            _("The approved discount ({0}%) is below the {1}% on this sale.").format(
                doc.discount_percent, discount_percent
            )
        )
    return doc.approver_name


def validate_return(request_name, return_invoice):
    """Submit-time check for a Return request; returns the approver name."""
    doc = _validate(request_name, "Return")
    if doc.return_invoice and doc.return_invoice != return_invoice:
        frappe.throw(_("This return approval is for invoice {0}.").format(doc.return_invoice))
    return doc.approver_name


def consume(request_name, invoice_name):
    """Mark an approval used by the sale / credit note that posted (single-use)."""
    if not request_name:
        return
    doc = frappe.get_doc(REQUEST_DOCTYPE, request_name)
    if doc.consumed:
        return
    doc.consumed = 1
    doc.invoice = invoice_name
    doc.save(ignore_permissions=True)
