import frappe
from frappe import _

from lumenpos.promotions.loader import get_active_promotions


@frappe.whitelist()
def get_bootstrap(pos_profile=None):
    """Everything the POS needs to start: profile, payment modes, item groups,
    promotions, currency and the current register session."""
    if not frappe.has_permission("POS Invoice", "read"):
        frappe.throw(
            _("You do not have access to the POS. Ask an administrator to grant you the LumenPOS Cashier role (or POS Invoice access)."),
            frappe.PermissionError,
        )
    profile_name = pos_profile or _default_pos_profile()
    if not profile_name:
        frappe.throw(
            _("No POS Profile is assigned to you. Create one and add yourself under Applicable for Users.")
        )

    profile = frappe.get_doc("POS Profile", profile_name)

    payment_modes = []
    for row in profile.payments:
        mop_type = frappe.db.get_value("Mode of Payment", row.mode_of_payment, "type")
        payment_modes.append(
            {
                "mode_of_payment": row.mode_of_payment,
                "type": mop_type or "General",
                "default": row.default,
            }
        )

    currency = profile.currency or frappe.get_cached_value(
        "Company", profile.company, "default_currency"
    )

    item_groups = [row.item_group for row in (profile.item_groups or [])]
    if not item_groups:
        item_groups = frappe.get_all(
            "Item Group",
            filters={"is_group": 0},
            order_by="name",
            limit_page_length=50,
            pluck="name",
        )

    session = get_open_session(profile_name)

    return {
        "user": frappe.session.user,
        "user_fullname": frappe.utils.get_fullname(frappe.session.user),
        "desk_theme": frappe.db.get_value("User", frappe.session.user, "desk_theme")
        or "Automatic",
        "pos_profile": profile_name,
        "company": profile.company,
        "currency": currency,
        "price_list": profile.selling_price_list,
        "warehouse": profile.warehouse,
        "default_customer": profile.customer,
        "default_customer_name": frappe.db.get_value(
            "Customer", profile.customer, "customer_name"
        )
        if profile.customer
        else None,
        "allow_negative_stock": frappe.db.get_single_value(
            "Stock Settings", "allow_negative_stock"
        ),
        "payment_modes": payment_modes,
        "item_groups": item_groups,
        "taxes": _profile_taxes(profile),
        "promotions": get_active_promotions(profile_name),
        "register_session": session,
        "pending_closing": _pending_closing(profile_name),
        "permissions": get_user_permissions(),
        "available_profiles": _user_profiles(),
        "printer_configured": bool(profile.get("lumenpos_printer_ip")),
        "print_format": profile.print_format,
        "store_credit_mode": "Store Credit",
        "gift_card_mode": _gift_card_mode(),
        "sales_persons": _sales_persons(),
        "settings": _client_settings(),
        "bundles": get_bundles(profile_name),
    }


def _gift_card_mode():
    from lumenpos import gift_cards

    return gift_cards.mode_of_payment()


def get_user_permissions():
    """Capability map derived from the user's ERPNext DocType permissions, so
    admins control who can see/do what entirely through the standard Role
    Permissions Manager (no LumenPOS-specific switches). The frontend uses this to
    show/hide tabs and disable actions; every API also re-checks server-side."""
    has = frappe.has_permission

    def caps(doctype):
        return {
            "read": bool(has(doctype, "read")),
            "write": bool(has(doctype, "write")),
            "create": bool(has(doctype, "create")),
            "delete": bool(has(doctype, "delete")),
        }

    roles = set(frappe.get_roles())
    return {
        "sell": bool(has("POS Invoice", "create")),
        "view_history": bool(has("POS Invoice", "read")),
        "customers": bool(has("Customer", "read")),
        "open_register": bool(has("POS Opening Entry", "create")),
        "close_register": bool(has("POS Closing Entry", "create")),
        "promotions": caps("POS Promotion"),
        "bundles": caps("POS Bundle"),
        "price_books": caps("POS Price Book"),
        "edit_item_prices": bool(has("Item Price", "write")),
        "create_price_list": bool(has("Price List", "create")),
        "settings": bool(has("LumenPOS Settings", "write")),
        "loyalty": bool(has("Loyalty Program", "create")),
        "gift_cards": bool(has("POS Gift Card", "write")),
        "is_manager": bool(
            {"System Manager", "LumenPOS Manager"} & roles or has("LumenPOS Settings", "write")
        ),
    }


def _pending_closing(pos_profile):
    """A shift on this register whose close hasn't fully consolidated yet
    (status 'Closing'). The Sell screen uses it to prompt 'retry the closing'
    instead of letting anyone resume or sell on a finished shift."""
    row = frappe.db.get_value(
        "POS Register Session",
        {"pos_profile": pos_profile, "status": "Closing"},
        ["name", "closing_status", "closing_error", "pos_closing_entry", "closed_at"],
        as_dict=True,
    )
    if not row:
        return None
    return {
        "session": row.name,
        "closing_status": row.closing_status,
        "closing_error": row.closing_error,
        "pos_closing_entry": row.pos_closing_entry,
        "closed_at": str(row.closed_at) if row.closed_at else None,
    }


def get_bundles(pos_profile=None):
    """Active, in-date POS Bundles for the sell screen, filtered by outlet."""
    from frappe.utils import getdate, nowdate

    today = getdate(nowdate())
    bundles = []
    for name in frappe.get_all("POS Bundle", filters={"status": "Active"}, pluck="name"):
        doc = frappe.get_doc("POS Bundle", name)
        # Validity window: not before valid_from, not after valid_to (expired).
        if doc.get("valid_from") and getdate(doc.valid_from) > today:
            continue
        if doc.get("valid_to") and getdate(doc.valid_to) < today:
            continue
        profiles = [row.pos_profile for row in (doc.pos_profiles or [])]
        if pos_profile and profiles and pos_profile not in profiles:
            continue
        bundles.append(
            {
                "name": doc.name,
                "title": doc.title,
                "bundle_price": doc.bundle_price,
                "items": [
                    {
                        "item_code": row.item_code,
                        "item_name": row.item_name
                        or frappe.get_cached_value("Item", row.item_code, "item_name"),
                        "qty": row.qty,
                        "allocated_amount": row.get("allocated_amount"),
                    }
                    for row in doc.items
                ],
            }
        )
    return bundles


def _profile_taxes(profile):
    """The profile's tax template rows, so the cart can compute taxes the
    same way the server will — the displayed total must equal the invoice
    grand total."""
    if not profile.taxes_and_charges:
        return []
    template = frappe.get_cached_doc(
        "Sales Taxes and Charges Template", profile.taxes_and_charges
    )
    return [
        {
            "description": row.description,
            "charge_type": row.charge_type,
            "rate": row.rate or 0,
            "tax_amount": row.tax_amount or 0,
            "included": row.included_in_print_rate or 0,
        }
        for row in (template.taxes or [])
    ]


def _sales_persons():
    """ALL enabled sales persons; includes the site's custom
    sales_person_no field when it exists so cashiers can pick by number."""
    fields = ["name", "sales_person_name"]
    meta = frappe.get_meta("Sales Person")
    number_field = next(
        (f for f in ("sales_person_no", "custom_sales_person_no") if meta.has_field(f)),
        None,
    )
    if number_field:
        fields.append(f"{number_field} as sales_person_no")
    return frappe.get_all(
        "Sales Person",
        filters={"is_group": 0, "enabled": 1},
        fields=fields,
        order_by="sales_person_name asc",
        limit_page_length=0,
    )


def _client_settings():
    from lumenpos import __version__
    from lumenpos.install import EXCHANGE_RETURN_REASON

    from frappe.utils import cint

    from lumenpos.api import approval_requests

    doc = frappe.get_cached_doc("LumenPOS Settings")
    return {
        "version": __version__,
        "discount_limit_percent": doc.discount_limit_percent or 0,
        "discount_approval_mode": doc.get("discount_approval_mode") or "Passcode only",
        "can_approve_requests": approval_requests.can_approve(),
        "restrict_returns_to_window": 1 if doc.get("restrict_returns_to_window") else 0,
        "return_window_days": cint(doc.get("return_window_days")) or 0,
        "exchanges_enabled": 1 if doc.get("exchanges_enabled") else 0,
        "show_out_of_stock": 1 if doc.get("show_out_of_stock") else 0,
        "serial_scan_only": 1 if doc.get("serial_scan_only") else 0,
        "return_reasons": [
            r.reason for r in (doc.get("return_reasons") or []) if (r.reason or "").strip()
        ],
        "exchange_return_reason": EXCHANGE_RETURN_REASON,
        "delivery_apps": [
            {
                "app_name": row.app_name,
                "price_list": row.price_list,
                "require_order_id": row.require_order_id,
            }
            for row in (doc.delivery_apps or [])
        ],
    }


@frappe.whitelist()
def get_promotions(pos_profile):
    """Lightweight refresh endpoint so the client can re-pull promotions."""
    return get_active_promotions(pos_profile)


@frappe.whitelist()
def check_coupon(pos_profile, code):
    """Validate a coupon code and hand back its promotion. Coupon-locked
    promotions are never shipped in the bootstrap payload, so this is the
    only way a client learns about one — and only with the right code."""
    raw = (code or "").strip()
    if not raw:
        frappe.throw(_("Enter a coupon code"))
    upper = raw.upper()
    active = get_active_promotions(pos_profile, coupon_only=True)
    # Legacy single coupon_code on a promotion.
    for promo in active:
        if (promo.get("coupon_code") or "").upper() == upper:
            return promo
    # Bulk coupon pool: a generated/imported code that unlocks its promotion.
    from lumenpos import coupons

    row = coupons.resolve(raw)
    if row:
        for promo in active:
            if promo.get("name") == row.promotion:
                promo["coupon_code"] = raw  # so the live cart engine unlocks it
                return promo
        frappe.throw(_("This coupon's promotion isn't available right now"))
    frappe.throw(_("Invalid or expired coupon code"))


def get_open_session(pos_profile):
    name = frappe.db.get_value(
        "POS Register Session", {"pos_profile": pos_profile, "status": "Open"}, "name"
    )
    if not name:
        return None
    doc = frappe.get_doc("POS Register Session", name)
    return {
        "name": doc.name,
        "opened_at": str(doc.opened_at),
        "opened_by": doc.opened_by,
        "opening_float": doc.opening_float,
        "pos_opening_entry": doc.get("pos_opening_entry"),
    }


def _default_pos_profile():
    user = frappe.session.user
    name = frappe.db.get_value(
        "POS Profile User", {"user": user, "parenttype": "POS Profile"}, "parent"
    )
    if name:
        return name
    # Fall back to any enabled profile (single-store setups often skip user mapping)
    return frappe.db.get_value("POS Profile", {"disabled": 0}, "name")


def _user_profiles():
    user = frappe.session.user
    names = frappe.get_all(
        "POS Profile User",
        filters={"user": user, "parenttype": "POS Profile"},
        pluck="parent",
    )
    if not names:
        names = frappe.get_all(
            "POS Profile", filters={"disabled": 0}, pluck="name", limit_page_length=20
        )
    return sorted(set(names))
