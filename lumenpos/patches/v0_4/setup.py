# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""v0.4: POS Invoice migration — create the custom fields on POS Invoice
(idempotent for the rest)."""

from lumenpos.install import make_custom_fields


def execute():
    make_custom_fields()
