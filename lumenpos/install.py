# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.utils import cint, flt

# Roles LumenPOS ships so admins have ready-made handles to assign in the Role
# Permissions Manager. Cashiers sell + run the register; managers also edit the
# back office (promotions, bundles, price books, settings). Actual access is
# governed by standard DocType permissions, so these can be tuned freely.
LumenPOS_ROLES = ["LumenPOS Cashier", "LumenPOS Manager"]

# Core ERPNext doctypes the LumenPOS roles need so they are turnkey: granting a
# user "LumenPOS Cashier" should let them load the POS, sell, and run the register
# (the closing consolidation runs as the cashier, so they also need the merge
# log + Sales Invoice rights). These are ADDITIVE, existing perms are never
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
# freely in Settings → Returns). They are shipped in English and carry an Arabic
# translation, so an Arabic till shows Arabic while the invoice keeps one
# canonical wording whatever language the cashier works in. A reason an admin
# types is stored and shown exactly as typed. "Other" is always offered by the
# till on top of this list.
DEFAULT_RETURN_REASONS = [
    "Damaged product",
    "Manufacturing defect",
    "Wrong size",
    "Wrong colour",
    "Does not match the description",
    "Customer changed their mind",
    "Ordered by mistake",
]

# The starter list used to be Arabic. A row still holding one of those exact
# strings was never edited, so move it to the English default it matches.
# Anything an admin typed does not match and is left alone.
LEGACY_RETURN_REASONS = {
    "منتج تالف": "Damaged product",
    "منتج به عيب صناعة": "Manufacturing defect",
    "مقاس غير مناسب": "Wrong size",
    "لون مختلف عن المطلوب": "Wrong colour",
    "المنتج لا يطابق الوصف": "Does not match the description",
    # Both spellings: the original seed carried a shadda, which the 0.46.2
    # sweep took out of everything generated after it. Old data still has it,
    # so this one place keeps the mark on purpose, to recognise those rows.
    "غيّر العميل رأيه": "Customer changed their mind",
    "غير العميل رأيه": "Customer changed their mind",
    "خطأ في الطلب": "Ordered by mistake",
}


def ensure_setup():
    """Idempotent setup re-run on every migrate (Frappe Cloud deploy): make
    sure the LumenPOS roles, their core permissions, and custom fields exist."""
    ensure_roles()
    grant_core_permissions()
    # Before make_custom_fields: it re-syncs the invoice tables, and that sync is
    # what used to drop these indexes.
    ensure_index_fields()
    make_custom_fields()
    drop_deprecated_custom_fields()
    migrate_price_books()
    ensure_return_reasons()
    migrate_coupon_limits()
    backfill_store_credit_references()
    default_insights_on()
    default_cashback_on()
    recost_open_holds()
    ensure_hot_indexes()


def recost_open_holds():
    """0.50.1: put the tax back on holds that were quoted without it.

    A hold used to total the held prices and nothing else. At an outlet whose
    price list is net of VAT that is not what the customer pays: the hand-over
    invoice adds the tax, so someone who had paid the hold "in full" was short
    by exactly that and the sale would not settle.

    Runs here rather than as a patch because patches.txt has no
    [post_model_sync] marker (and v13 cannot parse one), so a patch would run
    BEFORE tax_amount exists as a column, do nothing, and be logged as done.
    Only OPEN holds are touched, and only ones still sitting at zero: a
    completed hold's money is already spent, and an outlet whose prices include
    tax correctly comes out at zero anyway."""
    if not frappe.db.exists("DocType", "POS Layaway"):
        return
    if not frappe.db.has_column("POS Layaway", "tax_amount"):
        return
    names = frappe.get_all(
        "POS Layaway",
        filters={"status": "Open", "tax_amount": 0},
        pluck="name",
        limit_page_length=200,
    )
    if not names:
        return

    from lumenpos.api import layaway

    fixed = []
    for name in names:
        try:
            doc = frappe.get_doc("POS Layaway", name)
            if not doc.items:
                continue
            profile = layaway._profile(doc.pos_profile)
            items = [
                {"item_code": row.item_code, "qty": row.qty, "rate": row.rate}
                for row in doc.items
            ]
            net = flt(sum(flt(row.amount) for row in doc.items), 2)
            tax = flt(layaway._goods_total(profile, doc.customer, items) - net, 2)
            if tax <= 0:
                continue
            doc.tax_amount = tax
            doc.flags.ignore_permissions = True
            doc.save()
            fixed.append(f"{name} +{tax}")
        except Exception:
            # A hold whose outlet, item or tax template has moved on since is
            # left exactly as it was. Nothing is worse than an upgrade that
            # stops because one old record cannot be re-priced.
            frappe.db.rollback()
            continue
    if fixed:
        frappe.db.commit()  # nosemgrep
        print("LumenPOS: re-costed open holds with tax: " + ", ".join(fixed))


def default_insights_on():
    """enable_insights ships ON. A Check field's default only reaches new
    installs, and a loaded Single zeroes missing Check fields, so an
    upgraded site would silently read OFF. Write the ON down once, only
    while the value has never been stored, so an admin's later OFF is
    never overwritten."""
    # get_single_value casts a missing Check to 0, so only the tabSingles
    # row itself can distinguish "never stored" from "switched off".
    stored = frappe.db.sql(
        "select value from tabSingles where doctype=%s and field=%s",
        ("LumenPOS Settings", "enable_insights"),
    )
    if not stored:
        from lumenpos.api.insights import set_setting

        set_setting("enable_insights", 1)


def default_cashback_on():
    """enable_cashback ships ON (inert until a rule exists). A loaded Single
    zeroes a missing Check, so only the tabSingles row can tell "never
    stored" from "switched off". Write the ON down once."""
    from lumenpos.api.insights import set_setting

    stored = frappe.db.sql(
        "select value from tabSingles where doctype=%s and field=%s",
        ("LumenPOS Settings", "enable_cashback"),
    )
    if not stored:
        set_setting("enable_cashback", 1)


def backfill_store_credit_references():
    """Give every existing store-credit entry a reference_doctype.

    POS Store Credit Entry.reference_invoice used to be a plain Link to Sales
    Invoice, so a POS Invoice reference could not be written at all: it failed
    link validation and took the whole refund or redemption down with it. The
    field is a Dynamic Link now and needs a reference_doctype beside it.

    Rather than assume every old row points at a Sales Invoice, each reference
    is resolved against both doctypes, and one that resolves to neither has its
    dangling value cleared. Idempotent: rows that already carry a type are
    skipped, so re-running on every migrate costs nothing.

    Deliberately NOT a patch. Frappe v13 has no [post_model_sync] section, so a
    patch would run before the column exists.
    """
    if not frappe.db.has_column("POS Store Credit Entry", "reference_doctype"):
        return
    rows = frappe.get_all(
        "POS Store Credit Entry",
        filters={
            "reference_invoice": ["not in", ("", None)],
            "reference_doctype": ["in", ("", None)],
        },
        fields=["name", "reference_invoice"],
    )
    for row in rows:
        resolved = None
        for doctype in ("Sales Invoice", "POS Invoice"):
            if frappe.db.exists(doctype, row.reference_invoice):
                resolved = doctype
                break
        frappe.db.set_value(
            "POS Store Credit Entry",
            row.name,
            {
                "reference_doctype": resolved,
                "reference_invoice": row.reference_invoice if resolved else None,
            },
            update_modified=False,
        )
    # No commit here. ensure_setup() runs as an after_migrate hook, and on
    # every supported version that hook chain is already committed for us.
    # v14 and v15 wrap it in migrate.py's @atomic, which commits on success
    # and rolls back on any exception. v13's migrate() commits right after
    # running every installed app's after_migrate hooks. Verified on frappe
    # 13.58.22, 14.101.1 and 15.119.1.


# Indexes LumenPOS's own hot paths need. Harmless on a small site, decisive on a
# large one. (name, doctype, [columns]), created only if the column exists.
HOT_INDEXES = [
    # Every sale checks "did this idempotency key already post?" before
    # inserting. Unindexed, that is a FULL SCAN of the invoice table on EVERY
    # sale, imperceptible at demo size, seconds per sale at a million rows.
    # The custom field is unique, so on a healthy site Frappe's own UNIQUE index
    # already serves this and nothing is built here.
    ("lumenpos_idem_idx", "POS Invoice", ["lumenpos_idempotency_key"]),
    ("lumenpos_idem_idx", "Sales Invoice", ["lumenpos_idempotency_key"]),
    # Shift queries: every X-report, close and Z-report filters by session.
    ("lumenpos_session_idx", "POS Invoice", ["lumenpos_session"]),
    ("lumenpos_session_idx", "Sales Invoice", ["lumenpos_session"]),
    # ERPNext itself, on EVERY submit, asks "how much of this item is reserved by
    # unconsolidated POS invoices?", joining the largest table on the site, once
    # per cart line. This composite serves exactly that query.
    ("lumenpos_item_wh_idx", "POS Invoice Item", ["item_code", "warehouse"]),
    # Loyalty lookups per sale/receipt.
    ("lumenpos_loyalty_inv_idx", "Loyalty Point Entry", ["invoice"]),
    # History free-text probes (see sales._search_probe_names).
    ("lumenpos_cust_name_idx", "POS Invoice", ["customer_name"]),
    ("lumenpos_cust_name_idx", "Sales Invoice", ["customer_name"]),
]


# Columns above that Frappe would otherwise un-index. Frappe's schema sync drops
# any non-unique index whose first column is not marked as a search_index field,
# and it re-syncs these tables on every migrate (create_custom_fields calls
# frappe.db.updatedb). Marking the field tells Frappe the column is indexed, so
# it keeps the index instead of dropping it and LumenPOS rebuilding it. This is
# what frappe.db.add_index does on v14+, done here for v13 as well, and for the
# core fields it cannot reach. Not listed here, on purpose:
#   lumenpos_idempotency_key - the custom field is unique, so Frappe already
#     keeps a UNIQUE index on it, and marking it too would add a second one.
#   POS Invoice Item.item_code - ERPNext already ships it as a search_index
#     field, which is what keeps the composite index above.
INDEX_FIELDS = [
    ("POS Invoice", "customer_name"),
    ("Sales Invoice", "customer_name"),
    ("Loyalty Point Entry", "invoice"),
]


def _leading_index(doctype, columns):
    """The name of an index on this table whose first columns are exactly
    `columns`, in order, or None. Matched by columns, not by name, so an index
    Frappe made itself (`<fieldname>_index`, or the UNIQUE one behind a unique
    field) counts and is never duplicated.

    Asked via information_schema so the table name is a BOUND PARAMETER, not an
    interpolated identifier. A "SHOW INDEX FROM tab<doctype>" cannot bind its
    table name, which would mean an f-string inside a frappe.db.sql call, the
    exact shape of a SQL-injection finding."""
    rows = frappe.db.sql(
        """
        select index_name, column_name, seq_in_index
        from information_schema.statistics
        where table_schema = database() and table_name = %s
        order by index_name, seq_in_index
        """,
        (f"tab{doctype}",),
    )
    wanted = [c.lower() for c in columns]
    found = {}
    for index_name, column_name, _seq in rows:
        found.setdefault(index_name, []).append((column_name or "").lower())
    for index_name, index_columns in found.items():
        if index_columns[: len(wanted)] == wanted:
            return index_name
    return None


def ensure_index_fields():
    """Mark the indexed core columns as search_index fields (see INDEX_FIELDS),
    so Frappe's own schema sync keeps their index instead of dropping it on
    every migrate. Idempotent, and skipped where the field is already marked."""
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    for doctype, fieldname in INDEX_FIELDS:
        try:
            if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, fieldname):
                continue
            field = frappe.get_meta(doctype).get_field(fieldname)
            if not field or cint(field.search_index):
                continue
            make_property_setter(
                doctype, fieldname, "search_index", 1, "Check",
                for_doctype=False, validate_fields_for_doctype=False,
            )
            frappe.clear_cache(doctype=doctype)
        except Exception:
            frappe.log_error(
                title="LumenPOS index field marking failed",
                message=f"{doctype}.{fieldname}: {frappe.get_traceback()}",
            )


def index_health():
    """Every performance index with its state: built / missing / n-a (the column
    doesn't exist on this site). Index builds fail SILENTLY into the Error Log, 
    a big site can refuse the lock, so this is surfaced in Settings → Status
    with a rebuild button rather than being invisible."""
    out = []
    for index_name, doctype, columns in HOT_INDEXES:
        row = {"index": index_name, "doctype": doctype, "columns": ", ".join(columns)}
        try:
            if not frappe.db.table_exists(doctype) or not all(
                frappe.db.has_column(doctype, c) for c in columns
            ):
                row["state"] = "n-a"
            else:
                built_as = _leading_index(doctype, columns)
                row["state"] = "built" if built_as else "missing"
                if built_as and built_as != index_name:
                    # Frappe's own index on the same columns does the same job.
                    row["built_as"] = built_as
        except Exception:
            row["state"] = "unknown"
        out.append(row)
    return out


def ensure_hot_indexes():
    """Create any performance index the columns above still lack. Idempotent and
    best-effort: a failure is logged, never fatal to a migrate (building an
    index on a huge, busy table can be refused the lock. Deploy in a quiet
    window and re-run the migrate).

    With ensure_index_fields() in place, Frappe keeps these indexes itself, so
    this is normally a no-op check. It still runs on every migrate as the safety
    net for a site where an index is genuinely missing."""
    for index_name, doctype, columns in HOT_INDEXES:
        try:
            table = f"tab{doctype}"
            if not frappe.db.table_exists(doctype):
                continue
            if not all(frappe.db.has_column(doctype, c) for c in columns):
                continue
            if _leading_index(doctype, columns):
                continue
            cols = ", ".join(f"`{c}`" for c in columns)
            # ALTER TABLE commits implicitly, and Frappe refuses one while the
            # transaction holds writes ("This statement can cause implicit
            # commit", on v13, v14 and v15). ensure_setup() usually writes
            # before this, so the build used to fail. Commit those writes
            # first, exactly as frappe.db.add_index does before its own ALTER
            # (add_index itself is not used because on v14+ it also adds a
            # search_index Property Setter to the core field, which
            # ensure_index_fields does deliberately and on every version).
            frappe.db.commit()  # nosemgrep
            frappe.db.sql(f"ALTER TABLE `{table}` ADD INDEX `{index_name}` ({cols})")  # nosemgrep
        except Exception:
            frappe.log_error(
                title="LumenPOS index build failed",
                message=f"{index_name} on {doctype}: {frappe.get_traceback()}",
            )


def drop_deprecated_custom_fields():
    """Remove POS Profile custom fields LumenPOS no longer uses. Idempotent.
    `lumenpos_ignore_pricing_rules` was retired in v0.12.0. POS sales now ALWAYS
    ignore ERPNext Pricing Rules (the till never applies them), so the toggle
    only invited the price-book-vs-Pricing-Rule mismatch."""
    for name in ("POS Profile-lumenpos_ignore_pricing_rules",):
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, ignore_permissions=True)
    # `allow_multiple_opening` was retired with the no-resume rule: opening is
    # ALWAYS a fresh shift now, so "allow a second open shift" has no meaning.
    try:
        if frappe.db.has_column("LumenPOS Settings", "allow_multiple_opening"):
            frappe.db.sql(
                "ALTER TABLE `tabLumenPOS Settings` DROP COLUMN `allow_multiple_opening`"  # nosemgrep
            )
    except Exception:
        pass


def migrate_coupon_limits():
    """v0.18.0 coupons had a single_use flag; v0.19.0 uses a numeric usage_limit
    (0 = unlimited). Reusable old codes (single_use=0) would inherit the new Int
    default of 1 on migrate, restore them to unlimited. Idempotent."""
    if not frappe.db.exists("DocType", "POS Coupon"):
        return
    frappe.db.sql(
        "update `tabPOS Coupon` set usage_limit = 0 "
        "where coalesce(single_use, 0) = 0 and usage_limit = 1"
    )


def ensure_return_reasons():
    """Seed a starter list of return reasons the first time only, and move a
    still untouched Arabic starter row to its English default (see
    LEGACY_RETURN_REASONS). Admin edits are never touched."""
    if not frappe.db.exists("DocType", "POS Return Reason"):
        return
    doc = frappe.get_single("LumenPOS Settings")
    rows = doc.get("return_reasons") or []
    if rows:
        changed = False
        for row in rows:
            english = LEGACY_RETURN_REASONS.get((row.reason or "").strip())
            if english and english != row.reason:
                row.reason = english
                changed = True
        if changed:
            doc.save(ignore_permissions=True)
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
    exist. LumenPOS does not create them (see lumenpos.api.sales._set_custom)."""
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
            # Every X-report, close and Z-report filters by session. Marked as an
            # indexed field so Frappe builds and keeps that index itself (see
            # ensure_index_fields for the core fields it cannot reach).
            search_index=1,
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
        dict(
            fieldname="lumenpos_note",
            label="POS Note",
            fieldtype="Small Text",
            insert_after="lumenpos_return_reason",
            read_only=1,
        ),
        dict(
            fieldname="lumenpos_idempotency_key",
            label="POS Idempotency Key",
            fieldtype="Data",
            insert_after="lumenpos_note",
            read_only=1,
            unique=1,
            no_copy=1,
            description="Client key for an offline-queued sale, prevents a retried sync from posting a duplicate invoice.",
        ),
        # Delivery-app channel data is written to the site's OWN fields when
        # present, custom_app_type (Select), pick_order_no (Data),
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
                    "LumenPOS cash shift (optionally with POS Opening/Closing Entries. See below).",
                ),
                dict(
                    fieldname="lumenpos_si_opening_closing",
                    label="Use POS Opening/Closing Entries (cash control)",
                    fieldtype="Check",
                    default="0",
                    insert_after="lumenpos_invoice_mode",
                    depends_on="eval:doc.lumenpos_invoice_mode=='Sales Invoice'",
                    description="Sales Invoice mode only. On: opening the register creates a "
                    "POS Opening Entry and closing creates a POS Closing Entry (for cash "
                    "supervision and the standard ERPNext POS reports), with NO "
                    "consolidation, since sales already post as Sales Invoices. Off: a "
                    "lightweight cash shift with no opening/closing entry.",
                ),
                dict(
                    fieldname="lumenpos_printer_section",
                    label="LumenPOS Receipt Printer",
                    fieldtype="Section Break",
                    insert_after="lumenpos_si_opening_closing",
                    collapsible=1,
                ),
                dict(
                    fieldname="lumenpos_shift_schedule",
                    label="Shift Schedule",
                    fieldtype="Link",
                    options="POS Shift Schedule",
                    insert_after="lumenpos_si_opening_closing",
                    description="Used by the forgotten-shift alert to know when this outlet's shifts should end.",
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
                # ERPNext's own pos_transactions table links POS Invoices, so a
                # shift that posts Sales Invoices directly leaves the Z-report
                # with takings but no way to see WHICH invoices they came from.
                # An accountant checking the drawer needs that list.
                dict(
                    fieldname="lumenpos_invoices_section",
                    label="LumenPOS Sales Invoices",
                    fieldtype="Section Break",
                    insert_after="lumenpos_cash_movements",
                    collapsible=1,
                ),
                dict(
                    fieldname="lumenpos_sales_invoices",
                    label="Sales Invoices in this shift",
                    fieldtype="Table",
                    options="POS Shift Invoice",
                    insert_after="lumenpos_invoices_section",
                    read_only=1,
                    description=(
                        "Every Sales Invoice this shift posted, including returns. "
                        "Filled when the outlet sells as Sales Invoice instead of POS Invoice."
                    ),
                ),
            ],
        },
        ignore_validate=True,
    )
    # exchange_against_invoice already exists on POS Invoice (a site field). LumenPOS
    # does not create it; exchanges.py writes the original invoice to it directly.
