import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class POSBundle(Document):
    def validate(self):
        if not self.bundle_price or self.bundle_price <= 0:
            frappe.throw(_("Bundle Price must be greater than zero"))
        if not self.items:
            frappe.throw(_("Add the items that make up the bundle"))
        for row in self.items:
            if (row.qty or 0) < 1:
                frappe.throw(_("Row {0}: Qty must be at least 1").format(row.idx))
            if frappe.get_cached_value("Item", row.item_code, "has_serial_no"):
                frappe.throw(
                    _("Row {0}: {1} is serialized — serialized items cannot be sold in bundles").format(
                        row.idx, row.item_code
                    )
                )
        self.validate_allocations()

    def validate_allocations(self):
        """Allocated prices are all-or-nothing and must sum EXACTLY to the
        bundle price — otherwise a customer would pay something different
        from the advertised bundle."""
        allocated = [row for row in self.items if row.get("allocated_amount")]
        if not allocated:
            return
        if len(allocated) != len(self.items):
            frappe.throw(
                _("Either give every component an Allocated Price or leave them all empty")
            )
        total = sum(flt(row.allocated_amount) for row in self.items)
        if abs(total - flt(self.bundle_price)) > 0.01:
            frappe.throw(
                _("Allocated prices add up to {0}, but the Bundle Price is {1} — they must match exactly").format(
                    flt(total, 2), flt(self.bundle_price, 2)
                )
            )
