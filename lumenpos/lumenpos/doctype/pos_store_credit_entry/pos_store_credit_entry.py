import frappe
from frappe import _
from frappe.model.document import Document


class POSStoreCreditEntry(Document):
    def validate(self):
        if not self.amount or self.amount <= 0:
            frappe.throw(_("Amount must be positive; use Entry Type to add or subtract"))
