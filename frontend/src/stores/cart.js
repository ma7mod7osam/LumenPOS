import { defineStore } from 'pinia'
import { call, OfflineError } from '../api'
import { queueSale, queueCount, getCatalogItems } from '../offline'
import { evaluatePromotions, suggestOffers } from '../promotions'
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
    discountPasscode: null, // manager passcode for over-limit discounts
    discountRequest: null, // approved POS Discount Request name (role approval)
    activePriceList: null,
    note: '',
    submitting: false,
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

    // Suggestions placed on the cart line they relate to — a line can carry
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
      // splits — including lines adjusted upward — always net correctly
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

    // Net of all discounts, before exclusive taxes
    netTotal() {
      return Math.max(
        0,
        this.subtotal - this.promoSavings - this.manualDiscountTotal - this.bundleSavings
      )
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
      return round2(this.netTotal + this.taxBreakdown.exclusiveTotal)
    },

    itemCount: (state) => state.lines.reduce((sum, l) => sum + l.qty, 0),

    maxManualDiscount: (state) =>
      state.lines.reduce((max, l) => Math.max(max, l.manual_discount_percent || 0), 0),

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
  },

  actions: {
    // For serialized items pass the scanned serial; qty is always locked to
    // the number of serials on the line.
    addItem(item, serial = null) {
      if (item.has_serial_no && !serial) return false // strict: no serial, no sale
      // never merge into a bundle line — bundle pricing is per-instance
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

    async setChannel(appName) {
      this.appType = appName || null
      if (!this.appType) this.orderId = ''
      await this.reprice()
    },

    // Re-resolve cart prices when the active price list changes (customer
    // with a price book, or a delivery-app channel). Server-authoritative.
    async reprice() {
      const session = useSessionStore()
      if (session.offline || !this.lines.length) return
      try {
        const data = await call('lumenpos.api.catalog.get_prices', {
          pos_profile: session.posProfile,
          item_codes: this.lines.map((l) => l.item_code),
          customer_group: this.customer?.customer_group || null,
          app_type: this.appType,
        })
        this.activePriceList = data.price_list
        for (const line of this.lines) {
          if (data.prices[line.item_code] !== undefined) {
            line.price = data.prices[line.item_code]
          }
          const std = data.standard_prices?.[line.item_code]
          line.standard_price = std != null ? std : line.price
        }
      } catch {
        /* keep current prices; server re-resolves at submit anyway */
      }
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
      this.customer = customer
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
      this.discountPasscode = null
      this.discountRequest = null
      this.activePriceList = null
      this.note = ''
      // salesPerson intentionally kept — it's the staff member on shift
    },

    async addCoupon(code) {
      code = (code || '').trim().toUpperCase()
      if (!code) return
      if (this.couponCodes.includes(code)) {
        throw new Error(`Coupon ${code} is already applied`)
      }
      const session = useSessionStore()
      // Coupon promos are never in the bootstrap payload — fetch via the
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
          serial_nos: l.serial_nos || [],
          bundle_key: l.bundle_key || null,
        })),
        coupon_codes: this.couponCodes,
        sales_person: this.salesPerson,
        app_type: this.appType,
        order_id: this.orderId || null,
        note: this.note || null,
      }
    },

    // Authoritative amount to collect, computed by the SERVER with the same math
    // as submit — so the till charges exactly what the posted invoice shows (no
    // phantom rounding "change"). Returns null offline / on error so the caller
    // falls back to the client-side cart total.
    async quoteTotal() {
      try {
        const res = await call('lumenpos.api.sales.quote_sale', { payload: this._basePayload() })
        return res && typeof res.payable === 'number' ? res.payable : null
      } catch {
        return null
      }
    },

    async submit(payments, redeemLoyaltyPoints = 0, giftCards = []) {
      const payload = {
        ...this._basePayload(),
        gift_cards: giftCards,
        payments,
        redeem_loyalty_points: redeemLoyaltyPoints || 0,
        discount_passcode: this.discountPasscode,
        discount_request: this.discountRequest,
      }
      this.submitting = true
      try {
        const receipt = await call('lumenpos.api.sales.submit_sale', { payload })
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
      if (payload.items.some((i) => (i.serial_nos || []).length)) {
        throw new Error('Serialized items need a connection — they cannot be queued offline')
      }
      if (payload.app_type) {
        throw new Error('Delivery-app sales need a connection — they cannot be queued offline')
      }
      if ((payload.gift_cards || []).length) {
        throw new Error('Gift card payments need a connection — remove them and retry')
      }
      if (payload.redeem_loyalty_points > 0) {
        throw new Error('Loyalty redemption needs a connection — remove it and retry')
      }
      if (payments.some((p) => p.mode_of_payment === session.storeCreditMode)) {
        throw new Error('Store credit needs a connection — remove it and retry')
      }
      session.markOffline()
      await queueSale(payload)
      session.queuedCount = await queueCount()

      // Client-side receipt stand-in; the real invoice posts when the queue
      // syncs. Totals here exclude server-side taxes.
      const paid = payments.reduce((sum, p) => sum + p.amount, 0)
      const receipt = {
        offline: true,
        name: `QUEUED-${new Date().toISOString().replace(/\D/g, '').slice(0, 14)}`,
        company: session.company,
        customer_name: this.customer?.customer_name || session.defaultCustomerName || 'Walk-in',
        posting_date: new Date().toISOString().slice(0, 10),
        posting_time: new Date().toTimeString().slice(0, 8),
        currency: session.currency,
        items: this.lines.map((l, i) => {
          const promoDiscount = this.evaluation.line_discounts[i] || 0
          const lineTotal =
            (l.price * l.qty - promoDiscount) * (1 - (l.manual_discount_percent || 0) / 100)
          return {
            item_code: l.item_code,
            item_name: l.item_name,
            qty: l.qty,
            rate: l.qty ? lineTotal / l.qty : 0,
            amount: lineTotal,
          }
        }),
        discount_amount: this.evaluation.basket_discount,
        taxes: [],
        grand_total: this.total,
        rounded_total: this.total,
        paid_amount: paid,
        change_amount: Math.max(0, paid - this.total),
        payments,
        applied_promotions: this.evaluation.applied,
      }
      this.clear()
      return receipt
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
