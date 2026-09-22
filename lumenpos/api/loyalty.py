# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import frappe
from frappe.utils import flt

from lumenpos.store_credit import get_balance


def _cashback_balance(customer):
    from lumenpos import cashback

    return cashback.get_balance(customer)


@frappe.whitelist()
def get_wallet(customer, company):
    """Loyalty points + store credit balance for the cart sidebar and the
    payment screen."""
    wallet = {
        "customer": customer,
        "loyalty_program": None,
        "loyalty_points": 0,
        "conversion_factor": 0,
        "store_credit": get_balance(customer),
        "cashback": _cashback_balance(customer),
    }
    try:
        from lumenpos.erpnext_compat import loyalty_details

        details = loyalty_details(customer, company)
        if details and details.get("loyalty_program"):
            wallet.update(
                {
                    "loyalty_program": details.loyalty_program,
                    "loyalty_points": int(details.loyalty_points or 0),
                    "conversion_factor": flt(details.conversion_factor),
                }
            )
    except Exception:
        # No loyalty program configured for this customer, wallet still
        # carries the store credit balance.
        pass
    return wallet
