"""Pure promotion-evaluation engine (Vend / Lightspeed X-Series style).

This module has NO Frappe imports. Carts and promotion definitions are plain
dicts, so the engine can be unit-tested standalone and is mirrored line-for-line
in the POS frontend (frontend/src/promotions.js). If you change behaviour here,
change it there too.

Promotion dict shape (produced by lumenpos.promotions.loader.serialize):
    {
        "name": "PROMO-0001",
        "title": "Buy 2 Get 1 Free",
        "promotion_type": "Simple Discount" | "Buy X Get Y" | "Spend and Save",
        "priority": 1,                  # higher wins ties between exclusives
        "stackable": 0 | 1,
        "start_date": "2026-01-01" | None,
        "end_date": "2026-12-31" | None,
        "start_time": "HH:MM:SS" | None,   # daily window; wraps midnight if start > end
        "end_time": "HH:MM:SS" | None,
        "days": {"monday": 1, ... "sunday": 1},
        "pos_profiles": [],             # empty = all outlets
        "customer_eligibility": "All Customers" | "Selected Customer Groups",
        "customer_groups": [],
        "apply_on_all": 0 | 1,
        "items": [{"applies_to": "Item"|"Item Group"|"Brand", "value": "...", "role": "Buy"|"Get"}],
        # Simple Discount
        "discount_type": "Percentage" | "Amount" | "Fixed Price",
        "discount_value": 10.0,
        # Buy X Get Y
        "buy_qty": 2, "get_qty": 1,
        "get_discount_type": "Free" | "Percentage" | "Amount" | "Fixed Price",
        "get_discount_value": 0.0,
        "max_applications": 0,          # 0 = unlimited repeats per sale
        # Spend and Save
        "min_spend": 100.0,
        "basket_discount_type": "Percentage" | "Amount",
        "basket_discount_value": 10.0,
    }

Cart dict shape:
    {
        "customer_group": "Retail" | None,
        "pos_profile": "Main Store" | None,
        "items": [{"item_code", "item_group", "brand", "qty", "price"}],
    }
    `price` is the unit selling price before any discounts.

evaluate() returns:
    {
        "line_discounts": [total discount amount per cart line, aligned by index],
        "line_promotions": [[promo titles per line]],
        "basket_discount": 0.0,
        "applied": [{"name", "title", "promotion_type", "savings"}],
        "total_savings": 0.0,
    }

Stacking rule (documented behaviour, kept deliberately simple and predictable):
  - All applicable promotions marked `stackable` combine with each other.
  - Non-stackable promotions compete: only the single one with the highest
    total savings can apply.
  - The engine then picks whichever is worth more to the customer: the combined
    stackable set, or the best non-stackable promotion alone.
  - Line discounts are always capped at the line total; the basket discount is
    capped at what remains of the basket after line discounts.
"""

from datetime import datetime

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ---------------------------------------------------------------------------
# Applicability filters
# ---------------------------------------------------------------------------

def is_active(promo, now, cart):
    """Date window, daily time window, weekday, outlet and customer checks."""
    date_str = now.strftime("%Y-%m-%d")
    if promo.get("start_date") and date_str < str(promo["start_date"]):
        return False
    if promo.get("end_date") and date_str > str(promo["end_date"]):
        return False

    days = promo.get("days") or {}
    # Misconfiguration guard: a promotion with every day unticked is treated
    # as running every day rather than never.
    if any(days.values()):
        if not days.get(DAYS[now.weekday()]):
            return False

    start_t, end_t = promo.get("start_time"), promo.get("end_time")
    if start_t and end_t:
        start_t, end_t = _norm_time(start_t), _norm_time(end_t)
        # Equal times (e.g. both saved as 00:00:00 by an empty form field)
        # mean "no daily window" — the promotion runs all day.
        if start_t != end_t:
            t = now.strftime("%H:%M:%S")
            if start_t <= end_t:
                if not (start_t <= t <= end_t):
                    return False
            else:  # window wraps midnight, e.g. 22:00 - 02:00
                if not (t >= start_t or t <= end_t):
                    return False

    profiles = promo.get("pos_profiles") or []
    if profiles and cart.get("pos_profile") not in profiles:
        return False

    if promo.get("requires_coupon"):
        codes = {str(c).upper() for c in (cart.get("coupon_codes") or [])}
        if (promo.get("coupon_code") or "").upper() not in codes:
            return False

    if promo.get("customer_eligibility") == "Selected Customer Groups":
        groups = promo.get("customer_groups") or []
        if not cart.get("customer_group") or cart["customer_group"] not in groups:
            return False

    return True


def _norm_time(value):
    value = str(value)
    return value if len(value) > 5 else value + ":00"


def _line_matches(line, rows, role=None):
    """Does a cart line match any promotion item row (optionally of a role)?"""
    for row in rows:
        if role and (row.get("role") or "Buy") != role:
            continue
        applies_to = row.get("applies_to") or "Item"
        value = row.get("value")
        if applies_to == "Item" and line.get("item_code") == value:
            return True
        if applies_to == "Item Group" and line.get("item_group") == value:
            return True
        if applies_to == "Brand" and line.get("brand") == value:
            return True
        if applies_to == "Tag" and value in (line.get("tags") or []):
            return True
    return False


def _matching_indexes(cart, promo, role=None):
    """Include rows select lines; exclude rows then subtract from the result.
    'Apply on all' (or include rows absent while exclude rows exist) starts
    from the whole cart — enabling 'everything except brand X'."""
    rows = promo.get("items") or []
    include_rows = [r for r in rows if not r.get("exclude")]
    exclude_rows = [r for r in rows if r.get("exclude")]

    if promo.get("apply_on_all") or (exclude_rows and not include_rows):
        base = list(range(len(cart["items"])))
    else:
        if role:
            role_rows = [r for r in include_rows if (r.get("role") or "Buy") == role]
            if not role_rows:
                return []
        base = [
            i for i, line in enumerate(cart["items"])
            if _line_matches(line, include_rows, role=role)
        ]
    if exclude_rows:
        base = [
            i for i in base if not _line_matches(cart["items"][i], exclude_rows)
        ]
    return base


# ---------------------------------------------------------------------------
# Per-promotion candidate computation (always against original prices)
# ---------------------------------------------------------------------------

def _unit_discount(price, dtype, value):
    if dtype == "Percentage":
        d = price * (value or 0) / 100.0
    elif dtype == "Amount":
        d = value or 0
    elif dtype == "Fixed Price":
        d = price - (value or 0)
    elif dtype == "Free":
        d = price
    else:
        d = 0
    return max(0.0, min(d, price))


def _basis_unit_discount(line, promo, dtype, value):
    """Per-unit discount applied to the line's (effective / price-book) price.

    With the default "Price Book Price" basis the promo is computed on that
    price (stacks on the book). With "Standard Price" basis the promo is
    computed on the item's STANDARD price and the customer gets the LOWER of the
    price-book price and (standard - promo): discounts never stack with the
    price book and a promo can never raise the price."""
    book = line["price"]
    if (promo.get("price_basis") or "Price Book Price") == "Standard Price":
        std = line.get("standard_price")
        if std is None:
            std = book
        candidate = std - _unit_discount(std, dtype, value)  # promo price off standard
        return max(0.0, book - candidate)  # lowest wins; 0 when the book is already lower
    return _unit_discount(book, dtype, value)


def _candidate_simple(cart, promo):
    line_discounts = {}
    for i in _matching_indexes(cart, promo):
        line = cart["items"][i]
        per_unit = _basis_unit_discount(
            line, promo, promo.get("discount_type"), promo.get("discount_value")
        )
        if per_unit > 0:
            line_discounts[i] = per_unit * line["qty"]
    return line_discounts, 0.0


def _expand_units(cart, indexes):
    """One entry per whole unit: (unit_price, standard_price, line_index).
    Fractional quantities are excluded from Buy X Get Y counting."""
    units = []
    for i in indexes:
        line = cart["items"][i]
        std = line.get("standard_price")
        if std is None:
            std = line["price"]
        for _ in range(int(line["qty"])):
            units.append((line["price"], std, i))
    return units


def _candidate_bxgy(cart, promo):
    buy_qty = int(promo.get("buy_qty") or 0)
    get_qty = int(promo.get("get_qty") or 0)
    if buy_qty < 1 or get_qty < 1:
        return {}, 0.0

    has_get_rows = any(
        (r.get("role") or "Buy") == "Get" for r in (promo.get("items") or [])
    )
    buy_idx = _matching_indexes(cart, promo, role="Buy")
    if promo.get("apply_on_all"):
        buy_idx = _matching_indexes(cart, promo)
    get_idx = _matching_indexes(cart, promo, role="Get") if has_get_rows else buy_idx

    buy_units = _expand_units(cart, buy_idx)
    get_units = _expand_units(cart, get_idx)
    if not buy_units or not get_units:
        return {}, 0.0

    shared = bool(set(buy_idx) & set(get_idx))
    apps = min(
        len(buy_units) // buy_qty,
        len(get_units) // get_qty,
    )
    if shared:
        # A unit cannot be both the trigger and the reward: classic
        # "buy 2 get 1 free" needs 3 units in the cart.
        union = _expand_units(cart, sorted(set(buy_idx) | set(get_idx)))
        apps = min(apps, len(union) // (buy_qty + get_qty))

    max_apps = int(promo.get("max_applications") or 0)
    if max_apps > 0:
        apps = min(apps, max_apps)
    if apps < 1:
        return {}, 0.0

    # Reward the cheapest eligible units (Vend behaviour).
    reward_count = apps * get_qty
    rewards = sorted(get_units)[:reward_count]
    line_discounts = {}
    for price, std, idx in rewards:
        d = _basis_unit_discount(
            {"price": price, "standard_price": std},
            promo,
            promo.get("get_discount_type") or "Free",
            promo.get("get_discount_value"),
        )
        if d > 0:
            line_discounts[idx] = line_discounts.get(idx, 0.0) + d
    return line_discounts, 0.0


def _candidate_spend_save(cart, promo):
    if promo.get("apply_on_all") or promo.get("items"):
        indexes = _matching_indexes(cart, promo)
    else:
        # no product rows at all: the whole basket counts toward the spend
        indexes = list(range(len(cart["items"])))
    eligible_total = sum(
        cart["items"][i]["price"] * cart["items"][i]["qty"] for i in indexes
    )
    min_spend = promo.get("min_spend") or 0
    if eligible_total <= 0 or eligible_total < min_spend:
        return {}, 0.0

    dtype = promo.get("basket_discount_type") or "Percentage"
    value = promo.get("basket_discount_value") or 0
    if dtype == "Percentage":
        discount = eligible_total * value / 100.0
    else:
        discount = value
    return {}, max(0.0, min(discount, eligible_total))


def _candidate_bundle(cart, promo):
    """Bundle Price: the listed items bought together (row qty each) go for a
    fixed total. Items stay separate lines — the saving is spread across the
    consumed units proportionally to price. Cheapest matching units are
    consumed first; the bundle repeats while the cart can fill it."""
    rows = [r for r in (promo.get("items") or []) if not r.get("exclude")]
    bundle_price = promo.get("bundle_price") or 0
    if not rows or bundle_price <= 0:
        return {}, 0.0

    pool = []
    for i, line in enumerate(cart["items"]):
        for _ in range(int(line["qty"])):
            pool.append({"price": line["price"], "idx": i, "used": False})

    max_apps = int(promo.get("max_applications") or 0)
    consumed, apps = [], 0
    while True:
        round_selected, filled = [], True
        for row in rows:
            need = int(row.get("qty") or 1)
            candidates = sorted(
                (
                    u
                    for u in pool
                    if not u["used"] and _line_matches(cart["items"][u["idx"]], [row])
                ),
                key=lambda u: u["price"],
            )
            if len(candidates) < need:
                filled = False
                break
            for unit in candidates[:need]:
                unit["used"] = True
                round_selected.append(unit)
        if not filled:
            for unit in round_selected:
                unit["used"] = False
            break
        consumed.extend(round_selected)
        apps += 1
        if max_apps and apps >= max_apps:
            break

    if not apps:
        return {}, 0.0
    natural = sum(u["price"] for u in consumed)
    discount = natural - bundle_price * apps
    if discount <= 0 or natural <= 0:
        return {}, 0.0

    line_discounts = {}
    for unit in consumed:
        share = discount * (unit["price"] / natural)
        line_discounts[unit["idx"]] = line_discounts.get(unit["idx"], 0.0) + share

    # Cent-correct the proportional split: rounded shares must sum exactly
    # to the bundle saving (the largest line absorbs the remainder).
    rounded = {idx: round(v, 2) for idx, v in line_discounts.items()}
    delta = round(round(discount, 2) - sum(rounded.values()), 2)
    if delta and rounded:
        biggest = max(rounded, key=lambda idx: rounded[idx])
        rounded[biggest] = round(rounded[biggest] + delta, 2)
    return rounded, 0.0


_CANDIDATES = {
    "Simple Discount": _candidate_simple,
    "Buy X Get Y": _candidate_bxgy,
    "Spend and Save": _candidate_spend_save,
    "Bundle Price": _candidate_bundle,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(cart, promotions, now=None):
    now = now or datetime.now()
    if isinstance(now, str):
        now = datetime.fromisoformat(now)

    items = cart.get("items") or []
    result = {
        "line_discounts": [0.0] * len(items),
        "line_promotions": [[] for _ in items],
        "basket_discount": 0.0,
        "applied": [],
        "total_savings": 0.0,
    }
    if not items:
        return result

    candidates = []
    for promo in promotions:
        if (promo.get("status") or "Active") != "Active":
            continue
        if not is_active(promo, now, cart):
            continue
        fn = _CANDIDATES.get(promo.get("promotion_type"))
        if not fn:
            continue
        line_discounts, basket_discount = fn(cart, promo)
        savings = sum(line_discounts.values()) + basket_discount
        if savings > 0:
            candidates.append(
                {
                    "promo": promo,
                    "line_discounts": line_discounts,
                    "basket_discount": basket_discount,
                    "savings": savings,
                }
            )

    if not candidates:
        return result

    stackable = [c for c in candidates if c["promo"].get("stackable")]
    exclusive = [c for c in candidates if not c["promo"].get("stackable")]
    exclusive.sort(
        key=lambda c: (c["savings"], c["promo"].get("priority") or 0), reverse=True
    )

    stack_total = sum(c["savings"] for c in stackable)
    best_exclusive = exclusive[0] if exclusive else None

    if best_exclusive and best_exclusive["savings"] > stack_total:
        chosen = [best_exclusive]
    else:
        chosen = stackable

    for c in chosen:
        for idx, amount in c["line_discounts"].items():
            result["line_discounts"][idx] += amount
            result["line_promotions"][idx].append(c["promo"].get("title"))
        result["basket_discount"] += c["basket_discount"]
        result["applied"].append(
            {
                "name": c["promo"].get("name"),
                "title": c["promo"].get("title"),
                "promotion_type": c["promo"].get("promotion_type"),
                "savings": round(c["savings"], 2),
            }
        )

    # Caps: line discounts cannot exceed the line total; the basket discount
    # cannot exceed what remains of the basket.
    basket_total = 0.0
    for i, line in enumerate(items):
        line_total = line["price"] * line["qty"]
        result["line_discounts"][i] = round(min(result["line_discounts"][i], line_total), 2)
        basket_total += line_total - result["line_discounts"][i]
    result["basket_discount"] = round(min(result["basket_discount"], basket_total), 2)
    result["total_savings"] = round(
        sum(result["line_discounts"]) + result["basket_discount"], 2
    )
    return result
