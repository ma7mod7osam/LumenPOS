"""v0.4: POS Invoice migration — create the custom fields on POS Invoice
(idempotent for the rest)."""

from lumenpos.install import make_custom_fields


def execute():
    make_custom_fields()
