# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""A reason for a short or over at the close (0.59.0).

Asked by the Zimbabwe shop (2026-10-02): "when closing a register, if there is
a short or over, there should be an option to put a reason or action". When a
counted drawer differs from what it should hold, the cashier writes the reason
in their own words, or taps one of the shop's reasons (owner, 2026-10-03: "ليش
ما نخليه يكتب سبب من عنده"), and can say what was done about it. Both are kept
on the shift (POS Register Session.variance_reason, variance_action), shown in
Previous sessions and the close panel, and sent with the variance email. A
tapped reason is kept as the shop wrote it, so it reads in each language.

LumenPOS Settings, General, Register and shifts:
- variance_reason_mode: Optional (the default: offered, never forced), Required
  (the register does not close without a reason, checked on the server), Off.
- variance_reason_threshold: in the company currency, a drawer in another
  currency valued at its shift rate. Required asks only past it (0 = any
  difference). Optional offers the reason for any difference.
- variance_reasons: the shop's quick reasons (POS Variance Reason rows),
  seeded once with DEFAULT_REASONS.

A close whose expected takings could not be worked out claims no difference
(register.close_register keeps expected_pending), so it asks for no reason.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt

MODES = ("Optional", "Required", "Off")
DEFAULT_REASONS = [
    "Counting mistake",
    "Wrong change given",
    "Sale or refund not recorded",
    "Cash paid out without a record",
    "Card or transfer counted as cash",
    "Theft or loss",
]
SEEDED_FLAG = "lumenpos_variance_reasons_seeded"
# A difference this small is rounding, not a short or over.
EPSILON = 0.005


def mode():
    """Optional, Required or Off."""
    try:
        value = frappe.db.get_single_value("LumenPOS Settings", "variance_reason_mode")
    except Exception:
        value = None  # a site that pulled the code without migrating
    return value if value in MODES else "Optional"


def threshold():
    try:
        return max(flt(frappe.db.get_single_value("LumenPOS Settings", "variance_reason_threshold")), 0)
    except Exception:
        return 0.0


def reasons():
    """The shop's reasons, in its order, without blanks or repeats."""
    try:
        rows = frappe.get_cached_doc("LumenPOS Settings").get("variance_reasons") or []
    except Exception:
        return []
    out, seen = [], set()
    for row in rows:
        reason = (row.reason or "").strip()
        if reason and reason.casefold() not in seen:
            seen.add(reason.casefold())
            out.append(reason)
    return out


def client_facts():
    """What the till needs to ask (session bootstrap and get_settings)."""
    return {"variance_reason_mode": mode(), "variance_reason_threshold": threshold(), "variance_reasons": reasons()}


def apply(doc, reason, action, figures_known):
    """Check and keep the reason on a shift being closed, before anything is
    saved: a refusal leaves the shift open. `doc.payment_counts` holds the
    counts with their differences. Raises when Required and missing."""
    from lumenpos.api.register import _in_company_currency

    current = mode()
    reason = (reason or "").strip()[:140]
    action = (action or "").strip()[:500]
    differs = [r for r in (doc.get("payment_counts") or []) if abs(flt(r.difference)) > EPSILON]
    if current == "Off" or not figures_known or not differs:
        doc.variance_reason = None
        doc.variance_action = None
        return
    limit = threshold()
    over = [r for r in differs if abs(_in_company_currency(doc, r.difference, r.get("currency"))) > limit + EPSILON]
    if current == "Required" and over and not reason:
        frappe.throw(_("The count is short or over: write a reason before closing the register."),
                     title=_("Reason for the difference"))
    doc.variance_reason = reason or None
    doc.variance_action = action or None


def ensure_reasons():
    """Seed the starter reasons once (after_migrate). An admin's list, even an
    emptied one, is never touched again."""
    if frappe.db.get_default(SEEDED_FLAG):
        return
    meta = frappe.get_meta("LumenPOS Settings")
    if not meta.has_field("variance_reasons"):
        return
    doc = frappe.get_single("LumenPOS Settings")
    if not (doc.get("variance_reasons") or []):
        for reason in DEFAULT_REASONS:
            doc.append("variance_reasons", {"reason": reason})
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        doc.save()
    frappe.db.set_default(SEEDED_FLAG, "1")
