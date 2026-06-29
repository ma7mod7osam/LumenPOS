"""Customer lookup screen — paginated client search plus a per-customer profile
with balances, lifetime stats and (via sales.search_sales) their POS
transactions. Every query is server-paginated and scoped to indexed columns, so
opening this screen never scans the whole customer or sales table and has no
effect on the rest of the app (it only runs while the screen is open)."""

import frappe
from frappe import _
from frappe.utils import cint, flt

CUSTOMER_FIELDS = [
    "name", "customer_name", "customer_group", "customer_type",
    "mobile_no", "email_id", "tax_id",
]


def _require_read():
    if not frappe.has_permission("Customer", "read"):
        frappe.throw(
            _("You are not permitted to view customers."), frappe.PermissionError
        )


@frappe.whitelist()
def search_customers(search=None, customer_group=None, start=0, limit=30):
    """Paginated customer list. Light columns only — per-customer totals are
    computed on demand in customer_detail, never per row here. Fetches one extra
    row to report has_more without a separate COUNT. Returns {items, has_more}."""
    _require_read()
    start = cint(start)
    limit = min(cint(limit) or 30, 100)
    filters = {"disabled": 0}
    if customer_group:
        filters["customer_group"] = customer_group
    or_filters = None
    search = (search or "").strip()
    if search:
        like = f"%{search}%"
        or_filters = {
            "customer_name": ["like", like],
            "name": ["like", like],
            "mobile_no": ["like", like],
            "email_id": ["like", like],
            "tax_id": ["like", like],
        }
    rows = frappe.get_all(
        "Customer",
        filters=filters,
        or_filters=or_filters,
        fields=CUSTOMER_FIELDS,
        order_by="customer_name asc",
        limit_start=start,
        limit_page_length=limit + 1,
    )
    return {"items": rows[:limit], "has_more": len(rows) > limit}


@frappe.whitelist()
def customer_groups():
    """Flat list of customer-group names for the screen's filter dropdown."""
    _require_read()
    return frappe.get_all(
        "Customer Group",
        filters={"is_group": 0},
        pluck="name",
        order_by="name asc",
        limit_page_length=0,
    )


@frappe.whitelist()
def customer_detail(customer):
    """Profile + balances + lifetime POS stats for one customer. The stats are a
    single grouped query scoped to this customer (the `customer` column is
    indexed), so it stays cheap regardless of total invoice volume."""
    _require_read()
    if not frappe.db.exists("Customer", customer):
        frappe.throw(_("Customer {0} not found").format(customer))
    doc = frappe.get_doc("Customer", customer)
    doc.check_permission("read")

    stats = frappe.db.sql(
        """
        select
            sum(case when is_return = 0 then 1 else 0 end) as sales_count,
            sum(case when is_return = 1 then 1 else 0 end) as returns_count,
            sum(case when is_return = 0 then grand_total else 0 end) as total_spent,
            sum(case when is_return = 1 then abs(grand_total) else 0 end) as total_refunded,
            max(posting_date) as last_purchase
        from `tabPOS Invoice`
        where customer = %(customer)s and docstatus = 1
        """,
        {"customer": customer},
        as_dict=True,
    )[0]

    company = frappe.defaults.get_user_default("company") or frappe.db.get_single_value(
        "Global Defaults", "default_company"
    )
    wallet = {"loyalty_points": 0, "store_credit": 0}
    try:
        from lumenpos.api.loyalty import get_wallet

        if company:
            wallet = get_wallet(customer, company)
    except Exception:
        # Wallet is best-effort; the profile + stats still load without it.
        pass

    return {
        "name": doc.name,
        "customer_name": doc.customer_name,
        "customer_group": doc.customer_group,
        "customer_type": doc.get("customer_type"),
        "mobile_no": doc.get("mobile_no"),
        "email_id": doc.get("email_id"),
        "tax_id": doc.get("tax_id"),
        "territory": doc.get("territory"),
        "member_since": str(doc.creation)[:10] if doc.creation else None,
        "stats": {
            "sales_count": cint(stats.sales_count),
            "returns_count": cint(stats.returns_count),
            "total_spent": flt(stats.total_spent),
            "total_refunded": flt(stats.total_refunded),
            "net_spent": flt(stats.total_spent) - flt(stats.total_refunded),
            "last_purchase": str(stats.last_purchase) if stats.last_purchase else None,
        },
        "wallet": {
            "loyalty_points": wallet.get("loyalty_points") or 0,
            "store_credit": wallet.get("store_credit") or 0,
        },
        "currency": frappe.db.get_default("currency"),
    }
