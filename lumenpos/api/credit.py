# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""A customer's account at the till (0.60.0, lumenpos.credit_sales): what they
owe sale by sale, a payment of it taken into the drawer, and the manager's
switch and limit on the customer's card.

The owner, 2026-10-03, asked whether a customer paying several sales at once
could: one payment, spread over the oldest first or over the sales the cashier
ticks, one receipt. The payment is ERPNext's own receipt voucher, a Cash Entry
(or a Bank Entry for a card or a transfer), its lines allocated to each sale's
entry, posted at once to the drawer's account; the shift that took it expects
it in that drawer at the close (register._customer_payments).

Why not a Payment Entry: ERPNext builds one AS the cashier and checks, as them,
read on Payment Entry and on every document it pays (get_account_details,
get_reference_details, v13 to v16). Read on Journal Entry would open the whole
of a company's books to every cashier, so LumenPOS records the receipt the
other way ERPNext has, which checks neither.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate

from lumenpos import credit_sales
from lumenpos.api import permissions


def _company_allowed(company):
    companies = permissions.allowed_companies()
    if companies is not None and company not in companies:
        frappe.throw(_("You do not have access to {0}.").format(company), frappe.PermissionError)


@frappe.whitelist()
def customer_credit(customer: str, company: str):
    """The customer's account at this company: may they buy on account, the
    limit, what they owe and each debt still open, oldest first."""
    if not frappe.has_permission("Customer", "read"):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    _company_allowed(company)
    out = credit_sales.facts(customer, company)
    out["items"] = credit_sales.open_items(customer, company) if out["enabled"] else []
    return out


def _internal_modes():
    from lumenpos import cashback, exchanges, gift_cards, store_credit

    return {
        credit_sales.MODE_OF_PAYMENT,
        exchanges.MODE_OF_PAYMENT,
        store_credit.MODE_OF_PAYMENT,
        cashback.MODE_OF_PAYMENT,
        gift_cards.mode_of_payment(),
    }


def _mode_account(mode, company):
    return frappe.db.get_value("Mode of Payment Account", {"parent": mode, "company": company}, "default_account")


def _allocate(items, amount, chosen):
    """Spread `amount` over the open debts, oldest first, or over the chosen ones
    only. All on one receivable account (a Payment Entry has one)."""
    pick = [item for item in items if not chosen or (item["doctype"], item["name"]) in chosen]
    if not pick:
        frappe.throw(_("Nothing is owed on the sales chosen."), title=_("Take a payment"))
    account = pick[0]["account"]
    pick = [item for item in pick if item["account"] == account]
    open_total = flt(sum(item["outstanding"] for item in pick), 2)
    if amount > open_total + credit_sales.EPSILON:
        frappe.throw(
            _("The customer owes {0} on the sales chosen: take at most that.").format(open_total),
            title=_("Take a payment"),
        )
    left = amount
    rows = []
    for item in pick:
        take = flt(min(item["outstanding"], left), 2)
        if take <= 0:
            break
        rows.append((item, take))
        left = flt(left - take, 2)
    return account, rows


@frappe.whitelist()
def receive_payment(
    customer: str,
    pos_profile: str,
    amount: float | str,
    mode_of_payment: str,
    items: list | str | None = None,
    reference_no: str | None = None,
    idempotency_key: str | None = None,
):
    """Take a payment of what the customer owes into this till's drawer: one
    Cash Entry (a Bank Entry for a card or a transfer), allocated oldest
    first, or to `items` ([{doctype, name}])."""
    if not permissions.can_take_customer_payments():
        frappe.throw(_("You are not allowed to take customer payments."), frappe.PermissionError)
    permissions.assert_outlet(pos_profile)
    key = (idempotency_key or "").strip()
    if key:
        posted = frappe.db.get_value("Journal Entry", {"lumenpos_idempotency_key": key, "docstatus": 1}, "name")
        if posted:
            return payment_receipt(posted)
    profile = frappe.get_cached_doc("POS Profile", pos_profile)
    company = profile.company
    amount = flt(amount, 2)
    if amount <= 0:
        frappe.throw(_("Enter the amount the customer pays."), title=_("Take a payment"))

    from lumenpos.api.session import get_open_session

    session = get_open_session(pos_profile)
    if not session:
        frappe.throw(_("Open the register first: the payment goes into its drawer."), title=_("Take a payment"))
    outlet_modes = {row.mode_of_payment for row in profile.payments or []}
    if mode_of_payment not in outlet_modes or mode_of_payment in _internal_modes():
        frappe.throw(_("{0} is not a payment method of this outlet.").format(mode_of_payment), title=_("Take a payment"))
    paid_to = _mode_account(mode_of_payment, company)
    company_currency = frappe.get_cached_value("Company", company, "default_currency")
    if not paid_to or frappe.get_cached_value("Account", paid_to, "account_currency") != company_currency:
        frappe.throw(
            _("A payment of what is owed is taken in {0}, with a payment method on a {0} account.").format(
                company_currency
            ),
            title=_("Take a payment"),
        )

    if isinstance(items, str):
        items = json.loads(items or "[]")
    chosen = {(row.get("doctype"), row.get("name")) for row in (items or []) if row.get("name")}
    account, rows = _allocate(credit_sales.open_items(customer, company), amount, chosen)

    cost_center = profile.get("cost_center") or frappe.get_cached_value("Company", company, "cost_center")
    dims = credit_sales._dimensions(profile)
    reference = (reference_no or "").strip() or session["name"]
    bank = frappe.get_cached_value("Account", paid_to, "account_type") == "Bank"
    lines = [
        {
            "account": paid_to,
            "debit_in_account_currency": amount,
            "credit_in_account_currency": 0,
            "cost_center": cost_center,
            **dims,
        }
    ]
    for item, take in rows:
        lines.append(
            {
                "account": account,
                "party_type": "Customer",
                "party": customer,
                "debit_in_account_currency": 0,
                "credit_in_account_currency": take,
                "reference_type": item["doctype"],
                "reference_name": item["name"],
                "cost_center": cost_center,
                **dims,
            }
        )
    je = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            # ERPNext's own receipt vouchers; a Bank Entry asks for a reference.
            "voucher_type": "Bank Entry" if bank else "Cash Entry",
            "company": company,
            "posting_date": nowdate(),
            "mode_of_payment": mode_of_payment,
            "cheque_no": reference,
            "cheque_date": nowdate(),
            "user_remark": _("{0} paid {1} by {2} at {3}, shift {4}").format(
                frappe.db.get_value("Customer", customer, "customer_name") or customer,
                amount,
                mode_of_payment,
                pos_profile,
                session["name"],
            ),
            "accounts": lines,
            "lumenpos_credit_kind": "Payment",
            "lumenpos_credit_customer": customer,
            "lumenpos_session": session["name"],
            "lumenpos_idempotency_key": key or None,
        }
    )
    credit_sales.post(je)

    from lumenpos.api import audit

    audit.log(
        audit.CUSTOMER_PAYMENT,
        detail=_("{0} paid {1} by {2}").format(customer, amount, mode_of_payment),
        amount=amount,
        reference_doctype="Journal Entry",
        reference_name=je.name,
        pos_profile=pos_profile,
    )
    return payment_receipt(je.name)


@frappe.whitelist()
def payment_receipt(payment: str):
    """A customer's payment as the till prints it: what was paid, against which
    sales, and what is still owed."""
    je = frappe.get_doc("Journal Entry", payment)
    if je.get("lumenpos_credit_kind") != "Payment":
        frappe.throw(_("{0} is not a payment taken at the till.").format(payment))
    if not (permissions.can_take_customer_payments() or frappe.has_permission("Journal Entry", "read", je)):
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    allocations = []
    paid_to = None
    for row in je.accounts or []:
        if row.get("party_type") != "Customer":
            paid_to = paid_to or row.account
            continue
        invoice = row.reference_name
        if row.reference_type == "Journal Entry":
            invoice = frappe.db.get_value("Journal Entry", row.reference_name, "lumenpos_credit_invoice") or invoice
        allocations.append(
            {
                "doctype": row.reference_type,
                "name": row.reference_name,
                "invoice": invoice,
                "allocated": flt(row.credit_in_account_currency, 2),
            }
        )
    customer = je.get("lumenpos_credit_customer")
    return {
        "name": je.name,
        "doctype": "Journal Entry",
        "customer": customer,
        "customer_name": frappe.db.get_value("Customer", customer, "customer_name") or customer,
        "company": je.company,
        "currency": frappe.get_cached_value("Company", je.company, "default_currency"),
        "posting_date": str(je.posting_date),
        "mode_of_payment": je.get("mode_of_payment"),
        "amount": flt(sum(row["allocated"] for row in allocations), 2),
        "reference_no": je.get("cheque_no"),
        "allocations": allocations,
        "owed_after": credit_sales.owed(customer, je.company),
        "pos_profile": frappe.db.get_value("POS Register Session", je.get("lumenpos_session"), "pos_profile")
        if je.get("lumenpos_session")
        else None,
    }


@frappe.whitelist()
def set_customer_credit(customer: str, company: str, allow: int | str | None = None, limit: float | str | None = None):
    """A manager allows a customer on account and sets their credit limit at
    this company (ERPNext's own, on the customer's card). 0 removes the
    customer's own limit, so their group's, the company's or LumenPOS's
    default applies. ERPNext refuses a limit below what is already owed."""
    if not permissions.can_set_customer_credit():
        frappe.throw(_("You are not allowed to set a customer's credit."), frappe.PermissionError)
    _company_allowed(company)
    doc = frappe.get_doc("Customer", customer)
    if allow not in (None, ""):
        doc.lumenpos_allow_credit = 1 if cint(allow) else 0
    if limit not in (None, ""):
        limit = flt(limit, 2)
        if limit < 0:
            frappe.throw(_("A credit limit cannot be negative."))
        rows = [row for row in doc.get("credit_limits") or [] if row.company == company]
        if limit > 0 and rows:
            rows[0].credit_limit = limit
        elif limit > 0:
            doc.append("credit_limits", {"company": company, "credit_limit": limit})
        else:
            doc.set("credit_limits", [row for row in doc.get("credit_limits") or [] if row.company != company])
    doc.flags.ignore_permissions = True
    doc.save()

    from lumenpos.api import audit

    audit.log(
        audit.CUSTOMER_CREDIT,
        detail=_("{0}: on account {1}, limit {2}").format(
            customer, _("allowed") if cint(doc.get("lumenpos_allow_credit")) else _("not allowed"), limit if limit not in (None, "") else "-"
        ),
        reference_doctype="Customer",
        reference_name=customer,
    )
    return customer_credit(customer, company)
