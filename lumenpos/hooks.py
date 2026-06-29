app_name = "lumenpos"
app_title = "LumenPOS"
app_publisher = "Mahmoud"
app_description = "Professional, multi-business Point of Sale for ERPNext / Frappe"
app_email = "mhusam.b@gmail.com"
app_license = "MIT"

required_apps = ["erpnext"]

after_install = "lumenpos.install.after_install"
# Runs on every app update (Frappe Cloud deploy) — keeps the LumenPOS roles and
# custom fields in place on existing sites without shell access.
after_migrate = "lumenpos.install.ensure_setup"

# Self-healer: re-drive any register shift stuck in "Closing" (a consolidation
# that timed out or failed) toward "Closed", serialized so it never collides
# with a live close. This is the backstop that guarantees no shift is ever left
# half-closed for the next cashier to stumble into.
scheduler_events = {
    "cron": {
        "*/10 * * * *": [
            "lumenpos.api.register.reconcile_stuck_closings",
        ],
    },
}

# The POS single-page app is served at /pos (see lumenpos/www/pos.py).
# All sub-paths resolve to the same page; the frontend uses a hash router.
website_route_rules = [
    {"from_route": "/pos/<path:app_path>", "to_route": "pos"},
]
