"""v0.2: printer fields on POS Profile (existing installs got the Sales
Invoice fields at install time; create_custom_fields is idempotent)."""

from lumenpos.install import make_custom_fields


def execute():
    make_custom_fields()
