export class ApiError extends Error {}

// The network itself failed (no connection / server unreachable) — distinct
// from the server rejecting the request. Callers use this to switch the POS
// into offline mode.
export class OfflineError extends Error {
  constructor() {
    super('No connection to the server')
  }
}

export async function call(method, args = {}) {
  let res
  try {
    res = await fetch(`/api/method/${method}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        'X-Frappe-CSRF-Token': window.csrf_token || '',
      },
      body: JSON.stringify(args),
    })
  } catch {
    throw new OfflineError()
  }
  let data = {}
  try {
    data = await res.json()
  } catch {
    /* non-JSON error page */
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
