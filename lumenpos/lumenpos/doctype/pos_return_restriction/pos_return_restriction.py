# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import frappe
from frappe import _
from frappe.model.document import Document


class POSReturnRestriction(Document):
    def validate(self):
        target = {
            "Item": self.item_code,
            "Item Group": self.item_group,
            "Brand": self.brand,
            "Tag": self.tag,
        }.get(self.applies_to or "Item Group")
        if not target:
            frappe.throw(_("Choose the {0} this rule applies to").format(_(self.applies_to or "Item Group")))
