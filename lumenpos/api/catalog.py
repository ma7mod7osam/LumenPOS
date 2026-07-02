import frappe
from frappe import _
from frappe.utils import flt

from lumenpos.price_books import effective_prices, resolve_price_list, standard_prices


def warranty_field():
    """The Item field holding the warranty period in days — the site's custom
    'warranty_days' if present, otherwise ERPNext's standard 'warranty_period'."""
    if frappe.db.has_column("Item", "warranty_days"):
        return "warranty_days"
    if frappe.db.has_column("Item", "warranty_period"):
        return "warranty_period"
    return None


def _gift_card_item_code():
    """The gift-card placeholder item code — hidden from the product grid/search
    (it's sold via the gift-card action, not tapped as a product)."""
    try:
        from lumenpos import gift_cards

        return gift_cards.item_code()
    except Exception:
        return None


@frappe.whitelist()
def get_items(pos_profile, search="", item_group="", start=0, limit=60, price_list=None):
    """Items with selling price and stock for the POS grid."""
    start, limit = int(start), min(int(limit), 500)
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    active_price_list = price_list or resolve_price_list(profile)

    filters = {"disabled": 0, "is_sales_item": 1, "has_variants": 0}
    # The gift-card placeholder item is sold via the gift-card action, not tapped
    # as a product — keep it out of the grid / search / offline cache.
    gc = _gift_card_item_code()
    if gc:
        filters["name"] = ["!=", gc]
    or_filters = None
    if search:
        or_filters = {
            "item_name": ["like", f"%{search}%"],
            "name": ["like", f"%{search}%"],
        }
    if item_group:
        filters["item_group"] = item_group
    elif profile.item_groups:
        filters["item_group"] = ["in", [r.item_group for r in profile.item_groups]]

    wf = warranty_field()
    fields = [
        "name as item_code",
        "item_name",
        "item_group",
        "brand",
        "stock_uom",
        "image",
        "is_stock_item",
        "has_serial_no",
        "has_batch_no",
        "_user_tags",
    ]
    if wf:
        fields.append(f"`{wf}` as warranty_days")
    items = frappe.get_all(
        "Item",
        filters=filters,
        or_filters=or_filters,
        fields=fields,
        order_by="item_name asc",
        limit_start=start,
        limit_page_length=limit,
    )
    if not items:
        return {"items": [], "price_list": active_price_list}

    codes = [i["item_code"] for i in items]
    uom_map = {i["item_code"]: i["stock_uom"] for i in items}
    # Browse pricing: standard price with any outlet-/date-scoped price book
    # overrides applied (customer-group books resolve when a customer is picked
    # and the cart reprices). standard_price stays the plain selling price.
    price_map = effective_prices(profile, codes, None, None, uom_map)
    standard_map = standard_prices(profile, codes, uom_map)

    stock_map = {}
    if profile.warehouse:
        bins = frappe.get_all(
            "Bin",
            filters={"item_code": ["in", codes], "warehouse": profile.warehouse},
            fields=["item_code", "actual_qty"],
        )
        stock_map = {b.item_code: b.actual_qty for b in bins}

    barcode_map = {}
    for row in frappe.get_all(
        "Item Barcode",
        filters={"parent": ["in", codes]},
        fields=["parent", "barcode"],
        order_by="idx asc",
    ):
        barcode_map.setdefault(row.parent, row.barcode)

    for item in items:
        item["price"] = price_map.get(item["item_code"], 0)
        item["standard_price"] = standard_map.get(item["item_code"]) or item["price"]
        item["actual_qty"] = stock_map.get(item["item_code"], 0)
        item["barcode"] = barcode_map.get(item["item_code"])
        # _user_tags is comma-joined with a leading comma — hand the client a list
        # so promotions can target items by tag.
        item["tags"] = [t.strip() for t in (item.pop("_user_tags", "") or "").split(",") if t.strip()]

    return {"items": items, "price_list": active_price_list}


@frappe.whitelist()
def get_full_catalog(pos_profile, max_items=50000):
    """Whole sellable catalog in one call, for the local-first IndexedDB
    cache (instant search + offline). With 'Cache only in-stock items'
    enabled in LumenPOS Settings, items without stock in the register's
    warehouse are skipped (non-stock items like services always stay)."""
    stock_only = frappe.db.get_single_value("LumenPOS Settings", "offline_stock_only")
    result = []
    start = 0
    while len(result) < int(max_items):
        batch = get_items(pos_profile, "", "", start, 500)["items"]
        if stock_only:
            result.extend(
                i for i in batch if not i["is_stock_item"] or (i["actual_qty"] or 0) > 0
            )
        else:
            result.extend(batch)
        if len(batch) < 500:
            break
        start += 500
    return result


@frappe.whitelist()
def resolve_scan(pos_profile, code, customer_group=None, app_type=None):
    """Fast path for the scanner: barcode -> item, serial -> item + serial.
    Returns the item priced on the cart's active price list."""
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    code = (code or "").strip()
    if not code:
        return {"found": False}

    item_code = frappe.db.get_value("Item Barcode", {"barcode": code}, "parent")
    serial = None
    if not item_code:
        sn = frappe.db.get_value(
            "Serial No", code, ["name", "item_code", "status", "warehouse"], as_dict=True
        )
        if sn and sn.status == "Active" and (
            not profile.warehouse or sn.warehouse == profile.warehouse
        ):
            item_code = sn.item_code
            serial = sn.name
    if not item_code:
        return {"found": False}

    app_price_list = _app_price_list(app_type)
    wf = warranty_field()
    scan_fields = [
        "name as item_code", "item_name", "item_group", "brand", "stock_uom",
        "is_stock_item", "has_serial_no", "has_batch_no", "_user_tags",
    ]
    if wf:
        scan_fields.append(f"`{wf}` as warranty_days")
    item = frappe.get_all(
        "Item",
        filters={"name": item_code, "disabled": 0, "is_sales_item": 1},
        fields=scan_fields,
    )
    if not item:
        return {"found": False}
    item = item[0]
    item["tags"] = [t.strip() for t in (item.pop("_user_tags", "") or "").split(",") if t.strip()]
    item["barcode"] = frappe.db.get_value("Item Barcode", {"parent": item_code}, "barcode")
    uom_map = {item_code: item["stock_uom"]}
    item["price"] = effective_prices(
        profile, [item_code], customer_group, app_price_list, uom_map
    ).get(item_code, 0)
    item["standard_price"] = (
        standard_prices(profile, [item_code], uom_map).get(item_code) or item["price"]
    )
    item["actual_qty"] = (
        frappe.db.get_value(
            "Bin", {"item_code": item_code, "warehouse": profile.warehouse}, "actual_qty"
        )
        or 0
        if profile.warehouse
        else 0
    )
    return {"found": True, "item": item, "serial": serial}


@frappe.whitelist()
def get_prices(pos_profile, item_codes, customer_group=None, app_type=None):
    """Batch reprice for the cart when the active price list changes
    (customer with a price book, or a delivery-app channel)."""
    if isinstance(item_codes, str):
        import json

        item_codes = json.loads(item_codes)
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    app_price_list = _app_price_list(app_type)
    price_list = resolve_price_list(profile, customer_group, app_price_list)
    uom_map = {
        d.name: d.stock_uom
        for d in frappe.get_all(
            "Item", filters={"name": ["in", item_codes]}, fields=["name", "stock_uom"]
        )
    }
    return {
        "price_list": price_list,
        "prices": effective_prices(profile, item_codes, customer_group, app_price_list, uom_map),
        "standard_prices": standard_prices(profile, item_codes, uom_map),
    }


def _app_price_list(app_type):
    if not app_type:
        return None
    settings = frappe.get_cached_doc("LumenPOS Settings")
    row = next(
        (r for r in (settings.delivery_apps or []) if r.app_name == app_type), None
    )
    return row.price_list if row else None


@frappe.whitelist()
def price_check(pos_profile, query):
    """Look up an item's live price + stock WITHOUT adding it to a sale
    (Settings → Features → Price / stock checker). Matches a barcode, serial,
    exact item code, or a name fragment. Returns up to 10 matches, each priced
    on the profile's active list with stock at the register's warehouse and the
    company-wide total."""
    q = (query or "").strip()
    if not q:
        return {"matches": []}
    profile = frappe.get_cached_doc("POS Profile", pos_profile)

    # 1) Exact match: barcode -> item, serial -> item, or an item code.
    item_codes = []
    barcode_item = frappe.db.get_value("Item Barcode", {"barcode": q}, "parent")
    if barcode_item:
        item_codes = [barcode_item]
    else:
        sn_item = frappe.db.get_value("Serial No", q, "item_code")
        if sn_item:
            item_codes = [sn_item]
        elif frappe.db.exists("Item", q):
            item_codes = [q]

    # 2) Otherwise a name / code fragment search.
    if not item_codes:
        rows = frappe.get_all(
            "Item",
            filters={"disabled": 0, "is_sales_item": 1},
            or_filters={"item_name": ["like", f"%{q}%"], "name": ["like", f"%{q}%"]},
            fields=["name"],
            order_by="item_name asc",
            limit=10,
        )
        item_codes = [r.name for r in rows]

    # Never surface the gift-card placeholder item in a price check.
    gc = _gift_card_item_code()
    if gc:
        item_codes = [c for c in item_codes if c != gc]

    if not item_codes:
        return {"matches": []}

    fields = [
        "name as item_code", "item_name", "item_group", "brand",
        "stock_uom", "is_stock_item",
    ]
    items = frappe.get_all(
        "Item",
        filters={"name": ["in", item_codes], "disabled": 0, "is_sales_item": 1},
        fields=fields,
    )
    codes = [i["item_code"] for i in items]
    uom_map = {i["item_code"]: i["stock_uom"] for i in items}
    prices = effective_prices(profile, codes, None, None, uom_map)
    stds = standard_prices(profile, codes, uom_map)

    # Stock: the register's warehouse, plus the company-wide total.
    here = {}
    if profile.warehouse and codes:
        for b in frappe.get_all(
            "Bin",
            filters={"item_code": ["in", codes], "warehouse": profile.warehouse},
            fields=["item_code", "actual_qty"],
        ):
            here[b.item_code] = b.actual_qty
    totals = {}
    if codes:
        for b in frappe.get_all(
            "Bin", filters={"item_code": ["in", codes]}, fields=["item_code", "actual_qty"]
        ):
            totals[b.item_code] = (totals.get(b.item_code) or 0) + flt(b.actual_qty)

    matches = []
    for i in items:
        code = i["item_code"]
        matches.append(
            {
                "item_code": code,
                "item_name": i["item_name"],
                "item_group": i["item_group"],
                "brand": i["brand"],
                "uom": i["stock_uom"],
                "is_stock_item": i["is_stock_item"],
                "price": prices.get(code, 0),
                "standard_price": stds.get(code) or prices.get(code, 0),
                "stock_here": flt(here.get(code, 0)),
                "stock_total": flt(totals.get(code, 0)),
                "barcode": frappe.db.get_value("Item Barcode", {"parent": code}, "barcode"),
            }
        )
    return {"warehouse": profile.warehouse, "matches": matches}


@frappe.whitelist()
def get_quick_keys(pos_profile):
    """Resolve the configured favourites (Settings → Features → Quick keys) into
    sell-grid item cards, preserving the configured order + any custom labels.
    Codes that no longer resolve (disabled/deleted) are silently dropped."""
    settings = frappe.get_cached_doc("LumenPOS Settings")
    if not settings.get("enable_quick_keys"):
        return {"items": []}
    rows = [(r.item_code, r.label) for r in (settings.get("quick_keys") or []) if r.item_code]
    if not rows:
        return {"items": []}
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    label_map = {code: (label or "") for code, label in rows}

    wf = warranty_field()
    fields = [
        "name as item_code", "item_name", "item_group", "brand", "stock_uom",
        "image", "is_stock_item", "has_serial_no", "has_batch_no", "_user_tags",
    ]
    if wf:
        fields.append(f"`{wf}` as warranty_days")
    found = frappe.get_all(
        "Item",
        filters={"name": ["in", list(label_map)], "disabled": 0, "is_sales_item": 1},
        fields=fields,
    )
    by_code = {i["item_code"]: i for i in found}
    fcodes = list(by_code.keys())
    if not fcodes:
        return {"items": []}

    uom_map = {i["item_code"]: i["stock_uom"] for i in found}
    price_map = effective_prices(profile, fcodes, None, None, uom_map)
    standard_map = standard_prices(profile, fcodes, uom_map)
    stock_map = {}
    if profile.warehouse:
        for b in frappe.get_all(
            "Bin",
            filters={"item_code": ["in", fcodes], "warehouse": profile.warehouse},
            fields=["item_code", "actual_qty"],
        ):
            stock_map[b.item_code] = b.actual_qty
    barcode_map = {}
    for row in frappe.get_all(
        "Item Barcode", filters={"parent": ["in", fcodes]}, fields=["parent", "barcode"], order_by="idx asc"
    ):
        barcode_map.setdefault(row.parent, row.barcode)

    items = []
    seen = set()
    for code, _label in rows:
        item = by_code.get(code)
        if not item or code in seen:
            continue
        seen.add(code)
        item["price"] = price_map.get(code, 0)
        item["standard_price"] = standard_map.get(code) or item["price"]
        item["actual_qty"] = stock_map.get(code, 0)
        item["barcode"] = barcode_map.get(code)
        item["tags"] = [t.strip() for t in (item.pop("_user_tags", "") or "").split(",") if t.strip()]
        item["quick_label"] = label_map.get(code) or item["item_name"]
        items.append(item)
    return {"items": items}


@frappe.whitelist()
def validate_serial(pos_profile, item_code, serial_no):
    """Strict check used live at the cart and re-run on submit: the serial
    must exist, belong to this item, be Active stock, and sit in the
    register's warehouse."""
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    return _check_serial(item_code, serial_no, profile.warehouse)


def _check_serial(item_code, serial_no, warehouse):
    serial_no = (serial_no or "").strip()
    if not serial_no:
        return {"valid": False, "message": "Scan or type a serial number"}
    sn = frappe.db.get_value(
        "Serial No", serial_no, ["name", "item_code", "status", "warehouse"], as_dict=True
    )
    if not sn:
        return {"valid": False, "message": f"Serial {serial_no} does not exist"}
    if sn.item_code != item_code:
        return {"valid": False, "message": f"Serial {serial_no} belongs to {sn.item_code}"}
    if sn.status != "Active":
        return {"valid": False, "message": f"Serial {serial_no} is not in stock ({sn.status})"}
    if warehouse and sn.warehouse != warehouse:
        return {
            "valid": False,
            "message": f"Serial {serial_no} is in {sn.warehouse}, not this register's warehouse",
        }
    return {"valid": True, "message": "OK", "serial_no": sn.name}


# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------

@frappe.whitelist()
def recent_customers(pos_profile, limit=2000):
    """A CAPPED set of recent/frequent customers to cache for OFFLINE select.
    Prefers customers this outlet's company has recently transacted with, topped
    up with the most-recently-created ones. Deliberately NOT the full directory
    (a huge client mirror hurts search perf + risks eviction) — online search
    still hits the server. Same shape as search_customers."""
    limit = min(int(limit or 0) or 2000, 10000)
    from lumenpos.api.sales import _table_doctype

    company = frappe.db.get_value("POS Profile", pos_profile, "company")
    sale_doctype = _table_doctype(pos_profile)

    ordered, seen = [], set()
    # 1) recently transacted with this company (the customers you actually serve)
    for r in frappe.get_all(
        sale_doctype,
        filters={"company": company, "docstatus": 1, "customer": ["is", "set"]},
        fields=["customer", "max(posting_date) as last"],
        group_by="customer",
        order_by="last desc",
        limit_page_length=limit,
    ):
        if r.customer and r.customer not in seen:
            seen.add(r.customer)
            ordered.append(r.customer)
    # 2) top up with the most-recently-created customers (covers a fresh site)
    if len(ordered) < limit:
        for r in frappe.get_all(
            "Customer",
            filters={"disabled": 0},
            fields=["name"],
            order_by="creation desc",
            limit_page_length=limit - len(ordered) + 100,
        ):
            if r.name not in seen:
                seen.add(r.name)
                ordered.append(r.name)
                if len(ordered) >= limit:
                    break

    if not ordered:
        return {"customers": []}

    detail = {
        c["name"]: c
        for c in frappe.get_all(
            "Customer",
            filters={"name": ["in", ordered], "disabled": 0},
            fields=[
                "name", "customer_name", "customer_group", "customer_type",
                "mobile_no", "email_id", "tax_id",
            ],
        )
    }
    return {"customers": [detail[n] for n in ordered if n in detail]}


@frappe.whitelist()
def search_customers(search=""):
    or_filters = None
    if search:
        or_filters = {
            "customer_name": ["like", f"%{search}%"],
            "name": ["like", f"%{search}%"],
            "mobile_no": ["like", f"%{search}%"],
            "tax_id": ["like", f"%{search}%"],
        }
    return frappe.get_all(
        "Customer",
        filters={"disabled": 0},
        or_filters=or_filters,
        fields=[
            "name", "customer_name", "customer_group", "customer_type",
            "mobile_no", "email_id", "tax_id",
        ],
        order_by="customer_name asc",
        limit_page_length=20,
    )


@frappe.whitelist()
def create_customer(payload):
    """Strict customer creation:
      Individual -> name + mobile mandatory
      Company    -> name, mobile, tax id and national address details mandatory
    """
    import json

    if isinstance(payload, str):
        payload = json.loads(payload)

    customer_type = payload.get("customer_type") or "Individual"
    name = (payload.get("customer_name") or "").strip()
    mobile = (payload.get("mobile_no") or "").strip()

    if not name:
        frappe.throw(_("Customer name is required"))
    if not mobile:
        frappe.throw(_("Mobile number is required"))

    address_fields = {}
    if customer_type == "Company":
        if not (payload.get("tax_id") or "").strip():
            frappe.throw(_("Tax ID is required for company customers"))
        address_fields = {
            key: (payload.get(key) or "").strip()
            for key in ("building_no", "street", "district", "city", "postal_code", "additional_no")
        }
        missing = [k for k in ("building_no", "street", "district", "city", "postal_code") if not address_fields[k]]
        if missing:
            frappe.throw(
                _("National address is required for company customers (missing: {0})").format(
                    ", ".join(m.replace("_", " ") for m in missing)
                )
            )

    selling = frappe.get_cached_doc("Selling Settings")
    customer = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": customer_type,
            "customer_group": selling.customer_group,
            "territory": selling.territory,
            "mobile_no": mobile,
            "email_id": (payload.get("email_id") or "").strip() or None,
            "tax_id": (payload.get("tax_id") or "").strip() or None,
        }
    ).insert()

    if customer_type == "Company":
        frappe.get_doc(
            {
                "doctype": "Address",
                "address_title": name,
                "address_type": "Billing",
                "address_line1": f"{address_fields['building_no']} {address_fields['street']}",
                "address_line2": " ".join(
                    v
                    for v in [address_fields["district"], address_fields["additional_no"]]
                    if v
                )
                or None,
                "city": address_fields["city"],
                "pincode": address_fields["postal_code"],
                "country": frappe.db.get_default("country") or "Saudi Arabia",
                "links": [{"link_doctype": "Customer", "link_name": customer.name}],
            }
        ).insert()

    return {
        "name": customer.name,
        "customer_name": customer.customer_name,
        "customer_group": customer.customer_group,
        "customer_type": customer_type,
        "mobile_no": mobile,
        "email_id": payload.get("email_id"),
        "tax_id": payload.get("tax_id"),
    }


@frappe.whitelist()
def resolve_pending_customer(payload):
    """Reconcile a customer created OFFLINE on reconnect: MATCH an existing
    customer by mobile (the 'already there' case → link, no duplicate) else
    CREATE one. Idempotent by mobile, so a retry after a lost ACK never
    duplicates. Returns the same shape as create_customer, plus `matched`."""
    import json

    if isinstance(payload, str):
        payload = json.loads(payload)
    mobile = (payload.get("mobile_no") or "").strip()
    if mobile:
        existing = frappe.db.get_value(
            "Customer", {"mobile_no": mobile, "disabled": 0}, "name"
        )
        if existing:
            c = frappe.db.get_value(
                "Customer",
                existing,
                ["name", "customer_name", "customer_group", "customer_type",
                 "mobile_no", "email_id", "tax_id"],
                as_dict=True,
            )
            c["matched"] = True
            return c
    c = create_customer(payload)
    c["matched"] = False
    return c
