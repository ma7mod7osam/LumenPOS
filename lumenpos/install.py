import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

# Roles LumenPOS ships so admins have ready-made handles to assign in the Role
# Permissions Manager. Cashiers sell + run the register; managers also edit the
# back office (promotions, bundles, price books, settings). Actual access is
# governed by standard DocType permissions, so these can be tuned freely.
LumenPOS_ROLES = ["LumenPOS Cashier", "LumenPOS Manager"]

# Core ERPNext doctypes the LumenPOS roles need so they are turnkey: granting a
# user "LumenPOS Cashier" should let them load the POS, sell, and run the register
# (the closing consolidation runs as the cashier, so they also need the merge
# log + Sales Invoice rights). These are ADDITIVE — existing perms are never
# removed, so admins can still tighten/loosen everything in the Role
# Permissions Manager afterwards.
CORE_GRANTS = {
    "LumenPOS Cashier": {
        "POS Invoice": ["read", "write", "create", "submit", "print"],
        "POS Opening Entry": ["read", "write", "create", "submit"],
        "POS Closing Entry": ["read", "write", "create", "submit"],
        "POS Invoice Merge Log": ["read", "write", "create", "submit"],
        "Sales Invoice": ["read", "write", "create", "submit"],
    },
    "LumenPOS Manager": {
        "POS Invoice": ["read", "write", "create", "submit", "cancel", "amend", "print", "delete"],
        "POS Opening Entry": ["read", "write", "create", "submit", "cancel"],
        "POS Closing Entry": ["read", "write", "create", "submit", "cancel"],
        "POS Invoice Merge Log": ["read", "write", "create", "submit", "cancel"],
        "Sales Invoice": ["read", "write", "create", "submit", "cancel", "amend", "print"],
    },
}


def after_install():
    ensure_setup()


# Default reasons seeded into LumenPOS Settings the first time (admins edit them
# freely in Settings → Return Reasons). The store runs in Arabic, so these are
# Arabic; "Other" is always offered by the till on top of this list.
DEFAULT_RETURN_REASONS = [
    "منتج تالف",
    "منتج به عيب صناعة",
    "مقاس غير مناسب",
    "لون مختلف عن المطلوب",
    "المنتج لا يطابق الوصف",
    "غيّر العميل رأيه",
    "خطأ في الطلب",
]


def ensure_setup():
    """Idempotent setup re-run on every migrate (Frappe Cloud deploy): make
    sure the LumenPOS roles, their core permissions, and custom fields exist."""
    ensure_roles()
    grant_core_permissions()
    make_custom_fields()
    migrate_price_books()
    ensure_return_reasons()
    migrate_coupon_limits()


def migrate_coupon_limits():
    """v0.18.0 coupons had a single_use flag; v0.19.0 uses a numeric usage_limit
    (0 = unlimited). Reusable old codes (single_use=0) would inherit the new Int
    default of 1 on migrate — restore them to unlimited. Idempotent."""
    if not frappe.db.exists("DocType", "POS Coupon"):
        return
    frappe.db.sql(
        "update `tabPOS Coupon` set usage_limit = 0 "
        "where coalesce(single_use, 0) = 0 and usage_limit = 1"
    )


def ensure_return_reasons():
    """Seed a starter list of return reasons the first time only. Never touches
    the list again, so admin edits (add/remove) are preserved across migrates."""
    if not frappe.db.exists("DocType", "POS Return Reason"):
        return
    doc = frappe.get_single("LumenPOS Settings")
    if doc.get("return_reasons"):
        return
    for reason in DEFAULT_RETURN_REASONS:
        doc.append("return_reasons", {"reason": reason})
    doc.save(ignore_permissions=True)


def migrate_price_books():
    """Price books used to point at a dedicated ERPNext Price List; they now
    store item prices directly. Copy each legacy book's list prices into its
    items table once (skips base selling lists, which were never valid books)."""
    if not frappe.db.exists("DocType", "POS Price Book"):
        return
    protected = set()
    ss = frappe.db.get_single_value("Selling Settings", "selling_price_list")
    if ss:
        protected.add(ss)
    for pl in frappe.get_all("POS Profile", pluck="selling_price_list"):
        if pl:
            protected.add(pl)
    protected.add("Standard Selling")

    for name in frappe.get_all("POS Price Book", pluck="name"):
        doc = frappe.get_doc("POS Price Book", name)
        if doc.get("items") or not doc.get("price_list") or doc.price_list in protected:
            continue
        prices = frappe.get_all(
            "Item Price",
            filters={"price_list": doc.price_list, "selling": 1},
            fields=["item_code", "price_list_rate"],
        )
        if not prices:
            continue
        for p in prices:
            doc.append("items", {"item_code": p.item_code, "rate": p.price_list_rate})
        doc.save(ignore_permissions=True)


def ensure_roles():
    for role in LumenPOS_ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc(
                {"doctype": "Role", "role_name": role, "desk_access": 1}
            ).insert(ignore_permissions=True)


def grant_core_permissions():
    from frappe.permissions import add_permission, update_permission_property

    for role, doctypes in CORE_GRANTS.items():
        for doctype, ptypes in doctypes.items():
            if not frappe.db.exists("DocType", doctype):
                continue
            # Ensure a permlevel-0 permission row exists for this role, then turn
            # on each needed action. add_permission is a no-op if it's there.
            add_permission(doctype, role, 0)
            for ptype in ptypes:
                try:
                    update_permission_property(doctype, role, 0, ptype, 1, validate=False)
                except Exception:
                    # A ptype that doesn't apply to a doctype is harmless to skip.
                    pass


def make_custom_fields():
    """Custom fields: POS Invoice (and legacy Sales Invoice) get the
    register-session link and the applied-promotions audit field; POS
    Profile gets receipt-printer settings.

    Delivery-app channel data is written to the site's existing fields
    (custom_app_type, pick_order_no, pick_customer, is_exchange) when they
    exist — LumenPOS does not create them (see lumenpos.api.sales._set_custom)."""
    invoice_fields = [
        dict(
            fieldname="lumenpos_section",
            label="LumenPOS",
            fieldtype="Section Break",
            insert_after="remarks",
            collapsible=1,
        ),
        dict(
            fieldname="lumenpos_session",
            label="POS Register Session",
            fieldtype="Link",
            options="POS Register Session",
            insert_after="lumenpos_section",
            read_only=1,
        ),
        dict(
            fieldname="lumenpos_promotions",
            label="Applied Promotions",
            fieldtype="Long Text",
            insert_after="lumenpos_session",
            read_only=1,
        ),
        dict(
            fieldname="lumenpos_return_reason",
            label="Return Reason",
            fieldtype="Small Text",
            insert_after="lumenpos_promotions",
            read_only=1,
        ),
        # Delivery-app channel data is written to the site's OWN fields when
        # present — custom_app_type (Select), pick_order_no (Data),
        # pick_customer (Check), is_exchange (Check). LumenPOS does not create
        # those; it only reads/writes them if they exist.
    ]
    create_custom_fields(
        {
            "POS Profile": [
                dict(
                    fieldname="lumenpos_options_section",
                    label="LumenPOS Options",
                    fieldtype="Section Break",
                    insert_after="print_format",
                    collapsible=1,
                ),
                dict(
                    fieldname="lumenpos_invoice_mode",
                    label="Sale posts as",
                    fieldtype="Select",
                    options="POS Invoice\nSales Invoice",
                    default="POS Invoice",
                    insert_after="lumenpos_options_section",
                    description="POS Invoice (default): sales are POS Invoices that "
                    "ERPNext consolidates into Sales Invoices at register close. "
                    "Sales Invoice: each sale posts a Sales Invoice directly (GL posts "
                    "immediately, no consolidation); the register is a lightweight "
                    "LumenPOS cash shift with no POS Opening/Closing Entry.",
                ),
                dict(
                    fieldname="lumenpos_ignore_pricing_rules",
                    label="Ignore ERPNext Pricing Rules",
                    fieldtype="Check",
                    default="1",
                    insert_after="lumenpos_invoice_mode",
                    description="On (default): ERPNext Pricing Rules are bypassed and "
                    "LumenPOS uses its own promotion engine. Off: Pricing Rules apply "
                    "(they stack on top of any LumenPOS promotions — avoid running both).",
                ),
                dict(
                    fieldname="lumenpos_printer_section",
                    label="LumenPOS Receipt Printer",
                    fieldtype="Section Break",
                    insert_after="lumenpos_ignore_pricing_rules",
                    collapsible=1,
                ),
                dict(
                    fieldname="lumenpos_printer_ip",
                    label="Printer IP (ESC/POS, RAW 9100)",
                    fieldtype="Data",
                    insert_after="lumenpos_printer_section",
                ),
                dict(
                    fieldname="lumenpos_printer_port",
                    label="Printer Port",
                    fieldtype="Int",
                    insert_after="lumenpos_printer_ip",
                    default="9100",
                ),
            ],
            "POS Invoice": invoice_fields,
            "Sales Invoice": invoice_fields,  # legacy v0.1-0.3 sales keep working
            # Lines sold together as a bundle / buy-x-get-y set carry a group id so
            # a regular return can enforce returning the whole set together.
            "POS Invoice Item": [
                dict(
                    fieldname="lumenpos_return_group",
                    label="LumenPOS Return Group",
                    fieldtype="Data",
                    insert_after="warehouse",
                    read_only=1,
                    hidden=1,
                    print_hide=1,
                )
            ],
            # Same group tag on Sales Invoice Item for the Sales-Invoice backend.
            "Sales Invoice Item": [
                dict(
                    fieldname="lumenpos_return_group",
                    label="LumenPOS Return Group",
                    fieldtype="Data",
                    insert_after="warehouse",
                    read_only=1,
                    hidden=1,
                    print_hide=1,
                )
            ],
            # Declare the shift's drawer cash in/out on the official Z-report so
            # the movements are visible/traceable beside the reconciliation (the
            # cash row's expected_amount already nets them in).
            "POS Closing Entry": [
                dict(
                    fieldname="lumenpos_cash_section",
                    label="LumenPOS Cash Movements",
                    fieldtype="Section Break",
                    insert_after="payment_reconciliation",
                    collapsible=1,
                ),
                dict(
                    fieldname="lumenpos_cash_in",
                    label="Cash In (drawer)",
                    fieldtype="Currency",
                    insert_after="lumenpos_cash_section",
                    read_only=1,
                ),
                dict(
                    fieldname="lumenpos_cash_out",
                    label="Cash Out (drawer)",
                    fieldtype="Currency",
                    insert_after="lumenpos_cash_in",
                    read_only=1,
                ),
                dict(
                    fieldname="lumenpos_cash_movements",
                    label="Cash Movements",
                    fieldtype="Table",
                    options="POS Cash Movement",
                    insert_after="lumenpos_cash_out",
                    read_only=1,
                ),
            ],
        },
        ignore_validate=True,
    )
    # exchange_against_invoice already exists on POS Invoice (a site field) — LumenPOS
    # does not create it; exchanges.py writes the original invoice to it directly.
