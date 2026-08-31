"""Build a realistic LumenPOS demo site: masters, settings, and a month of trade.

Trigger it from a browser, signed in as a System Manager:

    frappe.call({method: "lumenpos.demo_data.build_demo_data"})

or from a bench:

    bench --site <site> execute lumenpos.demo_data.run

What it creates
    company (reused if the site already has one), VAT template, warehouses,
    item groups, brands, ~60 items with barcodes (a few serialised), opening
    stock, ~150 customers, every mode of payment, three POS Profiles with the
    LumenPOS settings filled in, a loyalty programme, price books, promotions of
    all four kinds, bundles, coupons, gift cards, then a register shift per
    outlet per day for 30 days with a realistic mix of baskets, tenders,
    discounts and returns, each shift closed and consolidated. The last day is
    left open so the till has a live shift to show.

Everything posts through LumenPOS's own submit_sale, so the demo data is real:
promotions resolved server side, sessions linked, receipts, loyalty, stock.

Safety
    It refuses to touch a site that already looks like a real shop (more than
    RECENT_SALES_GUARD posted POS invoices) unless you pass force=True.
    Nothing is ever deleted.
"""

import json
import random

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, flt, nowdate

# ---------------------------------------------------------------------------
# Knobs
# ---------------------------------------------------------------------------
INVOICE_TARGET = 1000
DAYS = 30
CUSTOMERS = 150
RECENT_SALES_GUARD = 50
CURRENCY = "SAR"
VAT_RATE = 15.0
SEED = 20260830

OUTLETS = [
    ("Lumen Riyadh Olaya", "Olaya Store"),
    ("Lumen Riyadh Exit 9", "Exit 9 Store"),
    ("Lumen Jeddah Tahlia", "Tahlia Store"),
]

# (group, [(code, name_en, price_including_vat, serialised)])
CATALOGUE = [
    ("Beverages", [
        ("BEV-001", "Arabic Coffee 250g", 24.00, 0),
        ("BEV-002", "Green Tea 100 bags", 18.50, 0),
        ("BEV-003", "Orange Juice 1L", 9.00, 0),
        ("BEV-004", "Sparkling Water 6x330ml", 12.00, 0),
        ("BEV-005", "Energy Drink 250ml", 7.50, 0),
        ("BEV-006", "Cold Brew Bottle 330ml", 14.00, 0),
        ("BEV-007", "Mineral Water 12x600ml", 11.00, 0),
        ("BEV-008", "Karak Tea Mix 400g", 21.00, 0),
    ]),
    ("Snacks", [
        ("SNK-001", "Salted Nuts Mix 300g", 27.00, 0),
        ("SNK-002", "Dark Chocolate 100g", 13.00, 0),
        ("SNK-003", "Potato Chips 165g", 8.50, 0),
        ("SNK-004", "Dates Premium 500g", 45.00, 0),
        ("SNK-005", "Biscuits Assorted 400g", 16.00, 0),
        ("SNK-006", "Popcorn Sweet 120g", 6.50, 0),
        ("SNK-007", "Granola Bars 6 pack", 19.00, 0),
        ("SNK-008", "Baklava Box 500g", 65.00, 0),
    ]),
    ("Household", [
        ("HOM-001", "Laundry Liquid 3L", 39.00, 0),
        ("HOM-002", "Dish Soap 750ml", 12.50, 0),
        ("HOM-003", "Paper Towels 6 rolls", 24.00, 0),
        ("HOM-004", "Trash Bags 50pcs", 17.00, 0),
        ("HOM-005", "Air Freshener 300ml", 15.00, 0),
        ("HOM-006", "Floor Cleaner 2L", 22.00, 0),
        ("HOM-007", "Glass Cleaner 500ml", 11.50, 0),
        ("HOM-008", "Storage Box 20L", 34.00, 0),
    ]),
    ("Personal Care", [
        ("PER-001", "Shampoo 400ml", 28.00, 0),
        ("PER-002", "Body Wash 500ml", 26.00, 0),
        ("PER-003", "Toothpaste 100ml", 14.00, 0),
        ("PER-004", "Face Cream 50ml", 79.00, 0),
        ("PER-005", "Deodorant 150ml", 18.00, 0),
        ("PER-006", "Hand Sanitiser 250ml", 9.50, 0),
        ("PER-007", "Oud Perfume 50ml", 245.00, 0),
        ("PER-008", "Razor Blades 8 pack", 42.00, 0),
    ]),
    ("Apparel", [
        ("APP-001", "Cotton T-Shirt", 59.00, 0),
        ("APP-002", "Denim Jeans", 149.00, 0),
        ("APP-003", "Hoodie", 129.00, 0),
        ("APP-004", "Socks 3 pack", 29.00, 0),
        ("APP-005", "Baseball Cap", 45.00, 0),
        ("APP-006", "Leather Belt", 89.00, 0),
        ("APP-007", "Running Shorts", 69.00, 0),
        ("APP-008", "Linen Shirt", 139.00, 0),
    ]),
    ("Electronics", [
        ("ELE-001", "Wireless Earbuds", 249.00, 1),
        ("ELE-002", "Bluetooth Speaker", 329.00, 1),
        ("ELE-003", "Power Bank 20000mAh", 149.00, 1),
        ("ELE-004", "USB-C Cable 2m", 35.00, 0),
        ("ELE-005", "Phone Case", 49.00, 0),
        ("ELE-006", "Smart Watch", 599.00, 1),
        ("ELE-007", "Wall Charger 30W", 79.00, 0),
        ("ELE-008", "Screen Protector", 25.00, 0),
    ]),
]

BRANDS = ["Lumen", "Najd", "Riyad Basics", "Tahlia Living"]

FIRST_NAMES = [
    "Mohammed", "Abdullah", "Fahad", "Sultan", "Khalid", "Faisal", "Omar",
    "Yousef", "Saad", "Nasser", "Turki", "Bandar", "Majed", "Ziad", "Rayan",
    "Sara", "Noura", "Reem", "Lama", "Hind", "Aisha", "Maha", "Dana", "Layan",
    "Jood", "Ghada", "Amal", "Salma", "Wafa", "Rana",
]
LAST_NAMES = [
    "Al Qahtani", "Al Otaibi", "Al Harbi", "Al Ghamdi", "Al Shehri",
    "Al Dosari", "Al Malki", "Al Zahrani", "Al Subaie", "Al Anazi",
    "Al Mutairi", "Al Juhani", "Al Balawi", "Al Rashidi", "Al Amri",
]
COMPANY_CUSTOMERS = [
    "Najd Trading Est", "Tahlia Contracting Co", "Olaya Facilities Co",
    "Rawabi Logistics", "Falcon Office Supplies", "Dar Al Riyadh Services",
]

MODES = [
    ("Cash", "Cash"),
    ("Mada", "Bank"),
    ("Credit Card", "Bank"),
    ("Bank Transfer", "Bank"),
]

rng = random.Random(SEED)
LOG = []


def say(message):
    LOG.append(message)
    print(message, flush=True)


FAILURES = {}


def _note_failure(exc):
    """Remember why a sale did not post. A generator that quietly skips every
    basket and then reports success is worse than one that stops."""
    key = str(exc).strip()[:180] or type(exc).__name__
    FAILURES[key] = FAILURES.get(key, 0) + 1
    if FAILURES[key] == 1:
        say("  ! sale refused: %s" % key)


# ---------------------------------------------------------------------------
# Backdating
# ---------------------------------------------------------------------------
_ORIGINAL_INSERT = Document.insert
_DATED = (
    "POS Invoice",
    "Sales Invoice",
    "Stock Entry",
    "POS Opening Entry",
    "POS Closing Entry",
    "Payment Entry",
)


def _dated_insert(self, *args, **kwargs):
    """Post historical documents on the day they belong to.

    submit_sale has no posting-date argument, on purpose: a till sells today.
    A demo history needs dated documents, so the date is applied here instead
    of adding a back-dating path to the product. This patch lives only for the
    length of the run, and is removed in a finally block.
    """
    stamp = frappe.flags.get("lumenpos_demo_stamp")
    if stamp and self.doctype in _DATED:
        # Overwrite unconditionally. ERPNext has already defaulted posting_date
        # to today by the time insert() runs (set_missing_values does it while
        # the cart is being priced), so "only if empty" would never fire and the
        # whole history would land on one day.
        self.set_posting_time = 1
        self.posting_date, self.posting_time = stamp
    return _ORIGINAL_INSERT(self, *args, **kwargs)


# ---------------------------------------------------------------------------
# Masters
# ---------------------------------------------------------------------------
def _company():
    """Reuse the site's company, or run ERPNext's setup wizard if there is none.

    A bare site has no Warehouse Types, UOMs or Item Groups, so inserting a
    Company directly fails on its own default warehouses. The wizard is what
    installs those fixtures, so it is the only correct way to set up an empty
    site. On a site that is already set up (which is the normal case) nothing
    here runs at all.
    """
    existing = frappe.db.get_value("Company", {}, "name")
    if existing:
        say("company: reusing %s" % existing)
        _ksa_company_fields(existing)
        return existing

    from frappe.desk.page.setup_wizard.setup_wizard import setup_complete

    year = frappe.utils.getdate(nowdate()).year
    setup_complete(
        {
            "currency": CURRENCY,
            "full_name": "Lumen Admin",
            "company_name": "Lumen Retail",
            "company_abbr": "LR",
            "company_tagline": "Retail",
            "industry": "Retail",
            "country": "Saudi Arabia",
            "timezone": "Asia/Riyadh",
            "language": "english",
            "chart_of_accounts": "Standard",
            "fy_start_date": "%d-01-01" % (year - 1),
            "fy_end_date": "%d-12-31" % (year - 1),
        }
    )
    frappe.db.commit()
    name = frappe.db.get_value("Company", {}, "name")
    _ksa_company_fields(name)
    say("company: set up %s through ERPNext's own setup wizard" % name)
    return name


def _ksa_company_fields(company):
    """On a Saudi site ERPNext builds a ZATCA QR for every invoice, and refuses
    to post without the seller's Arabic name and VAT number on the Company. Fill
    them in rather than let every sale fail at the till."""
    meta = frappe.get_meta("Company")
    values = {}
    if meta.has_field("company_name_in_arabic") and not frappe.db.get_value(
        "Company", company, "company_name_in_arabic"
    ):
        values["company_name_in_arabic"] = "لومن ريتيل"
    if not frappe.db.get_value("Company", company, "tax_id"):
        values["tax_id"] = "300000000000003"
    if values:
        frappe.db.set_value("Company", company, values, update_modified=False)
        say("company: filled %s (needed for the ZATCA QR)" % ", ".join(sorted(values)))


def _fiscal_years(company):
    """A fiscal year covering every day this demo posts into."""
    years = {frappe.utils.getdate(nowdate()).year, frappe.utils.getdate(add_days(nowdate(), -DAYS)).year}
    for year in sorted(years):
        name = str(year)
        if not frappe.db.exists("Fiscal Year", name):
            frappe.get_doc(
                {
                    "doctype": "Fiscal Year",
                    "year": name,
                    "year_start_date": "%d-01-01" % year,
                    "year_end_date": "%d-12-31" % year,
                }
            ).insert(ignore_permissions=True)
        doc = frappe.get_doc("Fiscal Year", name)
        if company not in [row.company for row in (doc.get("companies") or [])]:
            doc.append("companies", {"company": company})
            doc.save(ignore_permissions=True)
    say("fiscal years: %s" % sorted(years))


def _account(company, name_like, root=None):
    filters = {"company": company, "is_group": 0, "account_name": ["like", name_like]}
    if root:
        filters["root_type"] = root
    return frappe.db.get_value("Account", filters, "name")


def _vat_template(company, abbr):
    """KSA style: 15% VAT, included in the shelf price."""
    name = "KSA VAT 15%% - %s" % abbr
    if frappe.db.exists("Sales Taxes and Charges Template", name):
        return name
    account = _account(company, "%VAT%", "Liability") or _account(company, "%Duties and Taxes%")
    if not account:
        parent = frappe.db.get_value(
            "Account", {"company": company, "is_group": 1, "account_name": ["like", "%Duties and Taxes%"]}, "name"
        ) or frappe.db.get_value("Account", {"company": company, "is_group": 1, "root_type": "Liability"}, "name")
        account = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": "VAT 15%",
                "parent_account": parent,
                "company": company,
                "account_type": "Tax",
                "root_type": "Liability",
                "is_group": 0,
            }
        ).insert(ignore_permissions=True).name
    doc = frappe.get_doc(
        {
            "doctype": "Sales Taxes and Charges Template",
            "title": "KSA VAT 15%",
            "company": company,
            "is_default": 1,
            "taxes": [
                {
                    "charge_type": "On Net Total",
                    "account_head": account,
                    "description": "VAT 15%",
                    "rate": VAT_RATE,
                    "included_in_print_rate": 1,
                }
            ],
        }
    ).insert(ignore_permissions=True)
    say("VAT template: %s (15%%, included in the price)" % doc.name)
    return doc.name


def _warehouses(company, abbr):
    parent = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name")
    made = []
    for _, store in OUTLETS:
        name = "%s - %s" % (store, abbr)
        if not frappe.db.exists("Warehouse", name):
            frappe.get_doc(
                {
                    "doctype": "Warehouse",
                    "warehouse_name": store,
                    "company": company,
                    "parent_warehouse": parent,
                }
            ).insert(ignore_permissions=True)
        made.append(name)
    say("warehouses: %s" % made)
    return made


def _item_groups():
    for group, _ in CATALOGUE:
        if not frappe.db.exists("Item Group", group):
            frappe.get_doc(
                {
                    "doctype": "Item Group",
                    "item_group_name": group,
                    "parent_item_group": "All Item Groups",
                    "is_group": 0,
                }
            ).insert(ignore_permissions=True)
    for brand in BRANDS:
        if not frappe.db.exists("Brand", brand):
            frappe.get_doc({"doctype": "Brand", "brand": brand}).insert(ignore_permissions=True)
    say("item groups: %d, brands: %d" % (len(CATALOGUE), len(BRANDS)))


def _price_list(company):
    """Standard Selling has to be in the company's currency or every line
    prices at zero. Point it at the company currency if the site has not been
    used for selling yet."""
    currency = frappe.db.get_value("Company", company, "default_currency") or CURRENCY
    listed = frappe.db.get_value("Price List", "Standard Selling", "currency")
    if listed and listed != currency:
        if frappe.db.count("Item Price", {"price_list": "Standard Selling"}):
            say("price list: Standard Selling is in %s but the company is in %s. "
                "Leaving it alone because it already has prices." % (listed, currency))
        else:
            frappe.db.set_value("Price List", "Standard Selling", "currency", currency,
                                update_modified=False)
            say("price list: Standard Selling switched to %s" % currency)
    return "Standard Selling"


def _items(company, warehouse):
    codes = []
    for group, rows in CATALOGUE:
        for code, name, price, serialised in rows:
            codes.append((code, price, serialised))
            if frappe.db.exists("Item", code):
                continue
            doc = frappe.get_doc(
                {
                    "doctype": "Item",
                    "item_code": code,
                    "item_name": name,
                    "item_group": group,
                    "brand": rng.choice(BRANDS),
                    "stock_uom": "Nos",
                    "is_stock_item": 1,
                    "has_serial_no": serialised,
                    "valuation_rate": flt(price * 0.55, 2),
                    "barcodes": [{"barcode": "628%010d" % (abs(hash(code)) % 10**10)}],
                    "item_defaults": [{"company": company, "default_warehouse": warehouse}],
                }
            )
            if serialised:
                doc.serial_no_series = code + "-.#####"
            doc.insert(ignore_permissions=True)
            frappe.get_doc(
                {
                    "doctype": "Item Price",
                    "item_code": code,
                    "price_list": "Standard Selling",
                    "price_list_rate": price,
                }
            ).insert(ignore_permissions=True)
    say("items: %d (%d serialised), each priced on Standard Selling"
        % (len(codes), sum(1 for c in codes if c[2])))
    return codes


def _stock(company, warehouses, codes, when):
    frappe.flags.lumenpos_demo_stamp = (when, "08:00:00")
    for warehouse in warehouses:
        rows = []
        for code, _price, serialised in codes:
            have = flt(frappe.db.get_value("Bin", {"item_code": code, "warehouse": warehouse}, "actual_qty"))
            if have >= 400:
                continue
            rows.append(
                {
                    "item_code": code,
                    "qty": 120 if serialised else 900,
                    "t_warehouse": warehouse,
                    "basic_rate": flt(_price * 0.55, 2),
                }
            )
        if not rows:
            continue
        entry = frappe.get_doc(
            {
                "doctype": "Stock Entry",
                "stock_entry_type": "Material Receipt",
                "company": company,
                "items": rows,
            }
        )
        entry.insert(ignore_permissions=True)
        entry.submit()
    frappe.flags.lumenpos_demo_stamp = None
    say("opening stock received into %d warehouse(s) on %s" % (len(warehouses), when))


def _modes_of_payment(company, abbr):
    from lumenpos.internal_accounts import fill_required_custom_fields

    cash = _account(company, "Cash", "Asset") or _account(company, "%Cash%")
    bank = _account(company, "%Bank%", "Asset") or cash
    for mode, kind in MODES:
        account = cash if kind == "Cash" else bank
        if not frappe.db.exists("Mode of Payment", mode):
            doc = frappe.get_doc(
                {
                    "doctype": "Mode of Payment",
                    "mode_of_payment": mode,
                    "type": kind,
                    "enabled": 1,
                    "accounts": [{"company": company, "default_account": account}],
                }
            )
            fill_required_custom_fields(doc, mode)
            doc.insert(ignore_permissions=True)
            continue
        doc = frappe.get_doc("Mode of Payment", mode)
        doc.type = kind
        doc.enabled = 1
        if not [row for row in doc.accounts if row.company == company]:
            doc.append("accounts", {"company": company, "default_account": account})
        fill_required_custom_fields(doc, mode)
        doc.save(ignore_permissions=True)
    say("modes of payment: %s (gift card and store credit are created on first use)"
        % ", ".join(m for m, _ in MODES))


def _customers():
    group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name")
    territory = frappe.db.get_value("Territory", {"is_group": 0}, "name")
    names = []
    for i in range(CUSTOMERS):
        if i < len(COMPANY_CUSTOMERS):
            name = COMPANY_CUSTOMERS[i]
            kind = "Company"
        else:
            name = "%s %s" % (rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES))
            kind = "Individual"
        name = "%s %03d" % (name, i + 1)
        names.append(name)
        if frappe.db.exists("Customer", name):
            continue
        doc = frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": name,
                "customer_type": kind,
                "customer_group": group,
                "territory": territory,
                "mobile_no": "05%08d" % rng.randint(0, 99999999),
            }
        )
        if kind == "Company":
            doc.tax_id = "3%014d" % rng.randint(0, 10**14 - 1)
        doc.insert(ignore_permissions=True)
    walk_in = "Walk-in Customer"
    if not frappe.db.exists("Customer", walk_in):
        frappe.get_doc(
            {
                "doctype": "Customer",
                "customer_name": walk_in,
                "customer_type": "Individual",
                "customer_group": group,
                "territory": territory,
            }
        ).insert(ignore_permissions=True)
    say("customers: %d named, plus %s" % (len(names), walk_in))
    return walk_in, names


def _loyalty(company, abbr):
    name = "Lumen Rewards"
    if not frappe.db.exists("Loyalty Program", name):
        frappe.get_doc(
            {
                "doctype": "Loyalty Program",
                "loyalty_program_name": name,
                "loyalty_program_type": "Single Tier Program",
                "from_date": add_days(nowdate(), -365),
                "company": company,
                "conversion_factor": 1,
                "expiry_duration": 0,
                "auto_opt_in": 1,
                "expense_account": _account(company, "%Cost of Goods Sold%", "Expense")
                or _account(company, "%Expense%", "Expense"),
                "cost_center": frappe.db.get_value("Cost Center", {"company": company, "is_group": 0}, "name"),
                "collection_rules": [{"tier_name": "Member", "collection_factor": 20, "min_spent": 0}],
            }
        ).insert(ignore_permissions=True)
    say("loyalty: %s (auto opt-in, 1 point per 20 spent)" % name)
    return name


def _enrol(customers, program, share=0.4):
    """Put some customers on the loyalty programme.

    A POS Invoice only earns points when the invoice carries a loyalty_program,
    and it inherits that from the customer record. ERPNext's own auto opt-in
    lookup runs in the Sales Invoice validate that POS Invoice deliberately
    skips, so without this nobody in the demo would ever earn a point.
    Enrolling a share of them, rather than all, is also closer to a real shop.
    """
    members = customers[: max(1, int(len(customers) * share))]
    for customer in members:
        if not frappe.db.get_value("Customer", customer, "loyalty_program"):
            frappe.db.set_value(
                "Customer", customer, "loyalty_program", program, update_modified=False
            )
    frappe.db.commit()
    say("loyalty: %d of %d customers enrolled" % (len(members), len(customers)))
    return members


def _pos_profiles(company, abbr, warehouses, walk_in, vat_template):
    profiles = []
    currency = frappe.db.get_value("Company", company, "default_currency") or CURRENCY
    for (profile_name, store), warehouse in zip(OUTLETS, warehouses):
        if not frappe.db.exists("POS Profile", profile_name):
            doc = frappe.get_doc(
                {
                    "doctype": "POS Profile",
                    "name": profile_name,
                    "company": company,
                    "warehouse": warehouse,
                    "currency": currency,
                    "customer": walk_in,
                    "selling_price_list": "Standard Selling",
                    "taxes_and_charges": vat_template,
                    "write_off_account": _account(company, "%Write Off%") or _account(company, "%Expense%", "Expense"),
                    "write_off_cost_center": frappe.db.get_value(
                        "Cost Center", {"company": company, "is_group": 0}, "name"
                    ),
                    "payments": [
                        {"mode_of_payment": mode, "default": 1 if mode == "Cash" else 0}
                        for mode, _ in MODES
                    ],
                    "applicable_for_users": [{"user": "Administrator"}],
                }
            )
            # v15 and v16 refuse a sale paid partly with loyalty points unless
            # this is on; LumenPOS still checks every sale adds up itself.
            if doc.meta.has_field("allow_partial_payment"):
                doc.allow_partial_payment = 1
            doc.insert(ignore_permissions=True)
        profile = frappe.get_doc("POS Profile", profile_name)
        for field, value in (
            ("lumenpos_invoice_mode", "POS Invoice"),
            ("lumenpos_printer_ip", "192.168.1.5%d" % (len(profiles) + 1)),
            ("lumenpos_printer_port", 9100),
        ):
            if profile.meta.has_field(field):
                profile.set(field, value)
        profile.save(ignore_permissions=True)
        profiles.append(profile_name)
    say("POS profiles: %s" % profiles)
    return profiles


def _finish_open_sessions(profiles):
    """Close any shift left open on our tills by an earlier run.

    The generator deliberately leaves today's shift open at the end, so a second
    run would otherwise stop at "already has an open session". Only the demo
    tills are touched.
    """
    from lumenpos.api import register

    for profile in profiles:
        stale = frappe.get_all(
            "POS Register Session",
            filters={"pos_profile": profile, "status": ["in", ("Open", "Closing")]},
            fields=["name", "status"],
        )
        for row in stale:
            try:
                if row.status == "Open":
                    summary = register.get_session_summary(row.name)
                    counted = {
                        line["mode_of_payment"]: flt(line.get("expected_amount"))
                        for line in (summary.get("expected") or [])
                    }
                    register.close_register(row.name, json.dumps(counted))
                    frappe.db.commit()
                register.build_closing_entry(row.name, {})
                frappe.db.commit()
            except Exception as exc:
                say("  ! could not finish %s: %s" % (row.name, str(exc)[:120]))
                frappe.db.rollback()
        if stale:
            say("closed %d leftover shift(s) on %s" % (len(stale), profile))


def _settings(company, profiles):
    doc = frappe.get_single("LumenPOS Settings")
    doc.update(
        {
            "show_out_of_stock": 0,
            "gift_card_expiry_days": 365,
            "restrict_returns_to_window": 1,
            "return_window_days": 14,
            "discount_limit_percent": 15,
            "discount_approval_mode": "Passcode or request",
            "enable_price_checker": 1,
            "enable_xreport": 1,
            "enable_audit_log": 1,
            "enable_quick_keys": 1,
            "enable_till_lock": 1,
            "auto_lock_minutes": 10,
            "allow_store_credit_refund": 1,
            "variance_alert_enabled": 1,
            "variance_alert_threshold": 50,
            "overdue_alert_enabled": 1,
            "overdue_alert_hours": 14,
            "receipt_header": "Lumen Retail",
            "receipt_footer": "Thank you for shopping with us. Returns within 14 days with the receipt.",
            "receipt_show_item_code": 1,
            "receipt_show_unit_price": 1,
            "receipt_show_payments": 1,
            "receipt_show_tax_id": 1,
            "receipt_tax_id": "300000000000003",
            "receipt_show_address": 1,
            "receipt_address": "Olaya Street, Riyadh 12244, Saudi Arabia",
            "receipt_show_terms": 1,
            "receipt_terms": "Goods remain exchangeable for 14 days in original condition.",
        }
    )
    if doc.meta.has_field("return_reasons") and not doc.get("return_reasons"):
        for reason in ("Wrong size", "Changed mind", "Faulty item", "Duplicate purchase"):
            if not frappe.db.exists("POS Return Reason", {"reason": reason}):
                frappe.get_doc(
                    {"doctype": "POS Return Reason", "reason": reason}
                ).insert(ignore_permissions=True)
    if doc.meta.has_field("quick_keys") and not doc.get("quick_keys"):
        for code in ("BEV-001", "SNK-004", "PER-007", "ELE-001", "APP-001", "HOM-001"):
            doc.append("quick_keys", {"item_code": code})
    doc.flags.ignore_permissions = True
    doc.save()
    say("LumenPOS settings: receipt, return window, discount limit, till lock, alerts")


def _promotions(profiles):
    from lumenpos.api import settings as settings_api

    wanted = [
        {
            "title": "10% off Personal Care",
            "promotion_type": "Simple Discount",
            "status": "Active",
            "discount_type": "Percentage",
            "discount_value": 10,
            "items": [{"applies_to": "Item Group", "item_group": "Personal Care"}],
        },
        {
            "title": "Buy 2 Get 1 Free on Snacks",
            "promotion_type": "Buy X Get Y",
            "status": "Active",
            "buy_qty": 2,
            "get_qty": 1,
            "get_discount_type": "Free",
            "items": [{"applies_to": "Item Group", "item_group": "Snacks"}],
        },
        {
            "title": "Spend 300 save 25",
            "promotion_type": "Spend and Save",
            "status": "Active",
            "min_spend": 300,
            "basket_discount_type": "Amount",
            "basket_discount_value": 25,
            "apply_on_all": 1,
            "items": [],
        },
        {
            "title": "Ramadan coupon 20%",
            "promotion_type": "Simple Discount",
            "status": "Active",
            "discount_type": "Percentage",
            "discount_value": 20,
            "requires_coupon": 1,
            "coupon_code": "LUMEN20",
            "apply_on_all": 1,
            "items": [],
        },
    ]
    made = []
    for payload in wanted:
        if frappe.db.exists("POS Promotion", {"title": payload["title"]}):
            made.append(payload["title"])
            continue
        payload = dict(payload)
        payload.update({"start_date": "", "end_date": "", "start_time": "", "end_time": ""})
        settings_api.save_promotion(payload)
        made.append(payload["title"])
    say("promotions: %s" % made)
    return made


def _bundle():
    title = "Movie Night Bundle"
    if frappe.db.exists("POS Bundle", {"title": title}):
        return title
    doc = frappe.get_doc(
        {
            "doctype": "POS Bundle",
            "title": title,
            "status": "Active",
            "bundle_price": 35,
            "items": [
                {"item_code": "SNK-003", "qty": 2},
                {"item_code": "BEV-005", "qty": 2},
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    say("bundle: %s (2 chips + 2 energy drinks for 35)" % title)
    return title


def _price_book(profiles):
    title = "Staff Prices"
    if frappe.db.exists("POS Price Book", {"title": title}):
        return title
    doc = frappe.get_doc(
        {
            "doctype": "POS Price Book",
            "title": title,
            "status": "Active",
            "items": [
                {"item_code": "APP-001", "rate": 45},
                {"item_code": "APP-003", "rate": 99},
            ],
        }
    )
    doc.insert(ignore_permissions=True)
    say("price book: %s" % title)
    return title


# ---------------------------------------------------------------------------
# Trade
# ---------------------------------------------------------------------------
def _basket(codes, walk_in, customers):
    """One realistic basket: a few lines, weighted to cheap fast movers."""
    cheap = [c for c in codes if c[1] < 50 and not c[2]]
    mid = [c for c in codes if 50 <= c[1] < 200 and not c[2]]
    pricey = [c for c in codes if c[1] >= 200 or c[2]]
    lines = []
    for _ in range(rng.choices([1, 2, 3, 4, 5, 6], weights=[18, 26, 22, 16, 10, 8])[0]):
        pool = rng.choices([cheap, mid, pricey], weights=[68, 26, 6])[0]
        code, price, serialised = rng.choice(pool)
        if any(line["item_code"] == code for line in lines):
            continue
        qty = 1 if serialised else rng.choices([1, 2, 3], weights=[70, 22, 8])[0]
        line = {"item_code": code, "qty": qty}
        if rng.random() < 0.05:
            line["manual_discount_percent"] = rng.choice([5, 10])
        lines.append(line)
    if not lines:
        code, price, serialised = rng.choice(cheap)
        lines = [{"item_code": code, "qty": 1}]
    # Most sales are anonymous; a named customer earns loyalty points.
    customer = walk_in if rng.random() < 0.62 else rng.choice(customers)
    return lines, customer


def _tender(total):
    """Split the total across tenders the way a real day looks."""
    pick = rng.choices(
        ["Cash", "Mada", "Credit Card", "split"], weights=[30, 42, 18, 10]
    )[0]
    if pick != "split":
        return [{"mode_of_payment": pick, "amount": total}]
    first = flt(round(total * rng.uniform(0.3, 0.7), 2), 2)
    return [
        {"mode_of_payment": "Cash", "amount": first},
        {"mode_of_payment": "Mada", "amount": flt(total - first, 2)},
    ]


def _sell_day(profile, day, count, codes, walk_in, customers, serial_codes):
    """One shift on one till: open, sell `count` baskets, close, consolidate."""
    from lumenpos.api import register, sales

    frappe.flags.lumenpos_demo_stamp = (day, "08:30:00")
    opened = register.open_register(profile, opening_float=500)
    session = opened.get("name") or opened.get("session")
    frappe.db.commit()

    made, returned, takings = 0, 0, 0.0
    for i in range(count):
        hour = rng.choices(
            [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
            weights=[3, 5, 6, 7, 6, 5, 5, 7, 9, 12, 14, 12, 9],
        )[0]
        frappe.flags.lumenpos_demo_stamp = (
            day,
            "%02d:%02d:%02d" % (hour, rng.randint(0, 59), rng.randint(0, 59)),
        )
        lines, customer = _basket(codes, walk_in, customers)
        for line in lines:
            if line["item_code"] in serial_codes:
                # A serial sold earlier in this shift still reads as Active
                # until the shift is consolidated, so the status filter alone
                # hands the same one out twice and ERPNext refuses the sale.
                # Track what has gone out and skip it.
                candidates = frappe.get_all(
                    "Serial No",
                    filters={
                        "item_code": line["item_code"],
                        "warehouse": _warehouse_of(profile),
                        "status": "Active",
                    },
                    limit=line["qty"] + len(USED_SERIALS) + 5,
                    pluck="name",
                )
                available = [s for s in candidates if s not in USED_SERIALS][: line["qty"]]
                if not available:
                    line["item_code"] = "ELE-004"  # a non-serialised stand-in
                    continue
                line["qty"] = len(available)
                line["serial_nos"] = available
                USED_SERIALS.update(available)
        payload = {
            "pos_profile": profile,
            "customer": customer,
            "items": lines,
            "payments": [],
        }
        if rng.random() < 0.04:
            payload["coupon_codes"] = ["LUMEN20"]
        # quote_sale is the same server computation submit_sale uses, so the
        # tender always matches to the halala. No guessing, no retry.
        try:
            payable = flt(sales.quote_sale(dict(payload))["payable"], 2)
            payload["payments"] = _tender(payable)
            result = sales.submit_sale(dict(payload))
        except Exception as exc:
            frappe.db.rollback()
            _note_failure(exc)
            continue
        name = result.get("invoice") or result.get("name")
        made += 1
        takings += flt(frappe.db.get_value("POS Invoice", name, "grand_total"))
        if made % 25 == 0:
            frappe.db.commit()
        # A few come back.
        if rng.random() < 0.04:
            first = lines[0]
            if "serial_nos" not in first:
                try:
                    sales.create_return(
                        name,
                        {first["item_code"]: 1},
                        rng.choice(["Cash", "Store Credit"]),
                        return_reason=rng.choice(["Wrong size", "Changed mind", "Faulty item"]),
                        pos_profile=profile,
                    )
                    returned += 1
                except Exception:
                    frappe.db.rollback()
    frappe.db.commit()

    frappe.flags.lumenpos_demo_stamp = (day, "22:15:00")
    summary = register.get_session_summary(session)
    counted = {}
    for row in summary.get("expected") or []:
        expected = flt(row.get("expected_amount"))
        # Real tills are a few riyals out now and then.
        drift = rng.choice([0, 0, 0, 0, -5, 5, -10, 2.5]) if row.get("is_cash") else 0
        counted[row["mode_of_payment"]] = flt(expected + drift, 2)
    register.close_register(session, json.dumps(counted))
    frappe.db.commit()
    register.build_closing_entry(session, counted)
    frappe.db.commit()
    frappe.flags.lumenpos_demo_stamp = None
    return made, returned, takings


USED_SERIALS = set()


def _seed_used_serials():
    """Serials already sitting on an unconsolidated sale from an earlier run."""
    rows = frappe.db.sql(
        """select ii.serial_no from `tabPOS Invoice Item` ii
           join `tabPOS Invoice` i on i.name = ii.parent
           where i.docstatus = 1 and ifnull(ii.serial_no, '') <> ''"""
    )
    for (blob,) in rows:
        USED_SERIALS.update(x.strip() for x in str(blob).splitlines() if x.strip())
    if USED_SERIALS:
        say("serials already sold: %d" % len(USED_SERIALS))


_WAREHOUSE_CACHE = {}


def _warehouse_of(profile):
    if profile not in _WAREHOUSE_CACHE:
        _WAREHOUSE_CACHE[profile] = frappe.db.get_value("POS Profile", profile, "warehouse")
    return _WAREHOUSE_CACHE[profile]


def _gift_cards(profile, walk_in):
    from lumenpos.api import sales

    made = []
    for amount in (100, 200, 500):
        try:
            result = sales.sell_gift_card(
                {
                    "pos_profile": profile,
                    "amount": amount,
                    "customer": walk_in,
                    "payments": [{"mode_of_payment": "Cash", "amount": amount}],
                }
            )
            made.append("%s (%s)" % (result.get("gift_card_no"), amount))
            frappe.db.commit()
        except Exception as exc:
            say("  gift card %s skipped: %s" % (amount, str(exc)[:120]))
            frappe.db.rollback()
    say("gift cards sold: %s" % (made or "none"))
    return made


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def run(invoice_target=INVOICE_TARGET, days=DAYS, force=False):
    posted = frappe.db.count("POS Invoice", {"docstatus": 1})
    if posted > RECENT_SALES_GUARD and not force:
        raise RuntimeError(
            "This site already has %d posted POS invoices, so it does not look "
            "like an empty demo site. Nothing was created. Pass force=True if "
            "you really mean to add demo data on top." % posted
        )

    frappe.set_user("Administrator")
    # Run the queued work inline. Consolidation is enqueued when a shift closes,
    # and a demo has to end with its shifts actually consolidated whether or not
    # this site has a worker free.
    frappe.flags.in_test = True
    # The wizard installs hundreds of fixture rows. Run it before the
    # back-dating patch goes on, and with no flags set, so it behaves exactly
    # as it does on a normal install.
    company = _company()
    if not company:
        raise RuntimeError(
            "No company on this site and the setup wizard did not produce one. "
            "Finish ERPNext's setup wizard in the browser first, then run this again."
        )
    abbr = frappe.db.get_value("Company", company, "abbr")

    Document.insert = _dated_insert
    try:
        _fiscal_years(company)
        _price_list(company)
        vat_template = _vat_template(company, abbr)
        warehouses = _warehouses(company, abbr)
        _item_groups()
        codes = _items(company, warehouses[0])
        serial_codes = {code for code, _p, serialised in codes if serialised}
        _modes_of_payment(company, abbr)
        walk_in, customers = _customers()
        program = _loyalty(company, abbr)
        _enrol(customers, program)
        profiles = _pos_profiles(company, abbr, warehouses, walk_in, vat_template)
        _finish_open_sessions(profiles)
        _settings(company, profiles)
        _promotions(profiles)
        _bundle()
        _price_book(profiles)
        frappe.db.commit()

        _stock(company, warehouses, codes, add_days(nowdate(), -(days + 1)))
        _seed_used_serials()
        frappe.db.commit()

        import math

        per_day = max(1, int(math.ceil(invoice_target / float(days * len(profiles)))))
        say("selling: %d day(s) x %d till(s) x about %d sales" % (days, len(profiles), per_day))

        total_made = total_returned = 0
        total_takings = 0.0
        for offset in range(days, 0, -1):
            day = add_days(nowdate(), -offset)
            for profile in profiles:
                made, returned, takings = _sell_day(
                    profile, day, per_day, codes, walk_in, customers, serial_codes
                )
                total_made += made
                total_returned += returned
                total_takings += takings
            say("  %s: running total %d invoices" % (day, total_made))

        # Leave today's shift open on the first till, with a few live sales, so
        # the demo opens onto a working register rather than a closed one.
        from lumenpos.api import register, sales

        opened = register.open_register(profiles[0], opening_float=500)
        frappe.db.commit()
        topups = 0
        while total_made < invoice_target + 6 and topups < invoice_target:
            topups += 1
            lines, customer = _basket(codes, walk_in, customers)
            lines = [line for line in lines if line["item_code"] not in serial_codes] or [
                {"item_code": "BEV-003", "qty": 1}
            ]
            payload = {
                "pos_profile": profiles[0],
                "customer": customer,
                "items": lines,
                "payments": [],
            }
            try:
                payload["payments"] = _tender(flt(sales.quote_sale(dict(payload))["payable"], 2))
                sales.submit_sale(dict(payload))
                total_made += 1
            except Exception as exc:
                frappe.db.rollback()
                _note_failure(exc)
        frappe.db.commit()
        _gift_cards(profiles[0], walk_in)

        if not total_made:
            raise RuntimeError(
                "No sale posted at all. Reasons: %s"
                % json.dumps(FAILURES, ensure_ascii=False, indent=1)
            )
        say("")
        say("DONE")
        if FAILURES:
            say("  baskets refused   : %d (%s)" % (
                sum(FAILURES.values()), "; ".join(sorted(FAILURES)[:3])))
        say("  invoices posted   : %d" % total_made)
        say("  returns           : %d" % total_returned)
        say("  takings           : %s %s" % (
            flt(total_takings, 2),
            frappe.db.get_value("Company", company, "default_currency") or CURRENCY))
        say("  tills             : %s" % ", ".join(profiles))
        say("  today's shift on %s is left OPEN" % profiles[0])
        return {
            "invoices": total_made,
            "returns": total_returned,
            "takings": flt(total_takings, 2),
            "profiles": profiles,
            "log": LOG,
        }
    finally:
        Document.insert = _ORIGINAL_INSERT
        frappe.flags.lumenpos_demo_stamp = None
        frappe.flags.in_test = False


@frappe.whitelist()
def build_demo_data(invoice_target=INVOICE_TARGET, days=DAYS, force=0):
    """Queue the demo build. System Manager only.

    Deliberately a background job: a thousand sales take far longer than a web
    request is allowed to live. Watch it by counting POS Invoices, or read the
    Console Log afterwards.

    Not wired to any button. It exists so a demo or evaluation site can be
    filled with believable trade in one call, and it refuses to run on a site
    that already looks like a real shop.
    """
    frappe.only_for("System Manager")
    invoice_target = int(invoice_target)
    days = int(days)
    force = bool(int(force))
    posted = frappe.db.count("POS Invoice", {"docstatus": 1})
    if posted > RECENT_SALES_GUARD and not force:
        frappe.throw(
            frappe._(
                "This site already has {0} posted POS invoices, so it does not look "
                "like an empty demo site. Nothing was created."
            ).format(posted)
        )
    frappe.enqueue(
        "lumenpos.demo_data.run",
        queue="long",
        timeout=30000,
        job_name="lumenpos_demo_data",
        invoice_target=invoice_target,
        days=days,
        force=force,
    )
    return {
        "queued": True,
        "invoice_target": invoice_target,
        "days": days,
        "watch": "count POS Invoice until it stops rising",
    }
