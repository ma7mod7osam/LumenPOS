# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""The Insights page: full sales statistics, delivered through Lumen Reports.

LumenPOS draws no charts of its own. When the separate Lumen Reports app is on
the site it exposes a small, documented contract (its
lumen_reports.integrations.lumenpos module, contract version 1): a GET
get_status that says what the POS should show, a POST ensure_dashboard that
creates the ready-made POS sales dashboard once, and one embed URL. LumenPOS
calls those two functions by dotted path at runtime and embeds the dashboard.
When the app is absent, the page suggests installing it.

Every combination degrades to a clear message rather than an error: Frappe older
than Lumen Reports supports (it needs v15, LumenPOS runs back to v13), the app
not installed, an installed release too old to carry the contract, or one of
Lumen Reports' own refusals (needs a role, not permitted, subscription lapsed),
which come back as a status and a message that this page shows as they are.

Licence boundary: LumenPOS is AGPL-3.0-only and Lumen Reports is proprietary.
The two meet only at that documented contract. Nothing here imports Lumen
Reports, and no code crosses in either direction. The module is resolved by
name at call time, never imported.
"""

import frappe
from frappe import _
from frappe.utils import cint

# The Lumen Reports contract. If a future release of theirs moves the module,
# this one line changes.
INTEGRATION_MODULE = "lumen_reports.integrations.lumenpos"
MIN_FRAPPE_MAJOR = 15  # Lumen Reports supports Frappe v15 and v16


def set_setting(field, value):
    """Write one LumenPOS Settings value, on every supported version.

    v14+ has db.set_single_value, the API Frappe now wants for a Single. v13
    does not, so there it goes through the loaded document's db_set, which
    updates tabSingles the same way. Deliberately NOT frappe.db.set_value on a
    Single: that path is deprecated on newer Frappe and flagged by the
    marketplace audit."""
    setter = getattr(frappe.db, "set_single_value", None)
    if setter:
        setter("LumenPOS Settings", field, value)
    else:
        frappe.get_single("LumenPOS Settings").db_set(field, value)
    frappe.clear_document_cache("LumenPOS Settings", "LumenPOS Settings")


def _stored_toggle():
    """The stored value, or None while nothing was ever stored.

    Neither the loaded Single (init_valid_columns zeroes a missing Check
    field) nor get_single_value (it casts a missing Check to 0) can say
    "not set yet", so ask the tabSingles row itself."""
    row = frappe.db.sql(
        "select value from tabSingles where doctype=%s and field=%s",
        ("LumenPOS Settings", "enable_insights"),
    )
    return row[0][0] if row else None


def enabled():
    """The admin toggle. Not-set counts as ON, the default a fresh install
    gets. install.ensure_setup writes the ON down on the first migrate, so
    the fallback only matters in the window before that runs."""
    value = _stored_toggle()
    return True if value is None else bool(cint(value))


def _require_access():
    from lumenpos.api import permissions

    if not enabled():
        frappe.throw(_("Insights are turned off in LumenPOS Settings"))
    if not permissions.is_manager():
        frappe.throw(_("Only managers can view Insights"), frappe.PermissionError)


def _frappe_major():
    try:
        return int(str(frappe.__version__).split(".")[0])
    except Exception:
        return 0


def _installed():
    return "lumen_reports" in frappe.get_installed_apps()


def _api(name):
    """Resolve one function of the Lumen Reports contract, or None when the
    installed release does not carry it yet (or the app is absent). Resolving
    by name at call time keeps the two apps from importing each other."""
    try:
        return frappe.get_attr(INTEGRATION_MODULE + "." + name)
    except Exception:
        return None


def _lang():
    """The desk language, so the dashboard's headings match the till. The POS
    itself picks its own language client-side; this is only the default the
    server passes when the dashboard is first built."""
    return str(getattr(frappe.local, "lang", None) or "en")


@frappe.whitelist()
def status():
    """Everything the Insights page needs to decide what to draw. When Lumen
    Reports is present and compatible, its own get_status is the authority on
    role, audience and licence state, so its reply is passed straight through
    under `lr`."""
    _require_access()
    out = {
        "compatible": _frappe_major() >= MIN_FRAPPE_MAJOR,
        "min_frappe": MIN_FRAPPE_MAJOR,
        "installed": _installed(),
        "integration_ready": False,
        "lr": None,
    }
    if not (out["compatible"] and out["installed"]):
        return out
    get_status = _api("get_status")
    out["integration_ready"] = get_status is not None
    if get_status:
        try:
            out["lr"] = get_status()
        except Exception as exc:
            frappe.clear_last_message()
            out["lr_error"] = str(exc)
    return out


@frappe.whitelist()
def ensure_dashboard(lang=None):
    """Ask Lumen Reports to create the POS sales dashboard. Their side is
    idempotent and never overwrites a dashboard that already exists, so this is
    safe to call repeatedly. Returns the fresh status()."""
    _require_access()
    if _frappe_major() < MIN_FRAPPE_MAJOR:
        frappe.throw(_("Lumen Reports needs Frappe v{0} or newer").format(MIN_FRAPPE_MAJOR))
    if not _installed():
        frappe.throw(_("Lumen Reports is not installed on this site"))
    ensure = _api("ensure_dashboard")
    if ensure is None:
        frappe.throw(
            _(
                "This version of Lumen Reports does not include the LumenPOS "
                "dashboard yet. Update Lumen Reports, then try again."
            )
        )
    result = ensure(lang=lang or _lang()) or {}
    # Success is status == "ready". Their refusal payload also carries a slug
    # (both share the same links block), so keying on slug would read a refusal
    # as success. Surface the refusal's own message instead.
    if result.get("status") != "ready":
        frappe.throw(result.get("message") or _("Lumen Reports could not set up the dashboard"))
    return status()
