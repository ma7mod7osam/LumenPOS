"""Helpers for the internal documents LumenPOS auto-provisions (clearing modes of
payment, liability accounts, the gift-card item).

Sites often add their OWN mandatory custom fields to core doctypes — e.g. an
"In Arabic" name on Mode of Payment, or a required attribute on Item. LumenPOS has
no value for those when it creates a clearing/internal record, so without help
the insert fails with "Value missing for ...". fill_required_custom_fields puts
a safe placeholder in every empty mandatory field so provisioning succeeds; the
standard fields LumenPOS already sets are left untouched.
"""

import frappe

_TEXTLIKE = {
    "Data", "Small Text", "Text", "Long Text", "Text Editor", "Code", "HTML Editor",
}
_NUMERIC = {"Int", "Float", "Currency", "Percent"}


def fill_required_custom_fields(doc, default):
    """Fill empty mandatory fields on `doc` with a sensible placeholder so a
    site's custom required fields can't block LumenPOS auto-provisioning."""
    for df in doc.meta.fields:
        if not df.reqd or doc.get(df.fieldname):
            continue
        if df.fieldtype in _TEXTLIKE:
            doc.set(df.fieldname, default)
        elif df.fieldtype in _NUMERIC:
            doc.set(df.fieldname, 0)
        elif df.fieldtype == "Select" and df.options:
            first = next((o.strip() for o in df.options.split("\n") if o.strip()), None)
            if first:
                doc.set(df.fieldname, first)
    return doc
