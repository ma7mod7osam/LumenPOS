# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""The new-customer form at the till, set by the shop (LumenPOS Settings,
General, Customers).

Every field is Hidden, Optional or Required, separately for individual and
company customers. The built-in fields are the ones the till always had (mobile,
email, tax ID and the Saudi national address); any other field of Customer, the
shop's own custom fields included, can be added. With nothing configured the
form is exactly what it was before: name and mobile for everyone, and for a
company also the tax ID and the national address. The server applies the same
rules as the screen, so a stale tab or a direct call cannot skip a required
field.
"""

import frappe
from frappe import _
from frappe.utils import cint

SETTINGS = "LumenPOS Settings"
STATES = ("Hidden", "Optional", "Required")

# fieldname, label, individuals, companies: the form as it has always been.
BUILT_IN = (
    ("mobile_no", "Mobile", "Required", "Required"),
    ("email_id", "Email", "Optional", "Optional"),
    ("tax_id", "Tax ID", "Hidden", "Required"),
    ("building_no", "Building no.", "Hidden", "Required"),
    ("street", "Street", "Hidden", "Required"),
    ("district", "District", "Hidden", "Required"),
    ("city", "City", "Hidden", "Required"),
    ("postal_code", "Postal code", "Hidden", "Required"),
    ("additional_no", "Additional no.", "Hidden", "Optional"),
)
BUILT_IN_NAMES = tuple(row[0] for row in BUILT_IN)
ADDRESS_FIELDS = ("building_no", "street", "district", "city", "postal_code", "additional_no")

# Customer fields a shop may add to the form, and what the till renders them as.
EXTRA_TYPES = (
    "Data", "Phone", "Small Text", "Text", "Int", "Float", "Currency", "Date", "Select", "Check", "Link",
)
# Handled by the till or ERPNext itself, never offered as an extra.
NOT_EXTRA = {"customer_name", "customer_type", "naming_series", "disabled", "is_internal_customer"}


def _column(customer_type):
    return "for_companies" if customer_type == "Company" else "for_individuals"


def rules():
    """Every field of the form in order, with its state for each customer
    type: [{fieldname, label, builtin, fieldtype, options, individual,
    company}]. Built-in fields first (the address block stays together),
    then the shop's own fields in the order it set them."""
    try:
        rows = frappe.get_cached_doc(SETTINGS).get("customer_form_fields") or []
    except Exception:
        rows = []  # a site that has not migrated yet: the built-in form
    by_name = {r.fieldname: r for r in rows if r.fieldname}
    out = []
    for fieldname, label, individual, company in BUILT_IN:
        row = by_name.get(fieldname)
        out.append(
            {
                "fieldname": fieldname,
                "label": label,
                "builtin": 1,
                "fieldtype": "Data",
                "options": None,
                "individual": row.for_individuals if row and row.for_individuals in STATES else individual,
                "company": row.for_companies if row and row.for_companies in STATES else company,
            }
        )
    meta = frappe.get_meta("Customer")
    for row in rows:
        if not row.fieldname or row.fieldname in BUILT_IN_NAMES or row.fieldname in NOT_EXTRA:
            continue
        df = meta.get_field(row.fieldname)
        if not df or df.fieldtype not in EXTRA_TYPES:
            continue  # the field was removed from Customer, or cannot be typed at a till
        out.append(
            {
                "fieldname": row.fieldname,
                "label": row.label or df.label or row.fieldname,
                "builtin": 0,
                "fieldtype": df.fieldtype,
                "options": _options(df),
                "individual": row.for_individuals if row.for_individuals in STATES else "Hidden",
                "company": row.for_companies if row.for_companies in STATES else "Hidden",
            }
        )
    return out


def _options(df):
    if df.fieldtype == "Select":
        return [o for o in (df.options or "").split("\n") if o.strip()]
    if df.fieldtype == "Link":
        return df.options
    return None


def client_form(company=None):
    """What the till's form needs: the fields per customer type, and what the
    address block is called (national address in Saudi Arabia)."""
    country = frappe.get_cached_value("Company", company, "country") if company else None
    return {
        "fields": rules(),
        "address_label": "National address" if (country or "Saudi Arabia") == "Saudi Arabia" else "Address",
    }


def validate(payload, customer_type):
    """Refuse a customer the shop's form would not let through, naming what is
    missing. Returns the fields to write: {fieldname: value} for the shop's own
    fields on Customer (built-in ones are handled by create_customer)."""
    column = "company" if customer_type == "Company" else "individual"
    missing, extras = [], {}
    for field in rules():
        state = field[column]
        if state == "Hidden":
            continue
        value = payload.get(field["fieldname"])
        empty = value is None or (isinstance(value, str) and not value.strip())
        if field["fieldtype"] == "Check":
            empty = not cint(value)
        if state == "Required" and empty:
            missing.append(_(field["label"]))
        if not field["builtin"] and not empty:
            extras[field["fieldname"]] = value.strip() if isinstance(value, str) else value
    if missing:
        frappe.throw(_("Fill in: {0}").format(", ".join(missing)), title=_("New customer"))
    return extras


def shown(customer_type, fieldname):
    """Whether the form shows this field for this customer type; a hidden
    field's value is ignored even when a client sends one."""
    column = "company" if customer_type == "Company" else "individual"
    for field in rules():
        if field["fieldname"] == fieldname:
            return field[column] != "Hidden"
    return False


@frappe.whitelist()
def field_choices():
    """Customer fields a shop can add to the form, its own custom fields
    included."""
    if not frappe.has_permission(SETTINGS, "write"):
        frappe.throw(_("Only someone who manages LumenPOS Settings can change the customer form."), frappe.PermissionError)
    out = []
    for df in frappe.get_meta("Customer").fields:
        if df.fieldtype not in EXTRA_TYPES or df.fieldname in NOT_EXTRA or df.fieldname in BUILT_IN_NAMES:
            continue
        if cint(df.get("read_only")) or cint(df.get("hidden")):
            continue
        out.append({"fieldname": df.fieldname, "label": df.label or df.fieldname, "fieldtype": df.fieldtype})
    return sorted(out, key=lambda f: (f["label"] or "").lower())


@frappe.whitelist()
def link_values(fieldname, search=""):
    """Values for a Link field the shop put on the form (a customer group, a
    city list of its own), for the cashier to pick from. Only for fields on
    the form, and through the user's own permissions."""
    from lumenpos.api.sales import _require_sell

    _require_sell()
    field = next((f for f in rules() if f["fieldname"] == fieldname and not f["builtin"]), None)
    if not field or field["fieldtype"] != "Link" or not field["options"]:
        frappe.throw(_("{0} is not a field of the customer form").format(fieldname))
    filters = {"name": ["like", f"%{search}%"]} if search else {}
    return frappe.get_list(field["options"], filters=filters, pluck="name", limit_page_length=20, order_by="name asc")
