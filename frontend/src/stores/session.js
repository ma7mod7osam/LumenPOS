// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import { defineStore } from 'pinia'
import { call, OfflineError } from '../api'
import { setCurrency } from '../format'
import {
  kvSet,
  kvGet,
  listQueue,
  removeQueued,
  queueCount,
  getPendingCustomer,
  listPendingCustomers,
  removePendingCustomer,
  patchSaleLog,
  pruneSaleLog,
} from '../offline'
import { syncFromErp } from '../theme'
import { useCatalogStore } from './catalog'

export const useSessionStore = defineStore('session', {
  state: () => ({
    loaded: false,
    error: null,
    user: null,
    userFullname: '',
    posProfile: null,
    invoiceMode: 'POS Invoice',
    availableProfiles: [],
    otherOpenRegisters: [],
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
    cashbackMode: 'Cashback',
    giftCardMode: 'Gift Card',
    salesPersons: [],
    allowNegativeStock: false,
    // Other currencies (LumenPOS Settings, General): which ones this till sells
    // in, each with its walk-in customer, cash drawer and the rate the shift
    // sells at. {enabled, company_currency, outlet_currency, outlet_rate,
    // currencies: [{currency, symbol, walk_in_customer, walk_in_name,
    // walk_in_group, cash_mode, show_equivalent, rate}]}
    multiCurrency: { enabled: 0, currencies: [] },
    settings: {
      delivery_apps: [],
      discount_limit_percent: 0,
      discount_approval_mode: 'Passcode only',
      can_approve_requests: false,
      restrict_returns_to_window: 0,
      return_window_days: 0,
      serial_scan_only: 0,
      enable_order_discount: 1,
      enable_service_charge: 0,
      service_charge_percent: 0,
      enable_price_checker: 1,
      enable_xreport: 1,
      enable_email_receipt: 0,
      enable_customer_display: 0,
      enable_till_lock: 0,
      auto_lock_minutes: 0,
      enable_quick_keys: 0,
      receipt_template: 'Standard',
      receipt_logo: '',
      receipt_header: '',
      receipt_footer: '',
      receipt_show_item_code: 0,
      receipt_show_barcode: 0,
      receipt_show_serial: 1,
      receipt_show_unit_price: 1,
      receipt_show_payments: 1,
      receipt_show_note: 1,
      receipt_show_tax_id: 0,
      receipt_tax_id: '',
      receipt_show_address: 0,
      receipt_address: '',
      receipt_show_terms: 0,
      receipt_terms: '',
    },
    locked: false,
    pinSet: true,
    bundles: [],
    permissions: {},
    pendingClosing: null,
    offline: false,
    queuedCount: 0,
    syncing: false,
    _heartbeat: null,
    toast: null,
  }),

  getters: {
    registerOpen: (s) => Boolean(s.registerSession),
    // The money the main drawer holds, and that change is given in: the
    // company currency (lumenpos.currency).
    localCurrency: (s) => s.multiCurrency?.company_currency || s.currency,
    // The currencies a sale can be switched to, besides the outlet's own.
    saleCurrencies: (s) =>
      s.multiCurrency?.enabled ? (s.multiCurrency.currencies || []).filter((c) => c.rate > 0) : [],
    // "Per cashier" scope: the takings land in the drawer of whoever OPENED the
    // shift, so only they may ring one up (no manager bypass, handover is
    // close + reopen). Empty when the shift is the outlet's.
    sellBlockedBy: (s) => {
      if ((s.settings?.shift_scope || 'Per outlet') !== 'Per cashier') return ''
      const owner = s.registerSession?.opened_by
      return owner && owner !== s.user ? owner : ''
    },
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
      // Multi-outlet users can switch outlets; remember the choice so a reload
      // keeps the same one. A stale/forbidden remembered outlet is cleared and
      // we fall back to the user's default.
      let target = posProfile
      if (!target) {
        try {
          target = localStorage.getItem('lumenpos_profile') || null
        } catch {
          target = null
        }
      }
      try {
        const data = await call('lumenpos.api.session.get_bootstrap', {
          pos_profile: target,
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
            this.startHeartbeat()
            this.notify('Offline, using cached data')
          } else {
            this.error =
              'No connection and no cached data yet. Connect once so the POS can cache its catalog.'
          }
        } else if (!posProfile && target) {
          // The remembered outlet is stale / no longer permitted, forget it and
          // boot the user's default outlet instead.
          try {
            localStorage.removeItem('lumenpos_profile')
          } catch {
            /* ignore */
          }
          return this.bootstrap(null)
        } else {
          this.error = e.message
        }
      }
      this.queuedCount = await queueCount().catch(() => 0)
      this.loaded = true
    },

    // Switch the active outlet (POS Profile) and reload everything for it. The
    // other outlet's shift stays open, this only changes what this screen shows.
    async switchProfile(name) {
      if (!name || name === this.posProfile) return
      try {
        localStorage.setItem('lumenpos_profile', name)
      } catch {
        /* ignore */
      }
      await this.bootstrap(name)
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
      this.otherOpenRegisters = data.other_open_registers || []
      this.printerConfigured = data.printer_configured || false
      this.printFormat = data.print_format || null
      this.storeCreditMode = data.store_credit_mode || 'Store Credit'
      this.cashbackMode = data.cashback_mode || 'Cashback'
      this.giftCardMode = data.gift_card_mode || 'Gift Card'
      this.salesPersons = data.sales_persons || []
      this.allowNegativeStock = Boolean(data.allow_negative_stock)
      this.multiCurrency = data.multi_currency || { enabled: 0, currencies: [] }
      this.settings = data.settings || { delivery_apps: [], discount_limit_percent: 0 }
      this.bundles = data.bundles || []
      this.permissions = data.permissions || {}
      this.pendingClosing = data.pending_closing || null
      this.pinSet = data.pin_set !== false
      syncFromErp(data.desk_theme) // follow ERPNext theme unless overridden in LumenPOS
      setCurrency(data.currency)
    },

    watchConnection() {
      window.addEventListener('online', () => this.reconnect())
      window.addEventListener('offline', () => {
        this.markOffline()
      })
      // Promotions edited on another terminal/tab show up when this till
      // regains focus, no reload needed.
      window.addEventListener('focus', () => {
        this.refreshPromotions().catch(() => {})
      })
      // navigator.onLine misses some failure modes; a failed API call also
      // flips `offline` via markOffline().
    },

    markOffline() {
      if (!this.offline) {
        this.offline = true
        this.notify('Connection lost, sales will be queued')
      }
      this.startHeartbeat()
    },

    // While offline, ask the server every few seconds whether it is back.
    // The browser's `online` event only knows about the network interface, and
    // waiting for the next sale to fail is why a cashier ends up reloading the
    // page to get the till trading again.
    startHeartbeat() {
      if (this._heartbeat) return
      this._heartbeat = setInterval(async () => {
        if (!this.offline) {
          this.stopHeartbeat()
          return
        }
        try {
          await call('lumenpos.api.session.ping', {}, { timeout: 4000 })
        } catch {
          return // still down, try again on the next tick
        }
        this.reconnect()
      }, 5000)
    },

    stopHeartbeat() {
      if (this._heartbeat) clearInterval(this._heartbeat)
      this._heartbeat = null
    },

    async reconnect() {
      try {
        await this.flushQueue()
        await this.bootstrap(this.posProfile)
        if (!this.offline) {
          this.stopHeartbeat()
          this.notify('Back online')
          this.refreshStockAfterOutage()
        }
      } catch {
        /* still offline, the heartbeat keeps trying */
      }
    },

    // Every till takes a fresh copy of the whole catalogue as soon as it is
    // back, so the stock it shows includes what the OTHER tills sold while the
    // connection was down. Once now, and once more a minute later: another
    // till may still be uploading its own queued sales when this one returns.
    refreshStockAfterOutage() {
      const catalog = useCatalogStore()
      catalog.cacheFullCatalog()
      clearTimeout(this._stockRefreshTimer)
      this._stockRefreshTimer = setTimeout(() => {
        if (!this.offline) catalog.cacheFullCatalog()
      }, 60000)
    },

    async flushQueue() {
      if (this.syncing) return
      this.syncing = true
      const localMap = {} // offline temp customer id -> resolved real name
      try {
        const queue = await listQueue()
        let synced = 0
        let failed = 0
        for (const entry of queue) {
          const key = entry.payload?.idempotency_key
          try {
            let payload = entry.payload
            // Reconcile an offline-created customer: resolve its temp id to a
            // real one (match existing by mobile, else create) and remap the
            // sale. resolve_pending_customer is idempotent, so a retry is safe.
            const cust = payload.customer
            if (typeof cust === 'string' && cust.startsWith('__local__')) {
              if (!localMap[cust]) {
                const pending = await getPendingCustomer(cust)
                if (!pending) throw new Error('offline customer record is missing')
                const res = await call('lumenpos.api.catalog.resolve_pending_customer', {
                  payload: pending.payload,
                })
                localMap[cust] = res.name
              }
              payload = { ...payload, customer: localMap[cust] }
            }
            const receipt = await call('lumenpos.api.sales.submit_sale', { payload })
            // The server's figure replaces the estimate the till made offline.
            useCatalogStore().applyStock(receipt?.stock_after)
            await removeQueued(entry.local_id)
            // Log it as uploaded, with the real server invoice number so the
            // cashier can see exactly where the offline sale landed.
            await patchSaleLog(key, {
              status: 'synced',
              receipt: (receipt && receipt.name) || null,
              synced_at: new Date().toISOString(),
              error: null,
            }).catch(() => {})
            synced++
          } catch (e) {
            if (e instanceof OfflineError) break // still down; keep the rest
            // Server REJECTED this sale (e.g. item deleted, price changed). Keep
            // it queued and record WHY, but move on so one bad sale can't block
            // every good sale behind it. It retries on the next flush.
            await patchSaleLog(key, {
              status: 'failed',
              error: e.message,
              error_at: new Date().toISOString(),
            }).catch(() => {})
            this.notify(`A queued sale was rejected: ${e.message}`, true)
            failed++
            continue
          }
        }
        // Prune pending customers no remaining queued sale references (kept ones
        // re-resolve safely on the next flush, resolution is idempotent).
        try {
          const remaining = await listQueue()
          const stillRef = new Set(remaining.map((e) => e.payload?.customer).filter(Boolean))
          for (const p of await listPendingCustomers()) {
            if (!stillRef.has(p.temp_id)) await removePendingCustomer(p.temp_id).catch(() => {})
          }
        } catch {
          /* best-effort cleanup */
        }
        this.queuedCount = await queueCount()
        pruneSaleLog().catch(() => {})
        if (synced) this.notify(`Synced ${synced} offline sale${synced > 1 ? 's' : ''}`)
        if (failed)
          this.notify(
            `${failed} offline sale${failed > 1 ? 's' : ''} still need attention. See the offline sales log`,
            true
          )
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
      // Opening is always a fresh shift now, the server never returns a
      // resume/retry control object, so the result IS the live session.
      this.registerSession = result
      return result
    },

    // Re-read the offline queue depth from IndexedDB. Called before closing a
    // register: queued sales belong to THIS shift's drawer, and closing before
    // they upload pushes them onto the next shift.
    async refreshQueueCount() {
      this.queuedCount = await queueCount().catch(() => this.queuedCount)
      return this.queuedCount
    },

    lockTill() {
      if (this.settings?.enable_till_lock) this.locked = true
    },

    notify(message, isError = false) {
      this.toast = { message, isError }
      clearTimeout(this._toastTimer)
      this._toastTimer = setTimeout(() => (this.toast = null), 3200)
    },
  },
})
