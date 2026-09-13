# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import frappe
from frappe.tests.utils import FrappeTestCase


class TestPOSPromotion(FrappeTestCase):
    def test_simple_discount_requires_value(self):
        promo = frappe.get_doc(
            {
                "doctype": "POS Promotion",
                "title": "Broken promo",
                "promotion_type": "Simple Discount",
                "apply_on_all": 1,
                "discount_type": "Percentage",
                "discount_value": 0,
            }
        )
        self.assertRaises(frappe.ValidationError, promo.insert)

    def test_valid_promo_inserts(self):
        promo = frappe.get_doc(
            {
                "doctype": "POS Promotion",
                "title": "10% storewide",
                "promotion_type": "Simple Discount",
                "apply_on_all": 1,
                "discount_type": "Percentage",
                "discount_value": 10,
            }
        ).insert()
        self.assertTrue(promo.name.startswith("PROMO-"))
        promo.delete()
