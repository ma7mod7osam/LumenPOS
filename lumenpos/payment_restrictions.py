"""Payment restrictions — "no gift cards on Tamara", expressed against the
catalogue.

A rule blocks ONE mode of payment when the cart contains a matching item
(by item, item group INCLUDING everything under it, brand, or tag), optionally
only at certain outlets.

Enforced in BOTH places on purpose: the till greys the method out so the cashier
never picks it, and the server re-checks before posting — a stale browser tab, a
queued offline sale or a direct API call must not be able to slip past a rule the
shop set.
"""

import frappe
from frappe import _


def _item_group_descendants(group):
    """A group and every group beneath it (nested set), so a rule on
    "Electronics" also covers "Electronics > Phones"."""
    node = frappe.db.get_value("Item Group", group, ["lft", "rgt"], as_dict=True)
    if not node:
        return [group]
    return frappe.get_all(
        "Item Group", filters={"lft": [">=", node.lft], "rgt": ["<=", node.rgt]}, pluck="name"
    )


def active_rules(pos_profile=None):
    """Enabled restrictions that apply at this outlet."""
    try:
        names = frappe.get_all("POS Payment Restriction", filters={"enabled": 1}, pluck="name")
    except Exception:
        return []  # doctype not migrated yet
    rules = []
    for name in names:
        doc = frappe.get_cached_doc("POS Payment Restriction", name)
        outlets = [r.pos_profile for r in (doc.get("pos_profiles") or [])]
        if pos_profile and outlets and pos_profile not in outlets:
            continue
        rules.append(doc)
    return rules


def _item_matches(rule, item):
    """`item` = {item_code, item_group, brand, tags:[...]}"""
    applies = rule.applies_to or "Item Group"
    if applies == "Item":
        return rule.item_code and item.get("item_code") == rule.item_code
    if applies == "Item Group":
        if not rule.item_group:
            return False
        return item.get("item_group") in set(_item_group_descendants(rule.item_group))
    if applies == "Brand":
        return rule.brand and item.get("brand") == rule.brand
    if applies == "Tag":
        return rule.tag and rule.tag in (item.get("tags") or [])
    return False


def blocked_modes(items, pos_profile=None):
    """Modes of payment that may NOT be used for this basket, as
    {mode: "why"}. `items` = the resolved cart lines."""
    out = {}
    rules = active_rules(pos_profile)
    if not rules or not items:
        return out
    for rule in rules:
        if not rule.mode_of_payment:
            continue
        for item in items:
            if _item_matches(rule, item):
                out[rule.mode_of_payment] = rule.title or rule.name
                break
    return out


def assert_allowed(items, payments, pos_profile=None):
    """Server-side gate — the authoritative one. Raises if a payment uses a mode
    blocked for this basket."""
    from frappe.utils import flt

    used = {p.get("mode_of_payment") for p in (payments or []) if flt(p.get("amount"))}
    if not used:
        return
    blocked = blocked_modes(items, pos_profile)
    clash = [m for m in used if m in blocked]
    if clash:
        frappe.throw(
            _("{0} can't be used for this sale ({1}). Choose another payment method.").format(
                ", ".join(sorted(clash)), blocked[clash[0]]
            )
        )
