# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Return restrictions, "we do not take underwear back", expressed against the
catalogue.

A rule refuses ONE kind of product (an item, an item group INCLUDING everything
under it, a brand, or a tag), optionally only at certain outlets. Two strengths:

- `allow_with_approval` on (the default): the cashier cannot return it on their
  own, but may send a return approval request, and the approver decides. This is
  the same request the till already uses for a return past the return window.
- `allow_with_approval` off: the item is never taken back, by anybody.

Enforced in BOTH places on purpose: the refund screen marks the line and says
why, and the server re-checks before posting a credit note, so a stale browser
tab or a direct API call cannot slip past a rule the shop set.

The matching itself is shared with payment_restrictions, so "Item Group means
everything under it" behaves identically in both features.
"""

import frappe
from frappe import _

from lumenpos.payment_restrictions import item_matches


def active_rules(pos_profile=None):
    """Enabled restrictions that apply at this outlet."""
    try:
        names = frappe.get_all("POS Return Restriction", filters={"enabled": 1}, pluck="name")
    except Exception:
        return []  # doctype not migrated yet
    rules = []
    for name in names:
        doc = frappe.get_cached_doc("POS Return Restriction", name)
        outlets = [r.pos_profile for r in (doc.get("pos_profiles") or [])]
        if pos_profile and outlets and pos_profile not in outlets:
            continue
        rules.append(doc)
    return rules


def blocked_items(items, pos_profile=None):
    """Which of these products may not be returned here, as
    {item_code: {"title", "note", "needs_approval"}}.

    `items` = [{item_code, item_group, brand, tags:[...]}] (see
    sales._restriction_items). A product caught by two rules takes the stricter
    one: never returnable wins over returnable with an approval."""
    out = {}
    rules = active_rules(pos_profile)
    if not rules or not items:
        return out
    for item in items:
        for rule in rules:
            if not item_matches(rule, item):
                continue
            needs_approval = bool(rule.allow_with_approval)
            current = out.get(item["item_code"])
            if current and not current["needs_approval"]:
                continue  # already blocked outright, nothing is stricter
            if current and current["needs_approval"] and needs_approval:
                continue  # keep the first reason
            out[item["item_code"]] = {
                "title": rule.title or rule.name,
                "note": (rule.note or "").strip() or None,
                "needs_approval": needs_approval,
            }
    return out


def _describe(item_code, block):
    name = frappe.get_cached_value("Item", item_code, "item_name") or item_code
    if block.get("note"):
        return "{0}: {1}".format(name, block["note"])
    return "{0} ({1})".format(name, block["title"])


def assert_returnable(items, pos_profile=None, approved=False):
    """Server-side gate, the authoritative one. Raises when a line cannot come
    back. `approved` says an approver has already allowed this return."""
    blocked = blocked_items(items, pos_profile)
    if not blocked:
        return
    never = [code for code, block in blocked.items() if not block["needs_approval"]]
    if never:
        frappe.throw(
            _("These items are never taken back: {0}").format(
                ", ".join(_describe(code, blocked[code]) for code in never)
            )
        )
    if approved:
        return
    frappe.throw(
        _("These items need an approved return request: {0}").format(
            ", ".join(_describe(code, blocked[code]) for code in blocked)
        )
    )
