import frappe
from frappe.utils import flt

from lumenpos.store_credit import get_balance


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
    }
    try:
        from erpnext.accounts.doctype.loyalty_program.loyalty_program import (
            get_loyalty_program_details_with_points,
        )

        details = get_loyalty_program_details_with_points(
            customer, company=company, silent=True, include_expired_entry=False
        )
        if details and details.get("loyalty_program"):
            wallet.update(
                {
                    "loyalty_program": details.loyalty_program,
                    "loyalty_points": int(details.loyalty_points or 0),
                    "conversion_factor": flt(details.conversion_factor),
                }
            )
    except Exception:
        # No loyalty program configured for this customer — wallet still
        # carries the store credit balance.
        pass
    return wallet
