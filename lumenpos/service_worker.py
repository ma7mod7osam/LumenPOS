# Copyright (c) 2026 Lumen Solutions
# SPDX-License-Identifier: AGPL-3.0-only
# "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
"""Serve the till's service worker at /sw.js.

A service worker may only control pages at or below its OWN path, so a worker
served from /assets/lumenpos/pos/ could never control /pos. It has to come from
the site root, and Frappe will not serve a .js file out of an app's www folder
(every version from v13 to v15 excludes js, css, json and friends from static
pages on purpose). A page renderer is the supported way in, so this one answers
exactly one path and leaves every other request alone.

The file itself is the one that ships with the bundle, so there is a single
copy: /assets/lumenpos/pos/sw.js and /sw.js are the same bytes.

On Frappe v13 the page_renderer hook does not exist, so /sw.js is simply not
found there: the till keeps working exactly as it did, it just cannot open
without a connection.
"""

import os

import frappe

PATH = "sw.js"


def _file():
    return os.path.join(frappe.get_app_path("lumenpos"), "public", "pos", "sw.js")


class ServiceWorkerPage:
    def __init__(self, path=None, http_status_code=None):
        self.path = (path or "").strip("/")
        self.http_status_code = http_status_code

    def can_render(self):
        return self.path == PATH and os.path.isfile(_file())

    def render(self):
        from werkzeug.wrappers import Response

        with open(_file(), "rb") as handle:
            body = handle.read()
        response = Response(body, mimetype="text/javascript")
        # Registered from the root so it can take charge of /pos, and told to
        # stay there: it must never answer for the desk.
        response.headers["Service-Worker-Allowed"] = "/pos"
        # The worker carries the app version in its URL, so the browser asks
        # for a new one on every release. Nothing gains from caching this.
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response
