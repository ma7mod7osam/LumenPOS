// Offline layer: IndexedDB cache for bootstrap + catalog, and a queue for
// sales made while the network is down. No external dependencies.

const DB_NAME = 'lumenpos'
const DB_VERSION = 1

let dbPromise = null

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

// --- offline sales queue ----------------------------------------------------

export async function queueSale(payload) {
  const database = await db()
  return new Promise((resolve, reject) => {
    const transaction = database.transaction('queue', 'readwrite')
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
