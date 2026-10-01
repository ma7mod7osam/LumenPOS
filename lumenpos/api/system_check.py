# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""The system check (0.57.0): one screen a manager can read, or photograph
and send, that says what is wrong with LumenPOS on this site and what to do.

Every check here is a fault a real shop met: ERPNext 16 set to make Sales
Invoices from the POS, shifts stuck in Closing, an opening entry from an
earlier day blocking an outlet, sales never posted to the books, change that
the books cannot take, a currency whose setup failed, background jobs that
stopped, errors piling up in the Error Log. Read only, and each check runs on
its own: one that cannot run says so and the others still answer.
"""

import sys

import frappe
from frappe import _
from frappe.utils import add_days, add_to_date, cint, flt, get_datetime, now_datetime, nowdate

from lumenpos import __version__, erpnext_compat
from lumenpos.api import permissions

# The ERPNext release of each major version LumenPOS was last tested on (the
# four test benches). A site on a newer one is told so, nothing more.
TESTED = {13: "13.55.2", 14: "14.92.14", 15: "15.120.0", 16: "16.36.0"}

PROBLEM, WARN, INFO, OK = "problem", "warn", "info", "ok"


def _row(area, level, title, detail="", items=None, fix=""):
    return {"area": area, "level": level, "title": title, "detail": detail, "items": items or [], "fix": fix}


def _version_tuple(text):
    out = []
    for part in str(text or "").split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def _versions():
    import erpnext

    return {
        "lumenpos": __version__,
        "erpnext": getattr(erpnext, "__version__", ""),
        "frappe": frappe.__version__,
        "python": "%d.%d.%d" % sys.version_info[:3],
    }


def _check_versions(versions):
    major = _version_tuple(versions["erpnext"])[0]
    tested = TESTED.get(major)
    if not tested:
        return [_row("versions", WARN, _("ERPNext {0} has not been tested with LumenPOS").format(versions["erpnext"]),
                     _("LumenPOS is tested on ERPNext 13 to 16."))]
    if _version_tuple(versions["erpnext"]) > _version_tuple(tested):
        return [_row("versions", INFO, _("ERPNext {0} is newer than the release LumenPOS was last tested on ({1})").format(
            versions["erpnext"], tested), _("Usually fine. If something stops working after an ERPNext update, send this screen."))]
    return [_row("versions", OK, _("ERPNext {0}, tested with LumenPOS").format(versions["erpnext"]))]


def _check_pos_settings():
    out = []
    refused = erpnext_compat.pos_invoice_refused()
    if refused:
        out.append(_row("settings", PROBLEM, _("ERPNext refuses POS Invoices on this site"), refused,
                        fix=_("POS Settings, Invoice Type Created via POS Screen: POS Invoice.")))
    from lumenpos import currency

    if currency.enabled() and not erpnext_compat.change_gl_entries_on():
        out.append(_row("settings", PROBLEM, _("Change given in another currency cannot reach the books"),
                        _("Other currencies are on, but ERPNext does not book change as its own entry."),
                        fix=_("{0}, Create Ledger Entries for Change Amount: on. Saving LumenPOS Settings turns it on.").format(
                            erpnext_compat.change_gl_setting() or "POS Settings")))
    if not out:
        out.append(_row("settings", OK, _("ERPNext accepts the till's invoices")))
    return out


def _outlet_taxes(template):
    rows = frappe.get_all("Sales Taxes and Charges", filters={"parent": template, "parenttype": "Sales Taxes and Charges Template"},
                          fields=["rate", "included_in_print_rate", "charge_type"])
    return rows


def _check_outlets():
    out = []
    profiles = frappe.get_all("POS Profile", filters={"disabled": 0},
                              fields=["name", "company", "warehouse", "selling_price_list", "taxes_and_charges"])
    if not profiles:
        return [_row("outlets", PROBLEM, _("No outlet (POS Profile) is set up"), fix=_("Create a POS Profile in ERPNext."))]
    for p in profiles:
        faults = []
        if not frappe.get_all("POS Payment Method", filters={"parent": p.name, "parenttype": "POS Profile"}, limit=1):
            faults.append(_("no payment methods"))
        if not p.warehouse:
            faults.append(_("no warehouse"))
        elif frappe.get_cached_value("Warehouse", p.warehouse, "company") != p.company:
            faults.append(_("its warehouse belongs to another company"))
        if not p.selling_price_list:
            faults.append(_("no price list"))
        if faults:
            out.append(_row("outlets", PROBLEM, _("Outlet {0} cannot sell").format(p.name), ", ".join(faults),
                            fix=_("Complete the outlet's POS Profile in ERPNext.")))
            continue
        users = frappe.get_all("POS Profile User", filters={"parent": p.name}, limit=1)
        tax = _tax_text(p.taxes_and_charges)
        level = WARN if tax[1] else OK
        detail = tax[0]
        if not users:
            level = INFO if level == OK else level
            detail += " " + _("Nobody is assigned to it yet (POS Profile, Applicable for Users).")
        out.append(_row("outlets", level, _("Outlet {0}").format(p.name), detail.strip()))
    return out


def _tax_text(template):
    """What the till does with tax at this outlet, and whether it is mixed."""
    if not template:
        return _("No tax template: sales carry no tax."), False
    rows = [r for r in _outlet_taxes(template) if r.charge_type != "Actual"]
    if not rows:
        return _("No tax template: sales carry no tax."), False
    rate = flt(sum(flt(r.rate) for r in rows), 2)
    included = [r for r in rows if cint(r.included_in_print_rate)]
    if included and len(included) != len(rows):
        return _("Tax template {0}: some rows are included in prices and some are added on top.").format(template), True
    if included:
        return _("Prices include tax ({0}%): the till shows them as they are and adds nothing at the total.").format(rate), False
    return _("Tax ({0}%) is added on top of prices: the till shows prices before tax and adds it at the total.").format(rate), False


def _check_shifts():
    out = []
    stuck = frappe.get_all(
        "POS Register Session",
        filters={"status": "Closing", "closing_started_at": ["<", add_to_date(now_datetime(), minutes=-30)]},
        fields=["name", "pos_profile", "closing_error", "closing_attempts"],
        limit_page_length=20,
    )
    failed = frappe.get_all("POS Register Session", filters={"status": "Closing", "closing_status": "Failed"},
                            fields=["name", "pos_profile", "closing_error"], limit_page_length=20)
    seen = {r.name for r in stuck}
    stuck += [r for r in failed if r.name not in seen]
    if stuck:
        out.append(_row("shifts", PROBLEM, _("Shifts stuck in Closing: {0}").format(len(stuck)),
                        _("Their sales are not in the books yet."),
                        items=["%s, %s: %s" % (r.name, r.pos_profile, (r.closing_error or "").strip().splitlines()[-1][:140]
                                                if (r.closing_error or "").strip() else _("no reason recorded")) for r in stuck],
                        fix=_("Register page, Retry. If it fails again, send this screen.")))
    old = frappe.get_all(
        "POS Register Session",
        filters={"status": "Open", "opened_at": ["<", add_to_date(now_datetime(), hours=-24)]},
        fields=["name", "pos_profile", "opened_by", "opened_at"],
        order_by="opened_at asc",
        limit_page_length=20,
    )
    if old:
        out.append(_row("shifts", WARN, _("Shifts open for more than a day: {0}").format(len(old)),
                        _("A shift left open holds its sales out of the books, and on ERPNext 16 can block its outlet."),
                        items=["%s, %s, %s, %s" % (r.name, r.pos_profile, r.opened_by, str(r.opened_at)[:16]) for r in old],
                        fix=_("Close them from the Register page (a manager can close anyone's).")))
    if erpnext_compat.one_open_shift_per_outlet():
        ours = {r.pos_opening_entry for r in frappe.get_all("POS Register Session", filters={"status": "Open"},
                                                           fields=["pos_opening_entry"]) if r.pos_opening_entry}
        stale = [
            r for r in frappe.get_all("POS Opening Entry", filters={"docstatus": 1, "status": "Open",
                                                                    "period_start_date": ["<", nowdate()]},
                                      fields=["name", "pos_profile", "user", "period_start_date"], limit_page_length=20)
            if r.name not in ours
        ]
        if stale:
            out.append(_row("shifts", PROBLEM, _("Opening entries from an earlier day blocking their outlet: {0}").format(len(stale)),
                            _("ERPNext 16 sells only on an opening entry opened today, one per outlet."),
                            items=["%s, %s, %s" % (r.name, r.pos_profile, r.period_start_date) for r in stale],
                            fix=_("Close them in ERPNext (POS Closing Entry) or cancel them if they hold no sales.")))
    unposted = frappe.db.sql(
        """select count(*), min(posting_date) from `tabPOS Invoice`
        where docstatus = 1 and ifnull(consolidated_invoice, '') = '' and posting_date < %s""",
        add_days(nowdate(), -3),
    )
    if unposted and cint(unposted[0][0]):
        out.append(_row("shifts", WARN, _("Sales older than 3 days not in the books: {0}").format(cint(unposted[0][0])),
                        _("Oldest from {0}. Their stock has not moved yet and they are missing from the accounts.").format(unposted[0][1]),
                        fix=_("Close the shifts they belong to. A shift stuck in Closing shows above.")))
    from lumenpos.api import register

    pending = register._sessions_with_pending_days()
    if pending:
        out.append(_row("shifts", WARN, _("Shifts with an ERPNext day past midnight still to post: {0}").format(len(pending)),
                        items=pending, fix=_("Register page, Retry, or wait for the next background run.")))
    if not out:
        out.append(_row("shifts", OK, _("No shift needs attention")))
    return out


def _check_settings():
    out = []
    from lumenpos import currency
    from lumenpos.api import salespeople

    if salespeople.mode() == "Required" and not frappe.get_all("Sales Person", filters={"enabled": 1, "is_group": 0}, limit=1):
        out.append(_row("settings", PROBLEM, _("A salesperson is required but none exists"),
                        _("Every sale will be refused."),
                        fix=_("Add a Sales Person in ERPNext, or set Salesperson at the till to Optional.")))
    if currency.enabled():
        for code, reason in sorted(currency.setup_errors().items()):
            text = reason.decode() if isinstance(reason, bytes) else reason
            out.append(_row("settings", PROBLEM, _("Currency {0} is not set up").format(code), text,
                            fix=_("Settings, General, Other currencies: fix the reason and save.")))
        settings = frappe.get_cached_doc("LumenPOS Settings")
        for row in settings.get("sale_currencies") or []:
            status = currency.auto_status(row)
            if (row.get("rate_source") or "") == "Automatic" and status.get("error"):
                out.append(_row("settings", WARN, _("The automatic rate for {0} did not update").format(row.currency),
                                status.get("error"), fix=_("The last rate is kept. Settings, Other currencies, Update now.")))
    from lumenpos import install

    missing = [r for r in install.index_health() if r.get("state") == "missing"]
    if missing:
        out.append(_row("settings", WARN, _("Performance indexes missing: {0}").format(len(missing)),
                        _("Sales, search and shift reports slow down on a large site."),
                        items=["%s: %s" % (r["doctype"], r["columns"]) for r in missing],
                        fix=_("Settings, Status, Rebuild missing indexes.")))
    try:
        auto_price = cint(frappe.db.get_single_value("Stock Settings", "auto_insert_price_list_rate_if_missing"))
    except Exception:
        auto_price = 0
    if auto_price:
        out.append(_row("settings", INFO, _("ERPNext adds a missing item price from a sale"),
                        _("Stock Settings, Auto Insert Item Price If Missing is on: a sale of an item with no price in the price list writes that sale's rate into it.")))
    if not out:
        out.append(_row("settings", OK, _("Settings are consistent")))
    return out


def _check_errors():
    out = []
    since = add_days(now_datetime(), -7)
    rows = frappe.db.sql(
        """select method, error from `tabError Log`
        where creation >= %s and (method like 'LumenPOS%%' or error like '%%/lumenpos/%%')
        order by creation desc limit 500""",
        since,
        as_dict=True,
    )
    groups = {}
    slow = 0
    for r in rows:
        if (r.method or "").startswith("LumenPOS slow sale"):
            slow += 1
            continue
        lines = [x for x in (r.error or "").strip().splitlines() if x.strip()]
        key = ((r.method or "")[:80], (lines[-1].strip() if lines else "")[:160])
        groups[key] = groups.get(key, 0) + 1
    if groups:
        top = sorted(groups.items(), key=lambda kv: -kv[1])[:8]
        out.append(_row("errors", WARN, _("LumenPOS errors in the last 7 days: {0}").format(sum(groups.values())),
                        _("Grouped, most frequent first."),
                        items=["%s x %s: %s" % (n, method, last) for (method, last), n in top],
                        fix=_("Send this screen with the Error Log entries (ERPNext, Error Log).")))
    else:
        out.append(_row("errors", OK, _("No LumenPOS errors in the last 7 days")))
    if slow:
        out.append(_row("errors", INFO, _("Slow sales logged in the last 7 days: {0}").format(slow),
                        _("A sale that took longer than usual is written to the Error Log with its timings.")))
    out += _check_jobs(since)
    return out


def _check_jobs(since):
    out = []
    try:
        from frappe.utils.scheduler import is_scheduler_disabled

        disabled = is_scheduler_disabled()
    except Exception:
        disabled = False
    if disabled:
        out.append(_row("errors", PROBLEM, _("Background jobs are switched off on this site"),
                        _("Stuck shifts are not retried, nightly cashback, rates and settlements do not run."),
                        fix=_("Enable the scheduler (bench enable-scheduler, or ask the hosting provider).")))
        return out
    if not frappe.db.table_exists("Scheduled Job Log"):
        return out
    failed = frappe.db.sql(
        """select t.method, count(*) from `tabScheduled Job Log` l
        join `tabScheduled Job Type` t on t.name = l.scheduled_job_type
        where t.method like 'lumenpos.%%' and l.status = 'Failed' and l.creation >= %s
        group by t.method""",
        since,
    )
    if failed:
        out.append(_row("errors", WARN, _("LumenPOS background jobs failed in the last 7 days"),
                        items=["%s x %s" % (n, method) for method, n in failed],
                        fix=_("Send this screen. The jobs run again on their own.")))
    last = frappe.db.sql(
        """select max(l.creation) from `tabScheduled Job Log` l
        join `tabScheduled Job Type` t on t.name = l.scheduled_job_type
        where t.method = 'lumenpos.api.register.reconcile_stuck_closings'"""
    )
    when = last[0][0] if last else None
    if when and get_datetime(when) < add_to_date(now_datetime(), hours=-2):
        out.append(_row("errors", WARN, _("LumenPOS background jobs have not run since {0}").format(str(when)[:16]),
                        _("They should run every 10 minutes. The workers may be stopped."),
                        fix=_("Check the site's background workers (on Frappe Cloud, the bench's Jobs).")))
    return out


CHECKS = (_check_pos_settings, _check_outlets, _check_shifts, _check_settings, _check_errors)


@frappe.whitelist()
def run():
    """Every check, worst first within each area. For whoever may "See the
    system check" (managers always)."""
    if not permissions.can_see_system_check():
        frappe.throw(_("You're not allowed to see the system check."), frappe.PermissionError)
    versions = _versions()
    rows = _check_versions(versions)
    for check in CHECKS:
        try:
            rows += check()
        except Exception as exc:
            frappe.db.rollback()
            rows.append(_row("errors", WARN, _("A check could not run"), "%s: %s" % (check.__name__.replace("_check_", ""), str(exc)[:200])))
    return {"versions": versions, "site": frappe.local.site, "checked_at": str(now_datetime())[:19], "rows": rows,
            "counts": {level: sum(1 for r in rows if r["level"] == level) for level in (PROBLEM, WARN, INFO, OK)}}
