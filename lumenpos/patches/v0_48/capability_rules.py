# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""v0.48: move the four single-role permission fields into "Who can do what".

A shop used to restrict an action with one Role field per action. The table
that replaces them says the same thing and can also name a person, so each
role that was set becomes one row and the old field is cleared. A site that
never restricted anything gets no rows and behaves exactly as before.

Idempotent: a capability that already has a row is left alone.
"""

import frappe

from lumenpos.api.permissions import LEGACY_FIELD


def execute():
    if not frappe.db.exists("DocType", "POS Capability Rule"):
        return
    settings = frappe.get_single("LumenPOS Settings")
    if not settings.meta.has_field("capability_rules"):
        return

    existing = {r.capability for r in (settings.get("capability_rules") or [])}
    moved = []
    for capability, field in LEGACY_FIELD.items():
        role = settings.get(field)
        if not role or capability in existing:
            continue
        settings.append("capability_rules", {"capability": capability, "role": role})
        settings.set(field, None)
        moved.append(f"{capability} -> {role}")

    if moved:
        settings.flags.ignore_permissions = True
        settings.save()
        frappe.db.commit()  # nosemgrep
        print("LumenPOS: moved permission roles into Who can do what: " + ", ".join(moved))
