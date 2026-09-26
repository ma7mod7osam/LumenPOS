# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""POS Cashback Rule: load the rules and work out what a sale earns.

A cashback rule reuses the promotion engine's schedule, eligibility and product
targeting exactly (same date, day, time, outlet, customer group, coupon and
item, item group, brand or tag matching), so the two stay consistent and there
is one place that decides whether something applies to a cart. What differs is
the reward: a percentage of the qualifying items or a fixed amount, capped, with
a minimum spend, and a validity window on what is earned.
"""

from frappe.utils import flt

from lumenpos.promotions.engine import DAYS, _matching_indexes, is_active
from lumenpos.promotions.loader import time_str


def serialize(doc):
    """A POS Cashback Rule as the plain dict the evaluator (and is_active) read.
    The schedule and targeting keys match a promotion's on purpose."""
    return {
        "name": doc.name,
        "title": doc.title,
        "status": doc.status,
        "priority": doc.priority or 0,
        "stackable": doc.stackable or 0,
        "amount_type": doc.amount_type or "Percentage",
        "amount_value": flt(doc.amount_value),
        "max_cashback": flt(doc.max_cashback),
        "min_spend": flt(doc.min_spend),
        "validity_days": int(doc.validity_days or 0),
        "activation_delay_days": int(doc.activation_delay_days or 0),
        "start_date": str(doc.start_date) if doc.start_date else None,
        "end_date": str(doc.end_date) if doc.end_date else None,
        "start_time": time_str(doc.start_time),
        "end_time": time_str(doc.end_time),
        "days": {day: doc.get(day) or 0 for day in DAYS},
        "pos_profiles": [row.pos_profile for row in (doc.pos_profiles or [])],
        "company": doc.get("company"),
        "customer_eligibility": doc.customer_eligibility or "All Customers",
        "customer_groups": [row.customer_group for row in (doc.customer_groups or [])],
        "requires_coupon": doc.requires_coupon or 0,
        "coupon_code": doc.coupon_code if doc.requires_coupon else None,
        "apply_on_all": doc.apply_on_all or 0,
        "items": [
            {
                "applies_to": row.applies_to,
                "value": (
                    row.item_code
                    if row.applies_to == "Item"
                    else row.item_group
                    if row.applies_to == "Item Group"
                    else row.brand
                    if row.applies_to == "Brand"
                    else row.get("tag")
                ),
                "exclude": row.get("exclude") or 0,
            }
            for row in (doc.items or [])
        ],
    }


def get_active_rules(pos_profile=None, include_coupon=False):
    """Every Active cashback rule, pre-filtered by outlet. Date and time
    filtering is left to the evaluator so a cached client copy keeps working as
    the clock moves. Coupon-locked rules are excluded unless asked for, so a
    code never leaks to the browser."""
    import frappe

    names = frappe.get_all("POS Cashback Rule", filters={"status": "Active"}, pluck="name")
    rules = []
    for name in names:
        rule = serialize(frappe.get_doc("POS Cashback Rule", name))
        from lumenpos import scope

        if not scope.applies_to(rule["company"], rule["pos_profiles"], pos_profile):
            continue
        if rule["requires_coupon"] and not include_coupon:
            continue
        rules.append(rule)
    return rules


def _qualifying_subtotal(cart, rule):
    """The amount of the cart the rule rewards: the matching lines, or the whole
    basket when it applies to everything."""
    items = cart.get("items") or []
    if rule.get("apply_on_all") or not rule.get("items"):
        indexes = range(len(items))
    else:
        indexes = _matching_indexes(cart, rule)
    return flt(sum(flt(items[i].get("amount")) for i in indexes), 2)


def _rule_cashback(rule, subtotal):
    """The cashback one rule pays on a qualifying subtotal, after the minimum
    spend, the type and the cap."""
    subtotal = flt(subtotal, 2)
    if subtotal <= 0 or subtotal + 0.005 < flt(rule.get("min_spend")):
        return 0.0
    if rule.get("amount_type") == "Fixed":
        amount = flt(rule.get("amount_value"))
    else:
        amount = subtotal * flt(rule.get("amount_value")) / 100.0
    cap = flt(rule.get("max_cashback"))
    if cap and amount > cap:
        amount = cap
    return flt(max(0.0, amount), 2)


def evaluate_earn(cart, rules, now, cashback_tendered=0.0):
    """What this cart earns. Stackable rules add up; the non-stackable ones
    compete and the best single one wins, then the two are summed, mirroring how
    promotions stack.

    `cashback_tendered` is how much of THIS sale was paid with cashback. It is
    taken off each rule's qualifying subtotal first, so paying with cashback
    cannot be churned back into new cashback.
    """
    tendered = flt(cashback_tendered)
    stack_total = 0.0
    best_exclusive = 0.0
    breakdown = []
    for rule in rules:
        if (rule.get("status") or "Active") != "Active":
            continue
        if not is_active(rule, now, cart):
            continue
        subtotal = max(0.0, _qualifying_subtotal(cart, rule) - tendered)
        amount = _rule_cashback(rule, subtotal)
        if amount <= 0:
            continue
        entry = {
            "rule": rule["name"],
            "title": rule.get("title"),
            "amount": amount,
            "validity_days": rule.get("validity_days") or 0,
            "activation_delay_days": rule.get("activation_delay_days") or 0,
        }
        if rule.get("stackable"):
            stack_total += amount
            breakdown.append(entry)
        elif amount > best_exclusive:
            best_exclusive = amount
            entry["_exclusive"] = True
            breakdown = [b for b in breakdown if not b.get("_exclusive")] + [entry]
    total = flt(stack_total + best_exclusive, 2)
    kept = [{k: v for k, v in b.items() if k != "_exclusive"} for b in breakdown]
    return {"total": total, "breakdown": kept}


def enabled():
    """The admin toggle in LumenPOS Settings. Not-set counts as ON, the
    default a fresh install gets."""
    import frappe
    from frappe.utils import cint

    row = frappe.db.sql(
        "select value from tabSingles where doctype=%s and field=%s",
        ("LumenPOS Settings", "enable_cashback"),
    )
    value = row[0][0] if row else None
    return True if value is None else bool(cint(value))
