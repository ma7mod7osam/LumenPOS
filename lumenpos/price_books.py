"""Vend-style price books — a set of per-item override prices that apply for a
period, scoped by outlet and customer group, with a priority to break ties.

A price book is NOT a separate ERPNext Price List. It simply holds
(item -> price) rows on the POS Price Book itself: while the book is active
(validity window + outlet + customer group match), those items sell at the book
price; everything else keeps its normal selling price. When several books match,
the HIGHEST priority wins per item. A delivery-app price list (a real ERPNext
Price List on a POS Delivery App row) overrides price books entirely.
"""

import frappe
from frappe.utils import flt, getdate, nowdate


def resolve_price_list(profile, customer_group=None, app_price_list=None):
    """The ERPNext Price List a sale posts against: a delivery app's own list
    when present, otherwise the profile's standard selling list. Price books no
    longer map to a list — they apply as per-item overrides (see book_overrides)."""
    return app_price_list or profile.selling_price_list


def get_price_map(item_codes, price_list, stock_uom_map=None):
    """Batch price lookup for a list of items on one price list."""
    if not item_codes or not price_list:
        return {}
    prices = frappe.get_all(
        "Item Price",
        filters={"item_code": ["in", item_codes], "price_list": price_list, "selling": 1},
        fields=["item_code", "price_list_rate", "uom", "valid_from"],
        order_by="valid_from asc",
    )
    price_map = {}
    for p in prices:
        if p.uom and stock_uom_map and p.uom != stock_uom_map.get(p.item_code):
            continue
        price_map[p.item_code] = p.price_list_rate
    return price_map


def book_overrides(profile, customer_group, item_codes, on_date=None):
    """{item_code: rate} from the active price books that match this outlet,
    customer group and date — highest priority wins per item."""
    if not item_codes:
        return {}
    today = getdate(on_date or nowdate())
    remaining = set(item_codes)
    overrides = {}
    books = frappe.get_all(
        "POS Price Book",
        filters={"status": "Active"},
        fields=["name", "priority", "valid_from", "valid_to"],
        order_by="priority desc, modified desc",
    )
    for book in books:
        if not remaining:
            break
        if book.valid_from and today < getdate(book.valid_from):
            continue
        if book.valid_to and today > getdate(book.valid_to):
            continue
        doc = frappe.get_cached_doc("POS Price Book", book.name)
        profiles = [r.pos_profile for r in (doc.pos_profiles or [])]
        if profiles and profile.name not in profiles:
            continue
        groups = [r.customer_group for r in (doc.customer_groups or [])]
        if groups and (not customer_group or customer_group not in groups):
            continue
        for row in (doc.get("items") or []):
            if row.item_code in remaining:
                overrides[row.item_code] = flt(row.rate)
                remaining.discard(row.item_code)
    return overrides


def effective_prices(profile, item_codes, customer_group=None, app_price_list=None, stock_uom_map=None):
    """The unit price each item actually sells at: the delivery-app price list
    (if any) else the standard selling price, with active price-BOOK overrides
    layered on top (books don't apply when a delivery app is active)."""
    base_list = app_price_list or profile.selling_price_list
    prices = get_price_map(item_codes, base_list, stock_uom_map)
    # Items unpriced on an app list fall back to the standard selling price.
    if app_price_list and app_price_list != profile.selling_price_list:
        missing = [c for c in item_codes if not prices.get(c)]
        if missing:
            for code, rate in get_price_map(missing, profile.selling_price_list, stock_uom_map).items():
                prices.setdefault(code, rate)
    if not app_price_list:
        for code, rate in book_overrides(profile, customer_group, item_codes, ).items():
            prices[code] = rate
    return prices


def standard_prices(profile, item_codes, stock_uom_map=None):
    """The plain selling price (no books, no apps) — promotions on the
    'Standard Price' basis discount from this."""
    return get_price_map(item_codes, profile.selling_price_list, stock_uom_map)


def get_effective_price_map(item_codes, price_list, default_price_list, stock_uom_map=None):
    """Legacy helper kept for the delivery-app price editor: prices from
    `price_list`, falling back to `default_price_list` for unpriced items."""
    effective = get_price_map(item_codes, price_list, stock_uom_map)
    if default_price_list and default_price_list != price_list:
        missing = [code for code in item_codes if not effective.get(code)]
        if missing:
            for code, rate in get_price_map(missing, default_price_list, stock_uom_map).items():
                effective.setdefault(code, rate)
    return effective
