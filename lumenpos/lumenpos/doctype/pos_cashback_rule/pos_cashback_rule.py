# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
from frappe.model.document import Document


class POSCashbackRule(Document):
    def on_update(self):
        # A rule saved outside LumenPOS's own screen lands with a daily window
        # nobody set. See promotions.loader.clear_accidental_window.
        from lumenpos.promotions.loader import clear_accidental_window

        clear_accidental_window(self)
