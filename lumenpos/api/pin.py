"""Personal till-unlock PIN — one per user.

Replaces the SHARED unlock passcode on the lock screen. A shared code is a
shared identity: once it circulates, "who unlocked this till?" has no answer and
rotating it means telling everyone. Each cashier now sets their own PIN, and
unlocking verifies THEIR OWN — with no manager bypass, because the lock screen
protects an unattended till rather than authorising anything.

(The *approvals* passcode in LumenPOS Settings is a different mechanism for
authorising over-limit discounts and stays exactly as it was.)

Storage: PBKDF2-HMAC-SHA256, 60k iterations, per-PIN random salt, stored as
"salt$digest" and compared with secrets.compare_digest. The PIN itself is never
stored or logged.
"""

import hashlib
import secrets

import frappe
from frappe import _
from frappe.utils import add_to_date, cint, now_datetime

DOCTYPE = "LumenPOS User PIN"
ITERATIONS = 60_000
RESET_CODE_TTL_MINUTES = 15


def _hash(pin, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(pin).encode(), salt.encode(), ITERATIONS).hex()
    return f"{salt}${digest}"


def _verify(pin, stored):
    if not stored or "$" not in str(stored):
        return False
    salt, _digest = str(stored).split("$", 1)
    return secrets.compare_digest(_hash(pin, salt), str(stored))


def _validate_pin(pin):
    pin = (str(pin or "")).strip()
    if not pin.isdigit() or not (4 <= len(pin) <= 8):
        frappe.throw(_("A PIN must be 4 to 8 digits."))
    return pin


def _row(user=None, create=False):
    user = user or frappe.session.user
    name = frappe.db.exists(DOCTYPE, {"user": user})
    if name:
        return frappe.get_doc(DOCTYPE, name)
    if not create:
        return None
    doc = frappe.new_doc(DOCTYPE)
    doc.user = user
    return doc


def _throttle(key, limit, seconds):
    cache_key = f"lumenpos_pin:{key}:{frappe.session.user}"
    attempts = cint(frappe.cache().get_value(cache_key) or 0)
    if attempts >= limit:
        frappe.throw(_("Too many attempts — wait a moment and try again."))
    frappe.cache().set_value(cache_key, attempts + 1, expires_in_sec=seconds)


@frappe.whitelist()
def pin_is_set():
    """Does the current user have a PIN? Fails OPEN (returns True) if the table
    isn't migrated yet, so a half-deployed site can't lock everyone out."""
    try:
        return bool(_row())
    except Exception:
        return True


@frappe.whitelist()
def set_pin(pin, current_pin=None):
    """Set or change the caller's own PIN. Changing an existing one requires the
    current PIN, so an unattended unlocked session can't silently re-key it."""
    pin = _validate_pin(pin)
    doc = _row(create=True)
    if doc.get("pin_hash"):
        if not current_pin:
            frappe.throw(_("Enter your current PIN to change it."))
        _throttle("change", 8, 60)
        if not _verify(current_pin, doc.pin_hash):
            frappe.throw(_("That current PIN is not right."))
    doc.pin_hash = _hash(pin)
    doc.reset_code_hash = None
    doc.reset_expires = None
    doc.flags.ignore_permissions = True
    doc.save()
    return {"ok": True}


def check_own_pin(pin):
    """'ok' | 'wrong' | 'no_pin' — used by session.unlock_till."""
    doc = _row()
    if not doc or not doc.get("pin_hash"):
        return "no_pin"
    return "ok" if _verify(pin, doc.pin_hash) else "wrong"


@frappe.whitelist()
def request_pin_reset():
    """Email the caller a 6-digit reset code (valid 15 minutes).

    Sent with now=True on purpose: on a site with no outgoing email configured
    this fails LOUDLY here, instead of silently queueing a code that never
    arrives and leaving the cashier locked out with no explanation."""
    _throttle("reset_request", 3, 600)
    user = frappe.session.user
    email = frappe.db.get_value("User", user, "email") or user
    if not email:
        frappe.throw(_("Your user has no email address — ask an administrator to reset your PIN."))
    code = f"{secrets.randbelow(10**6):06d}"
    doc = _row(create=True)
    doc.reset_code_hash = _hash(code)
    doc.reset_expires = add_to_date(now_datetime(), minutes=RESET_CODE_TTL_MINUTES)
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.sendmail(
        recipients=[email],
        subject=_("Your LumenPOS PIN reset code"),
        message=_(
            "<p>Your PIN reset code is <b>{0}</b>.</p>"
            "<p>It expires in {1} minutes. If you didn't ask for this, ignore this email "
            "— your current PIN still works.</p>"
        ).format(code, RESET_CODE_TTL_MINUTES),
        now=True,
    )
    return {"ok": True, "email": email}


@frappe.whitelist()
def reset_pin_with_code(code, new_pin):
    """Set a new PIN using the emailed code."""
    _throttle("reset_use", 8, 60)
    new_pin = _validate_pin(new_pin)
    doc = _row()
    if not doc or not doc.get("reset_code_hash"):
        frappe.throw(_("Ask for a reset code first."))
    if not doc.reset_expires or now_datetime() > doc.reset_expires:
        frappe.throw(_("That code has expired — ask for a new one."))
    if not _verify((code or "").strip(), doc.reset_code_hash):
        frappe.throw(_("That code is not right."))
    doc.pin_hash = _hash(new_pin)
    doc.reset_code_hash = None
    doc.reset_expires = None
    doc.flags.ignore_permissions = True
    doc.save()
    return {"ok": True}
