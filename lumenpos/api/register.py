"""Register lifecycle — robust open / close with reliable consolidation.

Opening the register creates BOTH:
  - a LumenPOS `POS Register Session` (operational: cash float, cash in/out)
  - a native ERPNext `POS Opening Entry` (so POS Invoices validate and the
    closing can consolidate them into Sales Invoices)

CLOSING — the hard part. ERPNext consolidates the shift's POS Invoices into
Sales Invoices when a `POS Closing Entry` is submitted. For >=10 invoices it
*enqueues* that consolidation; if it fails (heavy load, or two shifts
consolidating the same customer at once) the closing entry is left "Failed",
its `frappe.db.rollback()` undoes every merge log (so nothing is half-posted),
and — critically — the linked POS Opening Entry stays "Open". The old code keyed
"is a shift open?" partly off that opening entry, so a failed close let the next
cashier resume a dead shift. The endless loop.

This module fixes it with a strict state machine on the LumenPOS session:

    Open  ->  Closing  ->  Closed
                  └─ (consolidation failed) stays "Closing", closing_status=Failed

  * The moment a cashier closes, the session flips to "Closing" and is committed.
    From then on it is NOT sellable (get_open_session only returns "Open") and
    NOT resumable — regardless of whether consolidation later succeeds or fails.
  * Consolidation runs in a background job, SERIALIZED behind a cluster-wide DB
    lock and driven SYNCHRONOUSLY (we call create_merge_logs ourselves instead
    of letting ERPNext enqueue it), so two shifts can never deadlock each other.
  * A failed consolidation is safe to retry (ERPNext rolls back atomically), so
    the retry button and a scheduled self-healer keep re-running it until the
    shift reaches "Closed" — at which point the opening entry is closed too.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime, nowdate

from lumenpos.api.session import get_open_session

LIVE_STATES = ["Open", "Closing"]  # a shift that blocks opening another
CLOSING_LOCK = "lumenpos_pos_closing"


def _is_manager():
    return bool({"System Manager", "LumenPOS Manager"} & set(frappe.get_roles()))


def _assert_owner_or_manager(session_doc):
    """A cashier may only act on their OWN register; managers may act on any.
    Stops one cashier from closing/altering a colleague's live till."""
    if session_doc.get("opened_by") != frappe.session.user and not _is_manager():
        frappe.throw(_("You can only manage your own register"), frappe.PermissionError)


# ---------------------------------------------------------------------------
# Opening
# ---------------------------------------------------------------------------

@frappe.whitelist()
def open_register(pos_profile, opening_float=0, resume_opening_entry=None, force_new=0):
    """STRICT by default: one live shift per register, and a shift whose closing
    has not finished can never be silently resumed.

    Responses:
      - the session dict (success)
      - {"requires_retry": ...} when a previous shift is still finalising or
        failed — the cashier must retry that closing first
      - {"requires_choice": ...} only for a genuine orphan POS Opening Entry
        (one with no live LumenPOS session), offering resume / force-new
    """
    if not frappe.has_permission("POS Opening Entry", "create"):
        frappe.throw(_("You are not permitted to open a register"), frappe.PermissionError)

    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    opening_float = flt(opening_float)

    # 1) This register must have no live shift (Open or still-finalising Closing).
    existing = frappe.db.get_value(
        "POS Register Session",
        {"pos_profile": profile.name, "status": ["in", LIVE_STATES]},
        ["name", "status"],
        as_dict=True,
    )
    if existing:
        if existing.status == "Closing":
            closing_status = frappe.db.get_value(
                "POS Register Session", existing.name, "closing_status"
            )
            # A genuinely FAILED close (not one still in progress) can be left
            # to the self-healer while a fresh shift is started — so a stuck
            # consolidation can't keep the store shut the next day.
            if cint(force_new) and closing_status == "Failed":
                return _force_new_after_failure(profile, opening_float, existing.name)
            resp = _retry_response(existing.name)
            resp["can_force_new"] = closing_status == "Failed"
            return resp
        frappe.throw(
            _("Register {0} already has an open session ({1}).").format(profile.name, existing.name)
        )

    if resume_opening_entry:
        return _resume_opening(profile, resume_opening_entry)

    # 2) Does THIS cashier already hold an open native opening entry?
    open_entry = frappe.db.get_value(
        "POS Opening Entry",
        {"user": frappe.session.user, "status": "Open", "docstatus": 1},
        ["name", "pos_profile", "period_start_date"],
        as_dict=True,
    )
    allow_multiple = cint(frappe.db.get_single_value("LumenPOS Settings", "allow_multiple_opening"))

    if open_entry and not (cint(force_new) and allow_multiple):
        # Is a LumenPOS session still attached to it? If it's "Closing", the previous
        # close didn't finish — send them to retry, never resume.
        attached = frappe.db.get_value(
            "POS Register Session",
            {"pos_opening_entry": open_entry.name, "status": ["in", LIVE_STATES]},
            ["name", "status"],
            as_dict=True,
        )
        if attached:
            if attached.status == "Closing":
                return _retry_response(attached.name)
            frappe.throw(
                _("You already have register {0} open (session {1}). Close it before opening another.").format(
                    open_entry.pos_profile, attached.name
                )
            )
        # A true orphan opening entry (no live session) — offer resume / force-new.
        return {
            "requires_choice": True,
            "open_entry": {
                "name": open_entry.name,
                "pos_profile": open_entry.pos_profile,
                "period_start_date": str(open_entry.period_start_date),
                "same_profile": open_entry.pos_profile == profile.name,
                "can_force_new": bool(allow_multiple),
            },
        }

    # 3) Fresh shift.
    cash_modes = set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))
    opening_entry = frappe.get_doc(
        {
            "doctype": "POS Opening Entry",
            "company": profile.company,
            "pos_profile": profile.name,
            "user": frappe.session.user,
            "period_start_date": now_datetime(),
            "posting_date": nowdate(),
            "balance_details": [
                {
                    "mode_of_payment": row.mode_of_payment,
                    "opening_amount": opening_float if row.mode_of_payment in cash_modes else 0,
                }
                for row in profile.payments
            ],
        }
    )
    if open_entry:
        # force_new (testing): ERPNext core blocks a second open entry per
        # cashier in validate, so skip validation for this insert only.
        opening_entry.flags.ignore_validate = True
    opening_entry.insert(ignore_permissions=True)
    opening_entry.submit()

    frappe.get_doc(
        {
            "doctype": "POS Register Session",
            "pos_profile": profile.name,
            "opened_by": frappe.session.user,
            "opened_at": now_datetime(),
            "status": "Open",
            "opening_float": opening_float,
            "pos_opening_entry": opening_entry.name,
        }
    ).insert()
    return get_open_session(pos_profile)


def _retry_response(session_name):
    row = frappe.db.get_value(
        "POS Register Session",
        session_name,
        ["closing_status", "closing_error", "pos_closing_entry"],
        as_dict=True,
    ) or frappe._dict()
    return {
        "requires_retry": True,
        "session": session_name,
        "closing_status": row.closing_status,
        "closing_error": row.closing_error,
        "pos_closing_entry": row.pos_closing_entry,
        "message": _(
            "The previous shift ({0}) is still finalising or its closing failed. "
            "Retry the closing before opening a new register."
        ).format(session_name),
    }


def _force_new_after_failure(profile, opening_float, stuck_session):
    """The previous shift's closing keeps FAILING — let the store keep trading.
    Open a fresh shift now; the failed shift stays in 'Closing' and the
    self-healer keeps retrying its consolidation in the background, so no
    invoice is lost. Bypasses the one-live-shift / one-open-entry guards on
    purpose (the stuck shift is being recovered separately)."""
    if not frappe.has_permission("POS Closing Entry", "create"):
        frappe.throw(_("You are not permitted to do this"), frappe.PermissionError)

    # Nudge the stuck shift to consolidate once more right now.
    _enqueue_consolidation(stuck_session)

    cash_modes = set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))
    opening_entry = frappe.get_doc(
        {
            "doctype": "POS Opening Entry",
            "company": profile.company,
            "pos_profile": profile.name,
            "user": frappe.session.user,
            "period_start_date": now_datetime(),
            "posting_date": nowdate(),
            "balance_details": [
                {
                    "mode_of_payment": row.mode_of_payment,
                    "opening_amount": opening_float if row.mode_of_payment in cash_modes else 0,
                }
                for row in profile.payments
            ],
        }
    )
    opening_entry.flags.ignore_validate = True  # allow a 2nd open entry for this cashier
    opening_entry.insert(ignore_permissions=True)
    opening_entry.submit()

    session = frappe.get_doc(
        {
            "doctype": "POS Register Session",
            "pos_profile": profile.name,
            "opened_by": frappe.session.user,
            "opened_at": now_datetime(),
            "status": "Open",
            "opening_float": opening_float,
            "pos_opening_entry": opening_entry.name,
        }
    )
    session.flags.ignore_validate = True  # the stuck 'Closing' shift would block this otherwise
    session.insert()
    return get_open_session(profile.name)


def _resume_opening(profile, opening_name):
    """Continue a genuine orphan open shift: attach a fresh LumenPOS session to an
    existing POS Opening Entry that has no live session. The float comes from
    the entry itself."""
    entry = frappe.get_doc("POS Opening Entry", opening_name)
    if entry.user != frappe.session.user or entry.status != "Open" or entry.docstatus != 1:
        frappe.throw(_("Opening entry {0} is not an open shift of yours").format(opening_name))
    if entry.pos_profile != profile.name:
        frappe.throw(
            _("Opening entry {0} belongs to {1} — switch to that POS Profile to continue it").format(
                opening_name, entry.pos_profile
            )
        )
    # Guard: never resume an opening that already has a finalising/failed session.
    stuck = frappe.db.get_value(
        "POS Register Session",
        {"pos_opening_entry": entry.name, "status": ["in", LIVE_STATES]},
        "name",
    )
    if stuck:
        return _retry_response(stuck)

    cash_modes = set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))
    opening_cash = sum(
        flt(d.opening_amount)
        for d in (entry.balance_details or [])
        if d.mode_of_payment in cash_modes
    )
    frappe.get_doc(
        {
            "doctype": "POS Register Session",
            "pos_profile": profile.name,
            "opened_by": frappe.session.user,
            "opened_at": entry.period_start_date,
            "status": "Open",
            "opening_float": opening_cash,
            "pos_opening_entry": entry.name,
        }
    ).insert()
    return get_open_session(profile.name)


# ---------------------------------------------------------------------------
# Cash movements + live summary
# ---------------------------------------------------------------------------

@frappe.whitelist()
def add_cash_movement(session, movement_type, amount, reason=None):
    if not frappe.has_permission("POS Register Session", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("POS Register Session", session)
    _assert_owner_or_manager(doc)
    if doc.status != "Open":
        frappe.throw(_("Register session is not open"))
    doc.append(
        "cash_movements",
        {
            "movement_type": movement_type,
            "amount": flt(amount),
            "reason": reason,
            "recorded_at": now_datetime(),
            "recorded_by": frappe.session.user,
        },
    )
    doc.save()


@frappe.whitelist()
def get_session_summary(session):
    """Expected takings per payment mode for the close-register screen."""
    if not frappe.has_permission("POS Register Session", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("POS Register Session", session)
    _assert_owner_or_manager(doc)
    payments = _payments_by_mode(doc.name)

    cash_modes = set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))
    cash_in = sum(m.amount for m in (doc.cash_movements or []) if m.movement_type == "Cash In")
    cash_out = sum(m.amount for m in (doc.cash_movements or []) if m.movement_type == "Cash Out")

    expected = []
    for mode, amount in payments.items():
        row = {"mode_of_payment": mode, "expected_amount": flt(amount, 2)}
        if mode in cash_modes:
            row["expected_amount"] = flt(amount + (doc.opening_float or 0) + cash_in - cash_out, 2)
            row["is_cash"] = 1
        expected.append(row)

    if not any(r.get("is_cash") for r in expected) and (doc.opening_float or cash_in or cash_out):
        default_cash = next(iter(cash_modes), "Cash")
        expected.append(
            {
                "mode_of_payment": default_cash,
                "expected_amount": flt((doc.opening_float or 0) + cash_in - cash_out, 2),
                "is_cash": 1,
            }
        )

    totals = frappe.get_all(
        "POS Invoice",
        filters={"lumenpos_session": doc.name, "docstatus": 1},
        fields=[
            "count(name) as sales_count",
            "sum(grand_total) as total_sales",
            "sum(discount_amount) as invoice_discounts",
        ],
    )
    line_discounts = frappe.db.sql(
        """
        select coalesce(sum(pii.discount_amount * pii.qty), 0)
        from `tabPOS Invoice Item` pii
        join `tabPOS Invoice` pi on pi.name = pii.parent
        where pi.lumenpos_session = %s and pi.docstatus = 1
        """,
        doc.name,
    )[0][0]
    total_discounts = flt(line_discounts) + flt(totals[0].invoice_discounts if totals else 0)

    return {
        "session": doc.name,
        "status": doc.status,
        "pos_opening_entry": doc.get("pos_opening_entry"),
        "opened_at": str(doc.opened_at),
        "opening_float": doc.opening_float,
        "cash_in": flt(cash_in, 2),
        "cash_out": flt(cash_out, 2),
        "cash_movements": [
            {
                "movement_type": m.movement_type,
                "amount": m.amount,
                "reason": m.reason,
                "recorded_at": str(m.recorded_at),
            }
            for m in (doc.cash_movements or [])
        ],
        "expected": expected,
        "sales_count": totals[0].sales_count if totals else 0,
        "total_sales": flt(totals[0].total_sales, 2) if totals else 0,
        "total_discounts": flt(total_discounts, 2),
    }


# ---------------------------------------------------------------------------
# Closing
# ---------------------------------------------------------------------------

@frappe.whitelist()
def close_register(session, counted, closing_note=None):
    """Flip the session to 'Closing' (committed immediately, so it can never be
    sold-on or resumed again), then consolidate in a serialized background job.
    The shift only reaches 'Closed' once consolidation succeeds."""
    if not frappe.has_permission("POS Closing Entry", "create"):
        frappe.throw(_("You are not permitted to close a register"), frappe.PermissionError)
    if isinstance(counted, str):
        counted = json.loads(counted)

    doc = frappe.get_doc("POS Register Session", session)
    if doc.status == "Closed":
        frappe.throw(_("Register session is already closed"))
    if doc.status == "Closing":
        # Already finalising (double-tap or post-failure): just push the
        # consolidation again. Benign — no new counts, no live shift touched.
        _enqueue_consolidation(doc.name, counted)
        return _close_result(doc, queued=True)
    # The sensitive Open->Closing flip is owner/manager only (also enforced via
    # get_session_summary below). A cashier can't close a colleague's live till.
    _assert_owner_or_manager(doc)

    summary = get_session_summary(session)
    expected_map = {r["mode_of_payment"]: r["expected_amount"] for r in summary["expected"]}

    modes = sorted(set(expected_map) | set(counted or {}))
    doc.payment_counts = []
    for mode in modes:
        expected_amount = flt(expected_map.get(mode))
        counted_amount = flt((counted or {}).get(mode))
        doc.append(
            "payment_counts",
            {
                "mode_of_payment": mode,
                "expected_amount": expected_amount,
                "counted_amount": counted_amount,
                "difference": flt(counted_amount - expected_amount, 2),
            },
        )

    doc.status = "Closing"
    doc.closed_at = now_datetime()
    doc.closing_started_at = now_datetime()
    doc.closing_status = "Pending"
    doc.closing_error = None
    doc.closing_note = closing_note
    doc.total_sales = summary["total_sales"]
    doc.total_discounts = summary["total_discounts"]
    doc.sales_count = summary["sales_count"]
    doc.save()
    # Persist the "Closing" state NOW: from here the shift is neither sellable
    # nor resumable, whatever happens to the consolidation next.
    frappe.db.commit()

    if doc.get("pos_opening_entry"):
        _enqueue_consolidation(doc.name, counted)
        queued = True
    else:
        # Legacy session with no opening entry — nothing to consolidate.
        _mark_closed(doc.name, None)
        queued = False

    return _close_result(doc, queued=queued)


def _close_result(doc, queued):
    return {
        "name": doc.name,
        "status": doc.status,
        "closing_entry_queued": queued,
        "counts": [
            {
                "mode_of_payment": r.mode_of_payment,
                "expected_amount": r.expected_amount,
                "counted_amount": r.counted_amount,
                "difference": r.difference,
            }
            for r in doc.payment_counts
        ],
        "total_sales": doc.total_sales,
        "sales_count": doc.sales_count,
    }


def _enqueue_consolidation(session_name, counted=None, after_commit=True):
    """Queue one consolidation per session, de-duplicated by job id so repeated
    close/retry/self-heal triggers collapse into a single queued job instead of
    piling up on the long-worker pool."""
    job_id = f"lumenpos_close::{session_name}"
    try:
        from frappe.utils.background_jobs import is_job_enqueued

        if is_job_enqueued(job_id):
            return
    except Exception:
        pass
    frappe.enqueue(
        "lumenpos.api.register.build_closing_entry",
        queue="long",
        timeout=2000,
        enqueue_after_commit=after_commit,
        job_id=job_id,
        session_name=session_name,
        counted=counted or {},
    )


@frappe.whitelist()
def retry_closing(session):
    """Re-run consolidation for a session stuck in 'Closing' (manual retry)."""
    if not frappe.has_permission("POS Closing Entry", "create"):
        frappe.throw(_("You are not permitted to close a register"), frappe.PermissionError)
    doc = frappe.get_doc("POS Register Session", session)
    # No ownership gate here: retry only re-runs consolidation of an
    # already-closed shift (no count changes, no live till), and the next
    # cashier on the register legitimately needs to clear a stuck close.
    if doc.status == "Closed":
        return {"status": "Closed", "pos_closing_entry": doc.get("pos_closing_entry")}
    _enqueue_consolidation(doc.name)
    return {"status": doc.status, "queued": True}


def build_closing_entry(session_name, counted=None):
    """Create/submit + consolidate the POS Closing Entry for a session, fully
    serialized and idempotent. Safe to call repeatedly (initial job, manual
    retry, or the scheduled self-healer).

    NOT whitelisted on purpose — it runs only via the background queue and the
    scheduler. The HTTP entry point is retry_closing(), which is permission
    checked. (enqueue/scheduler resolve this by dotted path; no whitelist
    needed.)"""
    if isinstance(counted, str):
        counted = json.loads(counted)

    if not _acquire_lock(timeout=10):
        # Another consolidation holds the lock. Don't busy-wait a worker slot —
        # re-queue (de-duplicated) and let it run when the lock frees. The
        # 10-minute self-healer is the backstop if this is ever lost.
        _enqueue_consolidation(session_name, counted, after_commit=False)
        return None
    try:
        return _reconcile_session(session_name, counted or {})
    finally:
        _release_lock()


def _reconcile_session(session_name, counted):
    """Drive ONE session from 'Closing' to 'Closed'. Assumes the global closing
    lock is held."""
    session = frappe.get_doc("POS Register Session", session_name)
    if session.status == "Closed":
        return session.get("pos_closing_entry")

    opening_name = session.get("pos_opening_entry")
    if not opening_name:
        _mark_closed(session.name, None)
        return None

    closing_name = session.get("pos_closing_entry") or frappe.db.get_value(
        "POS Closing Entry",
        {"pos_opening_entry": opening_name, "docstatus": ["!=", 2]},
        "name",
    )

    if not closing_name:
        try:
            closing = _make_closing_entry(session, counted)
        except Exception as exc:
            frappe.db.rollback()
            _mark_failed(session.name, None, _short(exc))
            return None
        closing_name = closing.name
        session.db_set("pos_closing_entry", closing_name, commit=True)
    else:
        closing = frappe.get_doc("POS Closing Entry", closing_name)
        if closing.docstatus == 0:
            try:
                _suppress_consolidation(closing)
                closing.submit()
            except Exception as exc:
                frappe.db.rollback()
                _mark_failed(session.name, closing_name, _short(exc))
                return None
            session.db_set("pos_closing_entry", closing_name, commit=True)
        elif closing.docstatus == 2:
            # The closing was cancelled — start over with a fresh one.
            session.db_set("pos_closing_entry", None, commit=True)
            return _reconcile_session(session_name, counted)

    closing = frappe.get_doc("POS Closing Entry", closing_name)
    if closing.status == "Submitted" and _opening_closed(opening_name):
        _mark_closed(session.name, closing_name)
        return closing_name

    status = _consolidate_now(closing)
    if status == "Submitted":
        _mark_closed(session.name, closing_name)
    else:
        _mark_failed(
            session.name, closing_name, closing.get("error_message") or _("Consolidation failed")
        )
    return closing_name


def _consolidate_now(closing):
    """Run consolidation SYNCHRONOUSLY (never via ERPNext's >=10 enqueue) so it
    stays inside our global lock and concurrent shifts can't deadlock. Returns
    the resulting closing-entry status. A failed consolidation rolls back every
    merge log (ERPNext is atomic here), so this is always safe to retry."""
    from erpnext.accounts.doctype.pos_invoice_merge_log.pos_invoice_merge_log import (
        create_merge_logs,
        get_invoice_customer_map,
    )

    # Only feed invoices that aren't already consolidated, so a retry after a
    # partial/odd state can't double-post.
    pending = []
    for row in closing.get("pos_transactions") or []:
        state = frappe.db.get_value(
            "POS Invoice", row.pos_invoice, ["status", "consolidated_invoice"], as_dict=True
        )
        if state and state.status != "Consolidated" and not state.consolidated_invoice:
            pending.append(row)

    if not pending:
        # Everything already consolidated (or no sales) — just finalize.
        closing.set_status(update=True, status="Submitted")
        closing.db_set("error_message", "")
        closing.update_opening_entry()
        frappe.db.commit()
        return "Submitted"

    try:
        create_merge_logs(get_invoice_customer_map(pending), closing)
        return frappe.db.get_value("POS Closing Entry", closing.name, "status") or "Submitted"
    except Exception:
        # create_merge_logs already rolled back, set status=Failed + error.
        return "Failed"


def _make_closing_entry(session_doc, counted):
    """Build + submit the native POS Closing Entry for this session, WITHOUT
    triggering ERPNext's on-submit consolidation (we consolidate ourselves,
    serialized). Returns the submitted closing doc."""
    # The cashier's real counts live on the session's payment_counts (written +
    # committed at close time). Treat THAT as authoritative — a retry or the
    # self-healer calls in without the `counted` dict, and we must never post a
    # Z-report with zeroed counts and a false full-shortage variance.
    session_counts = {
        r.mode_of_payment: flt(r.counted_amount)
        for r in (session_doc.get("payment_counts") or [])
    }
    if session_counts:
        counted = session_counts

    opening = frappe.get_doc("POS Opening Entry", session_doc.get("pos_opening_entry"))
    invoices = frappe.get_all(
        "POS Invoice",
        filters={"lumenpos_session": session_doc.name, "docstatus": 1},
        fields=["name", "customer", "grand_total", "is_return", "posting_date"],
    )

    closing = frappe.new_doc("POS Closing Entry")
    closing.update(
        {
            "pos_opening_entry": opening.name,
            "period_start_date": opening.period_start_date,
            "period_end_date": now_datetime(),
            "posting_date": nowdate(),
            "company": opening.company,
            "pos_profile": opening.pos_profile,
            "user": opening.user,
        }
    )

    grand_total = net_total = qty_total = 0.0
    for inv in invoices:
        closing.append(
            "pos_transactions",
            {
                "pos_invoice": inv.name,
                "customer": inv.customer,
                "grand_total": inv.grand_total,
                "is_return": inv.is_return,
                "posting_date": inv.posting_date,
            },
        )
        full = frappe.get_doc("POS Invoice", inv.name)
        grand_total += flt(full.grand_total)
        net_total += flt(full.net_total)
        qty_total += sum(flt(i.qty) for i in full.items)
        for tax in full.taxes or []:
            _accumulate_tax(closing, tax)
        for payment in full.payments or []:
            if payment.amount:
                _accumulate_payment(closing, payment.mode_of_payment, payment.amount)
        if full.change_amount:
            cash_modes = set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))
            for row in closing.payment_reconciliation:
                if row.mode_of_payment in cash_modes:
                    row.expected_amount = flt(row.expected_amount) - flt(full.change_amount)
                    break

    cash_modes = set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))
    cash_in = sum(m.amount for m in (session_doc.cash_movements or []) if m.movement_type == "Cash In")
    cash_out = sum(m.amount for m in (session_doc.cash_movements or []) if m.movement_type == "Cash Out")
    cash_adjust_applied = False
    for detail in opening.balance_details:
        row = _get_reconciliation_row(closing, detail.mode_of_payment)
        row.opening_amount = flt(detail.opening_amount)
        row.expected_amount = flt(row.expected_amount) + flt(detail.opening_amount)
        # Net the drawer cash in/out into the (single) cash row so expected
        # matches what's physically in the till. Applied once even with several
        # cash modes configured.
        if detail.mode_of_payment in cash_modes and not cash_adjust_applied:
            row.expected_amount = flt(row.expected_amount) + cash_in - cash_out
            cash_adjust_applied = True

    for row in closing.payment_reconciliation:
        row.closing_amount = flt(counted.get(row.mode_of_payment))
        row.difference = flt(row.closing_amount) - flt(row.expected_amount)

    # Declare the shift's cash movements ON the closing entry (they otherwise
    # live only on the session and are invisible on the official Z-report).
    _declare_cash_movements(closing, session_doc, cash_in, cash_out)

    closing.grand_total = flt(grand_total, 2)
    closing.net_total = flt(net_total, 2)
    closing.total_quantity = flt(qty_total, 2)

    closing.insert(ignore_permissions=True)
    _suppress_consolidation(closing)
    closing.submit()
    return closing


def _declare_cash_movements(closing, session_doc, cash_in, cash_out):
    """Copy the session's drawer cash in/out onto the POS Closing Entry's LumenPOS
    fields (created in install.make_custom_fields) so the Z-report itself shows
    what was added to / taken from the drawer. Guarded with has_field so a
    not-yet-migrated site still closes cleanly."""
    meta = frappe.get_meta("POS Closing Entry")
    if not meta.has_field("lumenpos_cash_in"):
        return
    closing.lumenpos_cash_in = flt(cash_in, 2)
    closing.lumenpos_cash_out = flt(cash_out, 2)
    if not meta.has_field("lumenpos_cash_movements"):
        return
    closing.set("lumenpos_cash_movements", [])
    for m in session_doc.cash_movements or []:
        closing.append(
            "lumenpos_cash_movements",
            {
                "movement_type": m.movement_type,
                "amount": m.amount,
                "reason": m.reason,
                "recorded_at": m.recorded_at,
                "recorded_by": m.recorded_by,
            },
        )


def _suppress_consolidation(closing):
    """Neuter ERPNext's on_submit (it only consolidates + fires a realtime
    event) so the submit itself stays small and reliable; we run the heavy
    consolidation ourselves, serialized and retryable."""
    closing.on_submit = lambda *args, **kwargs: None


def _mark_closed(session_name, closing_name):
    values = {"status": "Closed", "closing_status": "Submitted", "closing_error": None}
    if closing_name:
        values["pos_closing_entry"] = closing_name
    frappe.db.set_value("POS Register Session", session_name, values)
    frappe.db.commit()


def _mark_failed(session_name, closing_name, error):
    # Count only REAL consolidation failures toward the self-healer cap (so
    # finalize/no-op passes don't burn the budget).
    attempts = cint(frappe.db.get_value("POS Register Session", session_name, "closing_attempts")) + 1
    values = {
        "closing_status": "Failed",
        "closing_error": _short(error),
        "closing_attempts": attempts,
    }
    if closing_name:
        values["pos_closing_entry"] = closing_name
    # status stays "Closing" — the shift is finalised operationally but its
    # consolidation must still complete (retry / self-healer).
    frappe.db.set_value("POS Register Session", session_name, values)
    frappe.db.commit()


def _opening_closed(opening_name):
    return frappe.db.get_value("POS Opening Entry", opening_name, "status") == "Closed"


def _short(value, length=480):
    return str(value)[:length] if value is not None else None


# ---------------------------------------------------------------------------
# Self-healer (scheduled) — converge any stuck shift to Closed
# ---------------------------------------------------------------------------

def reconcile_stuck_closings():
    """Scheduled backstop: re-drive every session stuck in 'Closing' toward
    'Closed'. Idempotent and serialized behind the same lock as live closings,
    so it can never collide with an in-flight close."""
    stuck = frappe.get_all(
        "POS Register Session",
        filters={"status": "Closing"},
        fields=["name", "closing_attempts", "closing_error"],
        order_by="closing_started_at asc",
        limit_page_length=50,
    )
    for row in stuck:
        # Cap automatic retries so a genuinely broken shift surfaces for a human
        # instead of looping forever; the manual retry button still works.
        if cint(row.closing_attempts) >= 30:
            frappe.log_error(
                title="LumenPOS register stuck — manual closing needed",
                message=f"Session {row.name} has failed to consolidate {row.closing_attempts} times "
                f"and is no longer auto-retried.\n\nLast error:\n{row.closing_error}",
            )
            continue
        try:
            build_closing_entry(row.name)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="LumenPOS closing reconcile failed", message=frappe.get_traceback()
            )
    _alert_orphan_invoices()


def _alert_orphan_invoices():
    """Surface any submitted POS Invoice that is tagged to an already-Closed
    session but never got consolidated (e.g. a manual desk edit that re-tagged
    an invoice after close). The Open->Closing->Closed flow + the sell-time row
    lock prevent these from forming normally; this is a visibility backstop so
    an admin sees it in the Error Log rather than it sitting silently un-posted."""
    orphans = frappe.db.sql(
        """
        select pi.name
        from `tabPOS Invoice` pi
        join `tabPOS Register Session` s on s.name = pi.lumenpos_session
        where pi.docstatus = 1 and coalesce(pi.consolidated_invoice, '') = ''
          and pi.status != 'Consolidated' and s.status = 'Closed'
        limit 50
        """,
        as_dict=True,
    )
    if orphans:
        frappe.log_error(
            title="LumenPOS un-consolidated invoices on closed shifts",
            message="These submitted POS Invoices belong to a closed shift but were "
            "never consolidated — consolidate them from the desk:\n"
            + "\n".join(o.name for o in orphans),
        )


def _acquire_lock(timeout=55):
    """Cluster-wide advisory lock (MariaDB GET_LOCK) so only one consolidation
    runs at a time across all workers/nodes."""
    try:
        result = frappe.db.sql("select get_lock(%s, %s)", (CLOSING_LOCK, timeout))
        return bool(result and result[0][0] == 1)
    except Exception:
        # If advisory locks aren't available, proceed (best effort).
        return True


def _release_lock():
    try:
        frappe.db.sql("select release_lock(%s)", (CLOSING_LOCK,))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Status + history
# ---------------------------------------------------------------------------

@frappe.whitelist()
def closing_entry_status(session):
    """Poll the close/consolidation state for a session."""
    if not frappe.has_permission("POS Register Session", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    # Status polling is benign (status + last error) and the next cashier needs
    # it to know when a stuck shift on their register has cleared, so it's
    # gated only by read permission, not ownership.
    doc = frappe.db.get_value(
        "POS Register Session",
        session,
        ["status", "closing_status", "closing_error", "pos_closing_entry"],
        as_dict=True,
    ) or frappe._dict()
    return {
        "status": doc.status,
        "closing_status": doc.closing_status,
        "closing_error": doc.closing_error,
        "pos_closing_entry": doc.pos_closing_entry,
    }


@frappe.whitelist()
def list_sessions(pos_profile, limit=20):
    """Closed + still-finalising register sessions for the history panel, with
    their native POS Opening/Closing Entry links and count differences."""
    if not frappe.has_permission("POS Register Session", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    filters = {"pos_profile": pos_profile, "status": ["in", ["Closed", "Closing"]]}
    # Cashiers see only their own shifts; managers see the whole register.
    if not _is_manager():
        filters["opened_by"] = frappe.session.user
    sessions = frappe.get_all(
        "POS Register Session",
        filters=filters,
        fields=[
            "name", "opened_by", "opened_at", "closed_at", "opening_float",
            "total_sales", "total_discounts", "sales_count", "status",
            "closing_status", "closing_error",
            "pos_opening_entry", "pos_closing_entry",
        ],
        order_by="closed_at desc",
        limit_page_length=min(int(limit), 50),
    )
    for session in sessions:
        counts = frappe.get_all(
            "POS Register Payment Count",
            filters={"parent": session.name},
            fields=["mode_of_payment", "expected_amount", "counted_amount", "difference"],
            order_by="idx asc",
        )
        session["counts"] = counts
        session["total_difference"] = flt(sum(flt(c.difference) for c in counts), 2)
    return sessions


def _get_reconciliation_row(closing, mode_of_payment):
    for row in closing.payment_reconciliation:
        if row.mode_of_payment == mode_of_payment:
            return row
    return closing.append(
        "payment_reconciliation",
        {"mode_of_payment": mode_of_payment, "opening_amount": 0, "expected_amount": 0},
    )


def _accumulate_payment(closing, mode_of_payment, amount):
    row = _get_reconciliation_row(closing, mode_of_payment)
    row.expected_amount = flt(row.expected_amount) + flt(amount)


def _accumulate_tax(closing, tax):
    for row in closing.taxes:
        if row.account_head == tax.account_head:
            row.amount = flt(row.amount) + flt(tax.tax_amount)
            return
    closing.append(
        "taxes",
        {"account_head": tax.account_head, "rate": tax.rate, "amount": flt(tax.tax_amount)},
    )


def _payments_by_mode(session):
    # POS Invoice reuses the Sales Invoice Payment child doctype
    rows = frappe.db.sql(
        """
        select sip.mode_of_payment, sum(sip.amount) as amount
        from `tabSales Invoice Payment` sip
        join `tabPOS Invoice` pi on pi.name = sip.parent and sip.parenttype = 'POS Invoice'
        where pi.lumenpos_session = %s and pi.docstatus = 1
        group by sip.mode_of_payment
        """,
        session,
        as_dict=True,
    )
    result = {}
    for row in rows:
        result[row.mode_of_payment] = flt(row.amount)

    change = frappe.db.sql(
        """
        select coalesce(sum(change_amount), 0) from `tabPOS Invoice`
        where lumenpos_session = %s and docstatus = 1
        """,
        session,
    )[0][0]
    if change:
        cash_modes = set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))
        for mode in result:
            if mode in cash_modes:
                result[mode] = flt(result[mode] - change)
                break
    return result
