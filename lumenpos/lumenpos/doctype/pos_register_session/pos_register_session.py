import frappe
from frappe import _
from frappe.model.document import Document


class POSRegisterSession(Document):
    def validate(self):
        # A register can hold only one live shift at a time: neither a still-
        # open session NOR one whose closing is still finalising/failed
        # ("Closing") may coexist with a new open session. This is the safety
        # net behind lumenpos.api.register.open_register's friendlier checks.
        if self.status == "Open" and self.is_new():
            existing = frappe.db.get_value(
                "POS Register Session",
                {"pos_profile": self.pos_profile, "status": ["in", ["Open", "Closing"]]},
                ["name", "status"],
                as_dict=True,
            )
            if existing:
                if existing.status == "Closing":
                    frappe.throw(
                        _("Register {0} has a previous shift ({1}) whose closing is still finalising or has failed. Retry that closing before opening a new shift.").format(
                            self.pos_profile, existing.name
                        )
                    )
                frappe.throw(
                    _("Register {0} already has an open session ({1})").format(
                        self.pos_profile, existing.name
                    )
                )
