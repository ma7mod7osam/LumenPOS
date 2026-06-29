import { defineStore } from 'pinia'
import { call, OfflineError } from '../api'
import { setCurrency } from '../format'
import { kvSet, kvGet, listQueue, removeQueued, queueCount } from '../offline'
import { syncFromErp } from '../theme'

export const useSessionStore = defineStore('session', {
  state: () => ({
    loaded: false,
    error: null,
    user: null,
    userFullname: '',
    posProfile: null,
    invoiceMode: 'POS Invoice',
    availableProfiles: [],
    company: null,
    currency: 'USD',
    priceList: null,
    defaultCustomer: null,
    defaultCustomerName: null,
    paymentModes: [],
    itemGroups: [],
    taxes: [],
    promotions: [],
    registerSession: null,
    printerConfigured: false,
    printFormat: null,
    storeCreditMode: 'Store Credit',
    giftCardMode: 'Gift Card',
    salesPersons: [],
    allowNegativeStock: false,
    settings: {
      delivery_apps: [],
      discount_limit_percent: 0,
      discount_approval_mode: 'Passcode only',
      can_approve_requests: false,
      restrict_returns_to_window: 0,
      return_window_days: 0,
      serial_scan_only: 0,
    },
    bundles: [],
    permissions: {},
    pendingClosing: null,
    offline: false,
    queuedCount: 0,
    syncing: false,
    toast: null,
  }),

  getters: {
    registerOpen: (s) => Boolean(s.registerSession),
    // Cashier-facing return reasons (configured in Settings → Return Reasons).
    returnReasons: (s) => s.settings?.return_reasons || [],
    // Over-limit discount approval flow (Settings → Discount Approval).
    discountApprovalMode: (s) => s.settings?.discount_approval_mode || 'Passcode only',
    // This user may approve requests AND at least one request type is enabled
    // (discount requests on, or returns limited to a window), so the Approvals
    // tray is worth showing.
    canApprove: (s) =>
      Boolean(s.settings?.can_approve_requests) &&
      ((s.settings?.discount_approval_mode || 'Passcode only') !== 'Passcode only' ||
        Boolean(s.settings?.restrict_returns_to_window)),
    // The Settings gear is worth showing only if the user can manage at least
    // one back-office area.
    canManageAny: (s) => {
      const p = s.permissions || {}
      return Boolean(
        p.is_manager ||
          p.settings ||
          p.promotions?.read ||
          p.bundles?.read ||
          p.price_books?.read ||
          p.loyalty ||
          p.gift_cards
      )
    },
  },

  actions: {
    async bootstrap(posProfile = null) {
      this.error = null
      try {
        const data = await call('lumenpos.api.session.get_bootstrap', {
          pos_profile: posProfile,
        })
        this._applyBootstrap(data)
        this.offline = false
        await kvSet('bootstrap', data)
      } catch (e) {
        if (e instanceof OfflineError) {
          const cached = await kvGet('bootstrap')
          if (cached) {
            this._applyBootstrap(cached)
            this.offline = true
            this.notify('Offline — using cached data')
          } else {
            this.error =
              'No connection and no cached data yet. Connect once so the POS can cache its catalog.'
          }
        } else {
          this.error = e.message
        }
      }
      this.queuedCount = await queueCount().catch(() => 0)
      this.loaded = true
    },

    _applyBootstrap(data) {
      this.user = data.user
      this.userFullname = data.user_fullname
      this.posProfile = data.pos_profile
      this.invoiceMode = data.invoice_mode || 'POS Invoice'
      this.availableProfiles = data.available_profiles || []
      this.company = data.company
      this.currency = data.currency
      this.priceList = data.price_list
      this.defaultCustomer = data.default_customer
      this.defaultCustomerName = data.default_customer_name
      this.paymentModes = data.payment_modes || []
      this.itemGroups = data.item_groups || []
      this.taxes = data.taxes || []
      this.promotions = data.promotions || []
      this.registerSession = data.register_session
      this.printerConfigured = data.printer_configured || false
      this.printFormat = data.print_format || null
      this.storeCreditMode = data.store_credit_mode || 'Store Credit'
      this.giftCardMode = data.gift_card_mode || 'Gift Card'
      this.salesPersons = data.sales_persons || []
      this.allowNegativeStock = Boolean(data.allow_negative_stock)
      this.settings = data.settings || { delivery_apps: [], discount_limit_percent: 0 }
      this.bundles = data.bundles || []
      this.permissions = data.permissions || {}
      this.pendingClosing = data.pending_closing || null
      syncFromErp(data.desk_theme) // follow ERPNext theme unless overridden in LumenPOS
      setCurrency(data.currency)
    },

    watchConnection() {
      window.addEventListener('online', () => this.reconnect())
      window.addEventListener('offline', () => {
        this.offline = true
      })
      // Promotions edited on another terminal/tab show up when this till
      // regains focus — no reload needed.
      window.addEventListener('focus', () => {
        this.refreshPromotions().catch(() => {})
      })
      // navigator.onLine misses some failure modes; a failed API call also
      // flips `offline` via markOffline().
    },

    markOffline() {
      if (!this.offline) {
        this.offline = true
        this.notify('Connection lost — sales will be queued')
      }
    },

    async reconnect() {
      try {
        await this.flushQueue()
        await this.bootstrap(this.posProfile)
        if (!this.offline) this.notify('Back online')
      } catch {
        /* still offline */
      }
    },

    async flushQueue() {
      if (this.syncing) return
      this.syncing = true
      try {
        const queue = await listQueue()
        let synced = 0
        for (const entry of queue) {
          try {
            await call('lumenpos.api.sales.submit_sale', { payload: entry.payload })
            await removeQueued(entry.local_id)
            synced++
          } catch (e) {
            if (e instanceof OfflineError) break // still down; keep the rest
            // Server rejected this sale (e.g. item deleted): keep it queued
            // and surface the reason rather than silently dropping a sale.
            this.notify(`Queued sale could not sync: ${e.message}`, true)
            break
          }
        }
        this.queuedCount = await queueCount()
        if (synced) this.notify(`Synced ${synced} offline sale${synced > 1 ? 's' : ''}`)
      } finally {
        this.syncing = false
      }
    },

    async refreshPromotions() {
      if (!this.posProfile || this.offline) return
      this.promotions = await call('lumenpos.api.session.get_promotions', {
        pos_profile: this.posProfile,
      })
    },

    async openRegister(openingFloat, extra = {}) {
      const result = await call('lumenpos.api.register.open_register', {
        pos_profile: this.posProfile,
        opening_float: openingFloat,
        ...extra,
      })
      // Control responses are not a live session — the caller renders the
      // choice / retry prompt. Only a real open-session dict becomes the
      // active register (otherwise registerOpen would flip true on garbage).
      if (result?.requires_choice || result?.requires_retry) return result
      this.registerSession = result
      return result
    },

    notify(message, isError = false) {
      this.toast = { message, isError }
      clearTimeout(this._toastTimer)
      this._toastTimer = setTimeout(() => (this.toast = null), 3200)
    },
  },
})
