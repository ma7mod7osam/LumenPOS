// Offline layer: IndexedDB cache for bootstrap + catalog, and a queue for
// sales made while the network is down. No external dependencies.

const DB_NAME = 'lumenpos'
const DB_VERSION = 3

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
// and a manual cache-clear still wipes it — so it pairs with server-side
// idempotent replay — but it is the standard guard for an offline queue.
export async function ensurePersistentStorage() {
  try {
    if (navigator.storage?.persisted && navigator.storage?.persist) {
      if (await navigator.storage.persisted()) return true
      return await navigator.storage.persist()
    }
  } catch {
    /* not supported / blocked — ignore */
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
      }
      req.onsuccess = () => resolve(req.result)
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

export async function searchCatalog(search = '', itemGroup = '', limit = 80) {
  const database = await db()
  const all = await request(database.transaction('items').objectStore('items').getAll())
  const term = search.trim().toLowerCase()
  const filtered = all.filter((item) => {
    if (itemGroup && item.item_group !== itemGroup) return false
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

export async function queueSale(payload) {
  const database = await db()
  return new Promise((resolve, reject) => {
    // strict durability: the write is flushed to disk BEFORE oncomplete fires,
    // so a power cut / crash right after a sale can't silently drop a queued
    // invoice (Chrome 121+ defaults to relaxed, which acks before the disk
    // flush). Unknown to older engines — the option is safely ignored there.
    const transaction = database.transaction('queue', 'readwrite', { durability: 'strict' })
    const req = transaction
      .objectStore('queue')
      .add({ payload: JSON.parse(JSON.stringify(payload)), queued_at: new Date().toISOString() })
    transaction.oncomplete = () => resolve(req.result)
    transaction.onerror = () => reject(transaction.error)
  })
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
