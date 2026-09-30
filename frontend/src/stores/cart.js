// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
import { defineStore } from 'pinia'
import { call, OfflineError } from '../api'
import {
  queueEntry,
  queueCount,
  getCatalogItems,
  newId,
  logSale,
  putShiftSale,
  requestBackgroundUpload,
  markReturned,
} from '../offline'
import { evaluatePromotions, suggestOffers, matchingIndexes } from '../promotions'
import { frappeRound, fromReceipt, returnGroups } from '../refund'
import { money } from '../format'
import { locale } from '../i18n'
import { useCatalogStore } from './catalog'
import { useSessionStore } from './session'

function round2(n) {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

export const useCartStore = defineStore('cart', {
  state: () => ({
    lines: [], // {item_code, item_name, item_group, brand, qty, price, manual_discount_percent}
    customer: null, // {name, customer_name, customer_group}
    wallet: null, // {loyalty_points, conversion_factor, store_credit}
    couponCodes: [],
    salesPerson: null, // persists across sales (shift-based)
    appType: null, // delivery-app channel (null = walk-in)
    orderId: '',
    orderDiscountPercent: 0, // whole-cart discount (Settings → Features)
    discountPasscode: null, // manager passcode for over-limit discounts
    discountRequest: null, // approved POS Discount Request name (role approval)
    activePriceList: null,
    note: '',
    // An exchange in progress: what is coming back and against which sale. The
    // cart itself holds what the customer is taking INSTEAD, so the sell screen
    // behaves exactly as usual while one is open, and the pair posts together
    // at payment. {invoice, items, serials, reason, request, value, customer}
    exchange: null,
    submitting: false,
    // {signature, key}: the idempotency key of the sale being paid for. A sale
    // has it from its FIRST attempt, and the same basket tried again keeps it,
    // so a sale whose answer was lost on the way back (and that the till then
    // queued, or the cashier retried) can never post twice.
    _saleKey: null,
    _quoteCache: null, // {signature, at, promise} see quote()
    _quoteTimer: null,
  }),

  getters: {
    // Promotions only see NON-bundle lines (bundle pricing is final);
    // results are remapped back onto the full line list.
    _promoView(state) {
      const session = useSessionStore()
      const idx = []
      const items = []
      state.lines.forEach((line, i) => {
        if (!line.bundle_key) {
          idx.push(i)
          items.push(line)
        }
      })
      return {
        idx,
        cart: {
          customer_group: state.customer?.customer_group || null,
          pos_profile: session.posProfile,
          coupon_codes: state.couponCodes,
          items,
        },
      }
    },

    evaluation(state) {
      const session = useSessionStore()
      const { idx, cart } = this._promoView
      const raw = evaluatePromotions(cart, session.promotions)
      const line_discounts = state.lines.map(() => 0)
      const line_promotions = state.lines.map(() => [])
      idx.forEach((orig, k) => {
        line_discounts[orig] = raw.line_discounts[k]
        line_promotions[orig] = raw.line_promotions[k]
      })
      return { ...raw, line_discounts, line_promotions }
    },

    suggestions() {
      const session = useSessionStore()
      return suggestOffers(this._promoView.cart, session.promotions)
    },

    // Suggestions placed on the cart line they relate to, a line can carry
    // several (one item, many promotions). Basket-level ones stay separate.
    lineSuggestions(state) {
      const { idx } = this._promoView
      const perLine = state.lines.map(() => [])
      for (const suggestion of this.suggestions) {
        for (const filteredIdx of suggestion.for_lines || []) {
          const orig = idx[filteredIdx]
          if (orig !== undefined) perLine[orig].push(suggestion)
        }
      }
      return perLine
    },

    basketSuggestions() {
      return this.suggestions.filter((s) => !(s.for_lines || []).length)
    },

    // Per-line bundle discounts (cent-correct, mirrors the server math)
    bundleBreakdown(state) {
      const groups = {}
      state.lines.forEach((line, i) => {
        if (line.bundle_key) {
          const group = (groups[line.bundle_key] ??= {
            idxs: [],
            title: line.bundle_title,
            price: line.bundle_price,
          })
          group.idxs.push(i)
        }
      })
      const discounts = state.lines.map(() => 0)
      const applied = []
      for (const [key, group] of Object.entries(groups)) {
        const natural = group.idxs.reduce(
          (sum, i) => sum + state.lines[i].price * state.lines[i].qty,
          0
        )
        const saving = round2(Math.max(0, natural - (group.price || 0)))
        const allocated = group.idxs.every((i) => state.lines[i].bundle_allocated != null)
        if (allocated) {
          // Manager-defined split: discount each line down to its share
          for (const i of group.idxs) {
            discounts[i] = round2(
              state.lines[i].price * state.lines[i].qty - state.lines[i].bundle_allocated
            )
          }
          applied.push({ key, title: group.title, savings: round2(Math.max(0, natural - (group.price || 0))) })
          continue
        }
        if (saving > 0 && natural > 0) {
          const shares = {}
          for (const i of group.idxs) {
            shares[i] = round2(
              (saving * (state.lines[i].price * state.lines[i].qty)) / natural
            )
          }
          const delta = round2(saving - Object.values(shares).reduce((a, b) => a + b, 0))
          if (delta) {
            const biggest = group.idxs.reduce((a, b) => (shares[a] >= shares[b] ? a : b))
            shares[biggest] = round2(shares[biggest] + delta)
          }
          for (const i of group.idxs) discounts[i] = shares[i]
        }
        applied.push({ key, title: group.title, savings: saving })
      }
      return { discounts, applied }
    },

    bundleSavings() {
      // Sum the per-line discounts (not the applied list) so allocation
      // splits, including lines adjusted upward, always net correctly
      return round2(
        this.bundleBreakdown.discounts.reduce((sum, amount) => sum + amount, 0)
      )
    },

    subtotal: (state) =>
      state.lines.reduce((sum, l) => sum + l.price * l.qty, 0),

    manualDiscountTotal(state) {
      const promoDiscounts = this.evaluation.line_discounts
      return state.lines.reduce((sum, l, i) => {
        const afterPromo = l.price * l.qty - (promoDiscounts[i] || 0)
        return sum + (afterPromo * (l.manual_discount_percent || 0)) / 100
      }, 0)
    },

    promoSavings() {
      return this.evaluation.total_savings
    },

    // Whole-cart discount, applied AFTER line-level discounts (promo + manual
    // + bundle). Gated by the Settings → Features toggle; disabling it makes
    // any lingering percent inert. Mirrored on the server in _line_discounts.
    orderDiscountTotal(state) {
      const session = useSessionStore()
      if (!session.settings?.enable_order_discount) return 0
      const pct = state.orderDiscountPercent || 0
      if (pct <= 0) return 0
      const base = Math.max(
        0,
        this.subtotal - this.promoSavings - this.manualDiscountTotal - this.bundleSavings
      )
      return round2((base * pct) / 100)
    },

    // Net of all discounts, before exclusive taxes
    netTotal() {
      return Math.max(
        0,
        this.subtotal -
          this.promoSavings -
          this.manualDiscountTotal -
          this.bundleSavings -
          this.orderDiscountTotal
      )
    },

    // Optional flat-percent service charge / tip, added AFTER taxes as its own
    // line (so it is not itself taxed, matches the common "tip line" model).
    // The percent is server-authoritative (read from Settings), never the cart.
    serviceCharge() {
      const session = useSessionStore()
      if (!session.settings?.enable_service_charge) return 0
      const pct = session.settings?.service_charge_percent || 0
      if (pct <= 0) return 0
      return round2((this.netTotal * pct) / 100)
    },

    // Mirror ERPNext's tax math on the profile's template so the displayed
    // total equals the server's grand total. Inclusive rows are shown for
    // information; exclusive rows add to what the customer pays.
    taxBreakdown() {
      const session = useSessionStore()
      const net = this.netTotal
      const exclusive = []
      const included = []
      let running = net
      for (const tax of session.taxes || []) {
        let amount
        if (tax.charge_type === 'Actual') {
          amount = round2(tax.tax_amount || 0)
        } else {
          const base = tax.charge_type === 'On Previous Row Total' ? running : net
          amount = round2((base * (tax.rate || 0)) / 100)
        }
        if (!amount) continue
        if (tax.included) {
          // back the tax out of the (inclusive) net for display
          included.push({
            description: tax.description,
            amount: round2(net - net / (1 + (tax.rate || 0) / 100)),
          })
        } else {
          exclusive.push({ description: tax.description, amount })
          running = round2(running + amount)
        }
      }
      return {
        exclusive,
        included,
        exclusiveTotal: round2(exclusive.reduce((sum, t) => sum + t.amount, 0)),
      }
    },

    total() {
      return round2(
        this.netTotal + this.taxBreakdown.exclusiveTotal + this.serviceCharge
      )
    },

    // Per-unit discount of each line, worked out as the server does
    // (sales._line_discounts): offers and bundles, a share of a basket
    // discount, then the line's manual % and the whole-cart %. A sale queued
    // offline keeps each line's rate from it, so it can be taken back without
    // a connection at the rate ERPNext will post (refund.js).
    unitDiscounts(state) {
      const session = useSessionStore()
      const rule = session.settings?.rounding?.[session.currency] || {}
      const r2 = (x) => frappeRound(x, 2, rule.method, rule.commercial)
      const whole = state.lines.map(
        (l, i) => (this.evaluation.line_discounts[i] || 0) + (this.bundleBreakdown.discounts[i] || 0)
      )
      const basket = this.evaluation.basket_discount || 0
      if (basket > 0) {
        const eligible = state.lines.map((l, i) => i).filter((i) => !state.lines[i].bundle_key)
        const net = {}
        for (const i of eligible) net[i] = state.lines[i].price * state.lines[i].qty - whole[i]
        const totalNet = eligible.reduce((sum, i) => sum + (net[i] > 0 ? net[i] : 0), 0)
        if (totalNet > 0) {
          let spread = 0
          for (const i of eligible) {
            if (net[i] <= 0) continue
            const share = r2((basket * net[i]) / totalNet)
            whole[i] += share
            spread += share
          }
          const rest = r2(basket - spread)
          if (rest && eligible.length) {
            whole[eligible.reduce((a, b) => (net[a] >= net[b] ? a : b))] += rest
          }
        }
      }
      const orderPct = state.orderDiscountPercent || 0
      return state.lines.map((l, i) => {
        const promoPerUnit = whole[i] / (l.qty || 1)
        const bundle = Boolean(l.bundle_key)
        let unit = promoPerUnit + ((l.price - promoPerUnit) * (bundle ? 0 : l.manual_discount_percent || 0)) / 100
        if (orderPct && !bundle) unit += ((l.price - unit) * orderPct) / 100
        return Math.max(0, unit)
      })
    },

    itemCount: (state) => state.lines.reduce((sum, l) => sum + l.qty, 0),

    // The largest single discount on the sale, the per-line max OR the
    // whole-cart percent, whichever is bigger. Drives the approval gate so an
    // order-level discount is policed by the same limit as a line discount.
    maxManualDiscount: (state) =>
      Math.max(
        state.lines.reduce((max, l) => Math.max(max, l.manual_discount_percent || 0), 0),
        state.orderDiscountPercent || 0
      ),

    needsDiscountApproval(state) {
      const session = useSessionStore()
      const limit = session.settings?.discount_limit_percent || 0
      return (
        limit > 0 &&
        this.maxManualDiscount > limit &&
        !state.discountPasscode &&
        !state.discountRequest
      )
    },

    activeApp(state) {
      const session = useSessionStore()
      return (session.settings?.delivery_apps || []).find(
        (app) => app.app_name === state.appType
      )
    },

    // What this sale is in (lumenpos.currency). A customer billed in another
    // currency buys in it, at the rate the shift sells at. The cart keeps
    // adding up in the outlet's currency, exactly as before, and `factor`
    // converts for display; the server's quote is the authority at payment.
    // `blocked`: the customer is billed in a currency this till can't sell in
    // (the server refuses the sale, the cart says why up front).
    saleCurrency(state) {
      const session = useSessionStore()
      const mc = session.multiCurrency || {}
      const outlet = mc.outlet_currency || session.currency
      const local = {
        currency: outlet,
        foreign: false,
        blocked: false,
        factor: 1,
        rate: mc.outlet_rate || 1,
        row: null,
      }
      const billed = state.customer?.default_currency
      if (!billed || billed === outlet) return local
      const row = (mc.currencies || []).find((c) => c.currency === billed)
      if (!mc.enabled || !row || !row.rate || !mc.outlet_rate) {
        return { ...local, currency: billed, foreign: true, blocked: true }
      }
      return {
        currency: billed,
        foreign: true,
        blocked: false,
        factor: mc.outlet_rate / row.rate,
        rate: row.rate,
        row,
      }
    },

    // An amount the cart added up (outlet currency), in the sale's currency.
    inSale() {
      const factor = this.saleCurrency.blocked ? 1 : this.saleCurrency.factor
      return (amount) => round2((amount || 0) * factor)
    },

    // ...and formatted, for the screen.
    show() {
      const sale = this.saleCurrency
      const code = sale.blocked ? null : sale.currency
      return (amount) => money(this.inSale(amount), code)
    },

    // The sale's customer is a currency's own walk-in ("Walk-in ZWG"): its
    // prices are the ones the till keeps for selling in that currency offline.
    currencyWalkIn(state) {
      const session = useSessionStore()
      const name = state.customer?.name
      return Boolean(name) && session.saleCurrencies.some((c) => c.walk_in_customer === name)
    },

    // Only a walk-in can be switched to another currency: a named customer
    // buys in their own Billing Currency (ERPNext, Customer).
    currencySwitchable(state) {
      const session = useSessionStore()
      if (!session.saleCurrencies.length || state.appType || state.exchange) return false
      const name = state.customer?.name
      return (
        !name ||
        name === session.defaultCustomer ||
        session.saleCurrencies.some((c) => c.walk_in_customer === name)
      )
    },
  },

  actions: {
    // For serialized items pass the scanned serial; qty is always locked to
    // the number of serials on the line.
    addItem(item, serial = null) {
      if (item.has_serial_no && !serial) return false // strict: no serial, no sale
      // never merge into a bundle line, bundle pricing is per-instance
      const existing = this.lines.find(
        (l) => l.item_code === item.item_code && !l.bundle_key
      )
      if (existing) {
        if (item.has_serial_no) {
          if (existing.serial_nos.includes(serial)) return false
          existing.serial_nos.push(serial)
          existing.qty = existing.serial_nos.length
        } else {
          existing.qty += 1
        }
      } else {
        this.lines.push({
          item_code: item.item_code,
          item_name: item.item_name,
          item_group: item.item_group,
          brand: item.brand,
          tags: item.tags || [],
          barcode: item.barcode || null,
          warranty_days: item.warranty_days || 0,
          has_serial_no: item.has_serial_no || 0,
          serial_nos: serial ? [serial] : [],
          qty: 1,
          price: item.price || 0,
          // The outlet's own price, for a sale switched back from another
          // currency while offline (_offlineCurrencyPrices).
          catalog_price: item.price || 0,
          standard_price: item.standard_price ?? item.price ?? 0,
          manual_discount_percent: 0,
        })
      }
      // A price book or app channel may price this item differently
      if (this.appType || this.customer) this.reprice()
      return true
    },

    // One tap adds the whole bundle: components as SEPARATE lines (so each
    // can be returned individually), tagged + priced as one bundle instance.
    async addBundle(bundle) {
      const session = useSessionStore()
      this._bundleSeq = (this._bundleSeq || 0) + 1
      const key = `${bundle.name}#${this._bundleSeq}`

      const codes = bundle.items.map((component) => component.item_code)
      const info = {}
      for (const cached of await getCatalogItems(codes).catch(() => [])) {
        info[cached.item_code] = cached
      }
      if (!session.offline) {
        try {
          const data = await call('lumenpos.api.catalog.get_prices', {
            pos_profile: session.posProfile,
            item_codes: codes,
            customer_group: this.customer?.customer_group || null,
            app_type: this.appType,
            customer: this.customer?.name || null,
          })
          for (const [code, price] of Object.entries(data.prices || {})) {
            info[code] = { ...(info[code] || {}), price }
          }
        } catch {
          /* fall back to cached prices */
        }
      }

      const allAllocated = bundle.items.every((component) => component.allocated_amount)
      for (const component of bundle.items) {
        const detail = info[component.item_code] || {}
        if (detail.has_serial_no) {
          throw new Error(
            `${component.item_name}: serialized items cannot be sold in bundles`
          )
        }
        this.lines.push({
          item_code: component.item_code,
          item_name: detail.item_name || component.item_name,
          item_group: detail.item_group || null,
          brand: detail.brand || null,
          tags: detail.tags || [],
          barcode: detail.barcode || null,
          has_serial_no: 0,
          serial_nos: [],
          qty: component.qty,
          price: detail.price || 0,
          catalog_price: detail.price || 0,
          manual_discount_percent: 0,
          bundle_key: key,
          bundle_name: bundle.name,
          bundle_title: bundle.title,
          bundle_price: bundle.bundle_price,
          // manager-defined split of the bundle price (whole-row amount)
          bundle_allocated: allAllocated ? component.allocated_amount : null,
        })
      }
      return key
    },

    removeBundle(key) {
      this.lines = this.lines.filter((line) => line.bundle_key !== key)
    },

    // "Sell in dollars": the sale goes to that currency's walk-in customer,
    // who is billed in it; back to the outlet's currency clears it again.
    async setSaleCurrency(code) {
      const session = useSessionStore()
      const row = session.saleCurrencies.find((c) => c.currency === code)
      if (!row) return this.setCustomer(null)
      return this.setCustomer({
        name: row.walk_in_customer,
        customer_name: row.walk_in_name || row.walk_in_customer,
        customer_group: row.walk_in_group || null,
        default_currency: row.currency,
      })
    },

    async setChannel(appName) {
      this.appType = appName || null
      if (!this.appType) this.orderId = ''
      await this.reprice()
    },

    // Re-resolve cart prices when the active price list changes (customer
    // with a price book, or a delivery-app channel). Server-authoritative.
    async reprice() {
      const session = useSessionStore()
      if (!this.lines.length) return
      if (session.offline) {
        this._offlineCurrencyPrices()
        return
      }
      try {
        // The customer too: one billed in another currency may have their
        // own price list in it (lumenpos.currency).
        const data = await call('lumenpos.api.catalog.get_prices', {
          pos_profile: session.posProfile,
          item_codes: this.lines.map((l) => l.item_code),
          customer_group: this.customer?.customer_group || null,
          app_type: this.appType,
          customer: this.customer?.name || null,
        })
        this.activePriceList = data.price_list
        for (const line of this.lines) {
          const listed = data.prices[line.item_code]
          const std = data.standard_prices?.[line.item_code]
          // A typed price stays: the list's goes where clearing it returns to.
          if (line.price_override != null) {
            if (listed !== undefined) line.price_before_override = listed
            line.standard_before_override = std != null ? std : line.price_before_override
            continue
          }
          if (listed !== undefined) line.price = listed
          line.standard_price = std != null ? std : line.price
        }
      } catch {
        /* keep current prices; server re-resolves at submit anyway */
      }
    },

    // Offline, a sale in another currency takes the prices of that currency's
    // walk-in's own price list, as the server will (lumenpos.currency
    // .offline_prices), and a sale back in the outlet's currency the prices
    // the lines came with.
    _offlineCurrencyPrices() {
      const session = useSessionStore()
      const sale = this.saleCurrency
      const own = sale.foreign && !sale.blocked && this.currencyWalkIn
        ? (session.offlinePrices || {})[sale.currency] || {}
        : null
      for (const line of this.lines) {
        if (line.price_override != null) continue
        if (line.catalog_price == null) line.catalog_price = line.price
        const price = own ? own[line.item_code] : null
        line.price = price ? Math.round((price / sale.factor) * 1e6) / 1e6 : line.catalog_price
      }
    },

    // A price typed for one line, where the outlet allows it and the person
    // may (session.permissions.can_change_price; the server checks again):
    // in the sale's currency, it replaces the line's price before offers.
    // Empty goes back to the list's price.
    setLinePrice(index, value) {
      const line = this.lines[index]
      if (!line || line.bundle_key) return
      const text = String(value ?? '').trim().replace(',', '.')
      if (text === '') {
        this._clearPrice(line)
        return
      }
      const typed = Math.max(0, Math.round((Number(text) || 0) * 100) / 100)
      if (line.price_override == null) {
        line.price_before_override = line.price
        line.standard_before_override = line.standard_price
      }
      const factor = this.saleCurrency.blocked ? 1 : this.saleCurrency.factor || 1
      line.price_override = typed
      line.price = typed / factor
      line.standard_price = line.price
    },

    _clearPrice(line) {
      if (line.price_override == null) return
      line.price = line.price_before_override ?? line.price
      line.standard_price = line.standard_before_override ?? line.price
      line.price_override = null
    },

    hasSerial(serial) {
      return this.lines.some((l) => (l.serial_nos || []).includes(serial))
    },

    removeSerial(index, serial) {
      const line = this.lines[index]
      line.serial_nos = (line.serial_nos || []).filter((s) => s !== serial)
      line.qty = line.serial_nos.length
      if (!line.qty) this.lines.splice(index, 1)
    },

    setQty(index, qty) {
      if (this.lines[index]?.has_serial_no) return // qty is locked to serial count
      qty = Number(qty)
      if (!qty || qty <= 0) this.lines.splice(index, 1)
      else this.lines[index].qty = qty
    },

    removeLine(index) {
      this.lines.splice(index, 1)
    },

    async setCustomer(customer) {
      // A typed price is in the sale's currency: a customer who buys in
      // another one takes the lines back to their list prices first.
      const before = this.saleCurrency.currency
      this.customer = customer
      if (this.saleCurrency.currency !== before) {
        for (const line of this.lines) this._clearPrice(line)
      }
      this.wallet = null
      this.reprice() // customer group may activate a price book
      if (!customer) return
      const session = useSessionStore()
      if (session.offline) return // wallet needs the server
      try {
        this.wallet = await call('lumenpos.api.loyalty.get_wallet', {
          customer: customer.name,
          company: session.company,
        })
      } catch {
        /* wallet display is optional */
      }
    },

    clear() {
      this.lines = []
      this.customer = null
      this.wallet = null
      this.couponCodes = []
      this.appType = null
      this.orderId = ''
      this.orderDiscountPercent = 0
      this.discountPasscode = null
      this.discountRequest = null
      this.activePriceList = null
      this.note = ''
      this._saleKey = null
      // salesPerson intentionally kept, it's the staff member on shift
    },

    // The key for paying this basket: kept while the basket stays the same.
    _keyForSale() {
      const signature = JSON.stringify(this._basePayload())
      if (!this._saleKey || this._saleKey.signature !== signature) {
        this._saleKey = { signature, key: newId() }
      }
      return this._saleKey.key
    },

    // Keep a posted sale on this device for the rest of the shift, so it can
    // be taken back without a connection. Best effort, never holds a sale up.
    async _keepShiftSale(key, receipt) {
      const session = useSessionStore()
      if (!key || !session.registerSession?.name || !receipt?.name) return
      try {
        await putShiftSale({
          key,
          session: session.registerSession.name,
          pos_profile: session.posProfile,
          user: session.user,
          at: new Date().toISOString(),
          returned: {},
          ...fromReceipt(receipt),
        })
      } catch {
        /* a convenience for later */
      }
    },

    async addCoupon(code) {
      code = (code || '').trim().toUpperCase()
      if (!code) return
      if (this.couponCodes.includes(code)) {
        throw new Error(`Coupon ${code} is already applied`)
      }
      const session = useSessionStore()
      // Coupon promos are never in the bootstrap payload, fetch via the
      // validation endpoint (throws on a bad code) and merge it in.
      const promo = await call('lumenpos.api.session.check_coupon', {
        pos_profile: session.posProfile,
        code,
      })
      if (!session.promotions.some((p) => p.name === promo.name)) {
        session.promotions.push(promo)
      }
      this.couponCodes.push(code)
      return promo
    },

    removeCoupon(code) {
      this.couponCodes = this.couponCodes.filter((c) => c !== code)
    },

    // Whole-cart discount. Clamped to 0 to 100; changing it invalidates any
    // previously granted over-limit approval so a higher value must be
    // re-approved (mirrors the per-line discount flow).
    setOrderDiscount(percent) {
      const pct = Math.max(0, Math.min(100, Number(percent) || 0))
      if (pct !== this.orderDiscountPercent) {
        this.discountPasscode = null
        this.discountRequest = null
      }
      this.orderDiscountPercent = pct
    },

    // Cart fields the server needs to price the sale, WITHOUT payment/auth
    // details. Shared by submit() and quoteTotal() so the server prices both
    // identically.
    _basePayload() {
      const session = useSessionStore()
      return {
        pos_profile: session.posProfile,
        customer: this.customer?.name || null,
        items: this.lines.map((l) => ({
          item_code: l.item_code,
          qty: l.qty,
          manual_discount_percent: l.manual_discount_percent || 0,
          // A price typed at the till, in the sale's currency (setLinePrice).
          price_override: l.price_override ?? null,
          serial_nos: l.serial_nos || [],
          bundle_key: l.bundle_key || null,
        })),
        coupon_codes: this.couponCodes,
        sales_person: this.salesPerson,
        app_type: this.appType,
        order_id: this.orderId || null,
        order_discount_percent: this.orderDiscountPercent || 0,
        note: this.note || null,
      }
    },

    // Authoritative amount to collect, computed by the SERVER with the same math
    // as submit, so the till charges exactly what the posted invoice shows (no
    // phantom rounding "change"). Returns null offline / on error so the caller
    // falls back to the client-side cart total.
    // --- exchange -----------------------------------------------------------
    // Start one: the goods coming back are already picked (and approved, if the
    // shop required it), the cart is cleared for what the customer takes
    // instead. Nothing has posted yet, and nothing does until payment.
    startExchange(picked) {
      this.clear()
      this.exchange = picked
      if (picked?.customer) {
        this.customer = { name: picked.customer, customer_name: picked.customer_name }
      }
    },

    cancelExchange() {
      this.exchange = null
      this.clear()
    },

    // The credit note and the replacement sale post together, in one request:
    // there is no moment where the shop has taken the goods back without
    // handing over the replacement.
    async submitExchange(payments, refundMode, redeemLoyaltyPoints, giftCards) {
      const session = useSessionStore()
      if (session.offline) {
        throw new Error('An exchange needs a connection, it cannot be queued offline')
      }
      const payload = {
        ...this._basePayload(),
        original_invoice: this.exchange.invoice,
        return_items: this.exchange.items,
        serials: this.exchange.serials,
        return_reason: this.exchange.reason,
        return_request: this.exchange.request,
        refund_mode: refundMode || null,
        payments,
        gift_cards: giftCards || [],
        redeem_loyalty_points: redeemLoyaltyPoints || 0,
        discount_passcode: this.discountPasscode,
        discount_request: this.discountRequest,
        idempotency_key: newId(),
      }
      this.submitting = true
      try {
        const result = await call('lumenpos.api.exchanges.submit_exchange', { payload })
        // What came back moves too, not only what went out (0.56.1).
        useCatalogStore().applyStock({ ...(result?.return?.stock_after || {}), ...(result?.sale?.stock_after || {}) })
        markReturned(this.exchange.invoice, this.exchange.items)
        this.exchange = null
        this.clear()
        return result
      } finally {
        this.submitting = false
      }
    },

    // Asked AHEAD of the payment screen (see prefetchQuote), so pressing Pay
    // does not wait on a round trip: on a till in Riyadh talking to a server in
    // Mumbai every request costs about 190 ms before any work happens. The
    // answer is kept against the exact basket that produced it, and only for a
    // minute, because a promotion can start or end in between.
    async quote() {
      const payload = this._basePayload()
      const signature = JSON.stringify(payload)
      const cached = this._quoteCache
      if (cached && cached.signature === signature && Date.now() - cached.at < 60000) {
        return cached.promise
      }
      const promise = call('lumenpos.api.sales.quote_sale', { payload }).catch(() => null)
      this._quoteCache = { signature, at: Date.now(), promise }
      // A failed quote is not an answer, don't keep it (the till falls back to
      // its own total and tries again next time).
      promise.then((res) => {
        if (res == null && this._quoteCache && this._quoteCache.promise === promise) {
          this._quoteCache = null
        }
      })
      return promise
    },

    // Quote while the cashier is still scanning. Debounced, so a basket being
    // built quickly asks once, when it settles.
    prefetchQuote() {
      clearTimeout(this._quoteTimer)
      if (!this.lines.length) return
      this._quoteTimer = setTimeout(() => {
        this.quote().catch(() => {})
      }, 400)
    },

    async quoteTotal() {
      const res = await this.quote()
      return res && typeof res.payable === 'number' ? res.payable : null
    },

    async submit(payments, redeemLoyaltyPoints = 0, giftCards = []) {
      const payload = {
        ...this._basePayload(),
        gift_cards: giftCards,
        payments,
        redeem_loyalty_points: redeemLoyaltyPoints || 0,
        discount_passcode: this.discountPasscode,
        discount_request: this.discountRequest,
        idempotency_key: this._keyForSale(),
      }
      this.submitting = true
      try {
        const receipt = await call('lumenpos.api.sales.submit_sale', { payload })
        useCatalogStore().applyStock(receipt?.stock_after)
        this._keepShiftSale(payload.idempotency_key, receipt)
        this.clear()
        return receipt
      } catch (e) {
        if (e instanceof OfflineError) {
          return this._queueOffline(payload, payments)
        }
        throw e
      } finally {
        this.submitting = false
      }
    },

    async _queueOffline(payload, payments) {
      const session = useSessionStore()
      // A sale in another currency is priced at the rate the shift fixed as
      // it opened, which the till knows, and the server posts it only at that
      // rate (lumenpos.currency.assert_till_rate). A named customer billed in
      // another currency may have prices of their own the till does not keep.
      const sale = this.saleCurrency
      if (sale.foreign) {
        if (sale.blocked || !sale.rate) {
          throw new Error('There is no exchange rate for this currency yet, so a sale in it needs a connection')
        }
        if (!this.currencyWalkIn) {
          throw new Error("A customer billed in another currency needs a connection. Sell to that currency's walk-in instead")
        }
        payload.currency_rate = sale.rate
      }
      if (payload.items.some((i) => (i.serial_nos || []).length)) {
        throw new Error('Serialized items need a connection, they cannot be queued offline')
      }
      if (payload.app_type) {
        throw new Error('Delivery-app sales need a connection, they cannot be queued offline')
      }
      if ((payload.gift_cards || []).length) {
        throw new Error('Gift card payments need a connection. Remove them and retry')
      }
      if (payload.redeem_loyalty_points > 0) {
        throw new Error('Loyalty redemption needs a connection. Remove it and retry')
      }
      if (payments.some((p) => p.mode_of_payment === session.storeCreditMode)) {
        throw new Error('Store credit needs a connection. Remove it and retry')
      }
      if (payments.some((p) => p.mode_of_payment === session.cashbackMode)) {
        throw new Error('Cashback needs a connection. Remove it and retry')
      }
      session.markOffline()
      // Idempotency key so a retried sync (lost ACK) can't post a duplicate.
      payload.idempotency_key = payload.idempotency_key || newId()
      await queueEntry('sale', payload, locale.value)
      session.queuedCount = await queueCount()
      this._keepQueuedSale(payload, payments, sale)
      if (session.settings?.background_upload) requestBackgroundUpload()
      // No server answer offline, so take the sold quantity off the tiles here.
      // The real figure lands when the queue syncs.
      useCatalogStore().applyStockDelta(payload.items)

      // Client-side receipt stand-in; the real invoice posts when the queue
      // syncs. Totals here exclude server-side taxes. A sale in another
      // currency is shown in it, with its local value and the rate.
      const paid = payments.reduce((sum, p) => sum + p.amount, 0)
      const inSale = sale.foreign ? this.inSale : (amount) => amount
      const saleTotal = inSale(this.total)

      // Durable log entry so the cashier can later see this sale went out and
      // what became of it on reconnect (pending → synced with the real invoice
      // no., or failed with a reason). Best-effort, never block the sale.
      logSale({
        key: payload.idempotency_key,
        queued_at: new Date().toISOString(),
        customer_name:
          this.customer?.customer_name || session.defaultCustomerName || 'Walk-in',
        item_count: this.lines.length,
        total: saleTotal,
        currency: sale.foreign ? sale.currency : session.currency,
        paid,
        status: 'pending',
      }).catch(() => {})
      const receipt = {
        offline: true,
        name: `QUEUED-${new Date().toISOString().replace(/\D/g, '').slice(0, 14)}`,
        company: session.company,
        customer_name: this.customer?.customer_name || session.defaultCustomerName || 'Walk-in',
        posting_date: new Date().toISOString().slice(0, 10),
        posting_time: new Date().toTimeString().slice(0, 8),
        currency: sale.foreign ? sale.currency : session.currency,
        items: this.lines.map((l, i) => {
          const promoDiscount = this.evaluation.line_discounts[i] || 0
          const lineTotal = inSale(
            (l.price * l.qty - promoDiscount) * (1 - (l.manual_discount_percent || 0) / 100)
          )
          return {
            item_code: l.item_code,
            item_name: l.item_name,
            qty: l.qty,
            rate: l.qty ? lineTotal / l.qty : 0,
            amount: lineTotal,
          }
        }),
        discount_amount: inSale(this.evaluation.basket_discount),
        taxes: [],
        grand_total: saleTotal,
        rounded_total: saleTotal,
        paid_amount: paid,
        change_amount: Math.max(0, paid - saleTotal),
        payments: sale.foreign
          ? payments.map((p) => ({ ...p, currency: p.tender_currency, tendered: p.tender_amount }))
          : payments,
        // Savings in the sale's currency, as on the posted receipt.
        applied_promotions: sale.foreign
          ? this.evaluation.applied.map((p) => ({ ...p, savings: inSale(p.savings) }))
          : this.evaluation.applied,
        ...(sale.foreign
          ? {
              company_currency: session.localCurrency,
              conversion_rate: sale.rate,
              base_grand_total: Math.round(saleTotal * sale.rate * 100) / 100,
              change_currency: sale.row?.change_currency || session.localCurrency,
              base_change_amount: Math.round(Math.max(0, paid - saleTotal) * sale.rate * 100) / 100,
            }
          : {}),
      }
      this.clear()
      return receipt
    },

    // A sale queued offline, kept for a return without a connection before it
    // is even sent: each line at the rate ERPNext will post it at, the
    // outlet's taxes and rounding, and which lines must come back together.
    _keepQueuedSale(payload, payments, sale) {
      const session = useSessionStore()
      if (!session.registerSession?.name) return
      const factor = sale.foreign ? sale.factor : 1
      const units = this.unitDiscounts
      const { idx, cart } = this._promoView
      const groups = returnGroups(this.lines, this.evaluation.applied, session.promotions, cart, idx, matchingIndexes)
      const code = sale.foreign ? sale.currency : session.currency
      const rule = session.settings?.rounding?.[code] || {}
      const round = (x, p) => frappeRound(x, p, rule.method, rule.commercial)
      const lines = this.lines.map((l, i) => {
        const price = Number(l.price) || 0
        const listRate = round(price * factor, 2)
        const pct = price > 0 && units[i] > 0 ? round((Math.min(units[i], price) / price) * 100, 6) : 0
        return {
          item_code: l.item_code,
          item_name: l.item_name,
          qty: l.qty,
          rate: round(listRate * (1 - pct / 100), 2),
          item_tax_rate: {},
          serial: false,
          group: groups[i],
        }
      })
      putShiftSale({
        key: payload.idempotency_key,
        session: session.registerSession.name,
        pos_profile: session.posProfile,
        user: session.user,
        at: new Date().toISOString(),
        returned: {},
        name: null,
        queued: true,
        currency: code,
        company_currency: session.localCurrency,
        conversion_rate: sale.foreign ? sale.rate : 1,
        customer: this.customer?.name || null,
        customer_name: this.customer?.customer_name || session.defaultCustomerName || 'Walk-in',
        lines,
        taxes: (session.taxes || []).map((t) => ({
          charge_type: t.charge_type,
          rate: t.rate || 0,
          included: t.included || 0,
          account_head: t.account_head || null,
          row_id: t.row_id || null,
        })),
        rounding: session.settings?.rounding?.[code] || null,
        total: this.inSale(this.total),
        paid_modes: payments.filter((p) => Number(p.amount) > 0).map((p) => p.mode_of_payment),
        refund_modes: null,
        blocked: null,
        facts: false,
        loyalty: false,
        service_charge: this.serviceCharge > 0,
      }).catch(() => {})
    },

    async park(note) {
      const session = useSessionStore()
      await call('lumenpos.api.sales.park_sale', {
        pos_profile: session.posProfile,
        customer: this.customer?.name || null,
        customer_name: this.customer?.customer_name || null,
        note: note || null,
        cart: { lines: this.lines, note: this.note },
      })
      this.clear()
    },

    async retrieve(name) {
      const data = await call('lumenpos.api.sales.retrieve_parked', { name })
      this.lines = data.cart.lines || []
      this.note = data.cart.note || ''
      if (data.customer) {
        const matches = await call('lumenpos.api.catalog.search_customers', {
          search: data.customer,
        })
        await this.setCustomer(matches.find((c) => c.name === data.customer) || null)
      }
    },
  },
})
