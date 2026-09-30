# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Register lifecycle, robust open / close with reliable consolidation.

Opening the register creates BOTH:
  - a LumenPOS `POS Register Session` (operational: cash float, cash in/out)
  - a native ERPNext `POS Opening Entry` (so POS Invoices validate and the
    closing can consolidate them into Sales Invoices)

CLOSING, the hard part. ERPNext consolidates the shift's POS Invoices into
Sales Invoices when a `POS Closing Entry` is submitted. For >=10 invoices it
*enqueues* that consolidation; if it fails (heavy load, or two shifts
consolidating the same customer at once) the closing entry is left "Failed",
its `frappe.db.rollback()` undoes every merge log (so nothing is half-posted),
and, critically, the linked POS Opening Entry stays "Open". The old code keyed
"is a shift open?" partly off that opening entry, so a failed close let the next
cashier resume a dead shift. The endless loop.

This module fixes it with a strict state machine on the LumenPOS session:

    Open  ->  Closing  ->  Closed
                  └─ (consolidation failed) stays "Closing", closing_status=Failed

  * The moment a cashier closes, the session flips to "Closing" and is committed.
    From then on it is NOT sellable (get_open_session only returns "Open") and
    NOT resumable, regardless of whether consolidation later succeeds or fails.
  * Consolidation runs in a background job, SERIALIZED behind a cluster-wide DB
    lock and driven SYNCHRONOUSLY (we call create_merge_logs ourselves instead
    of letting ERPNext enqueue it), so two shifts can never deadlock each other.
  * A failed consolidation is safe to retry (ERPNext rolls back atomically), so
    the retry button and a scheduled self-healer keep re-running it until the
    shift reaches "Closed", at which point the opening entry is closed too.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate, now_datetime, nowdate, nowtime

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
    (profile row order, deterministic), else plain "Cash" if it exists.
    Returns None when the profile takes no cash at all."""
    cash = _cash_modes()
    if not cash:
        return None
    try:
        profile = frappe.get_cached_doc("POS Profile", pos_profile)
    except Exception:
        return "Cash" if "Cash" in cash else None
    # A drawer in another currency ("Cash USD") is never the main drawer, even
    # when it sits first on the outlet or is ticked as its default.
    foreign = _foreign_drawers(pos_profile)
    rows = [r for r in (profile.payments or []) if r.mode_of_payment in cash and r.mode_of_payment not in foreign]
    for row in rows:
        if row.get("default"):
            return row.mode_of_payment
    if rows:
        return rows[0].mode_of_payment
    return "Cash" if "Cash" in cash else None


def _foreign_drawers(pos_profile):
    """The outlet's cash drawers in another currency, {mode: currency}: a
    Cash-type tender whose account is not in the company currency ("Cash USD",
    lumenpos.currency). Each keeps its own float, movements, count and change,
    in its own money, apart from the main drawer."""
    from lumenpos import currency

    try:
        profile = frappe.get_cached_doc("POS Profile", pos_profile)
    except Exception:
        return {}
    ccy = currency.company_currency(profile.company)
    cash = _cash_modes()
    out = {}
    for row in profile.payments or []:
        if row.mode_of_payment in cash:
            mode_ccy = currency.mode_currency(row.mode_of_payment, profile.company)
            if mode_ccy != ccy:
                out[row.mode_of_payment] = mode_ccy
    return out


def _in_window(recorded_at, since=None, until=None):
    """Whether a cash movement belongs to the part of a shift from `since`
    (exclusive) to `until` (inclusive): one ERPNext day of a shift that ran
    past midnight (roll_day). No bounds, the whole shift."""
    if since is None and until is None:
        return True
    when = get_datetime(recorded_at) if recorded_at else None
    if when is None:
        return since is None
    if since is not None and when <= get_datetime(since):
        return False
    return until is None or when <= get_datetime(until)


def _drawer_movements(session_doc, mode, main_drawer, since=None, until=None):
    """(cash in, cash out) of ONE drawer. The main drawer takes every movement
    recorded without a drawer, which is all of them before drawers had
    currencies. `since` and `until` keep to one ERPNext day of the shift."""
    cash_in = cash_out = 0.0
    for m in session_doc.get("cash_movements") or []:
        if (m.get("mode_of_payment") or main_drawer) != mode:
            continue
        if not _in_window(m.get("recorded_at"), since, until):
            continue
        if m.movement_type == "Cash In":
            cash_in += flt(m.amount)
        elif m.movement_type == "Cash Out":
            cash_out += flt(m.amount)
    return cash_in, cash_out


def _foreign_floats(session_doc):
    return {r.mode_of_payment: flt(r.amount) for r in (session_doc.get("foreign_floats") or [])}


def _clean_floats(pos_profile, floats):
    """{mode: amount} for this outlet's drawers in another currency only, and
    none while selling in other currencies is off: the drawers stay on the
    outlet after the switch, but a new shift has no use for them."""
    from lumenpos import currency

    if isinstance(floats, str):
        floats = json.loads(floats or "{}")
    if not currency.enabled():
        return {}
    foreign = _foreign_drawers(pos_profile)
    return {mode: flt(amount) for mode, amount in (floats or {}).items() if mode in foreign and flt(amount) > 0}


def _float_rows(pos_profile, floats):
    foreign = _foreign_drawers(pos_profile)
    return [
        {"mode_of_payment": mode, "currency": foreign.get(mode), "amount": flt(amount)}
        for mode, amount in (floats or {}).items()
    ]


def _shift_rates(session_doc):
    """{currency: rate to company currency} the shift fixed (lumenpos.currency)."""
    return {r.currency: flt(r.exchange_rate) for r in (session_doc.get("currency_rates") or [])}


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

def _assert_no_other_open_shift(pos_profile):
    """LumenPOS Settings.one_shift_per_user on: refuse a new shift while this
    user still has one Open at another outlet they can reach, naming it. Off
    (the default), a person may hold shifts at several outlets at once (a
    manager covering branches) and the Open Register dialog only reminds them.

    Nobody is ever locked out by it: a shift whose close was started is
    Closing, not Open, even when that close failed; and an open shift at an
    outlet the user can no longer reach (disabled, access removed) does not
    count, since they could not close it themselves (a manager does)."""
    if not cint(frappe.db.get_single_value("LumenPOS Settings", "one_shift_per_user") or 0):
        return
    from lumenpos.api.session import _other_open_registers

    others = [r for r in _other_open_registers(pos_profile) if r.get("reachable")]
    if others:
        frappe.throw(
            _("Close your open shift first: {0}. This shop allows one open shift per person at a time.").format(
                ", ".join("{0} ({1})".format(r["pos_profile"], r["session"]) for r in others)
            )
            + " "
            + _("If you cannot close it, a manager can close it for you from that outlet's Register page."),
            title=_("Shift already open"),
        )


@frappe.whitelist()
def open_register(pos_profile, opening_float=0, resume_opening_entry=None, force_new=0, floats=None):
    """Opening is ALWAYS a fresh shift. A shift can never be resumed.

    The REGISTER SESSION's status is the only truth. Native POS Opening Entries
    are downstream paperwork and are never consulted to decide whether a shift is
    live, a failed or slow close leaves one "Open" indefinitely, and keying off
    that is exactly how the next cashier ends up resurrecting a dead shift (the
    single most common complaint about the stock ERPNext POS).

    `resume_opening_entry` and `force_new` are accepted and IGNORED: they only
    remain in the signature so a browser running cached JS doesn't fail on an
    unexpected argument.
    """
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    from lumenpos.api import permissions as outlet_permissions

    outlet_permissions.assert_outlet(pos_profile)
    opening_float = flt(opening_float)
    # The float of each drawer in another currency ("Cash USD"), in its own
    # money (lumenpos.currency). Anything else sent is ignored.
    floats = _clean_floats(pos_profile, floats)
    si_mode = profile.get("lumenpos_invoice_mode") == "Sales Invoice"
    # SI mode normally runs a lightweight cash shift (no POS Opening/Closing
    # Entry). A POS Profile can opt back into the entries for cash supervision, 
    # then SI mode opens/closes exactly like POS Invoice mode, minus the
    # consolidation step (there are no POS Invoices to merge at close).
    lightweight = si_mode and not cint(profile.get("lumenpos_si_opening_closing"))

    needed = "POS Register Session" if lightweight else "POS Opening Entry"
    if not frappe.has_permission(needed, "create"):
        frappe.throw(_("You are not permitted to open a register"), frappe.PermissionError)
    from lumenpos.api import permissions

    if not permissions.can_open_register():
        frappe.throw(_("You are not allowed to open a register"), frappe.PermissionError)
    # 0) A shop may hold every person to one open shift at a time (Settings,
    # General, Register and shifts): one still open at another outlet is
    # closed first.
    _assert_no_other_open_shift(profile.name)

    # 1) This register must have no live shift (Open or still-finalising Closing).
    # In "Per cashier" scope the shift belongs to the individual, so the check is
    # scoped to this user, several cashiers can trade on one counter, each with
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
        # must NEVER block the store from opening the next shift, no matter the
        # closing_status (Pending / Queued / Failed). Open a fresh shift now; the
        # stuck close keeps retrying independently, so no invoice is lost.
        # ERPNext 16 is the exception: it refuses every sale while the outlet
        # still has the old shift's entry open, so that close is finished first.
        if not lightweight and erpnext_compat.one_open_shift_per_outlet():
            _assert_outlet_free(profile, closing_session=existing.name)
            return _create_fresh_session(profile, opening_float, floats=floats)
        return _force_new_after_failure(profile, opening_float, existing.name, floats)

    # Lightweight Sales Invoice cash shift, just the float, no ERPNext POS
    # Opening Entry. Sales post as Sales Invoices directly, so there's nothing to
    # consolidate at close. (Skipped when the profile opts into POS Opening/
    # Closing Entries, that path falls through to the full opening below.)
    if lightweight:
        sess = frappe.get_doc(
            {
                "doctype": "POS Register Session",
                "pos_profile": profile.name,
                "opened_by": frappe.session.user,
                "opened_at": now_datetime(),
                "status": "Open",
                "opening_float": opening_float,
                "foreign_floats": _float_rows(pos_profile, floats),
            }
        )
        sess.insert()
        _pin_rates(sess.name, profile)
        _audit_register("open", sess.name, profile.name, opening_float)
        return get_open_session(pos_profile)

    # 2) Nothing live on this register -> always a brand-new shift. Any stale
    # native "Open" POS Opening Entry left behind by a failed close or by the
    # stock POS is ignored on purpose (see the docstring), except on ERPNext
    # 16, which refuses every sale of an outlet that has one (see
    # _assert_outlet_free).
    if erpnext_compat.one_open_shift_per_outlet():
        _assert_outlet_free(profile)
    return _create_fresh_session(profile, opening_float, floats=floats)


def _assert_outlet_free(profile, closing_session=None):
    """ERPNext 16 only: before a new shift adds its POS Opening Entry, the
    outlet must have none open, or ERPNext refuses every one of its sales
    ("has multiple open POS Opening Entries"). A previous shift of ours still
    closing is finished now when it can be (it normally finishes in the
    background within seconds); whatever stays open is named, with what to do,
    instead of opening a shift that cannot sell. Also refuses when ERPNext is
    set to make Sales Invoices from the POS and this outlet makes POS Invoices."""
    refused = erpnext_compat.pos_invoice_refused()
    if refused and profile.get("lumenpos_invoice_mode") != "Sales Invoice":
        frappe.throw(refused, title=_("Invoice type"))
    if closing_session:
        try:
            build_closing_entry(closing_session)
        except Exception:
            frappe.log_error(title="LumenPOS: finishing a close before opening", message=frappe.get_traceback())
    still_open = frappe.get_all(
        "POS Opening Entry",
        filters={"pos_profile": profile.name, "status": "Open", "docstatus": 1},
        fields=["name", "user", "period_start_date"],
        order_by="period_start_date asc",
    )
    if not still_open:
        return
    lines = []
    for entry in still_open:
        who = frappe.utils.get_fullname(entry.user) if entry.user else ""
        since = frappe.utils.format_datetime(entry.period_start_date, "yyyy-MM-dd HH:mm")
        ours = frappe.db.get_value(
            "POS Register Session",
            {"pos_opening_entry": entry.name},
            ["name", "status", "closing_error"],
            as_dict=True,
        )
        if ours and ours.status == "Closing":
            lines.append(
                _("Shift {0} is still being closed ({1}): retry its close from the Register screen.").format(
                    ours.name, ours.closing_error or _("the close has not finished")
                )
            )
        elif ours and ours.status == "Open":
            lines.append(_("{0} has shift {1} open since {2}: close it first.").format(who, ours.name, since))
        else:
            lines.append(
                _("POS Opening Entry {0} (by {1}, since {2}) is open outside LumenPOS: close or cancel it in ERPNext.").format(
                    entry.name, who, since
                )
            )
    frappe.throw(
        _("ERPNext 16 lets an outlet sell with only one open shift, and {0} still has one:").format(profile.name)
        + "<br>"
        + "<br>".join(lines)
        + "<br>"
        + _("Several cashiers on one outlet each need their own POS Profile on ERPNext 16."),
        title=_("Outlet already open"),
    )


def _create_fresh_session(profile, opening_float, bypass_live_guard=False, floats=None):
    """Build a new POS Opening Entry + Register Session for this register.

    `opening_entry.flags.ignore_validate` is set ALWAYS: ERPNext core refuses a
    second open entry per cashier, and an old native-POS leftover (or one from a
    close whose consolidation never finished) must never be able to stop a shop
    opening tomorrow. The session's own validation is only bypassed when we are
    deliberately jumping over a still-"Closing" shift."""
    # The float belongs to the ONE drawer mode (see _drawer_mode), never to
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
                    "opening_amount": opening_float
                    if row.mode_of_payment == drawer
                    else flt((floats or {}).get(row.mode_of_payment)),
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
            "foreign_floats": _float_rows(profile.name, floats),
            "pos_opening_entry": opening_entry.name,
        }
    )
    if bypass_live_guard:
        sess.flags.ignore_validate = True
    sess.insert()
    _pin_rates(sess.name, profile)
    _audit_register("open", sess.name, profile.name, opening_float)
    return get_open_session(profile.name)


def _pin_rates(session_name, profile):
    """Fix the shift's exchange rates as it opens (currency.pin_shift_rates),
    so a till that goes offline already knows them. Never stops a shift from
    opening."""
    try:
        from lumenpos import currency

        currency.pin_shift_rates(session_name, profile)
    except Exception:
        frappe.log_error(title="LumenPOS: fixing a shift's rates at open", message=frappe.get_traceback())


def _role_emails(role, company=None):
    """Enabled users holding a role, with an email address. With a company,
    only those who may see it: ERPNext User Permissions on Company hold a user
    to the companies listed (no such permission = every company), so one
    company's cash differences no longer reach another company's managers."""
    if not role:
        return []
    users = set(frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"))
    if not users:
        return []
    if company:
        allowed = {}
        for perm in frappe.get_all(
            "User Permission",
            filters={"allow": "Company", "user": ["in", list(users)]},
            fields=["user", "for_value"],
        ):
            allowed.setdefault(perm.user, set()).add(perm.for_value)
        users = {u for u in users if u not in allowed or company in allowed[u]}
    if not users:
        return []
    return frappe.get_all(
        "User",
        filters={"name": ["in", list(users)], "enabled": 1},
        pluck="email",
    )


def _in_company_currency(session_doc, amount, currency_code):
    """An amount counted in a drawer's own money, valued in the company
    currency at the rate the shift sold that currency at (or today's)."""
    from lumenpos import currency

    company = frappe.get_cached_value("POS Profile", session_doc.pos_profile, "company")
    ccy = currency.company_currency(company)
    if not currency_code or currency_code == ccy:
        return flt(amount)
    rate = _shift_rates(session_doc).get(currency_code)
    if not rate:
        try:
            rate = currency.current_rate(currency_code, ccy)
        except Exception:
            rate = 0
    return flt(amount) * flt(rate or 1)


def _maybe_alert_variance(doc):
    """Email a role when a counted drawer differs from expected by more than the
    threshold. RECORD AND NOTIFY, never an approval gate: a close must not be
    blocked waiting for a manager, and a shift left open is worse than a
    variance. Entirely best-effort; a mail failure only logs."""
    try:
        settings = frappe.get_cached_doc("LumenPOS Settings")
        if not settings.get("variance_alert_enabled"):
            return
        threshold = flt(settings.get("variance_alert_threshold"))
        role = settings.get("variance_alert_role")
        recipients = _role_emails(role, frappe.get_cached_value("POS Profile", doc.pos_profile, "company"))
        if not recipients:
            return
        # The threshold is in the company currency; a drawer in another one is
        # valued at the rate its shift sold at (lumenpos.currency).
        rows = [
            r for r in (doc.get("payment_counts") or [])
            if abs(_in_company_currency(doc, r.difference, r.get("currency"))) > threshold
        ]
        if not rows:
            return
        cells = "".join(
            f"<tr><td>{frappe.utils.escape_html(r.mode_of_payment or '')}</td>"
            f"<td>{frappe.utils.escape_html(r.get('currency') or '')}</td>"
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
                f"<tr><th>{_('Payment')}</th><th>{_('Currency')}</th><th>{_('Expected')}</th>"
                f"<th>{_('Counted')}</th><th>{_('Difference')}</th></tr>"
                f"{cells}</table>"
            ),
        )
    except Exception:
        frappe.log_error(
            title="LumenPOS variance alert failed", message=frappe.get_traceback()
        )


def _force_new_after_failure(profile, opening_float, stuck_session, floats=None):
    """The previous shift is still 'Closing' (consolidation pending, queued or
    failed), let the store keep trading. Open a fresh shift now; the stuck one
    stays in 'Closing' and the self-healer keeps retrying its consolidation, so
    no invoice is lost.

    NOTE: deliberately does NOT require "POS Closing Entry: create". The cashier
    opening the store must never be blocked by a colleague's stuck close."""
    # Nudge the stuck shift to consolidate once more right now.
    _enqueue_consolidation(stuck_session)
    return _create_fresh_session(profile, opening_float, bypass_live_guard=True, floats=floats)


# ---------------------------------------------------------------------------
# Cash movements + live summary
# ---------------------------------------------------------------------------

@frappe.whitelist()
def add_cash_movement(session, movement_type, amount, reason=None, mode_of_payment=None):
    if not frappe.has_permission("POS Register Session", "write"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    from lumenpos.api import permissions

    if not permissions.can_move_cash():
        frappe.throw(_("You are not allowed to put money in or take it out"), frappe.PermissionError)
    doc = frappe.get_doc("POS Register Session", session)
    _assert_owner_or_manager(doc)
    if doc.status != "Open":
        frappe.throw(_("Register session is not open"))
    # Empty: the main drawer. Otherwise a drawer in another currency on this
    # outlet ("Cash USD"), the amount in its money (lumenpos.currency).
    if mode_of_payment and mode_of_payment not in _foreign_drawers(doc.pos_profile):
        mode_of_payment = None
    doc.append(
        "cash_movements",
        {
            "movement_type": movement_type,
            "mode_of_payment": mode_of_payment,
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

    READ-ONLY on purpose, no owner/manager check here. Reading a shift's
    figures is not a mutation, and requiring ownership broke the X-report for
    any cashier working a till a colleague opened. The mutating callers
    (add_cash_movement, close_register) each call _assert_owner_or_manager
    themselves, so supervision is unchanged."""
    if not frappe.has_permission("POS Register Session", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    doc = frappe.get_doc("POS Register Session", session)
    # Which sale doctype this shift posted, by the profile's mode, NOT by whether
    # an opening entry exists (an SI shift can now have one for cash control).
    from lumenpos.api.sales import _table_doctype

    from lumenpos import currency

    sale_doctype = _table_doctype(doc.pos_profile)
    company = frappe.get_cached_value("POS Profile", doc.pos_profile, "company")
    ccy = currency.company_currency(company)
    # The float and cash in/out belong to the ONE main drawer mode, and each
    # drawer in another currency ("Cash USD") keeps its own. Adding them to
    # every Cash-type tender counted the float once per mode on the X-report and
    # at close (a site with delivery apps typed as Cash saw it 3-4 times over).
    drawer = _drawer_mode(doc.pos_profile)
    foreign = _foreign_drawers(doc.pos_profile)
    floats = _foreign_floats(doc)
    payments = _payments_by_mode(doc.name, sale_doctype, drawer)
    cash_in, cash_out = _drawer_movements(doc, drawer, drawer)

    expected, seen = [], set()
    for mode, amount in payments.items():
        row = {
            "mode_of_payment": mode,
            "expected_amount": flt(amount, 2),
            "currency": foreign.get(mode) or currency.mode_currency(mode, company),
        }
        if mode == drawer:
            row["expected_amount"] = flt(amount + (doc.opening_float or 0) + cash_in - cash_out, 2)
            row["is_cash"] = 1
        elif mode in foreign:
            f_in, f_out = _drawer_movements(doc, mode, drawer)
            row["expected_amount"] = flt(amount + floats.get(mode, 0) + f_in - f_out, 2)
            row["is_cash"] = 1
        expected.append(row)
        seen.add(mode)

    if drawer not in seen and (doc.opening_float or cash_in or cash_out):
        expected.append(
            {
                "mode_of_payment": drawer or "Cash",
                "expected_amount": flt((doc.opening_float or 0) + cash_in - cash_out, 2),
                "is_cash": 1,
                "currency": ccy,
            }
        )
    for mode, mode_ccy in foreign.items():
        if mode in seen:
            continue
        f_in, f_out = _drawer_movements(doc, mode, drawer)
        if floats.get(mode) or f_in or f_out:
            expected.append(
                {
                    "mode_of_payment": mode,
                    "expected_amount": flt(floats.get(mode, 0) + f_in - f_out, 2),
                    "is_cash": 1,
                    "currency": mode_ccy,
                }
            )

    totals = _session_totals(doc.name, sale_doctype)

    return {
        "session": doc.name,
        "status": doc.status,
        "pos_opening_entry": doc.get("pos_opening_entry"),
        "opened_at": str(doc.opened_at),
        "opening_float": doc.opening_float,
        "foreign_floats": floats,
        "company_currency": ccy,
        "rates": _shift_rates(doc),
        "cash_in": flt(cash_in, 2),
        "cash_out": flt(cash_out, 2),
        "cash_movements": [
            {
                "movement_type": m.movement_type,
                "amount": m.amount,
                "reason": m.reason,
                "recorded_at": str(m.recorded_at),
                "mode_of_payment": m.get("mode_of_payment") or drawer,
                "currency": foreign.get(m.get("mode_of_payment")) or ccy,
            }
            for m in (doc.cash_movements or [])
        ],
        "expected": expected,
        # The ERPNext days the shift closed while it sold on past midnight.
        "erpnext_days": _days_info(doc),
        **totals,
    }


def _session_totals(session_name, sale_doctype):
    """How many sales a shift made, what they took and what they gave away in
    discounts, in the company currency, so a shift that sold in dollars and in
    dirhams adds up to one figure the books agree with. Plain SQL: Frappe 16
    refuses SQL functions written as text in get_all fields (the X-report
    failed with "SQL functions are not allowed as strings in SELECT"), and v13
    has no other way to write them. `sale_doctype` is a fixed doctype name
    (_table_doctype), not user input."""
    totals = frappe.db.sql(  # nosemgrep
        f"""
        select count(name) as sales_count, sum(base_grand_total) as total_sales,
               sum(base_discount_amount) as invoice_discounts
        from `tab{sale_doctype}`
        where lumenpos_session = %s and docstatus = 1
        """,
        session_name,
        as_dict=True,
    )
    # `sale_doctype` is a fixed doctype name (POS Invoice / Sales Invoice from
    # _table_doctype), not user input, and a table identifier can't be a bound
    # param; the session filter is parameterized. Safe despite the f-string.
    line_discounts = frappe.db.sql(  # nosemgrep
        f"""
        select coalesce(sum(pii.discount_amount * pii.qty * pi.conversion_rate), 0)
        from `tab{sale_doctype} Item` pii
        join `tab{sale_doctype}` pi on pi.name = pii.parent
        where pi.lumenpos_session = %s and pi.docstatus = 1
        """,
        session_name,
    )[0][0]
    total_discounts = flt(line_discounts) + flt(totals[0].invoice_discounts if totals else 0)
    return {
        "sales_count": cint(totals[0].sales_count) if totals else 0,
        "total_sales": flt(totals[0].total_sales, 2) if totals else 0,
        "total_discounts": flt(total_discounts, 2),
    }


def _count_currency(session_doc, mode, summary):
    """The money a counted drawer is in when the shift's figures do not say:
    the company's with them, the payment method's own account otherwise."""
    if summary:
        return summary.get("company_currency")
    company = frappe.get_cached_value("POS Profile", session_doc.pos_profile, "company")
    try:
        from lumenpos import currency

        return currency.mode_currency(mode, company)
    except Exception:
        return frappe.get_cached_value("Company", company, "default_currency")


def _has_expected_pending():
    """Sites updated without a migrate lack the field (see the Frappe Cloud
    "Update Site Pull" trap): reading it there must not break the history."""
    return frappe.get_meta("POS Register Session").has_field("expected_pending")


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
    # directly, there is no POS Closing Entry to create or consolidate.
    needed = "POS Register Session" if not doc.get("pos_opening_entry") else "POS Closing Entry"
    if not frappe.has_permission(needed, "create"):
        frappe.throw(_("You are not permitted to close a register"), frappe.PermissionError)
    from lumenpos.api import permissions

    if not permissions.can_close_register():
        frappe.throw(_("You are not allowed to close a register"), frappe.PermissionError)
    if doc.status == "Closed":
        frappe.throw(_("Register session is already closed"))
    if doc.status == "Closing":
        # Already finalising (double-tap or post-failure): just push the
        # consolidation again. Benign, no new counts, no live shift touched.
        _enqueue_consolidation(doc.name, counted)
        return _close_result(doc, queued=True)
    # The sensitive Open->Closing flip is owner/manager only (also enforced via
    # get_session_summary below). A cashier can't close a colleague's live till.
    _assert_owner_or_manager(doc)

    # STALE-CLOSING-SCREEN GUARD. The cashier counts the drawer against the
    # figures on their screen. If a sale landed from another window or device
    # after that screen loaded, those figures, and therefore the variance they
    # just signed off, are wrong. The client sends the sales count it displayed;
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

    # What each drawer should hold. Working it out must never keep a shift
    # open: with 0.52.0 on ERPNext 16 it failed right here on every shift, so
    # none could close, and each one held its outlet (and, with one open shift
    # per person, its cashier). When it fails, the counts are kept and the
    # shift closes all the same; its expected figures then come from its own
    # POS Closing Entry at consolidation (_fill_pending_figures).
    try:
        summary = get_session_summary(session)
    except frappe.PermissionError:
        raise
    except Exception:
        frappe.log_error(title="LumenPOS: shift figures failed at close", message=frappe.get_traceback())
        summary = None
    expected_map = {r["mode_of_payment"]: r for r in (summary or {}).get("expected") or []}

    modes = sorted(set(expected_map) | set(counted or {}))
    doc.payment_counts = []
    for mode in modes:
        row = expected_map.get(mode) or {}
        expected_amount = flt(row.get("expected_amount"))
        counted_amount = flt((counted or {}).get(mode))
        doc.append(
            "payment_counts",
            {
                "mode_of_payment": mode,
                # Each drawer is counted in its own money (lumenpos.currency).
                "currency": row.get("currency") or _count_currency(doc, mode, summary),
                "expected_amount": expected_amount,
                "counted_amount": counted_amount,
                # Without the figures no difference is claimed yet.
                "difference": flt(counted_amount - expected_amount, 2) if summary else 0,
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
    doc.expected_pending = 0 if summary else 1
    totals = summary
    if not summary:
        # The sales themselves are counted on their own, so the history never
        # says "0 sales" for a shift that sold while its drawers wait.
        try:
            from lumenpos.api.sales import _table_doctype

            totals = _session_totals(doc.name, _table_doctype(doc.pos_profile))
        except Exception:
            totals = {}
    doc.total_sales = flt(totals.get("total_sales"))
    doc.total_discounts = flt(totals.get("total_discounts"))
    doc.sales_count = cint(totals.get("sales_count"))
    doc.save()
    # Persist the "Closing" state NOW: from here the shift is neither sellable
    # nor resumable, whatever happens to the consolidation next. Intentional, 
    # the state must survive even if the consolidation step below fails.
    frappe.db.commit()  # nosemgrep

    # AFTER the flip is committed: an email hiccup must never undo a close.
    # Without the figures there is no difference to report yet: the alert
    # goes out once they are filled in (_fill_pending_figures).
    if summary:
        _maybe_alert_variance(doc)

    if doc.get("pos_opening_entry"):
        _enqueue_consolidation(doc.name, counted)
        queued = True
    else:
        # No opening entry (Sales Invoice mode / legacy), nothing to consolidate;
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
        # The expected takings could not be worked out at the close; they come
        # from the POS Closing Entry at consolidation.
        "expected_pending": cint(doc.get("expected_pending")),
        "counts": [
            {
                "mode_of_payment": r.mode_of_payment,
                "currency": r.get("currency"),
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

    NOT whitelisted on purpose, it runs only via the background queue and the
    scheduler. The HTTP entry point is retry_closing(), which is permission
    checked. (enqueue/scheduler resolve this by dotted path; no whitelist
    needed.)"""
    if isinstance(counted, str):
        counted = json.loads(counted)

    if not _acquire_lock(timeout=10):
        # Another consolidation holds the lock. Don't busy-wait a worker slot, 
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

    # The ERPNext days this shift closed while it sold on past midnight
    # (roll_day) reach the books first: a return in a later day may be of a
    # sale in an earlier one, and ERPNext consolidates the original first.
    day_error = _consolidate_days(session.name) if session.get("erpnext_days") else None

    opening_name = session.get("pos_opening_entry")
    if not opening_name:
        _mark_closed(session.name, None)
        return None
    try:
        opening_name = _usable_opening_entry(session, opening_name)
    except Exception as exc:
        frappe.db.rollback()
        _mark_failed(session.name, None, _short(exc))
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
                # As _submit_closing: ERPNext's own checks refuse a shift
                # several cashiers sold on.
                closing.flags.ignore_validate = True
                closing.flags.ignore_permissions = True
                _suppress_consolidation(closing)
                closing.submit()
            except Exception as exc:
                frappe.db.rollback()
                _mark_failed(session.name, closing_name, _short(exc))
                return None
            session.db_set("pos_closing_entry", closing_name, commit=True)
        elif closing.docstatus == 2:
            # The closing was cancelled, start over with a fresh one.
            session.db_set("pos_closing_entry", None, commit=True)
            return _reconcile_session(session_name, counted)

    closing = frappe.get_doc("POS Closing Entry", closing_name)
    if session.get("expected_pending"):
        _fill_pending_figures(session.name, closing)
    if closing.status == "Submitted" and _opening_closed(opening_name):
        if day_error:
            _mark_failed(session.name, closing_name, day_error)
        else:
            _mark_closed(session.name, closing_name)
        return closing_name

    status = _consolidate_now(closing)
    if status == "Submitted" and not day_error:
        _mark_closed(session.name, closing_name)
    elif status == "Submitted":
        _mark_failed(session.name, closing_name, day_error)
    else:
        error = frappe.db.get_value("POS Closing Entry", closing_name, "error_message")
        _mark_failed(session.name, closing_name, day_error or error or _("Consolidation failed"))
    return closing_name


def _fill_pending_figures(session_name, closing=None, quiet=False):
    """A shift closed while its figures could not be worked out (close_register)
    gets them now: from its POS Closing Entry, which is built from the shift's
    own invoices, float and cash movements, or, for a shift without one (a
    Sales Invoice outlet's cash shift), from its own figures once they can be
    worked out again. What each drawer should have held, the difference from
    what was counted, the shift's totals, then the variance alert the close
    could not send. Best effort: until it succeeds the shift keeps saying its
    figures are pending, and the self-healer tries again (fill_pending_figures).
    `quiet` keeps that periodic retry out of the Error Log."""
    from lumenpos.api.sales import _table_doctype

    try:
        doc = frappe.get_doc("POS Register Session", session_name)
        if closing:
            recon = {r.mode_of_payment: flt(r.expected_amount) for r in closing.get("payment_reconciliation") or []}
        else:
            recon = {r["mode_of_payment"]: flt(r["expected_amount"]) for r in get_session_summary(session_name)["expected"]}
        counted_modes = set()
        for row in doc.get("payment_counts") or []:
            counted_modes.add(row.mode_of_payment)
            row.expected_amount = recon.get(row.mode_of_payment, 0)
            row.difference = flt(flt(row.counted_amount) - row.expected_amount, 2)
        for mode, expected in recon.items():
            if mode not in counted_modes and expected:
                doc.append(
                    "payment_counts",
                    {
                        "mode_of_payment": mode,
                        "currency": _count_currency(doc, mode, None),
                        "expected_amount": expected,
                        "counted_amount": 0,
                        "difference": flt(-expected, 2),
                    },
                )
        doc.update(_session_totals(doc.name, _table_doctype(doc.pos_profile)))
        doc.expected_pending = 0
        doc.flags.ignore_permissions = True
        doc.save()
        # Enqueued consolidation job, like every other step here.
        frappe.db.commit()  # nosemgrep
    except Exception:
        frappe.db.rollback()
        if not quiet:
            frappe.log_error(title="LumenPOS: filling in a closed shift's figures", message=frappe.get_traceback())
        return
    _maybe_alert_variance(doc)


def fill_pending_figures():
    """Scheduled with the self-healer: shifts of the last week that closed with
    their figures still pending get another try (see _fill_pending_figures)."""
    if not _has_expected_pending():
        return
    rows = frappe.get_all(
        "POS Register Session",
        filters={
            "status": "Closed",
            "expected_pending": 1,
            "closed_at": [">=", frappe.utils.add_days(now_datetime(), -7)],
        },
        fields=["name", "pos_closing_entry"],
        limit_page_length=20,
    )
    for row in rows:
        closing = None
        if row.pos_closing_entry:
            closing = frappe.get_doc("POS Closing Entry", row.pos_closing_entry)
            if closing.docstatus != 1:
                continue
        _fill_pending_figures(row.name, closing, quiet=True)


def _usable_opening_entry(session, opening_name):
    """The POS Opening Entry this shift closes against. Someone may have
    cancelled it in ERPNext (v13 to v15 allow that even with sales on it), and
    ERPNext refuses a POS Closing Entry that links a cancelled one ("Cannot
    link cancelled document"), so the shift could never close and its sales
    would never reach the books. ERPNext's own way back is to amend the
    cancelled entry: an amendment made earlier (by hand, or by an earlier try)
    is used, or one is made, and the shift points at it from then on."""
    if frappe.db.get_value("POS Opening Entry", opening_name, "docstatus") != 2:
        return opening_name
    cancelled = opening_name
    current = opening_name
    while True:
        amended = frappe.db.get_value(
            "POS Opening Entry", {"amended_from": current}, ["name", "docstatus"], as_dict=True
        )
        if not amended:
            break
        current = amended.name
        if amended.docstatus == 2:
            continue
        if amended.docstatus == 0:
            # A draft amendment someone started by hand: finish it.
            draft = frappe.get_doc("POS Opening Entry", amended.name)
            draft.flags.ignore_validate = True
            draft.flags.ignore_permissions = True
            draft.submit()
        return _point_session_at(session, cancelled, current)
    last = frappe.get_doc("POS Opening Entry", current)
    new = frappe.copy_doc(last)
    new.amended_from = last.name
    # Open again: nothing of the cancelled entry's own close carries over.
    new.status = "Draft"
    new.pos_closing_entry = None
    new.period_end_date = None
    # The same period, outlet and cashier as the shift; ERPNext's own checks
    # (one open entry per outlet and per cashier) are for opening a shift, not
    # for closing one that already ran, as in _create_fresh_session.
    new.flags.ignore_validate = True
    new.insert(ignore_permissions=True)
    new.submit()
    return _point_session_at(session, cancelled, new.name)


def _point_session_at(session, cancelled, opening_name):
    session.db_set("pos_opening_entry", opening_name, commit=True)
    try:
        frappe.get_doc("POS Register Session", session.name).add_comment(
            "Info",
            _("The POS Opening Entry {0} of this shift was cancelled in ERPNext, so the shift closes against its amendment {1}.").format(
                cancelled, opening_name
            ),
        )
        frappe.db.commit()  # nosemgrep
    except Exception:
        frappe.log_error(title="LumenPOS: note on an amended opening entry", message=frappe.get_traceback())
    return opening_name


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
    for row in closing.get(erpnext_compat.closing_invoice_table()) or []:
        state = frappe.db.get_value(
            "POS Invoice", row.pos_invoice, ["status", "consolidated_invoice"], as_dict=True
        )
        if state and state.status != "Consolidated" and not state.consolidated_invoice:
            pending.append(row)

    if not pending:
        # Everything already consolidated (or no sales), just finalize.
        closing.set_status(update=True, status="Submitted")
        closing.db_set("error_message", "")
        closing.update_opening_entry()
        # Enqueued consolidation job, commit the finalised state so it persists.
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
    # committed at close time). Treat THAT as authoritative, a retry or the
    # self-healer calls in without the `counted` dict, and we must never post a
    # Z-report with zeroed counts and a false full-shortage variance.
    session_counts = {
        r.mode_of_payment: flt(r.counted_amount)
        for r in (session_doc.get("payment_counts") or [])
    }
    if session_counts:
        counted = session_counts

    opening = frappe.get_doc("POS Opening Entry", session_doc.get("pos_opening_entry"))
    closing = _build_closing(session_doc, opening, counted=counted or {})
    _submit_closing(closing)
    return closing


def _build_closing(session_doc, opening, counted=None, until=None):
    """The native POS Closing Entry for the part of a shift `opening` covers,
    not saved yet. That is the whole shift, unless it ran past midnight on
    ERPNext 16 (roll_day): then its sales are the ones no earlier ERPNext day
    of it holds, and its cash in and out the ones recorded after that day
    ended, up to `until`. `counted` None closes a day that ends while the
    shift trades on at what each drawer should hold: the drawer is counted
    once, at the end of the shift."""
    from lumenpos.api.sales import _table_doctype

    # The one mode that represents this till's cash drawer (float, change and
    # cash in/out all belong to it alone).
    drawer = _drawer_mode(session_doc.pos_profile)
    sale_doctype = _table_doctype(session_doc.pos_profile)
    held = _day_invoices(session_doc)
    since = _last_day_end(session_doc)
    filters = {"lumenpos_session": session_doc.name, "docstatus": 1}
    if held:
        filters["name"] = ["not in", list(held)]
    invoices = frappe.get_all(
        sale_doctype,
        filters=filters,
        fields=["name", "customer", "grand_total", "is_return", "posting_date"],
        order_by="creation asc",
    )

    closing = erpnext_compat.new_doc("POS Closing Entry")
    closing.update(
        {
            "pos_opening_entry": opening.name,
            "period_start_date": opening.period_start_date,
            "period_end_date": until or now_datetime(),
            "posting_date": nowdate(),
            "company": opening.company,
            "pos_profile": opening.pos_profile,
            "user": opening.user,
        }
    )

    si_rows = []
    # ERPNext's table of the shift's POS Invoices (pos_transactions, renamed
    # pos_invoices in v16).
    invoice_table = erpnext_compat.closing_invoice_table()
    for inv in invoices:
        # That table links POS Invoices only. A Sales-Invoice-mode shift
        # leaves it empty (so _consolidate_now finds nothing to merge and just
        # finalizes), but its takings still roll into the payment reconciliation
        # and the Z-report totals below, the cash-control point of the entry.
        if sale_doctype == "POS Invoice":
            closing.append(
                invoice_table,
                {
                    "pos_invoice": inv.name,
                    "customer": inv.customer,
                    "grand_total": inv.grand_total,
                    "is_return": inv.is_return,
                    "posting_date": inv.posting_date,
                },
            )
        else:
            si_rows.append(inv)
    grand_total, net_total, qty_total = _invoice_totals(closing, sale_doctype, [inv.name for inv in invoices])

    # What each tender took, in ITS OWN account's currency, with change taken
    # off the drawer it really came out of (see _payments_by_mode). Change comes
    # OUT OF A DRAWER, never out of whichever Cash-type tender sorts first
    # (delivery apps are often typed Cash).
    for mode, amount in _payments_by_mode(session_doc.name, sale_doctype, drawer, exclude=held).items():
        if amount:
            _accumulate_payment(closing, mode, amount)

    cash_modes = _cash_modes()
    foreign = _foreign_drawers(session_doc.pos_profile)
    cash_in, cash_out = _drawer_movements(session_doc, drawer, drawer, since, until)
    # An entry a shift opened past midnight carries what each method held at
    # the end of the day before (_carried_opening), cash or not.
    carried = bool(session_doc.get("erpnext_days"))
    drawer_applied = False
    for detail in opening.balance_details:
        row = _get_reconciliation_row(closing, detail.mode_of_payment)
        opening_amt = flt(detail.opening_amount)
        # SELF-HEAL a shift opened before the single-drawer fix: the float was
        # written to EVERY Cash-type row back then, so crediting each one would
        # inflate expected by a multiple of the float. Keep the drawer's copy
        # only, and each drawer in another currency's own float.
        if (
            opening_amt
            and not carried
            and detail.mode_of_payment != drawer
            and detail.mode_of_payment in cash_modes
            and detail.mode_of_payment not in foreign
        ):
            opening_amt = 0
        row.opening_amount = opening_amt
        row.expected_amount = flt(row.expected_amount) + opening_amt
        # Net the shift's cash in/out into its drawer's row so expected matches
        # what is physically in each till drawer.
        if detail.mode_of_payment == drawer:
            row.expected_amount = flt(row.expected_amount) + cash_in - cash_out
            drawer_applied = True
        elif detail.mode_of_payment in foreign:
            f_in, f_out = _drawer_movements(session_doc, detail.mode_of_payment, drawer, since, until)
            row.expected_amount = flt(row.expected_amount) + f_in - f_out
    if not drawer_applied and (cash_in or cash_out):
        # The drawer mode isn't on this opening entry (profile changed mid-life)
        #, fall back to the first Cash-type row so the movements aren't lost.
        for row in closing.payment_reconciliation:
            if row.mode_of_payment in cash_modes and row.mode_of_payment not in foreign:
                row.expected_amount = flt(row.expected_amount) + cash_in - cash_out
                break

    for row in closing.payment_reconciliation:
        if counted is None:
            row.closing_amount = flt(row.expected_amount)
        else:
            row.closing_amount = flt(counted.get(row.mode_of_payment))
        row.difference = flt(row.closing_amount) - flt(row.expected_amount)

    # Declare the shift's cash movements ON the closing entry (they otherwise
    # live only on the session and are invisible on the official Z-report).
    _declare_cash_movements(closing, session_doc, cash_in, cash_out, since, until)
    # And, in Sales Invoice mode, the invoices themselves: the takings above are
    # a total, and an accountant checking this drawer has to be able to walk it
    # back to the documents that made it.
    _declare_sales_invoices(closing, si_rows)

    closing.grand_total = flt(grand_total, 2)
    closing.net_total = flt(net_total, 2)
    closing.total_quantity = flt(qty_total, 2)
    return closing


def _invoice_totals(closing, sale_doctype, names):
    """(grand total, net total, quantity) of these invoices in the company
    currency, a shift may hold sales in several currencies (lumenpos.currency)
    and the books add up in one, with their taxes added to the closing. In a
    few queries, not one document per sale: a shift that runs past midnight
    builds this inside the first sale of the new day (roll_day). `sale_doctype`
    is a fixed doctype name (_table_doctype), not user input."""
    if not names:
        return 0.0, 0.0, 0.0
    values = {"names": tuple(names), "doctype": sale_doctype}
    grand, net = frappe.db.sql(  # nosemgrep
        f"""select coalesce(sum(base_grand_total), 0), coalesce(sum(base_net_total), 0)
        from `tab{sale_doctype}` where name in %(names)s""",
        values,
    )[0]
    qty = frappe.db.sql(  # nosemgrep
        f"""select coalesce(sum(qty), 0) from `tab{sale_doctype} Item`
        where parenttype = %(doctype)s and parent in %(names)s""",
        values,
    )[0][0]
    for tax in frappe.db.sql(
        """select account_head, rate, base_tax_amount, tax_amount from `tabSales Taxes and Charges`
        where parenttype = %(doctype)s and parent in %(names)s order by parent, idx""",
        values,
        as_dict=True,
    ):
        _accumulate_tax(closing, tax)
    return flt(grand), flt(net), flt(qty)


def _submit_closing(closing):
    """Insert and submit one of our POS Closing Entries, without ERPNext's
    on-submit consolidation (we consolidate ourselves, serialized).

    ERPNext's own checks on the entry assume one cashier per POS Opening
    Entry: every invoice on it must have been made by the entry's user ("POS
    Invoice isn't created by user"). A shift shared by several cashiers, "Per
    outlet" (the default), can never meet that, so any such shift where a
    second person sold failed its close for good, on every version. Its
    invoices are this shift's own, submitted and not yet held by another
    closing (chosen so in _build_closing), so what else ERPNext checks is
    checked here, and its validation is skipped, as for our POS Opening
    Entries (_create_fresh_session)."""
    if frappe.db.get_value("POS Opening Entry", closing.pos_opening_entry, "status") != "Open":
        frappe.throw(_("Selected POS Opening Entry should be open."), title=_("Invalid Opening Entry"))
    table = erpnext_compat.closing_invoice_table()
    names = [row.pos_invoice for row in closing.get(table) or []]
    if names:
        taken = frappe.get_all(
            "POS Invoice",
            filters={"name": ["in", names], "consolidated_invoice": ["is", "set"]},
            pluck="name",
        )
        if taken:
            closing.set(table, [row for row in closing.get(table) if row.pos_invoice not in set(taken)])
    # What ERPNext 16's validate fills in.
    if closing.meta.has_field("posting_time"):
        closing.posting_time = nowtime()
    if closing.meta.has_field("invoice_type"):
        closing.invoice_type = frappe.db.get_single_value("POS Settings", "invoice_type")
    closing.flags.ignore_validate = True
    closing.insert(ignore_permissions=True)
    _suppress_consolidation(closing)
    closing.submit()
    return closing


def _declare_sales_invoices(closing, rows):
    """List a Sales-Invoice-mode shift's invoices on its POS Closing Entry.

    ERPNext's `pos_transactions` only links POS Invoices, so without this the
    Z-report of an outlet that posts Sales Invoices shows what was taken but
    not which documents it came from, and the reviewer has to go hunting by
    date and user. Guarded with has_field so a not-yet-migrated site still
    closes cleanly."""
    if not rows:
        return
    if not frappe.get_meta("POS Closing Entry").has_field("lumenpos_sales_invoices"):
        return
    closing.set("lumenpos_sales_invoices", [])
    for inv in rows:
        closing.append(
            "lumenpos_sales_invoices",
            {
                "sales_invoice": inv.name,
                "customer": inv.customer,
                "posting_date": inv.posting_date,
                "grand_total": inv.grand_total,
                "is_return": inv.is_return,
            },
        )


def _declare_cash_movements(closing, session_doc, cash_in, cash_out, since=None, until=None):
    """Copy the session's drawer cash in/out onto the POS Closing Entry's LumenPOS
    fields (created in install.make_custom_fields) so the Z-report itself shows
    what was added to / taken from the drawer. Guarded with has_field so a
    not-yet-migrated site still closes cleanly. `since` and `until` keep to
    one ERPNext day of a shift that ran past midnight (roll_day)."""
    meta = frappe.get_meta("POS Closing Entry")
    if not meta.has_field("lumenpos_cash_in"):
        return
    closing.lumenpos_cash_in = flt(cash_in, 2)
    closing.lumenpos_cash_out = flt(cash_out, 2)
    if not meta.has_field("lumenpos_cash_movements"):
        return
    closing.set("lumenpos_cash_movements", [])
    main = _drawer_mode(session_doc.pos_profile)
    for m in session_doc.cash_movements or []:
        if not _in_window(m.get("recorded_at"), since, until):
            continue
        # A movement of a drawer in another currency says which drawer, so its
        # amount is read in that drawer's money (lumenpos.currency).
        drawer = m.get("mode_of_payment")
        reason = m.reason if not drawer or drawer == main else f"{drawer}: {m.reason or ''}".strip()
        closing.append(
            "lumenpos_cash_movements",
            {
                "movement_type": m.movement_type,
                "amount": m.amount,
                "reason": reason,
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
    # Enqueued consolidation job, persist the closed state immediately.
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
    # status stays "Closing", the shift is finalised operationally but its
    # consolidation must still complete (retry / self-healer).
    frappe.db.set_value("POS Register Session", session_name, values)
    # Enqueued consolidation job, persist the failure state so the self-healer
    # can retry from a known point.
    frappe.db.commit()  # nosemgrep


def _opening_closed(opening_name):
    return frappe.db.get_value("POS Opening Entry", opening_name, "status") == "Closed"


def _short(value, length=480):
    return str(value)[:length] if value is not None else None


# ---------------------------------------------------------------------------
# A shift that sells on past midnight (ERPNext 16)
# ---------------------------------------------------------------------------

def carry_past_midnight():
    """LumenPOS Settings.carry_shift_past_midnight, on unless a shop switched
    it off (install.default_carry_past_midnight_on writes the ON down once).
    A site updated without its migrate has no such field yet: on."""
    try:
        return bool(cint(frappe.db.get_single_value("LumenPOS Settings", "carry_shift_past_midnight")))
    except Exception:
        return True


def from_earlier_day(started):
    """Whether a POS Opening Entry started on an earlier day than today, the
    one thing ERPNext 16 refuses a sale for once an outlet has one open."""
    return bool(started) and getdate(started) != getdate(nowdate())


def roll_day(session_name):
    """ERPNext 16 takes a POS Invoice only while its outlet's one open POS
    Opening Entry was opened today (SalesInvoice.validate_pos_opening_entry),
    so a shift still selling after midnight could no longer sell, take a
    return or upload a sale made offline, and the till would not close while
    such a sale waited to upload (a shop in Zimbabwe, 2026-09-30). With "Keep
    a shift open past midnight" on (the default), the first of them closes
    ERPNext's day for the shift and opens the next, ERPNext's own way: a POS
    Closing Entry for what the day sold and a new POS Opening Entry, while the
    LumenPOS shift sells on, with one drawer and one count at its own close.
    What each payment method should hold is carried into the new entry's
    opening amounts, so the shift's last POS Closing Entry still sets the
    count against the whole shift. The day's invoices are consolidated in the
    background, like any close (consolidate_days).

    Runs inside the request that needs it and commits nothing itself, so a
    sale that then fails takes the new day back with it. Serialized on the
    shift's row with every sale, cash movement and close. Returns True when
    it closed a day."""
    row = frappe.db.get_value(
        "POS Register Session", session_name, ["status", "pos_opening_entry"], as_dict=True, for_update=True
    )
    if not row or row.status != "Open" or not row.pos_opening_entry:
        return False
    opening = frappe.get_doc("POS Opening Entry", row.pos_opening_entry)
    if opening.docstatus != 1 or opening.status != "Open" or not from_earlier_day(opening.period_start_date):
        return False
    session_doc = frappe.get_doc("POS Register Session", session_name)
    now = now_datetime()
    closing = _build_closing(session_doc, opening, until=now)
    _submit_closing(closing)
    _close_opening(opening, closing.name)
    carried = _carried_opening(opening, closing, now)
    sales = len(closing.get(erpnext_compat.closing_invoice_table()) or [])
    session_doc.append(
        "erpnext_days",
        {
            "pos_opening_entry": opening.name,
            "pos_closing_entry": closing.name,
            "started_at": opening.period_start_date,
            "ended_at": now,
            "sales_count": sales,
            "closing_status": "Pending",
        },
    )
    session_doc.pos_opening_entry = carried.name
    session_doc.flags.ignore_permissions = True
    session_doc.save()
    note = _(
        "ERPNext's day was closed at {0} while this shift sold on past midnight: POS Closing Entry {1} holds "
        "its {2} sales, and POS Opening Entry {3} opens the next day. The drawer is counted once, when the shift closes."
    ).format(frappe.utils.format_datetime(now, "yyyy-MM-dd HH:mm"), closing.name, sales, carried.name)
    session_doc.add_comment("Info", note)
    from lumenpos.api import audit

    audit.log(
        audit.ERPNEXT_DAY,
        detail=note,
        reference_doctype="POS Register Session",
        reference_name=session_name,
        pos_profile=session_doc.pos_profile,
    )
    _enqueue_days(session_name)
    return True


def _close_opening(opening, closing_name):
    """What ERPNext does to a POS Opening Entry once its closing is through
    (POSClosingEntry.update_opening_entry), done at once for a day that ends
    while its shift sells on: ERPNext 16 takes no sale while the outlet still
    has it open. Its consolidation follows in the background and does the
    same again at its end."""
    opening.pos_closing_entry = closing_name
    opening.set_status()
    opening.flags.ignore_permissions = True
    opening.save()


def _carried_opening(opening, closing, now):
    """The next day's POS Opening Entry of a shift that sells on past
    midnight: same outlet, company and cashier, opened now, and each payment
    method opening at what the day just closed says it should hold, cash or
    not, since the shift is counted once at its own close."""
    carried = {r.mode_of_payment: flt(r.expected_amount) for r in closing.payment_reconciliation}
    modes = [r.mode_of_payment for r in opening.balance_details]
    modes += [mode for mode in carried if mode not in modes]
    entry = frappe.get_doc(
        {
            "doctype": "POS Opening Entry",
            "company": opening.company,
            "pos_profile": opening.pos_profile,
            "user": opening.user,
            "period_start_date": now,
            "posting_date": getdate(now),
            "balance_details": [
                {"mode_of_payment": mode, "opening_amount": flt(carried.get(mode))} for mode in modes
            ],
        }
    )
    # As in _create_fresh_session: ERPNext's checks are for a cashier opening
    # a shift, and this one is already running.
    entry.flags.ignore_validate = True
    entry.insert(ignore_permissions=True)
    entry.submit()
    return entry


def _day_invoices(session_doc):
    """The shift's POS Invoices that an ERPNext day it closed while selling on
    past midnight already holds (roll_day): none for any other shift."""
    closings = [r.pos_closing_entry for r in session_doc.get("erpnext_days") or [] if r.pos_closing_entry]
    if not closings:
        return set()
    rows = frappe.db.sql(
        """select pos_invoice from `tabPOS Invoice Reference`
        where parenttype = 'POS Closing Entry' and parent in %(closings)s""",
        {"closings": tuple(closings)},
    )
    return {r[0] for r in rows if r[0]}


def _last_day_end(session_doc):
    """When the shift's last closed ERPNext day ended (roll_day), or None."""
    ends = [get_datetime(r.ended_at) for r in session_doc.get("erpnext_days") or [] if r.ended_at]
    return max(ends) if ends else None


def _enqueue_days(session_name, after_commit=True):
    """Queue one consolidation of a shift's closed ERPNext days, de-duplicated
    like _enqueue_consolidation."""
    job_id = f"lumenpos_days::{session_name}"
    try:
        from frappe.utils.background_jobs import is_job_enqueued

        if is_job_enqueued(job_id):
            return
    except Exception:
        pass
    frappe.enqueue(
        "lumenpos.api.register.consolidate_days",
        queue="long",
        timeout=2000,
        enqueue_after_commit=after_commit,
        job_id=job_id,
        session_name=session_name,
    )


def consolidate_days(session_name):
    """Background job and self-healer: put the ERPNext days a shift closed
    while it sold on past midnight into the books, behind the same lock as
    every close. Not whitelisted: retry_days is the checked way in."""
    if not _acquire_lock(timeout=10):
        _enqueue_days(session_name, after_commit=False)
        return None
    try:
        return _consolidate_days(session_name)
    finally:
        _release_lock()


def _consolidate_days(session_name):
    """Consolidate, oldest first, the shift's closed ERPNext days not in the
    books yet. Stops at the first that fails: a return in a later day may be
    of a sale in it, and ERPNext consolidates the original first. Returns
    that failure's reason, or None when every day is in the books."""
    rows = frappe.get_all(
        "POS Session Day",
        filters={"parent": session_name, "parenttype": "POS Register Session", "closing_status": ["!=", "Submitted"]},
        fields=["name", "pos_closing_entry", "closing_attempts"],
        order_by="idx asc",
    )
    for row in rows:
        # A failed consolidation rolls back everything not committed yet.
        frappe.db.commit()  # nosemgrep
        closing = frappe.get_doc("POS Closing Entry", row.pos_closing_entry) if row.pos_closing_entry else None
        if not closing or closing.docstatus != 1:
            status, error = "Failed", _("POS Closing Entry {0} of this shift is not submitted.").format(
                row.pos_closing_entry
            )
        else:
            status = _consolidate_now(closing)
            error = None
            if status != "Submitted":
                status = "Failed"
                error = frappe.db.get_value("POS Closing Entry", closing.name, "error_message") or _(
                    "Consolidation failed"
                )
        frappe.db.set_value(
            "POS Session Day",
            row.name,
            {
                "closing_status": status,
                "closing_error": _short(error),
                "closing_attempts": 0 if status == "Submitted" else cint(row.closing_attempts) + 1,
            },
            update_modified=False,
        )
        # Background job or self-healer: keep what happened.
        frappe.db.commit()  # nosemgrep
        if error:
            return error
    return None


def _days_info(session_doc):
    return [
        {
            "pos_opening_entry": r.pos_opening_entry,
            "pos_closing_entry": r.pos_closing_entry,
            "started_at": str(r.started_at) if r.started_at else None,
            "ended_at": str(r.ended_at) if r.ended_at else None,
            "sales_count": cint(r.sales_count),
            "closing_status": r.closing_status,
            "closing_error": r.closing_error,
        }
        for r in session_doc.get("erpnext_days") or []
    ]


@frappe.whitelist()
def retry_days(session):
    """Book again the ERPNext days of a shift that did not reach the books
    (roll_day), once whatever stopped them is put right. Queued, like
    retry_closing, and allowed to the same people."""
    if not frappe.has_permission("POS Closing Entry", "create"):
        frappe.throw(_("You are not permitted to close a register"), frappe.PermissionError)
    doc = frappe.get_doc("POS Register Session", session)
    for row in doc.get("erpnext_days") or []:
        if row.closing_status == "Failed":
            frappe.db.set_value("POS Session Day", row.name, "closing_attempts", 0, update_modified=False)
    _enqueue_days(doc.name)
    return {"queued": True}


def _sessions_with_pending_days():
    """Open shifts with a closed ERPNext day not in the books yet (a closing
    shift's days go with its close)."""
    if not frappe.db.table_exists("POS Session Day"):
        return []
    return [
        r[0]
        for r in frappe.db.sql(
            """select distinct d.parent from `tabPOS Session Day` d
            join `tabPOS Register Session` s on s.name = d.parent
            where d.parenttype = 'POS Register Session' and d.closing_status != 'Submitted'
              and coalesce(d.closing_attempts, 0) < 30 and s.status = 'Open'
            limit 50"""
        )
    ]


# ---------------------------------------------------------------------------
# Self-healer (scheduled), converge any stuck shift to Closed
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
                title="LumenPOS register stuck, manual closing needed",
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
    # The ERPNext days of shifts still selling past midnight (roll_day).
    for name in _sessions_with_pending_days():
        try:
            consolidate_days(name)
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="LumenPOS: booking a closed ERPNext day failed", message=frappe.get_traceback())
    try:
        fill_pending_figures()
    except Exception:
        frappe.db.rollback()
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
            "never consolidated, consolidate them from the desk:\n"
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
def list_open_shifts(pos_profile):
    """For a manager: the shifts still open at this outlet that the Register
    page does not already show them, so one can be closed from there. In "Per
    cashier" scope each cashier holds their own, and a manager had no way to
    reach one from the till: a cashier who went home, who may not close a
    register, or who is held back at another outlet by "One open shift per
    person" left it open. Anyone else gets an empty list."""
    from lumenpos.api import permissions

    if not permissions.is_manager() or not permissions.can_use_outlet(pos_profile):
        return []
    shown = (get_open_session(pos_profile) or {}).get("name")
    rows = frappe.get_all(
        "POS Register Session",
        filters={"pos_profile": pos_profile, "status": "Open", "name": ["!=", shown or ""]},
        fields=["name", "opened_by", "opened_at", "opening_float"],
        order_by="opened_at asc",
    )
    return [
        {
            "session": r.name,
            "opened_by": r.opened_by,
            "opened_by_name": frappe.utils.get_fullname(r.opened_by) if r.opened_by else "",
            "opened_at": str(r.opened_at) if r.opened_at else None,
            "opening_float": r.opening_float,
        }
        for r in rows
    ]


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
        ] + (["expected_pending"] if _has_expected_pending() else []),
        order_by="closed_at desc",
        limit_page_length=min(int(limit), 50),
    )
    from lumenpos import currency

    ccy = currency.company_currency(frappe.get_cached_value("POS Profile", pos_profile, "company"))
    has_days = frappe.db.table_exists("POS Session Day")
    for session in sessions:
        counts = frappe.get_all(
            "POS Register Payment Count",
            filters={"parent": session.name},
            fields=["mode_of_payment", "currency", "expected_amount", "counted_amount", "difference"],
            order_by="idx asc",
        )
        session["counts"] = counts
        # The ERPNext days it closed while it sold on past midnight (roll_day).
        session["erpnext_days"] = (
            frappe.get_all(
                "POS Session Day",
                filters={"parent": session.name, "parenttype": "POS Register Session"},
                fields=["pos_closing_entry", "closing_status"],
                order_by="idx asc",
            )
            if has_days
            else []
        )
        # One figure in the company currency, however many currencies were
        # counted (lumenpos.currency). Only a shift with a drawer in another
        # currency needs its fixed rates read.
        if any(c.currency and c.currency != ccy for c in counts):
            doc = frappe.get_doc("POS Register Session", session.name)
            total = sum(_in_company_currency(doc, c.difference, c.currency) for c in counts)
        else:
            total = sum(flt(c.difference) for c in counts)
        session["total_difference"] = flt(total, 2)
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
    # In the company currency, like the closing's other totals: a shift may
    # hold sales in several currencies (lumenpos.currency).
    amount = flt(tax.get("base_tax_amount")) if tax.get("base_tax_amount") is not None else flt(tax.tax_amount)
    for row in closing.taxes:
        if row.account_head == tax.account_head:
            row.amount = flt(row.amount) + amount
            return
    closing.append(
        "taxes",
        {"account_head": tax.account_head, "rate": tax.rate, "amount": amount},
    )


def _payments_by_mode(session, doctype="POS Invoice", drawer=None, exclude=None):
    """What each tender took in this shift, in ITS OWN account's currency.

    A shift can hold sales in several currencies (lumenpos.currency): dirham
    cash taken on a dollar sale sits in the dirham drawer at its dirham value
    (the row's base amount), dollar cash in the dollar drawer at its dollar
    value. Adding the rows' raw amounts together, as before, mixed the two.
    Change is taken off the drawer it really came out of (the sale's change
    account), in that drawer's currency. `exclude`: invoices left out, the
    ones an earlier ERPNext day of the shift holds (roll_day)."""
    from lumenpos import currency

    profile_name = frappe.db.get_value("POS Register Session", session, "pos_profile")
    company = frappe.get_cached_value("POS Profile", profile_name, "company") if profile_name else None
    ccy = currency.company_currency(company) if company else None
    foreign = _foreign_drawers(profile_name) if profile_name else {}
    values = {"session": session, "exclude": tuple(exclude or ()) or ("",)}
    # Both POS Invoice and Sales Invoice use the Sales Invoice Payment child.
    # `doctype` is a fixed doctype name (POS Invoice / Sales Invoice), not user
    # input, and can't be a bound param as a table identifier; the session filter
    # is parameterized. Safe despite the f-string.
    rows = frappe.db.sql(  # nosemgrep
        f"""
        select sip.mode_of_payment, pi.currency,
               sum(sip.amount) as amount, sum(sip.base_amount) as base_amount
        from `tabSales Invoice Payment` sip
        join `tab{doctype}` pi on pi.name = sip.parent and sip.parenttype = '{doctype}'
        where pi.lumenpos_session = %(session)s and pi.docstatus = 1
          and pi.name not in %(exclude)s
        group by sip.mode_of_payment, pi.currency
        """,
        values,
        as_dict=True,
    )
    result = {}
    for row in rows:
        mode_ccy = currency.mode_currency(row.mode_of_payment, company) if company else row.currency
        # In the account's own money: the row amount when the account is in the
        # sale's currency, its company-currency value otherwise.
        value = flt(row.amount) if (row.currency == mode_ccy or not ccy) else flt(row.base_amount)
        result[row.mode_of_payment] = flt(result.get(row.mode_of_payment)) + value

    # `doctype` is a fixed doctype name (POS Invoice / Sales Invoice), not user
    # input; a table identifier can't be a bound param and the session filter is
    # parameterized. Safe despite the f-string.
    change_rows = frappe.db.sql(  # nosemgrep
        f"""
        select account_for_change_amount as account, currency,
               coalesce(sum(change_amount), 0) as change_amount,
               coalesce(sum(base_change_amount), 0) as base_change_amount
        from `tab{doctype}`
        where lumenpos_session = %(session)s and docstatus = 1 and change_amount != 0
          and name not in %(exclude)s
        group by account_for_change_amount, currency
        """,
        values,
        as_dict=True,
    )
    cash_modes = _cash_modes()
    accounts = {
        mode: frappe.db.get_value("Mode of Payment Account", {"parent": mode, "company": company}, "default_account")
        for mode in foreign
    }
    for row in change_rows:
        target = next((mode for mode, account in accounts.items() if account and account == row.account), None)
        if target:
            value = flt(row.change_amount) if row.currency == foreign[target] else flt(row.base_change_amount)
        else:
            # Change is given from the DRAWER. Falling back to "first Cash-type
            # mode" deducted it from whichever tender sorted first (a delivery
            # app typed as Cash, say) and left the drawer over by that amount.
            target = drawer if drawer in result else None
            if target is None:
                target = next((m for m in result if m in cash_modes and m not in foreign), None)
            local = row.currency == ccy or not ccy
            value = flt(row.change_amount) if local else (flt(row.base_change_amount) or flt(row.change_amount))
        if target:
            result[target] = flt(flt(result.get(target)) - value)
    return result

# ---------------------------------------------------------------------------
# Forgotten-shift alert (POS Shift Schedule)
# ---------------------------------------------------------------------------

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _as_time(value):
    """Frappe returns a Time field as a timedelta, normalise to a `time`."""
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
    shift whose end time is at or before its start crosses midnight, a 22:00→06:00
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
    should have ended. ALERT ONLY, never an auto-close: a close without a real
    cash count produces figures nobody can trust."""
    try:
        settings = frappe.get_cached_doc("LumenPOS Settings")
        if not settings.get("overdue_alert_enabled"):
            return
        role = settings.get("overdue_alert_role")
        if not _role_emails(role):
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
            # This outlet's company's managers only.
            recipients = _role_emails(role, frappe.get_cached_value("POS Profile", row.pos_profile, "company"))
            if not recipients:
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
                    f"<p>{_('The till has NOT been closed automatically, a close without a real cash count is worthless.')}</p>"
                ),
            )
            frappe.db.set_value(
                "POS Register Session", row.name, "overdue_notified", 1, update_modified=False
            )
    except Exception:
        frappe.log_error(
            title="LumenPOS overdue-shift alert failed", message=frappe.get_traceback()
        )
