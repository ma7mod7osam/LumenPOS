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
from lumenpos import erpnext_compat

LIVE_STATES = ["Open", "Closing"]  # a shift that blocks opening another
CLOSING_LOCK = "lumenpos_pos_closing"


def _cash_modes():
    return set(frappe.get_all("Mode of Payment", {"type": "Cash"}, pluck="name"))


def _drawer_mode(pos_profile):
    """THE single mode of payment that represents this till's cash drawer.

    A site often configures other tenders (delivery apps, "On Account") as type
    Cash. Treating every Cash-type mode as the drawer wrote the opening float to
    all of them, made the X-report add the float once per mode, and let change
    come off whichever mode happened to be first. The drawer is ONE mode:
    the profile's default Cash-type payment, else its first Cash-type payment
    (profile row order — deterministic), else plain "Cash" if it exists.
    Returns None when the profile takes no cash at all."""
    cash = _cash_modes()
    if not cash:
        return None
    try:
        profile = frappe.get_cached_doc("POS Profile", pos_profile)
    except Exception:
        return "Cash" if "Cash" in cash else None
    rows = [r for r in (profile.payments or []) if r.mode_of_payment in cash]
    for row in rows:
        if row.get("default"):
            return row.mode_of_payment
    if rows:
        return rows[0].mode_of_payment
    return "Cash" if "Cash" in cash else None


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
    """Opening is ALWAYS a fresh shift. A shift can never be resumed.

    The REGISTER SESSION's status is the only truth. Native POS Opening Entries
    are downstream paperwork and are never consulted to decide whether a shift is
    live — a failed or slow close leaves one "Open" indefinitely, and keying off
    that is exactly how the next cashier ends up resurrecting a dead shift (the
    single most common complaint about the stock ERPNext POS).

    `resume_opening_entry` and `force_new` are accepted and IGNORED: they only
    remain in the signature so a browser running cached JS doesn't fail on an
    unexpected argument.
    """
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    opening_float = flt(opening_float)
    si_mode = profile.get("lumenpos_invoice_mode") == "Sales Invoice"
    # SI mode normally runs a lightweight cash shift (no POS Opening/Closing
    # Entry). A POS Profile can opt back into the entries for cash supervision —
    # then SI mode opens/closes exactly like POS Invoice mode, minus the
    # consolidation step (there are no POS Invoices to merge at close).
    lightweight = si_mode and not cint(profile.get("lumenpos_si_opening_closing"))

    needed = "POS Register Session" if lightweight else "POS Opening Entry"
    if not frappe.has_permission(needed, "create"):
        frappe.throw(_("You are not permitted to open a register"), frappe.PermissionError)

    # 1) This register must have no live shift (Open or still-finalising Closing).
    # In "Per cashier" scope the shift belongs to the individual, so the check is
    # scoped to this user — several cashiers can trade on one counter, each with
    # their own drawer and Z-report.
    from lumenpos.api.session import shift_scope

    live_filters = {"pos_profile": profile.name, "status": ["in", LIVE_STATES]}
    if shift_scope() == "Per cashier":
        live_filters["opened_by"] = frappe.session.user
    existing = frappe.db.get_value(
        "POS Register Session", live_filters, ["name", "status"], as_dict=True
    )
    if existing:
        if existing.status == "Open":
            frappe.throw(
                _("Register {0} already has an open session ({1}).").format(
                    profile.name, existing.name
                )
            )
        # status == "Closing": the cashier already closed this shift. Its POS
        # Closing Entry consolidation runs (and self-heals) in the background and
        # must NEVER block the store from opening the next shift — no matter the
        # closing_status (Pending / Queued / Failed). Open a fresh shift now; the
        # stuck close keeps retrying independently, so no invoice is lost.
        return _force_new_after_failure(profile, opening_float, existing.name)

    # Lightweight Sales Invoice cash shift — just the float, no ERPNext POS
    # Opening Entry. Sales post as Sales Invoices directly, so there's nothing to
    # consolidate at close. (Skipped when the profile opts into POS Opening/
    # Closing Entries — that path falls through to the full opening below.)
    if lightweight:
        sess = frappe.get_doc(
            {
                "doctype": "POS Register Session",
                "pos_profile": profile.name,
                "opened_by": frappe.session.user,
                "opened_at": now_datetime(),
                "status": "Open",
                "opening_float": opening_float,
            }
        )
        sess.insert()
        _audit_register("open", sess.name, profile.name, opening_float)
        return get_open_session(pos_profile)

    # 2) Nothing live on this register -> always a brand-new shift. Any stale
    # native "Open" POS Opening Entry left behind by a failed close or by the
    # stock POS is ignored on purpose (see the docstring).
    return _create_fresh_session(profile, opening_float)


def _create_fresh_session(profile, opening_float, bypass_live_guard=False):
    """Build a new POS Opening Entry + Register Session for this register.

    `opening_entry.flags.ignore_validate` is set ALWAYS: ERPNext core refuses a
    second open entry per cashier, and an old native-POS leftover (or one from a
    close whose consolidation never finished) must never be able to stop a shop
    opening tomorrow. The session's own validation is only bypassed when we are
    deliberately jumping over a still-"Closing" shift."""
    # The float belongs to the ONE drawer mode (see _drawer_mode) — never to
    # every Cash-type tender.
    drawer = _drawer_mode(profile.name)
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
                    "opening_amount": opening_float if row.mode_of_payment == drawer else 0,
                }
                for row in profile.payments
            ],
        }
    )
    opening_entry.flags.ignore_validate = True
    opening_entry.insert(ignore_permissions=True)
    opening_entry.submit()

    sess = frappe.get_doc(
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
    if bypass_live_guard:
        sess.flags.ignore_validate = True
    sess.insert()
    _audit_register("open", sess.name, profile.name, opening_float)
    return get_open_session(profile.name)


def _role_emails(role):
    """Enabled users holding a role, with an email address."""
    if not role:
        return []
    users = frappe.get_all("Has Role", filters={"role": role}, pluck="parent")
    if not users:
        return []
    return frappe.get_all(
        "User",
        filters={"name": ["in", list(set(users))], "enabled": 1},
        pluck="email",
    )


def _maybe_alert_variance(doc):
    """Email a role when a counted drawer differs from expected by more than the
    threshold. RECORD AND NOTIFY — never an approval gate: a close must not be
    blocked waiting for a manager, and a shift left open is worse than a
    variance. Entirely best-effort; a mail failure only logs."""
    try:
        settings = frappe.get_cached_doc("LumenPOS Settings")
        if not settings.get("variance_alert_enabled"):
            return
        threshold = flt(settings.get("variance_alert_threshold"))
        role = settings.get("variance_alert_role")
        recipients = _role_emails(role)
        if not recipients:
            return
        rows = [
            r for r in (doc.get("payment_counts") or [])
            if abs(flt(r.difference)) > threshold
        ]
        if not rows:
            return
        cells = "".join(
            f"<tr><td>{frappe.utils.escape_html(r.mode_of_payment or '')}</td>"
            f"<td align='right'>{flt(r.expected_amount):,.2f}</td>"
            f"<td align='right'>{flt(r.counted_amount):,.2f}</td>"
            f"<td align='right'><b>{flt(r.difference):,.2f}</b></td></tr>"
            for r in rows
        )
        frappe.sendmail(
            recipients=recipients,
            subject=_("Cash variance on {0} ({1})").format(doc.pos_profile, doc.name),
            message=(
                f"<p>{_('A register closed with a counted difference over the alert threshold.')}</p>"
                f"<p><b>{_('Outlet')}:</b> {frappe.utils.escape_html(doc.pos_profile or '')}<br>"
                f"<b>{_('Shift')}:</b> {doc.name}<br>"
                f"<b>{_('Opened by')}:</b> {frappe.utils.escape_html(doc.opened_by or '')}<br>"
                f"<b>{_('Closed by')}:</b> {frappe.utils.escape_html(frappe.session.user)}</p>"
                "<table border='1' cellpadding='6' cellspacing='0'>"
                f"<tr><th>{_('Payment')}</th><th>{_('Expected')}</th>"
                f"<th>{_('Counted')}</th><th>{_('Difference')}</th></tr>"
                f"{cells}</table>"
            ),
        )
    except Exception:
        frappe.log_error(
            title="LumenPOS variance alert failed", message=frappe.get_traceback()
        )


def _force_new_after_failure(profile, opening_float, stuck_session):
    """The previous shift is still 'Closing' (consolidation pending, queued or
    failed) — let the store keep trading. Open a fresh shift now; the stuck one
    stays in 'Closing' and the self-healer keeps retrying its consolidation, so
    no invoice is lost.

    NOTE: deliberately does NOT require "POS Closing Entry: create". The cashier
    opening the store must never be blocked by a colleague's stuck close."""
    # Nudge the stuck shift to consolidate once more right now.
    _enqueue_consolidation(stuck_session)
    return _create_fresh_session(profile, opening_float, bypass_live_guard=True)


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
    """Expected takings per payment mode for the close-register screen, and for
    the mid-shift X-report.

    READ-ONLY on purpose — no owner/manager check here. Reading a shift's
    figures is not a mutation, and requiring ownership broke the X-report for
    any cashier working a till a colleague opened. The mutating callers
    (add_cash_movement, close_register) each call _assert_owner_or_manager
    themselves, so supervision is unchanged."""
    if not frappe.has_permission("POS Register Session", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("POS Register Session", session)
    # Which sale doctype this shift posted — by the profile's mode, NOT by whether
    # an opening entry exists (an SI shift can now have one for cash control).
    from lumenpos.api.sales import _table_doctype

    sale_doctype = _table_doctype(doc.pos_profile)
    payments = _payments_by_mode(doc.name, sale_doctype, _drawer_mode(doc.pos_profile))

    # The float and cash in/out belong to the ONE drawer mode. Adding them to
    # every Cash-type tender counted the float once per mode on the X-report and
    # at close (a site with delivery apps typed as Cash saw it 3-4 times over).
    drawer = _drawer_mode(doc.pos_profile)
    cash_in = sum(m.amount for m in (doc.cash_movements or []) if m.movement_type == "Cash In")
    cash_out = sum(m.amount for m in (doc.cash_movements or []) if m.movement_type == "Cash Out")

    expected = []
    for mode, amount in payments.items():
        row = {"mode_of_payment": mode, "expected_amount": flt(amount, 2)}
        if mode == drawer:
            row["expected_amount"] = flt(amount + (doc.opening_float or 0) + cash_in - cash_out, 2)
            row["is_cash"] = 1
        expected.append(row)

    if not any(r.get("is_cash") for r in expected) and (doc.opening_float or cash_in or cash_out):
        expected.append(
            {
                "mode_of_payment": drawer or "Cash",
                "expected_amount": flt((doc.opening_float or 0) + cash_in - cash_out, 2),
                "is_cash": 1,
            }
        )

    totals = frappe.get_all(
        sale_doctype,
        filters={"lumenpos_session": doc.name, "docstatus": 1},
        fields=[
            "count(name) as sales_count",
            "sum(grand_total) as total_sales",
            "sum(discount_amount) as invoice_discounts",
        ],
    )
    # `sale_doctype` is a fixed doctype name (POS Invoice / Sales Invoice from
    # _table_doctype), not user input, and a table identifier can't be a bound
    # param; the session filter is parameterized. Safe despite the f-string.
    line_discounts = frappe.db.sql(  # nosemgrep
        f"""
        select coalesce(sum(pii.discount_amount * pii.qty), 0)
        from `tab{sale_doctype} Item` pii
        join `tab{sale_doctype}` pi on pi.name = pii.parent
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
def close_register(session, counted, closing_note=None, expected_invoice_count=None):
    """Flip the session to 'Closing' (committed immediately, so it can never be
    sold-on or resumed again), then consolidate in a serialized background job.
    The shift only reaches 'Closed' once consolidation succeeds."""
    if isinstance(counted, str):
        counted = json.loads(counted)

    doc = frappe.get_doc("POS Register Session", session)
    # A session with no POS Opening Entry (Sales Invoice mode / legacy) closes
    # directly — there is no POS Closing Entry to create or consolidate.
    needed = "POS Register Session" if not doc.get("pos_opening_entry") else "POS Closing Entry"
    if not frappe.has_permission(needed, "create"):
        frappe.throw(_("You are not permitted to close a register"), frappe.PermissionError)
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

    # STALE-CLOSING-SCREEN GUARD. The cashier counts the drawer against the
    # figures on their screen. If a sale landed from another window or device
    # after that screen loaded, those figures — and therefore the variance they
    # just signed off — are wrong. The client sends the sales count it displayed;
    # if the shift has more now, refuse and make them re-read the screen.
    # (Chosen over blocking sales while a closing screen is open: a second device
    # never knows about that screen, whereas this check covers every path.)
    if expected_invoice_count not in (None, ""):
        from lumenpos.api.sales import _table_doctype

        current = frappe.db.count(
            _table_doctype(doc.pos_profile),
            {"lumenpos_session": doc.name, "docstatus": 1},
        )
        if cint(expected_invoice_count) != current:
            frappe.throw(
                _(
                    "New sales were recorded after the closing screen was loaded. "
                    "Refresh the closing screen, re-check the counts, then close again."
                ),
                title=_("Closing figures out of date"),
            )

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

    # Nothing unconfirmed survives the shift: void pending / approved-but-unused
    # approval requests BEFORE the flip, so none can be spent on the next shift.
    try:
        from lumenpos.api import approval_requests

        approval_requests.expire_session_requests(doc.name)
    except Exception:
        frappe.log_error(title="LumenPOS: expiring shift requests failed",
                         message=frappe.get_traceback())

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
    # nor resumable, whatever happens to the consolidation next. Intentional —
    # the state must survive even if the consolidation step below fails.
    frappe.db.commit()  # nosemgrep

    # AFTER the flip is committed: an email hiccup must never undo a close.
    _maybe_alert_variance(doc)

    if doc.get("pos_opening_entry"):
        _enqueue_consolidation(doc.name, counted)
        queued = True
    else:
        # No opening entry (Sales Invoice mode / legacy) — nothing to consolidate;
        # the shift closes outright. Reflect that on the doc for the response.
        _mark_closed(doc.name, None)
        doc.status = "Closed"
        doc.closing_status = "Submitted"
        queued = False

    _audit_register(
        "close",
        doc.name,
        doc.pos_profile,
        doc.total_sales,
        detail=_("{0} sales · takings {1}").format(doc.sales_count, doc.total_sales),
    )
    return _close_result(doc, queued=queued)


def _audit_register(kind, session_name, profile_name, amount, detail=None):
    """Best-effort audit entry for opening/closing the till."""
    from lumenpos.api import audit

    action = audit.REGISTER_OPEN if kind == "open" else audit.REGISTER_CLOSE
    audit.log(
        action,
        detail=detail or (_("Opened with float {0}").format(amount) if kind == "open" else None),
        amount=amount,
        reference_doctype="POS Register Session",
        reference_name=session_name,
        pos_profile=profile_name,
    )


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
    from lumenpos.erpnext_compat import merge_log_api

    create_merge_logs, get_invoice_customer_map = merge_log_api()

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
        # Enqueued consolidation job — commit the finalised state so it persists.
        frappe.db.commit()  # nosemgrep
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

    from lumenpos.api.sales import _table_doctype

    # The one mode that represents this till's cash drawer (float, change and
    # cash in/out all belong to it alone).
    drawer = _drawer_mode(session_doc.pos_profile)
    sale_doctype = _table_doctype(session_doc.pos_profile)
    opening = frappe.get_doc("POS Opening Entry", session_doc.get("pos_opening_entry"))
    invoices = frappe.get_all(
        sale_doctype,
        filters={"lumenpos_session": session_doc.name, "docstatus": 1},
        fields=["name", "customer", "grand_total", "is_return", "posting_date"],
    )

    closing = erpnext_compat.new_doc("POS Closing Entry")
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
        # pos_transactions links POS Invoices only. A Sales-Invoice-mode shift
        # leaves it empty (so _consolidate_now finds nothing to merge and just
        # finalizes), but its takings still roll into the payment reconciliation
        # and the Z-report totals below — the cash-control point of the entry.
        if sale_doctype == "POS Invoice":
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
        full = frappe.get_doc(sale_doctype, inv.name)
        grand_total += flt(full.grand_total)
        net_total += flt(full.net_total)
        qty_total += sum(flt(i.qty) for i in full.items)
        for tax in full.taxes or []:
            _accumulate_tax(closing, tax)
        for payment in full.payments or []:
            if payment.amount:
                _accumulate_payment(closing, payment.mode_of_payment, payment.amount)
        if full.change_amount:
            # Change comes OUT OF THE DRAWER — not out of whichever Cash-type
            # tender happens to sort first (delivery apps are often typed Cash).
            for row in closing.payment_reconciliation:
                if row.mode_of_payment == drawer:
                    row.expected_amount = flt(row.expected_amount) - flt(full.change_amount)
                    break

    cash_modes = _cash_modes()
    cash_in = sum(m.amount for m in (session_doc.cash_movements or []) if m.movement_type == "Cash In")
    cash_out = sum(m.amount for m in (session_doc.cash_movements or []) if m.movement_type == "Cash Out")
    drawer_applied = False
    for detail in opening.balance_details:
        row = _get_reconciliation_row(closing, detail.mode_of_payment)
        opening_amt = flt(detail.opening_amount)
        # SELF-HEAL a shift opened before the single-drawer fix: the float was
        # written to EVERY Cash-type row back then, so crediting each one would
        # inflate expected by a multiple of the float. Keep the drawer's copy only.
        if opening_amt and detail.mode_of_payment != drawer and detail.mode_of_payment in cash_modes:
            opening_amt = 0
        row.opening_amount = opening_amt
        row.expected_amount = flt(row.expected_amount) + opening_amt
        # Net the shift's cash in/out into the drawer row so expected matches
        # what is physically in the till.
        if detail.mode_of_payment == drawer:
            row.expected_amount = flt(row.expected_amount) + cash_in - cash_out
            drawer_applied = True
    if not drawer_applied and (cash_in or cash_out):
        # The drawer mode isn't on this opening entry (profile changed mid-life)
        # — fall back to the first Cash-type row so the movements aren't lost.
        for row in closing.payment_reconciliation:
            if row.mode_of_payment in cash_modes:
                row.expected_amount = flt(row.expected_amount) + cash_in - cash_out
                break

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
    # Enqueued consolidation job — persist the closed state immediately.
    frappe.db.commit()  # nosemgrep


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
    # Enqueued consolidation job — persist the failure state so the self-healer
    # can retry from a known point.
    frappe.db.commit()  # nosemgrep


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


def _payments_by_mode(session, doctype="POS Invoice", drawer=None):
    # Both POS Invoice and Sales Invoice use the Sales Invoice Payment child.
    # `doctype` is a fixed doctype name (POS Invoice / Sales Invoice), not user
    # input, and can't be a bound param as a table identifier; the session filter
    # is parameterized. Safe despite the f-string.
    rows = frappe.db.sql(  # nosemgrep
        f"""
        select sip.mode_of_payment, sum(sip.amount) as amount
        from `tabSales Invoice Payment` sip
        join `tab{doctype}` pi on pi.name = sip.parent and sip.parenttype = '{doctype}'
        where pi.lumenpos_session = %s and pi.docstatus = 1
        group by sip.mode_of_payment
        """,
        session,
        as_dict=True,
    )
    result = {}
    for row in rows:
        result[row.mode_of_payment] = flt(row.amount)

    # `doctype` is a fixed doctype name (POS Invoice / Sales Invoice), not user
    # input; a table identifier can't be a bound param and the session filter is
    # parameterized. Safe despite the f-string.
    change = frappe.db.sql(  # nosemgrep
        f"""
        select coalesce(sum(change_amount), 0) from `tab{doctype}`
        where lumenpos_session = %s and docstatus = 1
        """,
        session,
    )[0][0]
    if change:
        # Change is given from the DRAWER. Falling back to "first Cash-type mode"
        # deducted it from whichever tender sorted first (a delivery app typed
        # as Cash, say) and left the drawer over by that amount.
        cash_modes = _cash_modes()
        target = drawer if drawer in result else None
        if target is None:
            target = next((m for m in result if m in cash_modes), None)
        if target:
            result[target] = flt(result[target] - change)
    return result

# ---------------------------------------------------------------------------
# Forgotten-shift alert (POS Shift Schedule)
# ---------------------------------------------------------------------------

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _as_time(value):
    """Frappe returns a Time field as a timedelta — normalise to a `time`."""
    import datetime

    if value is None:
        return None
    if isinstance(value, datetime.time):
        return value
    if isinstance(value, datetime.timedelta):
        total = int(value.total_seconds())
        return datetime.time((total // 3600) % 24, (total % 3600) // 60, total % 60)
    try:
        parts = [int(p) for p in str(value).split(":")[:3]]
        while len(parts) < 3:
            parts.append(0)
        return datetime.time(*parts)
    except Exception:
        return None


def _scheduled_end(schedule_name, opened_at):
    """When SHOULD the shift that was opened at `opened_at` have ended?

    Builds candidate windows from the opening day AND the previous day, because a
    shift whose end time is at or before its start crosses midnight — a 22:00→06:00
    shift opened at 23:40 belongs to the PREVIOUS day's window. Returns the end of
    the window containing the open time; failing that, the next window starting
    later the same day (a cashier who opens a few minutes early); else None so the
    caller falls back to a flat number of hours."""
    import datetime

    if not schedule_name or not opened_at:
        return None
    try:
        slots = frappe.get_all(
            "POS Shift Schedule Slot",
            filters={"parent": schedule_name, "parenttype": "POS Shift Schedule"},
            fields=["day", "start_time", "end_time"],
        )
    except Exception:
        return None
    if not slots:
        return None

    candidates = []
    for base_offset in (1, 0):  # previous day first, then the opening day
        base_date = opened_at.date() - datetime.timedelta(days=base_offset)
        day_name = DAY_NAMES[base_date.weekday()]
        for slot in slots:
            if slot.day not in ("Every Day", day_name):
                continue
            start_t, end_t = _as_time(slot.start_time), _as_time(slot.end_time)
            if not start_t or not end_t:
                continue
            start = datetime.datetime.combine(base_date, start_t)
            end = datetime.datetime.combine(base_date, end_t)
            if end <= start:  # crosses midnight
                end += datetime.timedelta(days=1)
            candidates.append((start, end))

    inside = [end for start, end in candidates if start <= opened_at < end]
    if inside:
        return min(inside)
    later = [end for start, end in candidates if start > opened_at]
    return min(later) if later else None


def notify_overdue_sessions():
    """Hourly: email a role about shifts that are still open well past when they
    should have ended. ALERT ONLY — never an auto-close: a close without a real
    cash count produces figures nobody can trust."""
    try:
        settings = frappe.get_cached_doc("LumenPOS Settings")
        if not settings.get("overdue_alert_enabled"):
            return
        role = settings.get("overdue_alert_role")
        recipients = _role_emails(role)
        if not recipients:
            return
        grace = cint(settings.get("overdue_grace_minutes")) or 60
        fallback_hours = cint(settings.get("overdue_alert_hours")) or 14
        import datetime

        now = now_datetime()
        rows = frappe.get_all(
            "POS Register Session",
            filters={"status": "Open", "overdue_notified": 0},
            fields=["name", "pos_profile", "opened_by", "opened_at"],
        )
        for row in rows:
            if not row.opened_at:
                continue
            schedule = frappe.db.get_value(
                "POS Profile", row.pos_profile, "lumenpos_shift_schedule"
            )
            end = _scheduled_end(schedule, row.opened_at)
            deadline = (
                end + datetime.timedelta(minutes=grace)
                if end
                else row.opened_at + datetime.timedelta(hours=fallback_hours)
            )
            if now < deadline:
                continue
            frappe.sendmail(
                recipients=recipients,
                subject=_("Register still open: {0}").format(row.pos_profile),
                message=(
                    f"<p>{_('A register is still open well past the end of its shift.')}</p>"
                    f"<p><b>{_('Outlet')}:</b> {frappe.utils.escape_html(row.pos_profile or '')}<br>"
                    f"<b>{_('Shift')}:</b> {row.name}<br>"
                    f"<b>{_('Opened by')}:</b> {frappe.utils.escape_html(row.opened_by or '')}<br>"
                    f"<b>{_('Opened at')}:</b> {row.opened_at}<br>"
                    f"<b>{_('Expected to end')}:</b> {end or _('not scheduled')}</p>"
                    f"<p>{_('The till has NOT been closed automatically — a close without a real cash count is worthless.')}</p>"
                ),
            )
            frappe.db.set_value(
                "POS Register Session", row.name, "overdue_notified", 1, update_modified=False
            )
    except Exception:
        frappe.log_error(
            title="LumenPOS overdue-shift alert failed", message=frappe.get_traceback()
        )
