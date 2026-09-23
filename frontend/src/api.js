// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
export class ApiError extends Error {}

// The network itself failed (no connection / server unreachable), distinct
// from the server rejecting the request. Callers use this to switch the POS
// into offline mode.
export class OfflineError extends Error {
  constructor() {
    super('No connection to the server')
  }
}

// Every call gets a deadline. Without one, a connection that dies mid-request
// leaves the browser waiting a minute or more before it gives up, and all that
// time the till still shows itself as online. A deadline is what turns "the
// network went away" into offline mode quickly.
const TIMEOUT_MS = 12000
// Posting a sale, taking one back or pulling the whole catalogue legitimately
// takes longer. A sale carries an idempotency key, so the retry after a
// timeout can never post it twice.
const SLOW_CALLS = /submit_sale|create_return|sell_gift_card|close_register|get_full_catalog/
const LONG_TIMEOUT_MS = 20000
const CATALOG_TIMEOUT_MS = 60000

function deadlineFor(method) {
  if (/get_full_catalog/.test(method)) return CATALOG_TIMEOUT_MS
  return SLOW_CALLS.test(method) ? LONG_TIMEOUT_MS : TIMEOUT_MS
}

// The page can come back from the device's own copy (a reload while the shop
// was offline), and the token baked into it may be one the server has since
// rotated. Fetch a fresh one rather than making the cashier reload.
async function refreshCsrfToken() {
  try {
    const html = await fetch('/pos', { cache: 'reload', credentials: 'same-origin' }).then((r) =>
      r.text()
    )
    const found = html.match(/csrf_token\s*=\s*"([^"]+)"/)
    if (!found) return false
    window.csrf_token = found[1]
    return true
  } catch {
    return false
  }
}

export async function call(method, args = {}, options = {}) {
  let res
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), options.timeout || deadlineFor(method))
  try {
    res = await fetch(`/api/method/${method}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Frappe-CSRF-Token': window.csrf_token || '',
      },
      body: JSON.stringify(args),
      signal: controller.signal,
    })
  } catch {
    // A refused connection and a request that ran out of time mean the same
    // thing to the till: the server is not reachable right now.
    throw new OfflineError()
  } finally {
    clearTimeout(timer)
  }
  let data = {}
  try {
    data = await res.json()
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok && data && data.exc_type === 'CSRFTokenError' && !options._retried) {
    if (await refreshCsrfToken()) {
      return call(method, args, { ...options, _retried: true })
    }
  }
  if (!res.ok) {
    throw new ApiError(extractMessage(data) || `Request failed (${res.status})`)
  }
  return data.message
}

function extractMessage(data) {
  // Frappe packs user-facing errors into _server_messages (a JSON string of
  // JSON strings) or exception text.
  try {
    if (data._server_messages) {
      const messages = JSON.parse(data._server_messages)
      return messages
        .map((m) => {
          try {
            return stripHtml(JSON.parse(m).message)
          } catch {
            return stripHtml(m)
          }
        })
        .join('\n')
    }
    if (data.exception) {
      const parts = String(data.exception).split(':')
      return parts.slice(1).join(':').trim() || data.exception
    }
  } catch {
    /* fall through */
  }
  return null
}

function stripHtml(text) {
  const el = document.createElement('div')
  el.innerHTML = text
  return el.textContent || el.innerText || text
}
