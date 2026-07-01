import { defineStore } from 'pinia'
import { call, OfflineError } from '../api'
import { saveCatalog, searchCatalog, catalogCount, saveCustomers } from '../offline'
import { useSessionStore } from './session'

export const useCatalogStore = defineStore('catalog', {
  state: () => ({
    items: [],
    loading: false,
    search: '',
    itemGroup: '',
    cachedCount: 0,
    _searchTimer: null,
    _requestId: 0,
  }),

  actions: {
    // LOCAL-FIRST: searches run against the IndexedDB cache (instant, works
    // offline). The cache is filled on startup and refreshed in the
    // background — the server is only hit when the cache is empty.
    async fetch() {
      const session = useSessionStore()
      if (!session.posProfile) return
      const requestId = ++this._requestId

      if (!this.cachedCount) {
        this.cachedCount = await catalogCount().catch(() => 0)
      }
      if (this.cachedCount > 0) {
        const items = await searchCatalog(this.search, this.itemGroup)
        if (requestId === this._requestId) this.items = items
        return
      }

      // Cold start: no cache yet — query the server directly
      this.loading = true
      try {
        const data = await call('lumenpos.api.catalog.get_items', {
          pos_profile: session.posProfile,
          search: this.search,
          item_group: this.itemGroup,
          limit: 80,
        })
        if (requestId !== this._requestId) return // stale response
        this.items = data.items
      } catch (e) {
        if (e instanceof OfflineError) {
          session.markOffline()
          if (requestId === this._requestId) this.items = []
        } else {
          throw e
        }
      } finally {
        if (requestId === this._requestId) this.loading = false
      }
    },

    // Pull the whole catalog into IndexedDB so search is instant and the
    // POS keeps selling if the connection drops.
    async cacheFullCatalog() {
      const session = useSessionStore()
      if (!session.posProfile || session.offline) return
      try {
        const items = await call('lumenpos.api.catalog.get_full_catalog', {
          pos_profile: session.posProfile,
        })
        await saveCatalog(items)
        this.cachedCount = items.length
        this.fetch()
      } catch {
        /* cache refresh is best-effort */
      }
    },

    // Cache a capped recent/frequent customer subset for offline SELECT (not the
    // full directory — see the offline-customers decision). Best-effort.
    async cacheCustomers() {
      const session = useSessionStore()
      if (!session.posProfile || session.offline) return
      try {
        const res = await call('lumenpos.api.catalog.recent_customers', {
          pos_profile: session.posProfile,
        })
        await saveCustomers(res.customers || [])
      } catch {
        /* best-effort */
      }
    },

    setSearch(value) {
      this.search = value
      clearTimeout(this._searchTimer)
      // Local search is instant; tiny debounce just coalesces keystrokes
      this._searchTimer = setTimeout(() => this.fetch(), this.cachedCount ? 60 : 250)
    },

    setGroup(group) {
      this.itemGroup = group === this.itemGroup ? '' : group
      this.fetch()
    },

    clearSearch() {
      this.search = ''
      this.fetch()
    },
  },
})
