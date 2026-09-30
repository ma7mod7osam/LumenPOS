// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
// Offline layer: IndexedDB cache for bootstrap + catalog, and a queue for
// sales made while the network is down. No external dependencies.

const DB_NAME = 'lumenpos'
const DB_VERSION = 5

// The till page and the service worker's background upload (public/sw.js)
// take turns through this Web Lock, so one queued sale is never sent by both
// at once. sw.js uses the same name.
export const UPLOAD_LOCK = 'lumenpos-queue-upload'
// The Background Sync tag the page asks for and sw.js answers.
export const SYNC_TAG = 'lumenpos-queue'

// A unique client id for offline records (queued-sale idempotency keys,
// offline-created customer temp ids).
export function newId() {
  try {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) return crypto.randomUUID()
  } catch {
    /* fall through */
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

let dbPromise = null

// --- durable storage --------------------------------------------------------

// Ask the browser to make this origin's storage PERSISTENT so the offline
// queue can't be evicted under disk pressure / LRU (and survives Safari's
// 7-day "no interaction" wipe). Best-effort by design: the grant is heuristic
// and a manual cache-clear still wipes it, so it pairs with server-side
// idempotent replay, but it is the standard guard for an offline queue.
export async function ensurePersistentStorage() {
  try {
    if (navigator.storage?.persisted && navigator.storage?.persist) {
      if (await navigator.storage.persisted()) return true
      return await navigator.storage.persist()
    }
  } catch {
    /* not supported / blocked, ignore */
  }
  return false
}

export async function storagePersisted() {
  try {
    return Boolean(await navigator.storage?.persisted?.())
  } catch {
    return false
  }
}

function db() {
  if (!dbPromise) {
    dbPromise = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION)
      req.onupgradeneeded = () => {
        const database = req.result
        if (!database.objectStoreNames.contains('kv')) database.createObjectStore('kv')
        if (!database.objectStoreNames.contains('items'))
          database.createObjectStore('items', { keyPath: 'item_code' })
        if (!database.objectStoreNames.contains('queue'))
          database.createObjectStore('queue', { keyPath: 'local_id', autoIncrement: true })
        if (!database.objectStoreNames.contains('customers'))
          database.createObjectStore('customers', { keyPath: 'name' })
        if (!database.objectStoreNames.contains('pending_customers'))
          database.createObjectStore('pending_customers', { keyPath: 'temp_id' })
        if (!database.objectStoreNames.contains('sale_log'))
          database.createObjectStore('sale_log', { keyPath: 'key' })
        // 0.56.0: the sales this device made in its shift, so it can take one
        // back without a connection (refund.js). Keyed by the sale's
        // idempotency key, which a sale has from before its first attempt.
        if (!database.objectStoreNames.contains('shift_sales'))
          database.createObjectStore('shift_sales', { keyPath: 'key' })
      }
      // Another tab or the service worker may need a newer version: step aside.
      req.onsuccess = () => {
        const database = req.result
        database.onversionchange = () => {
          database.close()
          dbPromise = null
        }
        resolve(database)
      }
      req.onerror = () => reject(req.error)
    })
  }
  return dbPromise
}

function tx(store, mode, fn) {
  return db().then(
    (database) =>
      new Promise((resolve, reject) => {
        const transaction = database.transaction(store, mode)
        const result = fn(transaction.objectStore(store))
        transaction.oncomplete = () => resolve(result.__value !== undefined ? result.__value : result)
        transaction.onerror = () => reject(transaction.error)
      })
  )
}

function request(req) {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

// --- key/value (bootstrap snapshot etc.) -----------------------------------

export async function kvSet(key, value) {
  return tx('kv', 'readwrite', (store) => store.put(JSON.parse(JSON.stringify(value)), key))
}

export async function kvGet(key) {
  const database = await db()
  return request(database.transaction('kv').objectStore('kv').get(key))
}

// --- catalog cache ----------------------------------------------------------

export async function saveCatalog(items) {
  const database = await db()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction('items', 'readwrite')
    const store = transaction.objectStore('items')
    store.clear()
    for (const item of items) store.put(JSON.parse(JSON.stringify(item)))
    transaction.oncomplete = () => resolve(items.length)
    transaction.onerror = () => reject(transaction.error)
  })
}

// `groups`: the picked group and every group beneath it (the server sends
// them per chip), or one group name, or nothing for all.
export async function searchCatalog(search = '', groups = null, limit = 80) {
  const database = await db()
  const all = await request(database.transaction('items').objectStore('items').getAll())
  const term = search.trim().toLowerCase()
  const allowed = Array.isArray(groups) ? groups : groups ? [groups] : null
  const filtered = all.filter((item) => {
    if (allowed && !allowed.includes(item.item_group)) return false
    if (!term) return true
    return (
      (item.item_name || '').toLowerCase().includes(term) ||
      (item.item_code || '').toLowerCase().includes(term) ||
      (item.barcode || '').toLowerCase().includes(term)
    )
  })
  filtered.sort((a, b) => (a.item_name || '').localeCompare(b.item_name || ''))
  return filtered.slice(0, limit)
}

export async function catalogCount() {
  const database = await db()
  return request(database.transaction('items').objectStore('items').count())
}

export async function getCatalogItems(codes) {
  const database = await db()
  const out = []
  for (const code of codes) {
    const item = await request(
      database.transaction('items').objectStore('items').get(code)
    ).catch(() => null)
    if (item) out.push(item)
  }
  return out
}

// Write new stock figures onto the cached items. The catalogue cache is filled
// once per shift, so without this the tile keeps showing the quantity from the
// moment the till opened and the cashier only learns the truth at a refusal.
export async function patchCatalogStock(levels) {
  const codes = Object.keys(levels || {})
  if (!codes.length) return 0
  const database = await db()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction('items', 'readwrite')
    const store = transaction.objectStore('items')
    let written = 0
    for (const code of codes) {
      const req = store.get(code)
      req.onsuccess = () => {
        const item = req.result
        if (!item) return
        item.actual_qty = levels[code]
        store.put(item)
        written += 1
      }
    }
    transaction.oncomplete = () => resolve(written)
    transaction.onerror = () => reject(transaction.error)
  })
}

// --- customers cache (recent/frequent subset, for offline select) -----------

export async function saveCustomers(customers) {
  const database = await db()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction('customers', 'readwrite')
    const store = transaction.objectStore('customers')
    store.clear()
    for (const c of customers) store.put(JSON.parse(JSON.stringify(c)))
    transaction.oncomplete = () => resolve(customers.length)
    transaction.onerror = () => reject(transaction.error)
  })
}

export async function searchCustomersOffline(search = '', limit = 20) {
  const database = await db()
  const all = await request(database.transaction('customers').objectStore('customers').getAll())
  const term = search.trim().toLowerCase()
  const filtered = term
    ? all.filter(
        (c) =>
          (c.customer_name || '').toLowerCase().includes(term) ||
          (c.name || '').toLowerCase().includes(term) ||
          (c.mobile_no || '').toLowerCase().includes(term) ||
          (c.tax_id || '').toLowerCase().includes(term)
      )
    : all
  filtered.sort((a, b) => (a.customer_name || '').localeCompare(b.customer_name || ''))
  return filtered.slice(0, limit)
}

export async function customerCount() {
  const database = await db()
  return request(database.transaction('customers').objectStore('customers').count())
}

// Add/replace a single customer in the offline cache (e.g. one created offline
// so it's immediately searchable for the next offline sale).
export async function putCustomer(customer) {
  return tx('customers', 'readwrite', (store) => store.put(JSON.parse(JSON.stringify(customer))))
}

// --- offline-created customers (pending sync) -------------------------------

export async function savePendingCustomer(record) {
  return tx('pending_customers', 'readwrite', (store) =>
    store.put(JSON.parse(JSON.stringify(record)))
  )
}

export async function getPendingCustomer(tempId) {
  const database = await db()
  return request(
    database.transaction('pending_customers').objectStore('pending_customers').get(tempId)
  )
}

export async function removePendingCustomer(tempId) {
  return tx('pending_customers', 'readwrite', (store) => store.delete(tempId))
}

export async function listPendingCustomers() {
  const database = await db()
  return request(
    database.transaction('pending_customers').objectStore('pending_customers').getAll()
  )
}

// --- offline sales queue ----------------------------------------------------

// Run `fn` holding the upload lock (see UPLOAD_LOCK). A browser without Web
// Locks runs it straight away, as before.
export function withUploadLock(fn) {
  try {
    if (typeof navigator !== 'undefined' && navigator.locks?.request) {
      return navigator.locks.request(UPLOAD_LOCK, fn)
    }
  } catch {
    /* fall through */
  }
  return fn()
}

// Ask the browser to send the queue as soon as it has a network, even with
// the till closed (Background Sync: Chrome, Edge, Android). Elsewhere, and
// with the shop's switch off, the till sends it itself when it is open.
export async function requestBackgroundUpload() {
  try {
    const registration = await navigator.serviceWorker?.getRegistration('/pos')
    if (registration?.sync) await registration.sync.register(SYNC_TAG)
    return Boolean(registration?.sync)
  } catch {
    return false
  }
}

// What a queued entry is: a sale (the only kind before 0.56.0, so an entry
// without one is a sale) or a return made without a connection.
export function entryKind(entry) {
  return entry?.kind === 'return' ? 'return' : 'sale'
}

// `lang`: the till's language when it was made, so the server's answer (a
// refusal's reason) comes back in it even when the service worker sends it.
export async function queueEntry(kind, payload, lang = null) {
  const database = await db()
  return new Promise((resolve, reject) => {
    // strict durability: the write is flushed to disk BEFORE oncomplete fires,
    // so a power cut / crash right after a sale can't silently drop a queued
    // invoice (Chrome 121+ defaults to relaxed, which acks before the disk
    // flush). Unknown to older engines, the option is safely ignored there.
    const transaction = database.transaction('queue', 'readwrite', { durability: 'strict' })
    const req = transaction.objectStore('queue').add({
      kind,
      payload: JSON.parse(JSON.stringify(payload)),
      lang,
      queued_at: new Date().toISOString(),
    })
    transaction.oncomplete = () => resolve(req.result)
    transaction.onerror = () => reject(transaction.error)
  })
}

export async function queueSale(payload, lang = null) {
  return queueEntry('sale', payload, lang)
}

export async function listQueue() {
  const database = await db()
  return request(database.transaction('queue').objectStore('queue').getAll())
}

export async function removeQueued(localId) {
  return tx('queue', 'readwrite', (store) => store.delete(localId))
}

export async function queueCount() {
  const database = await db()
  return request(database.transaction('queue').objectStore('queue').count())
}

// What the queue holds: sales not tried yet (or still waiting for the
// connection), and sales the server refused, whose log row says why. A
// refused sale stays queued and is tried again on every upload, but it must
// never hold the shift's close: it may never go through on this shift.
export async function queueBreakdown() {
  const [queue, log] = await Promise.all([listQueue(), listSaleLog()])
  const refused = new Map(log.filter((r) => r.status === 'failed').map((r) => [r.key, r]))
  const rows = queue.filter((e) => refused.has(e.payload?.idempotency_key))
  const first = rows.length ? refused.get(rows[0].payload.idempotency_key) : null
  return {
    waiting: queue.length - rows.length,
    refused: rows.length,
    reason: first?.error || '',
  }
}

// --- offline sales log ------------------------------------------------------
// A durable, user-visible record of every sale made offline and what became of
// it on sync: pending (queued, not yet uploaded), synced (posted, with the
// real server invoice name), or failed (server rejected it, with the reason).
// Keyed by the sale's idempotency key so flushQueue can update the right row.
// This is a LOG for confidence/audit; the `queue` store remains the source of
// truth for what still needs uploading.

export async function logSale(record) {
  return tx('sale_log', 'readwrite', (store) => store.put(JSON.parse(JSON.stringify(record))))
}

// Merge a patch into one log row (read-modify-write in a single transaction).
export async function patchSaleLog(key, patch) {
  if (!key) return
  const database = await db()
  const clean = JSON.parse(JSON.stringify(patch))
  return new Promise((resolve, reject) => {
    const transaction = database.transaction('sale_log', 'readwrite')
    const store = transaction.objectStore('sale_log')
    const getReq = store.get(key)
    getReq.onsuccess = () => {
      const existing = getReq.result
      if (existing) store.put({ ...existing, ...clean })
    }
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
}

export async function listSaleLog() {
  const database = await db()
  const all = await request(database.transaction('sale_log').objectStore('sale_log').getAll())
  all.sort((a, b) => (b.queued_at || '').localeCompare(a.queued_at || ''))
  return all
}

// --- this device's sales of the shift (returns without a connection) -------

export async function putShiftSale(record) {
  return tx('shift_sales', 'readwrite', (store) => store.put(JSON.parse(JSON.stringify(record))))
}

export async function getShiftSale(key) {
  const database = await db()
  return request(database.transaction('shift_sales').objectStore('shift_sales').get(key))
}

// Merge a patch into one record, in one transaction.
export async function patchShiftSale(key, patch) {
  if (!key) return
  const database = await db()
  const clean = JSON.parse(JSON.stringify(patch))
  return new Promise((resolve, reject) => {
    const transaction = database.transaction('shift_sales', 'readwrite')
    const store = transaction.objectStore('shift_sales')
    const getReq = store.get(key)
    getReq.onsuccess = () => {
      if (getReq.result) store.put({ ...getReq.result, ...clean })
    }
    transaction.oncomplete = () => resolve()
    transaction.onerror = () => reject(transaction.error)
  })
}

// Newest first. A record from another shift is dropped (pruneShiftSales).
export async function listShiftSales() {
  const database = await db()
  const all = await request(database.transaction('shift_sales').objectStore('shift_sales').getAll())
  all.sort((a, b) => (b.at || '').localeCompare(a.at || ''))
  return all
}

// A sale of this shift taken back online, or in an exchange: its record
// learns what came back, so a return without a connection later cannot take
// the same goods back twice. Best effort.
export async function markReturned(invoice, items) {
  if (!invoice) return
  try {
    const record = (await listShiftSales()).find((r) => r.name === invoice)
    if (!record) return
    const returned = { ...(record.returned || {}) }
    for (const [code, qty] of Object.entries(items || {})) {
      returned[code] = (Number(returned[code]) || 0) + (Number(qty) || 0)
    }
    await patchShiftSale(record.key, { returned })
  } catch {
    /* the server still refuses what cannot come back */
  }
}

// Only the shift that is open on this till keeps its sales here: a return
// without a connection is for a sale of the same shift, on the same device.
export async function pruneShiftSales(session) {
  const all = await listShiftSales()
  for (const record of all) {
    if (record.session !== session) {
      await tx('shift_sales', 'readwrite', (store) => store.delete(record.key)).catch(() => {})
    }
  }
}

// Keep every pending/failed row; keep only the newest `keepSynced` synced ones
// so a busy till's log can't grow without bound. Best-effort.
export async function pruneSaleLog(keepSynced = 100) {
  const all = await listSaleLog()
  const drop = all.filter((r) => r.status === 'synced').slice(keepSynced)
  for (const r of drop) {
    await tx('sale_log', 'readwrite', (store) => store.delete(r.key)).catch(() => {})
  }
}
