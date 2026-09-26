# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import frappe
from frappe.utils import flt

from lumenpos.store_credit import get_balance


def _cashback_balance(customer, company=None):
    from lumenpos import cashback

    return cashback.get_balance(customer, company=company)


@frappe.whitelist()
def get_wallet(customer, company):
    """Loyalty points + store credit balance for the cart sidebar and the
    payment screen."""
    wallet = {
        "customer": customer,
        "loyalty_program": None,
        "loyalty_points": 0,
        "conversion_factor": 0,
        # What this company's outlets accept (lumenpos.inter_company).
        "store_credit": get_balance(customer, company),
        "cashback": _cashback_balance(customer, company),
    }
    try:
        from lumenpos.erpnext_compat import loyalty_details

        details = loyalty_details(customer, company)
        # ERPNext redeems a program's points only in the program's company
        # (validate_loyalty_points): elsewhere the till shows none to spend.
        if details and details.get("loyalty_program") and frappe.db.get_value(
            "Loyalty Program", details.loyalty_program, "company"
        ) not in (None, "", company):
            details = None
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
