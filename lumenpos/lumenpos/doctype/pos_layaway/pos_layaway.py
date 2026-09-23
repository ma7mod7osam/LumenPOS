# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Goods held for a customer who is paying for them over time.

The money lives on real POS sales (see lumenpos/deposits.py), this document is
the shop's record of WHAT is held, for WHOM, and how much is still owed. The
totals are derived, never typed: they are recomputed from the lines and the
instalments on every save, so a hold can never disagree with the invoices
behind it.
"""

from frappe.model.document import Document
from frappe.utils import flt


class POSLayaway(Document):
    def validate(self):
        # The total is what the customer will PAY, tax and all. On an outlet
        # that adds VAT at the till the held prices are net of it, so the tax
        # worked out on the day of the hold rides along here: a hold quoted at
        # the net would leave someone who paid "in full" short by the tax on
        # the day they collect, and the hand-over invoice would not settle.
        self.total = flt(
            sum(flt(row.amount) for row in (self.items or [])) + flt(self.tax_amount), 2
        )
        self.paid = flt(
            sum(flt(row.amount) for row in (self.payments or []) if not row.refunded), 2
        )
        # A balance only means anything while the hold is open: once the goods
        # are handed over the rest was collected on that sale, and a cancelled
        # hold has been refunded.
        self.balance = flt(self.total - self.paid, 2) if self.status == "Open" else 0
        if self.customer and not self.customer_name:
            self.customer_name = self.get("customer_name") or self.customer
