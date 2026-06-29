<template>
  <aside class="cart card">
    <div class="customer-row" role="button" tabindex="0" @click="customerOpen = true" @keydown.enter="customerOpen = true">
      <div class="avatar">{{ customerInitials }}</div>
      <div class="customer-meta">
        <div class="customer-name">{{ cart.customer?.customer_name || t('Add a customer') }}</div>
        <div class="muted small" v-if="cart.customer">
          {{ cart.customer.customer_group }}
          <template v-if="cart.wallet">
            <span v-if="cart.wallet.loyalty_points > 0"> · <Icon name="star" /> {{ cart.wallet.loyalty_points }} {{ t('pts') }}</span>
            <span v-if="cart.wallet.store_credit > 0"> · {{ money(cart.wallet.store_credit) }} {{ t('credit') }}</span>
          </template>
        </div>
      </div>
      <button v-if="cart.customer" class="btn-ghost" @click.stop="cart.setCustomer(null)"><Icon name="close" /></button>
    </div>

    <div class="channel-row">
      <select :value="cart.appType || ''" @change="cart.setChannel($event.target.value || null)">
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

    <div v-if="session.salesPersons.length" class="salesperson-row">
      <span class="muted small">{{ t('Salesperson') }}</span>
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

    <div class="coupon-row">
      <span v-for="code in cart.couponCodes" :key="code" class="coupon-chip">
        <Icon name="ticket" /> {{ code }}
        <button class="chip-x" @click="cart.removeCoupon(code)"><Icon name="close" /></button>
      </span>
      <form class="coupon-form" @submit.prevent="applyCoupon">
        <input v-model="couponInput" :placeholder="t('Coupon code')" />
        <button type="submit" class="btn btn-outline" :disabled="!couponInput.trim()">{{ t('Apply') }}</button>
      </form>
    </div>

    <div class="totals">
      <div class="row">
        <span>{{ t('Subtotal') }}</span>
        <span>{{ money(cart.subtotal) }}</span>
      </div>
      <div v-for="promo in evaluation.applied" :key="promo.name" class="row promo-row">
        <span class="promo-badge"><Icon name="star" /> {{ promo.title }}</span>
        <span>-{{ money(promo.savings) }}</span>
      </div>
      <div v-for="bundle in cart.bundleBreakdown.applied" :key="bundle.key" class="row bundle-row">
        <span class="bundle-badge-sm"><Icon name="gift" /> {{ bundle.title }}</span>
        <span>-{{ money(bundle.savings) }}</span>
      </div>
      <div v-if="cart.manualDiscountTotal > 0" class="row promo-row">
        <span class="muted">{{ t('Manual discounts') }}</span>
        <span>-{{ money(cart.manualDiscountTotal) }}</span>
      </div>
      <div v-for="tax in cart.taxBreakdown.exclusive" :key="'x' + tax.description" class="row">
        <span class="muted">{{ tax.description }}</span>
        <span>+{{ money(tax.amount) }}</span>
      </div>
      <div v-for="tax in cart.taxBreakdown.included" :key="'i' + tax.description" class="row tax-included">
        <span class="muted">{{ t('{description} (included)', { description: tax.description }) }}</span>
        <span class="muted">{{ money(tax.amount) }}</span>
      </div>
      <div class="row grand">
        <span>{{ t('Total') }} <span class="muted small">{{ t('({count} items)', { count: cart.itemCount }) }}</span></span>
        <span>{{ money(cart.total) }}</span>
      </div>
    </div>

    <div class="cart-note">
      <input
        v-model="cart.note"
        :placeholder="t('Add a note for this sale (optional)')"
        maxlength="280"
      />
    </div>

    <div class="actions">
      <button class="btn btn-outline" :disabled="!cart.lines.length" @click="$emit('park')">
        {{ t('Park') }}
      </button>
      <button class="btn btn-outline" :disabled="!cart.lines.length" @click="discard">
        {{ t('Discard') }}
      </button>
      <button
        class="btn btn-outline"
        :disabled="session.offline || !session.registerOpen || session.permissions.sell === false"
        :title="t('Sell a gift card')"
        @click="giftCardOpen = true"
      >
        <Icon name="gift" />
      </button>
    </div>
    <button
      class="btn btn-primary btn-lg pay"
      :disabled="!cart.lines.length || !session.registerOpen || session.permissions.sell === false"
      :title="session.permissions.sell === false ? t('You do not have permission to make sales') : ''"
      @click="$emit('pay')"
    >
      {{ t('Pay') }}&nbsp;&nbsp;{{ money(cart.total) }}
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
import { ref, computed } from 'vue'
import { t } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useSessionStore } from '../stores/session'
import { useCatalogStore } from '../stores/catalog'
import { money } from '../format'
import CartLine from './CartLine.vue'
import CustomerModal from './CustomerModal.vue'
import SellGiftCardModal from './SellGiftCardModal.vue'

const emit = defineEmits(['pay', 'park', 'receipt'])

const cart = useCartStore()
const session = useSessionStore()
const catalog = useCatalogStore()
const customerOpen = ref(false)
const couponInput = ref('')
const giftCardOpen = ref(false)

function onGiftCardSold(receipt) {
  giftCardOpen.value = false
  emit('receipt', receipt)
}

const evaluation = computed(() => cart.evaluation)
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
.cart-note { padding: 0 14px 8px; }
.cart-note input { width: 100%; font-size: 13px; }
.pricebook-note {
  padding: 6px 16px;
  font-size: 12px;
  color: var(--brand-dark);
  background: rgba(46, 91, 255, 0.06);
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
.sp-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--brand-dark);
  background: rgba(46, 91, 255, 0.08);
  border-radius: 999px;
  padding: 4px 11px;
}
.lines {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
.suggestions {
  border-top: 1px solid var(--border);
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
  padding: 8px 16px;
  border-top: 1px solid var(--border);
}
.coupon-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-dark);
  background: rgba(46, 91, 255, 0.1);
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
  padding: 12px 16px 4px;
}
.row {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
}
.promo-row { color: var(--promo); font-weight: 600; }
.bundle-row { color: var(--brand-dark); font-weight: 600; }
.tax-included { font-size: 12px; }
.bundle-badge-sm {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(46, 91, 255, 0.1);
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
