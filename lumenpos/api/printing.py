"""ESC/POS receipt printing for network thermal printers (RAW TCP port 9100).

No third-party dependencies: the byte stream is built by hand. Works with the
vast majority of Epson-compatible thermal printers. The printer is configured
per POS Profile via the custom fields `lumenpos_printer_ip` / `lumenpos_printer_port`
(created by lumenpos.install). If no printer is configured the client falls back
to browser printing.

Note: the *bench server* opens the socket, so the printer must be reachable
from where Frappe runs. On cloud-hosted sites use the browser-print fallback.
"""

import socket

import frappe
from frappe import _
from frappe.utils import flt

from lumenpos.api.sales import get_receipt

ESC = b"\x1b"
GS = b"\x1d"

INIT = ESC + b"@"
ALIGN_LEFT = ESC + b"a\x00"
ALIGN_CENTER = ESC + b"a\x01"
BOLD_ON = ESC + b"E\x01"
BOLD_OFF = ESC + b"E\x00"
DOUBLE_SIZE = GS + b"!\x11"
NORMAL_SIZE = GS + b"!\x00"
FEED_CUT = b"\n\n\n\n" + GS + b"V\x42\x00"
KICK_DRAWER = ESC + b"p\x00\x19\xfa"

WIDTH = 42  # characters per line on a typical 80mm printer


@frappe.whitelist()
def print_receipt(invoice, open_drawer=0):
    receipt = get_receipt(invoice)
    profile = frappe.db.get_value("POS Invoice", invoice, "pos_profile")
    ip = frappe.db.get_value("POS Profile", profile, "lumenpos_printer_ip")
    port = frappe.db.get_value("POS Profile", profile, "lumenpos_printer_port") or 9100
    if not ip:
        frappe.throw(_("No receipt printer configured on POS Profile {0}").format(profile))

    data = build_receipt_bytes(receipt, open_drawer=int(open_drawer))
    _send(ip, int(port), data)
    return {"printed": True}


def _send(ip, port, data):
    try:
        with socket.create_connection((ip, port), timeout=5) as sock:
            sock.sendall(data)
    except OSError as e:
        frappe.throw(_("Could not reach printer at {0}:{1} ({2})").format(ip, port, str(e)))


def build_receipt_bytes(receipt, open_drawer=0):
    out = bytearray(INIT)
    if open_drawer:
        out += KICK_DRAWER

    out += ALIGN_CENTER + BOLD_ON + DOUBLE_SIZE
    out += _text(receipt["company"]) + b"\n"
    out += NORMAL_SIZE + BOLD_OFF
    out += _text(receipt["name"]) + b"\n"
    out += _text(f"{receipt['posting_date']} {str(receipt['posting_time']).split('.')[0]}") + b"\n"
    out += _text(receipt["customer_name"] or "") + b"\n"
    out += ALIGN_LEFT + _line() + b"\n"

    for item in receipt["items"]:
        out += _text(item["item_name"][:WIDTH]) + b"\n"
        qty_part = f"  {_num(item['qty'])} x {_num(item['rate'])}"
        out += _text(_pad(qty_part, _num(item["amount"]))) + b"\n"

    out += _line() + b"\n"
    if receipt.get("discount_amount"):
        out += _text(_pad("Discount", "-" + _num(receipt["discount_amount"]))) + b"\n"
    for tax in receipt.get("taxes", []):
        out += _text(_pad(tax["description"][: WIDTH - 12], _num(tax["tax_amount"]))) + b"\n"

    out += BOLD_ON
    total = receipt.get("rounded_total") or receipt["grand_total"]
    out += _text(_pad("TOTAL", f"{receipt['currency']} {_num(total)}")) + b"\n"
    out += BOLD_OFF

    for payment in receipt.get("payments", []):
        out += _text(_pad(payment["mode_of_payment"], _num(payment["amount"]))) + b"\n"
    if receipt.get("loyalty_amount"):
        out += _text(_pad("Loyalty points", _num(receipt["loyalty_amount"]))) + b"\n"
    if receipt.get("change_amount"):
        out += _text(_pad("Change", _num(receipt["change_amount"]))) + b"\n"

    promos = receipt.get("applied_promotions") or []
    if promos:
        out += _line() + b"\n"
        for promo in promos:
            out += _text(f"* {promo['title']} (saved {_num(promo['savings'])})") + b"\n"
    if receipt.get("loyalty_points_earned"):
        out += _text(f"Points earned: {receipt['loyalty_points_earned']}") + b"\n"

    out += ALIGN_CENTER + b"\n" + _text("Thank you!") + b"\n"
    out += FEED_CUT
    return bytes(out)


def _text(value):
    # Thermal printers default to single-byte codepages; replace anything
    # exotic rather than printing garbage.
    return str(value).encode("ascii", errors="replace")


def _line():
    return b"-" * WIDTH


def _pad(left, right):
    right = str(right)
    space = max(1, WIDTH - len(left) - len(right))
    return f"{left}{' ' * space}{right}"


def _num(value):
    return f"{flt(value):,.2f}"
