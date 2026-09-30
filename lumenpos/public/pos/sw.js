/* Copyright (c) 2026 Lumen Solutions
   SPDX-License-Identifier: AGPL-3.0-only
   "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.

   The till's service worker: it keeps the SHELL of the POS (the page, its
   script, its stylesheet, its fonts) on the device, so the app opens with no
   connection at all. Before this, a shop that lost the network could keep
   selling only as long as nobody reloaded the tab, and a till that rebooted
   was a till that could not sell.

   It deliberately does NOT cache any data. Sales, the catalogue, customers and
   the queue live in IndexedDB, where the app can reason about them, and every
   API call is a POST which is passed straight through. A service worker that
   quietly answered an API call from a cache would be a shop selling against
   numbers nobody can see.

   Scope: it is served from the site root so it can control /pos, but it only
   ever answers requests for /pos and the POS assets. The desk is untouched.

   Versioning: the page registers it as /sw.js?v=<app version>, so a new
   release is a new worker and a new cache, and the old cache is dropped on
   activate. Nothing is version-stamped by hand.

   Since 0.56.0 it also SENDS the queue in the background (see the end of the
   file): the one thing it does with the till's data, and only what the till
   itself would send, the same way.
*/

const VERSION = new URL(self.location.href).searchParams.get('v') || 'dev'
const CACHE = 'lumenpos-shell-' + VERSION
const PAGE = '/pos'
const ASSETS = '/assets/lumenpos/pos/'
const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com']

const SHELL = [
  PAGE,
  ASSETS + 'pos.js?v=' + VERSION,
  ASSETS + 'pos.css?v=' + VERSION,
  ASSETS + 'manifest.json',
  ASSETS + 'icon-192.png',
  ASSETS + 'icon-512.png',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // One missing file must not leave the till with no shell at all, so each
      // is added on its own and a failure is tolerated.
      Promise.all(SHELL.map((url) => cache.add(url).catch(() => null)))
    )
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith('lumenpos-shell-') && name !== CACHE)
            .map((name) => caches.delete(name))
        )
      )
      .then(() => self.clients.claim())
  )
})

async function cacheFirst(request) {
  const cache = await caches.open(CACHE)
  const hit = await cache.match(request, { ignoreSearch: false })
  if (hit) return hit
  const response = await fetch(request)
  if (response && (response.ok || response.type === 'opaque')) {
    cache.put(request, response.clone()).catch(() => {})
  }
  return response
}

// The page itself: always ask the server first, so a deploy is picked up the
// moment the till has a connection, and fall back to the copy on the device.
async function pageNetworkFirst(request) {
  const cache = await caches.open(CACHE)
  try {
    const response = await fetch(request)
    if (response && response.ok) cache.put(PAGE, response.clone()).catch(() => {})
    return response
  } catch (e) {
    const hit = (await cache.match(request, { ignoreSearch: true })) || (await cache.match(PAGE))
    if (hit) return hit
    throw e
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return // every API call is a POST, never touched
  let url
  try {
    url = new URL(request.url)
  } catch (e) {
    return
  }
  const sameOrigin = url.origin === self.location.origin

  if (request.mode === 'navigate') {
    // Only the POS. A desk page must never be answered from this cache.
    if (sameOrigin && (url.pathname === PAGE || url.pathname.startsWith(PAGE + '/'))) {
      event.respondWith(pageNetworkFirst(request))
    }
    return
  }
  if (sameOrigin && url.pathname.startsWith(ASSETS)) {
    event.respondWith(cacheFirst(request))
    return
  }
  if (FONT_HOSTS.includes(url.hostname)) {
    event.respondWith(cacheFirst(request))
  }
})

// --- sending the queue in the background (0.56.0) ----------------------------
// A till that queued sales (or returns) without a connection asks for a
// Background Sync (offline.requestBackgroundUpload). The browser fires it as
// soon as it has a network, even when no till tab is open any more (Chrome,
// Edge, Android), and this sends the queue the way the till does
// (stores/session._sendQueue): in order, each with its idempotency key, so
// nothing can post twice. The till and this take turns through one Web Lock.
// An entry the server refuses stays queued with its reason, for the till's
// offline log. A request that fails leaves the rest for the next attempt,
// which the browser schedules itself.

const DB_NAME = 'lumenpos'
const SYNC_TAG = 'lumenpos-queue'
const UPLOAD_LOCK = 'lumenpos-queue-upload'
// The session is the till's problem, not a refusal: leave the entry queued.
const SESSION_ERRORS = ['CSRFTokenError', 'SessionExpired', 'AuthenticationError']

self.addEventListener('sync', (event) => {
  if (event.tag !== SYNC_TAG) return
  event.waitUntil(withUploadLock(sendQueue))
})

function withUploadLock(fn) {
  if (self.navigator && navigator.locks && navigator.locks.request) {
    return navigator.locks.request(UPLOAD_LOCK, fn)
  }
  return fn()
}

function idb(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

// The till's own database, never created or upgraded from here.
async function openTillDb() {
  if (indexedDB.databases) {
    const known = await indexedDB.databases().catch(() => null)
    if (known && !known.some((d) => d.name === DB_NAME)) return null
  }
  return new Promise((resolve) => {
    let request
    try {
      request = indexedDB.open(DB_NAME)
    } catch (e) {
      resolve(null)
      return
    }
    request.onsuccess = () => {
      const db = request.result
      db.onversionchange = () => db.close() // the till is moving to a newer version
      resolve(db)
    }
    request.onerror = () => resolve(null)
  })
}

function read(db, store, key) {
  if (!db.objectStoreNames.contains(store)) return Promise.resolve(null)
  return idb(db.transaction(store).objectStore(store).get(key)).catch(() => null)
}

function patchRow(db, store, key, patch) {
  return new Promise((resolve) => {
    if (!key || !db.objectStoreNames.contains(store)) return resolve()
    const tx = db.transaction(store, 'readwrite')
    const rows = tx.objectStore(store)
    const current = rows.get(key)
    current.onsuccess = () => {
      if (current.result) rows.put(Object.assign({}, current.result, patch))
    }
    tx.oncomplete = () => resolve()
    tx.onerror = () => resolve()
  })
}

function removeQueued(db, localId) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction('queue', 'readwrite')
    tx.objectStore('queue').delete(localId)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

// A fresh CSRF token from the page itself, as the till does after an outage
// (api.refreshCsrfToken). None means nobody is signed in: leave it all.
async function csrfToken() {
  const response = await fetch(PAGE, { cache: 'no-store', credentials: 'same-origin' })
  const found = (await response.text()).match(/csrf_token\s*=\s*"([^"]+)"/)
  return found && found[1] !== 'None' ? found[1] : null
}

function plain(text) {
  return String(text || '')
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&amp;/g, '&')
}

// The server's reason, as api.extractMessage reads it.
function reasonOf(data, status) {
  try {
    if (data._server_messages) {
      return JSON.parse(data._server_messages)
        .map((m) => {
          try {
            return plain(JSON.parse(m).message)
          } catch (e) {
            return plain(m)
          }
        })
        .join('\n')
    }
    if (data.exception) {
      const parts = String(data.exception).split(':')
      return parts.slice(1).join(':').trim() || String(data.exception)
    }
  } catch (e) {
    /* fall through */
  }
  return 'Request failed (' + status + ')'
}

// A network failure throws, which fails the sync and makes the browser retry.
async function post(method, body, csrf, lang) {
  const response = await fetch('/api/method/' + method, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
      'X-Frappe-CSRF-Token': csrf,
    },
    body: JSON.stringify(Object.assign({}, body, lang ? { _lang: lang } : {})),
  })
  let data = {}
  try {
    data = await response.json()
  } catch (e) {
    /* not JSON */
  }
  return { ok: response.ok, status: response.status, data }
}

async function sendQueue() {
  const db = await openTillDb()
  if (!db) return
  const report = { type: 'lumenpos-queue', synced: 0, failed: 0, stock: {} }
  try {
    if (!db.objectStoreNames.contains('queue')) return
    // The shop switched background sending off: the till sends it when open.
    const boot = await read(db, 'kv', 'bootstrap')
    if (boot && boot.settings && Number(boot.settings.background_upload) === 0) return
    const entries = await idb(db.transaction('queue').objectStore('queue').getAll())
    if (!entries.length) return
    const csrf = await csrfToken()
    if (!csrf) return
    const customers = {} // a customer made offline -> the real one
    for (const entry of entries) {
      const payload = entry.payload || {}
      const key = payload.idempotency_key
      const isReturn = entry.kind === 'return'
      let body = isReturn ? payload : { payload }
      let answer = null
      const local = !isReturn && typeof payload.customer === 'string' && payload.customer.indexOf('__local__') === 0
      if (local && !customers[payload.customer]) {
        const pending = await read(db, 'pending_customers', payload.customer)
        answer = pending
          ? await post('lumenpos.api.catalog.resolve_pending_customer', { payload: pending.payload }, csrf, entry.lang)
          : { ok: false, status: 0, data: { exception: 'x: offline customer record is missing' } }
        if (answer.ok) customers[payload.customer] = answer.data.message && answer.data.message.name
      }
      if (local && customers[payload.customer]) {
        body = { payload: Object.assign({}, payload, { customer: customers[payload.customer] }) }
      }
      if (!local || customers[payload.customer]) {
        answer = await post(
          isReturn ? 'lumenpos.api.sales.create_return' : 'lumenpos.api.sales.submit_sale',
          body,
          csrf,
          entry.lang
        )
      }
      if (answer.ok) {
        const receipt = answer.data.message || {}
        await removeQueued(db, entry.local_id)
        await patchRow(db, 'sale_log', key, {
          status: 'synced',
          receipt: receipt.name || null,
          synced_at: new Date().toISOString(),
          error: null,
          gap: receipt.offline_gap || 0,
        })
        // The till folds the receipt into the sale it keeps for a return
        // without a connection (session.loadShiftSales).
        if (!isReturn) {
          await patchRow(db, 'shift_sales', key, { name: receipt.name || null, queued: false, posted_receipt: receipt })
        }
        Object.assign(report.stock, receipt.stock_after || {})
        report.synced += 1
      } else if (answer.status === 401 || SESSION_ERRORS.includes(answer.data && answer.data.exc_type)) {
        return
      } else {
        await patchRow(db, 'sale_log', key, {
          status: 'failed',
          error: reasonOf(answer.data || {}, answer.status),
          error_at: new Date().toISOString(),
        })
        report.failed += 1
      }
    }
  } finally {
    db.close()
    if (report.synced || report.failed) {
      const tills = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
      for (const till of tills) till.postMessage(report)
    }
  }
}
