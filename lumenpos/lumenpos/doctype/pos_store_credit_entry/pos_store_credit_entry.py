# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import frappe
from frappe import _
from frappe.model.document import Document


class POSStoreCreditEntry(Document):
    def validate(self):
        if not self.amount or self.amount <= 0:
            frappe.throw(_("Amount must be positive, use Entry Type to add or subtract"))
