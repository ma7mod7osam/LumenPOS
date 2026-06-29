import frappe
from frappe import _
from frappe.model.document import Document


class POSPriceBook(Document):
    def validate(self):
        if self.valid_from and self.valid_to and self.valid_from > self.valid_to:
            frappe.throw(_("Valid To cannot be before Valid From"))
