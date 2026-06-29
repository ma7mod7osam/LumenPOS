import frappe
from frappe import _
from frappe.model.document import Document


class POSPromotion(Document):
    def validate(self):
        self.validate_dates()
        self.validate_offer()
        self.validate_items()
        self.validate_coupon()

    def validate_coupon(self):
        if not self.requires_coupon:
            self.coupon_code = None
            return
        if not self.coupon_code or not self.coupon_code.strip():
            frappe.throw(_("Set a Coupon Code or untick 'Requires Coupon Code'"))
        self.coupon_code = self.coupon_code.strip().upper()
        clash = frappe.db.get_value(
            "POS Promotion",
            {"coupon_code": self.coupon_code, "name": ["!=", self.name], "status": "Active"},
            "name",
        )
        if clash and self.status == "Active":
            frappe.throw(_("Coupon code {0} is already used by {1}").format(self.coupon_code, clash))

    def validate_dates(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            frappe.throw(_("End Date cannot be before Start Date"))
        if bool(self.start_time) != bool(self.end_time):
            frappe.throw(_("Set both Start Time and End Time, or neither"))

    def validate_offer(self):
        if self.promotion_type == "Simple Discount":
            if not self.discount_type:
                frappe.throw(_("Discount Type is required for a Simple Discount"))
            if not self.discount_value or self.discount_value <= 0:
                frappe.throw(_("Discount Value must be greater than zero"))
            if self.discount_type == "Percentage" and self.discount_value > 100:
                frappe.throw(_("Percentage discount cannot exceed 100"))

        elif self.promotion_type == "Buy X Get Y":
            if not self.buy_qty or self.buy_qty < 1:
                frappe.throw(_("Buy Quantity must be at least 1"))
            if not self.get_qty or self.get_qty < 1:
                frappe.throw(_("Get Quantity must be at least 1"))
            if self.get_discount_type != "Free" and (
                not self.get_discount_value or self.get_discount_value <= 0
            ):
                frappe.throw(_("Reward Value must be greater than zero"))

        elif self.promotion_type == "Spend and Save":
            if not self.min_spend or self.min_spend <= 0:
                frappe.throw(_("Minimum Spend must be greater than zero"))
            if not self.basket_discount_value or self.basket_discount_value <= 0:
                frappe.throw(_("Basket Discount Value must be greater than zero"))
            if (
                self.basket_discount_type == "Percentage"
                and self.basket_discount_value > 100
            ):
                frappe.throw(_("Percentage discount cannot exceed 100"))

        elif self.promotion_type == "Bundle Price":
            if not self.bundle_price or self.bundle_price <= 0:
                frappe.throw(_("Bundle Price must be greater than zero"))
            if self.apply_on_all:
                frappe.throw(_("A bundle needs specific product rows, not 'all products'"))
            if not self.items:
                frappe.throw(_("List the products that make up the bundle"))
            for row in self.items:
                if (row.qty or 1) < 1:
                    frappe.throw(_("Row {0}: bundle Qty must be at least 1").format(row.idx))

    def validate_items(self):
        if self.promotion_type == "Spend and Save":
            return  # empty product list means the whole basket counts
        include_rows = [row for row in (self.items or []) if not row.get("exclude")]
        if not self.apply_on_all and not include_rows and not self.items:
            frappe.throw(
                _("Add at least one product row or tick 'Apply on all products'")
            )
        for row in self.items or []:
            target = {
                "Item": row.item_code,
                "Item Group": row.item_group,
                "Brand": row.brand,
            }.get(row.applies_to)
            if not target:
                frappe.throw(
                    _("Row {0}: set the {1} field").format(row.idx, _(row.applies_to))
                )

    def on_change(self):
        # POS clients cache promotions; bump the cache so they refetch.
        frappe.cache().delete_value("lumenpos_promotions_version")
