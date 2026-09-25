# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Exchange in one step: goods come back and other goods go out, and only the
difference touches the drawer.

Two documents post, both ERPNext's own: a credit note for what came back and a
POS sale for what the customer took instead. They settle against each other
through the "Exchange" clearing tender (see lumenpos.exchanges), so:

    new sale dearer   -> the customer pays the difference, any tender
    new sale cheaper  -> the difference is refunded by the normal refund rules
    same value        -> nothing moves in the drawer at all

Both documents are written in ONE request, so a failure anywhere rolls the pair
back: there is no window where a shop has taken goods back without giving the
replacement, or the other way round.

Everything a return normally enforces still applies, because the credit note is
made by the same code path: return restrictions, the return window and its
approval request, serial checks, bundle groups and the refund method rules.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt

from lumenpos import currency, exchanges
from lumenpos.api import permissions, sales


def _require_exchange():
    if not permissions.can_exchange():
        frappe.throw(_("You are not allowed to exchange goods"), frappe.PermissionError)


def _assert_outlet_currency(original, profile, customer=None):
    """An exchange nets two documents through a clearing account in the
    company currency, each at its own rate, so it stays in the outlet's
    currency (lumenpos.currency). A sale in another currency is refunded and
    the new goods rung up as a new sale instead."""
    ctx = currency.sale_context(profile, customer or original.customer, profile.selling_price_list)
    if ctx.foreign or (original.get("currency") and original.currency != ctx.outlet_currency):
        frappe.throw(
            _(
                "Exchanges are in {0} only. For a sale in {1}, refund it and ring the new goods up as a new sale."
            ).format(ctx.outlet_currency, ctx.currency if ctx.foreign else original.currency),
            title=_("Customer currency"),
        )


def _leftover_rows(leftover, refund_mode, refund_payments):
    """How the shop hands back the part the new goods did not cover."""
    if isinstance(refund_payments, str):
        refund_payments = json.loads(refund_payments or "[]")
    rows = [
        {
            "mode_of_payment": (r.get("mode_of_payment") or "").strip(),
            "amount": abs(flt(r.get("amount"))),
            "reference_no": (r.get("reference_no") or "").strip() or None,
        }
        for r in (refund_payments or [])
        if (r.get("mode_of_payment") or "").strip() and abs(flt(r.get("amount"))) > 0
    ]
    if not rows:
        if not refund_mode:
            frappe.throw(
                _("The goods coming back are worth more than the new ones. Choose how to refund {0}.").format(
                    flt(leftover, 2)
                )
            )
        rows = [{"mode_of_payment": refund_mode, "amount": leftover, "reference_no": None}]
    total = flt(sum(r["amount"] for r in rows), 2)
    if abs(total - flt(leftover, 2)) > 0.005:
        frappe.throw(
            _("The refund split adds up to {0} but {1} is left over after the new items.").format(
                total, flt(leftover, 2)
            )
        )
    return rows


def _document_value(doctype, name):
    """What the credit note actually came to, the figure ERPNext validates
    against (rounded_total when rounding is on, else grand_total)."""
    row = frappe.db.get_value(doctype, name, ["rounded_total", "grand_total"], as_dict=True)
    return abs(flt(row.rounded_total or row.grand_total, 2))


@frappe.whitelist()
def quote_exchange(payload):
    """What the customer pays, or gets back, before anything posts.

    Both sides are valued by the code that will actually post them: the credit
    note is built (and thrown away) so the goods coming back are worth exactly
    what ERPNext will credit, and the replacement is quoted the same way the
    payment screen quotes any sale. So the figure on screen is the figure that
    settles, to the cent.
    """
    if isinstance(payload, str):
        payload = json.loads(payload)
    _require_exchange()

    original_name = payload.get("original_invoice")
    if not original_name:
        frappe.throw(_("Which sale is being exchanged?"))
    return_items = payload.get("return_items") or {}
    if isinstance(return_items, str):
        return_items = json.loads(return_items or "{}")
    return_items = {code: flt(qty) for code, qty in return_items.items() if flt(qty) > 0}
    if not return_items:
        return {"returned_value": 0, "new_total": 0, "due": 0, "refund": 0}

    sale_doctype = sales._doctype_of(original_name)
    original = frappe.get_doc(sale_doctype, original_name)
    profile_name = payload.get("pos_profile") or original.get("pos_profile")
    _assert_outlet_currency(original, frappe.get_cached_doc("POS Profile", profile_name), payload.get("customer"))
    return_doc, _session = sales._build_return_doc(
        original, sale_doctype, original_name, return_items, payload.get("serials"),
        profile_name, None,
    )
    returned_value = abs(flt(return_doc.rounded_total or return_doc.grand_total, 2))

    new_total = 0.0
    if payload.get("items"):
        quote_payload = dict(payload)
        for gone in ("return_items", "serials", "refund_payments", "refund_mode",
                     "return_reason", "return_request", "original_invoice", "payments"):
            quote_payload.pop(gone, None)
        quote_payload["pos_profile"] = profile_name
        new_total = flt(sales.quote_sale(quote_payload).get("payable"), 2)

    return {
        "returned_value": returned_value,
        "new_total": new_total,
        "due": flt(max(new_total - returned_value, 0), 2),
        "refund": flt(max(returned_value - new_total, 0), 2),
        "allowed_refund_modes": sales._allowed_refund_modes(original),
    }


@frappe.whitelist()
def submit_exchange(payload):
    """Post an exchange: the credit note and the replacement sale, settled.

    payload = {
        "pos_profile", "original_invoice",
        "return_items": {"ITEM-001": 1}, "serials": {"ITEM-001": ["SN-1"]},
        "return_reason", "return_request", "refund_mode", "refund_payments",
        "items": [...the new sale lines, same shape as submit_sale...],
        "payments": [...tenders for the difference, may be empty...],
        "customer", "sales_person", "coupon_codes", "note", "idempotency_key",
    }
    """
    if isinstance(payload, str):
        payload = json.loads(payload)

    _require_exchange()

    original = payload.get("original_invoice")
    if not original:
        frappe.throw(_("Which sale is being exchanged?"))
    return_items = payload.get("return_items") or {}
    if isinstance(return_items, str):
        return_items = json.loads(return_items or "{}")
    if not return_items:
        frappe.throw(_("Pick at least one item to take back"))
    new_items = payload.get("items") or []
    if not new_items:
        frappe.throw(_("Add at least one item the customer is taking instead"))

    profile = frappe.get_cached_doc("POS Profile", payload["pos_profile"])
    _assert_outlet_currency(
        frappe.get_doc(sales._doctype_of(original), original), profile, payload.get("customer")
    )

    # A retried exchange (lost answer, double tap) must not post twice. The new
    # sale carries the key, so finding it means the whole pair already posted.
    key = (payload.get("idempotency_key") or "").strip()
    if key:
        existing = sales._find_by_idempotency_key(key)
        if existing:
            return _result(existing)

    # The replacement sale, built once and used twice: quoted first so the
    # credit note can be split to the cent, then posted with the tenders.
    sale_payload = dict(payload)
    for gone in ("return_items", "serials", "refund_payments", "refund_mode",
                 "return_reason", "return_request", "original_invoice", "payments"):
        sale_payload.pop(gone, None)
    sale_payload["is_exchange"] = 1

    # 1. What will the replacement cost? Quoted with the same code that posts
    #    it, so the split below matches the sale to the cent.
    new_total = flt(sales.quote_sale(dict(sale_payload)).get("payable"), 2)

    exchanges.ensure_setup(profile.company)

    # 2. The credit note. Its value is only known once ERPNext has built it, so
    #    the split is decided there: everything the new sale can absorb goes to
    #    the clearing tender, the rest is a real refund.
    settled = {"amount": 0.0}

    def split(refund_value):
        to_clearing = min(flt(refund_value, 2), new_total)
        settled["amount"] = to_clearing
        rows = []
        if to_clearing > 0:
            rows.append(
                {"mode_of_payment": exchanges.MODE_OF_PAYMENT, "amount": to_clearing, "reference_no": None}
            )
        leftover = flt(flt(refund_value, 2) - to_clearing, 2)
        if leftover > 0:
            rows.extend(
                _leftover_rows(leftover, payload.get("refund_mode"), payload.get("refund_payments"))
            )
        return rows

    return_receipt = sales.create_return(
        invoice=original,
        items=return_items,
        refund_mode=payload.get("refund_mode") or exchanges.MODE_OF_PAYMENT,
        serials=payload.get("serials"),
        return_reason=payload.get("return_reason"),
        return_request=payload.get("return_request"),
        pos_profile=profile.name,
        _split_fn=split,
    )
    returned_value = _document_value(return_receipt["doctype"], return_receipt["name"])
    covered = flt(settled["amount"], 2)

    # 3. The replacement sale, paid by the clearing tender for the covered part
    #    plus whatever the cashier collected for the difference.
    collected = [p for p in (payload.get("payments") or []) if flt(p.get("amount"))]
    due = flt(new_total - covered, 2)
    paid = flt(sum(flt(p.get("amount")) for p in collected), 2)
    if abs(paid - due) > 0.005:
        frappe.throw(
            _("The new items come to {0}, {1} is covered by the return, so {2} is due but {3} was entered.").format(
                new_total, covered, due, paid
            )
        )

    sale_payload["payments"] = (
        [{"mode_of_payment": exchanges.MODE_OF_PAYMENT, "amount": covered}] if covered > 0 else []
    ) + collected
    sale_receipt = sales.submit_sale(sale_payload)
    _stamp_original(sale_receipt, original)

    return {
        "return": return_receipt,
        "sale": sale_receipt,
        "returned_value": returned_value,
        "new_total": new_total,
        "covered": covered,
        "difference": flt(new_total - returned_value, 2),
    }


def _stamp_original(sale_receipt, original):
    """Record WHICH sale this replaced, when the site has the field for it
    (exchange_against_invoice is a site field on POS Invoice, LumenPOS does not
    create it). The credit note already links the original the ERPNext way."""
    doctype, name = sale_receipt["doctype"], sale_receipt["name"]
    for field in ("exchange_against_invoice", "lumenpos_exchange_against"):
        try:
            if frappe.db.has_column(doctype, field):
                frappe.db.set_value(doctype, name, field, original, update_modified=False)
                return
        except Exception:
            continue


def _result(sale_name):
    """The answer for an exchange that already posted (a retried request). The
    sale is what the cashier needs back, the credit note is already filed
    against the original."""
    receipt = sales.get_receipt(sale_name)
    return {
        "return": None,
        "sale": receipt,
        "returned_value": None,
        "new_total": flt(receipt.get("grand_total"), 2),
        "covered": None,
        "difference": None,
        "repeat": True,
    }
