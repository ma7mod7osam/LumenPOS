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

    def on_cancel(self):
        self._cancel_opening_entry()

    def on_trash(self):
        # Deleting a shift that handled cash would leave its movements and its
        # native opening entry dangling with no way to reconcile them.
        if self.get("cash_movements"):
            frappe.throw(
                _("Shift {0} recorded cash movements and can't be deleted. Cancel it instead.").format(self.name)
            )
        self._cancel_opening_entry()

    def _cancel_opening_entry(self):
        """Cancel the native POS Opening Entry this shift created, so cancelling
        or deleting the shift never leaves an orphan "Open" entry behind — that
        orphan is exactly what used to make the next cashier resume a dead
        shift."""
        name = self.get("pos_opening_entry")
        if not name or not frappe.db.exists("POS Opening Entry", name):
            return
        try:
            entry = frappe.get_doc("POS Opening Entry", name)
            if entry.docstatus == 1:
                entry.flags.ignore_permissions = True
                entry.cancel()
        except Exception:
            frappe.log_error(
                title="LumenPOS: could not cancel POS Opening Entry",
                message=frappe.get_traceback(),
            )
