<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <aside class="cart card">
    <div class="customer-row" role="button" tabindex="0" @click="customerOpen = true" @keydown.enter="customerOpen = true">
      <div class="avatar">{{ customerInitials }}</div>
      <div class="customer-meta">
        <div class="customer-name">{{ cart.customer?.customer_name || t('Add a customer') }}</div>
        <div class="muted small" v-if="cart.customer">
          <span v-if="cart.saleCurrency.foreign" class="ccy-tag">{{ cart.saleCurrency.currency }}</span>
          {{ cart.customer.customer_group }}
          <template v-if="cart.wallet">
            <span v-if="cart.wallet.loyalty_points > 0"> · <Icon name="star" /> {{ cart.wallet.loyalty_points }} {{ t('pts') }}</span>
            <span v-if="cart.wallet.store_credit > 0"> · {{ money(cart.wallet.store_credit) }} {{ t('credit') }}</span>
            <span v-if="cart.wallet.cashback > 0"> · {{ money(cart.wallet.cashback) }} {{ t('cashback') }}</span>
          </template>
        </div>
      </div>
      <button v-if="cart.customer" class="btn-ghost" @click.stop="cart.setCustomer(null)"><Icon name="close" /></button>
    </div>

    <!-- The customer is billed in a currency this till can't sell in: say so
         now, not at payment (the server refuses such a sale). -->
    <div v-if="cart.saleCurrency.blocked" class="currency-warn">
      {{
        session.multiCurrency.enabled
          ? t('{name} is billed in {currency}, which this till does not sell in. Add it in Settings, General, Other currencies, or choose another customer.', { name: cart.customer?.customer_name, currency: cart.saleCurrency.currency })
          : t('{name} is billed in {currency}. Switch on Other currencies in Settings, General, or choose another customer.', { name: cart.customer?.customer_name, currency: cart.saleCurrency.currency })
      }}
    </div>

    <div class="channel-row">
      <!-- Sell in another currency: a walk-in paying in dollars is sold to the
           dollar walk-in customer. A named customer buys in their own. -->
      <select
        v-if="session.saleCurrencies.length"
        class="currency-select"
        :value="cart.saleCurrency.currency"
        :disabled="!cart.currencySwitchable"
        :title="cart.currencySwitchable ? t('Sell in') : t('This customer buys in {currency}', { currency: cart.saleCurrency.currency })"
        @change="cart.setSaleCurrency($event.target.value)"
      >
        <option :value="session.multiCurrency.outlet_currency || session.currency">
          {{ session.multiCurrency.outlet_currency || session.currency }}
        </option>
        <option v-for="c in session.saleCurrencies" :key="c.currency" :value="c.currency">
          {{ c.currency }}
        </option>
      </select>
      <select :value="cart.appType || ''" :disabled="cart.saleCurrency.foreign" @change="cart.setChannel($event.target.value || null)">
        <option value=""><Icon name="store" /> {{ t('Walk-in') }}</option>
        <option v-for="app in session.settings.delivery_apps" :key="app.app_name" :value="app.app_name">
          <Icon name="bike" /> {{ app.app_name }}
        </option>
      </select>
      <input
        v-if="cart.appType"
        v-model="cart.orderId"
        class="order-id"
        :placeholder="cart.activeApp?.require_order_id ? t('Order ID *') : t('Order ID')"
      />
    </div>
    <div v-if="cart.activePriceList && cart.activePriceList !== session.priceList" class="pricebook-note">
      {{ t('Prices from') }} <strong>{{ cart.activePriceList }}</strong>
    </div>

    <div
      v-if="session.salesPersons.length && session.settings.salesperson_mode !== 'Off'"
      class="salesperson-row"
      :class="{ needed: session.settings.salesperson_mode === 'Required' && !cart.salesPerson }"
    >
      <span class="muted small">{{ t('Salesperson') }}<template v-if="session.settings.salesperson_mode === 'Required'"> *</template></span>
      <template v-if="cart.salesPerson">
        <span class="sp-chip">
          {{ selectedSalesPersonLabel }}
          <button class="chip-x" @click="cart.salesPerson = null"><Icon name="close" /></button>
        </span>
      </template>
      <template v-else>
        <input
          v-model="spQuery"
          list="sp-options"
          :placeholder="t('Name or number…')"
          @change="pickSalesPerson"
        />
        <datalist id="sp-options">
          <option v-for="sp in session.salesPersons" :key="sp.name" :value="spLabel(sp)" />
        </datalist>
      </template>
    </div>

    <div class="lines">
      <div v-if="!cart.lines.length" class="empty">
        <p>{{ t('Cart is empty') }}</p>
        <p class="muted small">{{ t('Search or tap a product to add it') }}</p>
      </div>
      <CartLine
        v-for="(line, i) in cart.lines"
        :key="(line.bundle_key || '') + line.item_code + i"
        :line="line"
        :index="i"
        :promo-discount="evaluation.line_discounts[i]"
        :promo-titles="evaluation.line_promotions[i]"
        :bundle-discount="cart.bundleBreakdown.discounts[i]"
        :suggestions="cart.lineSuggestions[i]"
        @suggestion="onSuggestion"
      />
    </div>

    <!-- Everything under the goods. It takes only the room it needs and
         scrolls on a short screen, so the lines above always keep theirs. -->
    <div class="cart-foot">
      <div v-if="cart.basketSuggestions.length" class="suggestions">
        <button
          v-for="(suggestion, i) in cart.basketSuggestions"
          :key="i"
          class="suggestion"
          :title="suggestion.title"
          @click="onSuggestion(suggestion)"
        >
          <span class="bulb"><Icon name="bulb" /></span>
          <span>{{ suggestion.message }}</span>
        </button>
      </div>

      <!-- Coupon, order discount and note: one tap opens the field. A button
           that holds something (a coupon, a discount, a note) stays lit. -->
      <div class="cart-tools">
        <button
          type="button"
          class="tool"
          :class="{ on: tool === 'coupon' || cart.couponCodes.length }"
          :aria-expanded="tool === 'coupon' ? 'true' : 'false'"
          @click="toggleTool('coupon')"
        >
          <Icon name="ticket" /> {{ t('Coupon') }}
          <span v-if="cart.couponCodes.length" class="tool-count">{{ cart.couponCodes.length }}</span>
        </button>
        <button
          v-if="session.settings.enable_order_discount"
          type="button"
          class="tool"
          :class="{ on: tool === 'discount' || cart.orderDiscountPercent > 0 }"
          :disabled="!cart.lines.length"
          :aria-expanded="tool === 'discount' ? 'true' : 'false'"
          @click="toggleTool('discount')"
        >
          <Icon name="tag" />
          {{ cart.orderDiscountPercent > 0 ? t('Discount {pct}%', { pct: cart.orderDiscountPercent }) : t('Discount') }}
        </button>
        <button
          type="button"
          class="tool"
          :class="{ on: tool === 'note' || cart.note }"
          :title="cart.note || ''"
          :aria-expanded="tool === 'note' ? 'true' : 'false'"
          @click="toggleTool('note')"
        >
          <Icon name="report" /> {{ t('Note') }}
          <span v-if="cart.note" class="tool-dot" />
        </button>
      </div>

      <div v-if="tool === 'coupon'" class="tool-panel coupon-row">
        <span v-for="code in cart.couponCodes" :key="code" class="coupon-chip">
          <Icon name="ticket" /> {{ code }}
          <button class="chip-x" @click="cart.removeCoupon(code)"><Icon name="close" /></button>
        </span>
        <form class="coupon-form" @submit.prevent="applyCoupon">
          <input ref="toolInput" v-model="couponInput" :placeholder="t('Coupon code')" />
          <button type="submit" class="btn btn-outline" :disabled="!couponInput.trim()">{{ t('Apply') }}</button>
        </form>
      </div>
      <div v-if="tool === 'discount' && session.settings.enable_order_discount" class="tool-panel row order-discount-row">
        <span class="muted">{{ t('Order discount') }}</span>
        <span class="od-control">
          <input
            ref="toolInput"
            type="number"
            min="0"
            max="100"
            step="1"
            inputmode="decimal"
            class="od-input"
            :value="cart.orderDiscountPercent || ''"
            placeholder="0"
            :disabled="session.permissions.can_edit_price === false"
            @input="cart.setOrderDiscount($event.target.value)"
            @keydown.enter="tool = ''"
          />
          <span class="od-pct">%</span>
          <span v-if="cart.orderDiscountTotal > 0" class="od-amt"
            >-{{ cart.show(cart.orderDiscountTotal) }}</span
          >
        </span>
      </div>
      <div v-if="tool === 'note'" class="tool-panel cart-note">
        <input
          ref="toolInput"
          v-model="cart.note"
          :placeholder="t('Add a note for this sale (optional)')"
          maxlength="280"
          @keydown.enter="tool = ''"
        />
      </div>

      <div class="totals">
        <!-- The breakdown folds away under one line: the total, with what was
             saved beside the toggle. Opened or not, it is remembered here. -->
        <div v-if="cart.lines.length" class="totals-head">
          <button type="button" class="details-toggle" :aria-expanded="detailsOpen ? 'true' : 'false'" @click="toggleDetails">
            {{ detailsOpen ? t('Hide details') : t('Details') }} <span class="chev">{{ detailsOpen ? '▴' : '▾' }}</span>
          </button>
          <span v-if="!detailsOpen && savings > 0.005" class="saved">{{ t('Saved {amount}', { amount: cart.show(savings) }) }}</span>
        </div>
        <template v-if="detailsOpen && cart.lines.length">
          <div class="row">
            <span>{{ t('Subtotal') }}</span>
            <span>{{ cart.show(cart.subtotal) }}</span>
          </div>
          <div v-for="promo in evaluation.applied" :key="promo.name" class="row promo-row">
            <span class="promo-badge"><Icon name="star" /> {{ promo.title }}</span>
            <span>-{{ cart.show(promo.savings) }}</span>
          </div>
          <div v-for="bundle in cart.bundleBreakdown.applied" :key="bundle.key" class="row bundle-row">
            <span class="bundle-badge-sm"><Icon name="gift" /> {{ bundle.title }}</span>
            <span>-{{ cart.show(bundle.savings) }}</span>
          </div>
          <div v-if="cart.manualDiscountTotal > 0" class="row promo-row">
            <span class="muted">{{ t('Manual discounts') }}</span>
            <span>-{{ cart.show(cart.manualDiscountTotal) }}</span>
          </div>
          <div v-if="cart.orderDiscountTotal > 0" class="row promo-row">
            <span class="muted">{{ t('Order discount') }} ({{ cart.orderDiscountPercent }}%)</span>
            <span>-{{ cart.show(cart.orderDiscountTotal) }}</span>
          </div>
          <div v-for="tax in cart.taxBreakdown.exclusive" :key="'x' + tax.description" class="row">
            <span class="muted">{{ tax.description }}</span>
            <span>+{{ cart.show(tax.amount) }}</span>
          </div>
          <div v-for="tax in cart.taxBreakdown.included" :key="'i' + tax.description" class="row tax-included">
            <span class="muted">{{ t('{description} (included)', { description: tax.description }) }}</span>
            <span class="muted">{{ cart.show(tax.amount) }}</span>
          </div>
          <div v-if="cart.serviceCharge > 0" class="row">
            <span class="muted">{{ t('Service charge ({pct}%)', { pct: session.settings.service_charge_percent }) }}</span>
            <span>+{{ cart.show(cart.serviceCharge) }}</span>
          </div>
        </template>
        <div class="row grand">
          <span>{{ t('Total') }} <span class="muted small">{{ t('({count} items)', { count: cart.itemCount }) }}</span></span>
          <span>{{ cart.show(cart.total) }}</span>
        </div>
        <!-- The same total in other money: the local value of a sale in another
             currency, and the equivalents the shop chose to show, on one line. -->
        <div v-if="equivalents.length" class="row equiv">
          <span class="muted">≈</span>
          <span class="muted equiv-values">
            <span v-for="eq in equivalents" :key="eq.currency" :title="eq.label">{{ money(eq.amount, eq.currency) }}</span>
          </span>
        </div>
      </div>
    </div>

    <div class="actions">
      <button class="btn btn-outline" :disabled="!cart.lines.length" @click="$emit('park')">
        {{ t('Park') }}
      </button>
      <!-- Parking keeps a basket for later today. A HOLD keeps the goods for a
           customer who is paying for them over time. -->
      <button
        v-if="session.settings.enable_layaway && session.permissions.can_hold_goods !== false"
        class="btn btn-outline"
        :disabled="!cart.lines.length || session.offline || !session.registerOpen"
        :title="t('Hold these goods for a customer paying over time')"
        @click="$emit('hold')"
      >
        {{ t('Hold') }}
      </button>
      <button class="btn btn-outline" :disabled="!cart.lines.length" @click="discard">
        {{ t('Discard') }}
      </button>
      <button
        class="btn btn-outline"
        :disabled="session.offline || !session.registerOpen || session.permissions.sell === false || !!session.sellBlockedBy"
        :title="t('Sell a gift card')"
        @click="giftCardOpen = true"
      >
        <Icon name="gift" />
      </button>
    </div>
    <button
      class="btn btn-primary btn-lg pay"
      :disabled="!cart.lines.length || !session.registerOpen || session.permissions.sell === false || !!session.sellBlockedBy"
      :title="session.permissions.sell === false ? t('You do not have permission to make sales') : ''"
      @click="$emit('pay')"
    >
      {{ t('Pay') }}&nbsp;&nbsp;{{ cart.show(cart.total) }}
    </button>

    <CustomerModal v-if="customerOpen" @close="customerOpen = false" />
    <SellGiftCardModal
      v-if="giftCardOpen"
      @close="giftCardOpen = false"
      @done="onGiftCardSold"
    />
  </aside>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, nextTick } from 'vue'
import { t } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useSessionStore } from '../stores/session'
import { useCatalogStore } from '../stores/catalog'
import { money } from '../format'
import CartLine from './CartLine.vue'
import CustomerModal from './CustomerModal.vue'
import SellGiftCardModal from './SellGiftCardModal.vue'

const emit = defineEmits(['pay', 'park', 'hold', 'receipt'])

const cart = useCartStore()
const session = useSessionStore()
const catalog = useCatalogStore()
const customerOpen = ref(false)
const couponInput = ref('')
const giftCardOpen = ref(false)

// One of coupon, discount or note open under the lines, or none.
const tool = ref('')
const toolInput = ref(null)
async function toggleTool(name) {
  tool.value = tool.value === name ? '' : name
  if (!tool.value) return
  await nextTick()
  const el = Array.isArray(toolInput.value) ? toolInput.value[0] : toolInput.value
  if (el && el.focus) el.focus()
}

// The breakdown under the total: folded unless this device opened it.
const DETAILS_KEY = 'lumenpos-cart-details'
function detailsRemembered() {
  try {
    return localStorage.getItem(DETAILS_KEY) === '1'
  } catch {
    return false
  }
}
const detailsOpen = ref(detailsRemembered())
function toggleDetails() {
  detailsOpen.value = !detailsOpen.value
  try {
    localStorage.setItem(DETAILS_KEY, detailsOpen.value ? '1' : '0')
  } catch {
    /* private window: open or closed until the tab closes */
  }
}
// What the folded breakdown saves the customer, shown beside the toggle.
const savings = computed(
  () => cart.promoSavings + cart.bundleSavings + cart.manualDiscountTotal + cart.orderDiscountTotal
)

function onGiftCardSold(receipt) {
  giftCardOpen.value = false
  emit('receipt', receipt)
}

const evaluation = computed(() => cart.evaluation)

// The total in other money. A sale in another currency always shows what it
// comes to locally (change and card payments are local). A local sale shows
// the currencies the shop ticked "Show the equivalent" for.
const equivalents = computed(() => {
  const mc = session.multiCurrency || {}
  if (!mc.enabled || !cart.lines.length) return []
  const sale = cart.saleCurrency
  if (sale.blocked) return []
  const outletRate = mc.outlet_rate || 0
  if (!outletRate) return []
  const inCompany = cart.total * outletRate // the total in company currency
  const out = []
  if (sale.foreign && sale.currency !== mc.company_currency) {
    out.push({
      currency: mc.company_currency,
      amount: round2(inCompany),
      label: t('In {currency}', { currency: mc.company_currency }),
    })
  }
  for (const c of session.saleCurrencies) {
    if (!c.show_equivalent || c.currency === sale.currency || c.currency === mc.company_currency) continue
    out.push({
      currency: c.currency,
      amount: round2(inCompany / c.rate),
      label: t('In {currency}', { currency: c.currency }),
    })
  }
  return out
})

function round2(n) {
  return Math.round((n + Number.EPSILON) * 100) / 100
}
const spQuery = ref('')

function spLabel(sp) {
  return sp.sales_person_no
    ? `${sp.sales_person_name} #${sp.sales_person_no}`
    : sp.sales_person_name
}

const selectedSalesPersonLabel = computed(() => {
  const sp = session.salesPersons.find((s) => s.name === cart.salesPerson)
  return sp ? spLabel(sp) : cart.salesPerson
})

function pickSalesPerson() {
  const query = spQuery.value.trim().toLowerCase()
  if (!query) return
  const found = session.salesPersons.find(
    (sp) =>
      spLabel(sp).toLowerCase() === query ||
      sp.sales_person_name.toLowerCase() === query ||
      String(sp.sales_person_no || '').toLowerCase() === query
  )
  if (found) {
    cart.salesPerson = found.name
    spQuery.value = ''
  }
}

async function applyCoupon() {
  try {
    const promo = await cart.addCoupon(couponInput.value)
    couponInput.value = ''
    tool.value = ''
    if (promo) session.notify(t('Coupon applied: {title}', { title: promo.title }))
  } catch (e) {
    session.notify(e.message, true)
  }
}

function onSuggestion(suggestion) {
  // Clicking a suggestion pulls the suggested product up in the grid
  if (suggestion.target) catalog.setSearch(suggestion.target)
}

const customerInitials = computed(() => {
  const name = cart.customer?.customer_name
  if (!name) return '+'
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
})

function discard() {
  if (confirm(t('Discard this sale?'))) cart.clear()
}
</script>

<style scoped>
.cart {
  width: 380px;
  margin: 16px 16px 16px 0;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}
.customer-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  width: 100%;
  cursor: pointer;
}
.customer-row:hover { background: var(--surface-2); }
.avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  flex-shrink: 0;
}
.customer-meta { flex: 1; min-width: 0; }
.customer-name { font-weight: 600; }
.small { font-size: 12px; }
.channel-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
}
.channel-row select { flex: 1; padding: 6px 10px; font-size: 13px; min-width: 0; }
.channel-row .currency-select { flex: 0 0 auto; width: auto; font-weight: 700; }
.ccy-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 800;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.1);
  border-radius: 999px;
  padding: 1px 8px;
  margin-inline-end: 4px;
}
.currency-warn {
  padding: 8px 16px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--red);
  background: rgba(226, 48, 48, 0.08);
  border-bottom: 1px solid var(--border);
}
.equiv { font-size: 13px; padding-top: 0; }
.order-id { width: 110px; padding: 6px 10px; font-size: 13px; }
.exchange-btn {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 6px 12px;
  white-space: nowrap;
}
.exchange-btn:hover { color: var(--brand); border-color: var(--brand); }

.cart-note input { width: 100%; font-size: 13px; }
.pricebook-note {
  padding: 6px 16px;
  font-size: 12px;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.06);
  border-bottom: 1px solid var(--border);
}
.salesperson-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
}
.salesperson-row input { flex: 1; padding: 6px 10px; font-size: 13px; }
.salesperson-row.needed input { border-color: var(--amber); }
.sp-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.08);
  border-radius: 999px;
  padding: 4px 11px;
}
.lines {
  flex: 1 1 auto;
  overflow-y: auto;
  /* The goods never shrink below three lines: what sits under them scrolls
     first (.cart-foot). */
  min-height: 180px;
}
.cart-foot {
  flex: 0 1 auto;
  min-height: 0;
  overflow-y: auto;
  border-top: 1px solid var(--border);
}
.cart-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px 16px;
}
.tool {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text-muted);
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 5px 11px;
  cursor: pointer;
}
.tool:hover:not(:disabled) { color: var(--brand); border-color: var(--brand); }
.tool:disabled { opacity: 0.5; cursor: default; }
.tool.on {
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.08);
  border-color: rgba(20, 99, 255, 0.35);
}
html[data-theme='dark'] .tool.on { color: #9fc0ff; background: rgba(47, 123, 255, 0.16); }
.tool-count {
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--brand);
  color: #fff;
  font-size: 10.5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.tool-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--brand); }
.tool-panel { padding: 0 16px 8px; }
.totals-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 2px;
}
.details-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  background: transparent;
  padding: 2px 0;
  cursor: pointer;
}
.details-toggle:hover { color: var(--brand); }
.chev { font-size: 10px; }
.saved { font-size: 12px; font-weight: 700; color: var(--promo); }
html[data-theme='dark'] .saved { color: #c9b0ff; }
.equiv-values { display: inline-flex; flex-wrap: wrap; justify-content: flex-end; gap: 4px 12px; }
.suggestions {
  padding: 8px 16px 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.suggestion {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  text-align: start;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--promo);
  background: rgba(123, 47, 242, 0.12);
  border: 1px solid rgba(123, 47, 242, 0.3);
  border-radius: var(--radius);
  padding: 8px 10px;
}
.suggestion:hover { background: rgba(123, 47, 242, 0.2); }
/* Dark mode: a lighter purple on a stronger tint stays legible. */
html[data-theme='dark'] .suggestion {
  color: #c9b0ff;
  background: rgba(150, 100, 255, 0.2);
  border-color: rgba(150, 100, 255, 0.42);
}
html[data-theme='dark'] .suggestion:hover { background: rgba(150, 100, 255, 0.3); }
.bulb { flex-shrink: 0; }
.coupon-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}
.coupon-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.1);
  border-radius: 999px;
  padding: 3px 10px;
}
.chip-x { font-size: 10px; color: var(--text-muted); padding: 0 2px; }
.chip-x:hover { color: var(--red); }
.coupon-form { display: flex; gap: 6px; flex: 1; min-width: 170px; }
.coupon-form input { flex: 1; padding: 6px 10px; font-size: 12.5px; text-transform: uppercase; }
.coupon-form .btn { padding: 6px 12px; font-size: 12.5px; }
.empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
}
.totals {
  border-top: 1px solid var(--border);
  padding: 8px 16px 4px;
}
.row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
}
.promo-row { color: var(--promo); font-weight: 600; }
.bundle-row { color: var(--brand-dark); font-weight: 600; }
.tax-included { font-size: 12px; }
.order-discount-row { align-items: center; }
.od-control { display: inline-flex; align-items: center; gap: 4px; }
.od-input {
  width: 56px;
  padding: 3px 6px;
  font-size: 13px;
  text-align: right;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.od-input:disabled { opacity: 0.5; }
.od-pct { color: var(--text-muted); font-size: 12px; }
.od-amt { color: var(--promo); font-weight: 700; margin-inline-start: 6px; }
.bundle-badge-sm {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(20, 99, 255, 0.1);
  font-size: 11.5px;
  font-weight: 700;
  border-radius: 999px;
  padding: 2px 9px;
}
.grand {
  font-size: 19px;
  font-weight: 800;
  padding-top: 8px;
}
.actions {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
}
.actions .btn { flex: 1; }
.pay {
  margin: 4px 16px 16px;
  border-radius: 10px;
}
</style>
