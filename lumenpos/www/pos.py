import frappe

no_cache = 1


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/pos"
        raise frappe.Redirect
    context.csrf_token = frappe.sessions.get_csrf_token()
    # Cache-busting: assets keep fixed names, so stamp the app version on
    # the URLs — every update forces browsers to fetch the new build.
    from lumenpos import __version__

    context.lumenpos_version = __version__
    return context
