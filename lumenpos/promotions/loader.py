# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Load POS Promotion documents and serialize them for the engine
(and for shipping to the POS frontend, which runs the mirrored JS engine)."""

import datetime

import frappe

from lumenpos.promotions.engine import DAYS


def time_str(value):
    """A Time field as a plain, zero padded "HH:MM:SS" string, or None.

    Two things make this necessary:

    * Frappe stores Time columns as time(6) and REFILLS an empty one with the
      current time on insert. A promotion saved with no daily window therefore
      lands with a start and an end a few microseconds apart, which the engines
      read as a window that is open for a few microseconds a day - so the
      promotion never applies. Truncating to whole seconds hides that whenever
      both refills land inside the same second, and clear_accidental_window()
      plus the engines' one minute guard handle the case where they do not.
    * The raw value is a timedelta, and str(timedelta) drops the leading zero
      ("9:00:00"), which breaks the string comparison the engines do against
      "%H:%M:%S". Pad it here, once, for both engines.
    """
    if value is None or value == "":
        return None
    if isinstance(value, datetime.timedelta):
        total = int(value.total_seconds())
    elif isinstance(value, datetime.time):
        total = value.hour * 3600 + value.minute * 60 + value.second
    else:
        parts = str(value).split(".")[0].split(":")
        try:
            nums = [int(p) for p in parts[:3]]
        except ValueError:
            return None
        while len(nums) < 3:
            nums.append(0)
        total = nums[0] * 3600 + nums[1] * 60 + nums[2]
    total %= 24 * 3600
    return "%02d:%02d:%02d" % (total // 3600, (total % 3600) // 60, total % 60)


def clear_accidental_window(doc):
    """Blank a daily window nobody set. Frappe fills an empty Time field with
    the moment of the save, so a promotion or cashback rule saved anywhere but
    LumenPOS's own screen (the desk form, an import, a script) lands with a
    start and an end milliseconds apart. Read literally that is a window open
    for a blink each day, which switches the record off. A window under a
    minute is never typed by a person, so clear both times in the database,
    right after the save that created them. The engines carry the same guard
    for records saved before this existed."""
    from lumenpos.promotions.engine import window_seconds

    start_t, end_t = time_str(doc.start_time), time_str(doc.end_time)
    if not (start_t and end_t) or window_seconds(start_t, end_t) >= 60:
        return
    doc.start_time = None
    doc.end_time = None
    frappe.db.set_value(
        doc.doctype, doc.name, {"start_time": None, "end_time": None}, update_modified=False
    )


def serialize(doc):
    return {
        "name": doc.name,
        "title": doc.title,
        "status": doc.status,
        "promotion_type": doc.promotion_type,
        "priority": doc.priority or 1,
        "stackable": doc.stackable or 0,
        "price_basis": doc.get("price_basis") or "Price Book Price",
        "start_date": str(doc.start_date) if doc.start_date else None,
        "end_date": str(doc.end_date) if doc.end_date else None,
        "start_time": time_str(doc.start_time),
        "end_time": time_str(doc.end_time),
        "days": {day: doc.get(day) or 0 for day in DAYS},
        "pos_profiles": [row.pos_profile for row in (doc.pos_profiles or [])],
        "customer_eligibility": doc.customer_eligibility or "All Customers",
        "customer_groups": [row.customer_group for row in (doc.customer_groups or [])],
        "apply_on_all": doc.apply_on_all or 0,
        "requires_coupon": doc.requires_coupon or 0,
        "coupon_code": doc.coupon_code if doc.requires_coupon else None,
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
                "role": row.role or "Buy",
                "qty": row.qty or 1,
                "exclude": row.get("exclude") or 0,
            }
            for row in (doc.items or [])
        ],
        "discount_type": doc.discount_type,
        "discount_value": doc.discount_value or 0,
        "buy_qty": doc.buy_qty or 0,
        "get_qty": doc.get_qty or 0,
        "get_discount_type": doc.get_discount_type or "Free",
        "get_discount_value": doc.get_discount_value or 0,
        "max_applications": doc.max_applications or 0,
        "min_spend": doc.min_spend or 0,
        "basket_discount_type": doc.basket_discount_type or "Percentage",
        "basket_discount_value": doc.basket_discount_value or 0,
        "bundle_price": doc.bundle_price or 0,
    }


def get_active_promotions(pos_profile=None, include_coupon=False, coupon_only=False):
    """All Active promotions, pre-filtered by outlet to keep the client
    payload small. Date/time filtering is left to the engine so a cached
    client copy keeps working as the clock moves.

    Coupon-locked promotions are EXCLUDED by default so codes never leak to
    the browser; they're delivered one at a time via check_coupon, and the
    server evaluates with include_coupon=True on submit."""
    names = frappe.get_all("POS Promotion", filters={"status": "Active"}, pluck="name")
    promos = []
    for name in names:
        # get_doc (not get_cached_doc): a stale cross-worker cache must never
        # serve an outdated promotion to a till
        promo = serialize(frappe.get_doc("POS Promotion", name))
        if pos_profile and promo["pos_profiles"] and pos_profile not in promo["pos_profiles"]:
            continue
        if promo["requires_coupon"]:
            if not (include_coupon or coupon_only):
                continue
        elif coupon_only:
            continue
        promos.append(promo)
    return promos
