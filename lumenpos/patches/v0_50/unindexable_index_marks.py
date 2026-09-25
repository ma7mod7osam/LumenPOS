# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""v0.50.2: new fields can be added to Sales Invoice again.

Up to 0.50.1 LumenPOS marked Sales Invoice.customer_name as an indexed field
(a search_index Property Setter). That field is Small Text, which Frappe
refuses to index, so from then on every new Sales Invoice field, from
Customize Form or from another app, failed with "Fieldtype Small Text for
Customer Name cannot be indexed". This removes the marking; the index on the
column stays, Frappe never drops an index on a text column.

The same cleanup runs on every migrate (install.ensure_setup). It is ALSO a
patch so that a Frappe Cloud release carrying it runs as a full migrate: a
release with no patch, doctype or fixture change is applied as a plain code
pull, which skips after_migrate.
"""


def execute():
    from lumenpos.install import drop_unindexable_index_marks

    drop_unindexable_index_marks()
