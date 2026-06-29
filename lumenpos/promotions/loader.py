"""Load POS Promotion documents and serialize them for the engine
(and for shipping to the POS frontend, which runs the mirrored JS engine)."""

import frappe

from lumenpos.promotions.engine import DAYS


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
        "start_time": str(doc.start_time) if doc.start_time else None,
        "end_time": str(doc.end_time) if doc.end_time else None,
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
