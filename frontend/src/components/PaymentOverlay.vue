<template>
  <div class="pay-overlay">
    <header class="pay-header">
      <button class="btn-ghost back" @click="$emit('close')">‹ {{ t('Back to sale') }}</button>
      <div class="pay-title">{{ t('Amount to Pay') }}</div>
      <div />
    </header>

    <div class="pay-body">
      <div class="amount-due">
        <div class="due-label">{{ remaining > 0 ? t('Remaining') : t('Change') }}</div>
        <div class="due-value" :class="{ change: remaining < 0 }">
          {{ money(Math.abs(remaining)) }}
        </div>
      </div>

      <div v-if="wallet && (wallet.loyalty_points > 0 || wallet.store_credit > 0)" class="wallet card">
        <div v-if="wallet.loyalty_points > 0" class="wallet-row">
          <span><Icon name="star" /> {{ t('{points} loyalty points (worth {value})', { points: wallet.loyalty_points, value: money(wallet.loyalty_points * wallet.conversion_factor) }) }}</span>
          <span class="redeem">
            <input type="number" min="0" :max="maxRedeemablePoints" v-model.number="redeemPoints" />
            <span class="muted">{{ t('pts = {value}', { value: money(loyaltyAmount) }) }}</span>
          </span>
        </div>
        <div v-if="wallet.store_credit > 0" class="wallet-row">
          <span>{{ t('Store credit available:') }} <strong>{{ money(wallet.store_credit) }}</strong></span>
          <button class="btn btn-outline" @click="addStoreCredit">{{ t('Use store credit') }}</button>
        </div>
      </div>

      <div class="tender">
        <input
          ref="amountInput"
          type="number"
          min="0"
          step="0.01"
          v-model.number="amount"
          class="tender-input"
          @keydown.enter="payWithDefault"
        />
        <div class="quick-cash">
          <button v-for="value in quickAmounts" :key="value" class="btn btn-outline" @click="amount = value">
            {{ money(value) }}
          </button>
        </div>
      </div>

      <div class="methods">
        <button
          v-for="mode in methodTiles"
          :key="mode.mode_of_payment"
          class="method card"
          :class="{ branded: mode.brand }"
          @click="addPayment(mode.mode_of_payment)"
        >
          <PaymentBrand :brand="mode.brand" :type="mode.type" :size="mode.brand ? 30 : 22" />
          <span v-if="!mode.brand">{{ mode.mode_of_payment }}</span>
        </button>
        <button v-if="!session.offline" class="method card" @click="giftCardOpen = !giftCardOpen">
          <Icon class="method-icon" name="gift" :size="24" />
          {{ t('Gift Card') }}
        </button>
      </div>

      <div v-if="giftCardOpen" class="giftcard-box card">
        <div class="giftcard-row">
          <input
            v-model="giftCardNo"
            :placeholder="t('Scan or type gift card number')"
            @keydown.enter="checkGiftCard"
          />
          <button class="btn btn-outline" :disabled="!giftCardNo.trim() || giftCardChecking" @click="checkGiftCard">
            {{ giftCardChecking ? t('Checking…') : t('Check') }}
          </button>
        </div>
        <div v-if="giftCardInfo" class="giftcard-info">
          <span>
            {{ giftCardInfo.card_no }} — {{ t('balance') }} <strong>{{ money(giftCardInfo.balance) }}</strong>
            <span v-if="giftCardInfo.expiry_date" class="muted"> · {{ t('expires {date}', { date: giftCardInfo.expiry_date }) }}</span>
          </span>
          <button class="btn btn-primary" @click="applyGiftCard">
            {{ t('Apply {amount}', { amount: money(Math.min(giftCardInfo.balance, Math.max(remaining, 0))) }) }}
          </button>
        </div>
      </div>

      <div v-if="payments.length || loyaltyAmount > 0" class="splits card">
        <div v-if="loyaltyAmount > 0" class="split-row">
          <span>{{ t('Loyalty points ({count})', { count: redeemPoints }) }}</span>
          <span>{{ money(loyaltyAmount) }}</span>
          <button class="btn-ghost" @click="redeemPoints = 0"><Icon name="close" /></button>
        </div>
        <div v-for="(payment, i) in payments" :key="i" class="split-row">
          <span>{{ payment.mode_of_payment }}<span v-if="payment.card_no" class="muted"> ({{ payment.card_no }})</span></span>
          <span>{{ money(payment.amount) }}</span>
          <button class="btn-ghost" @click="payments.splice(i, 1)"><Icon name="close" /></button>
        </div>
      </div>

      <button
        class="btn btn-primary btn-lg complete"
        :disabled="!canComplete || cart.submitting"
        @click="complete"
      >
        {{ cart.submitting ? t('Processing…') : t('Complete Sale {amount}', { amount: money(total) }) }}
      </button>
      <p v-if="session.offline" class="muted offline-note">
        {{ t('Offline — this sale will be queued and synced automatically.') }}
      </p>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import PaymentBrand from './PaymentBrand.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { useCartStore } from '../stores/cart'
import { useSessionStore } from '../stores/session'
import { money } from '../format'
import { t } from '../i18n'

const emit = defineEmits(['close', 'done'])
const cart = useCartStore()
const session = useSessionStore()

const payments = ref([])
const amount = ref(0)
const redeemPoints = ref(0)
const amountInput = ref(null)
const giftCardOpen = ref(false)
const giftCardNo = ref('')
const giftCardInfo = ref(null)
const giftCardChecking = ref(false)

const wallet = computed(() => (session.offline ? null : cart.wallet))

// Amount to collect. Authoritative from the SERVER (same math as submit), so the
// till charges exactly what the posted invoice shows — no phantom rounding
// "change" on VAT-inclusive promo lines. Falls back to the client cart total
// offline or until the quote returns.
const serverTotal = ref(null)
const total = computed(() => (serverTotal.value != null ? serverTotal.value : cart.total))

const loyaltyAmount = computed(() => {
  if (!wallet.value || redeemPoints.value <= 0) return 0
  const points = Math.min(redeemPoints.value, wallet.value.loyalty_points)
  return round2(Math.min(points * wallet.value.conversion_factor, total.value))
})

const maxRedeemablePoints = computed(() => {
  if (!wallet.value?.conversion_factor) return 0
  return Math.min(
    wallet.value.loyalty_points,
    Math.floor(total.value / wallet.value.conversion_factor)
  )
})

const paid = computed(() => payments.value.reduce((sum, p) => sum + p.amount, 0))
const remaining = computed(() => round2(total.value - paid.value - loyaltyAmount.value))
const canComplete = computed(
  () =>
    (payments.value.length || loyaltyAmount.value > 0) &&
    paid.value + loyaltyAmount.value >= total.value - 0.005
)

const visibleModes = computed(() =>
  session.paymentModes.filter(
    (m) =>
      m.mode_of_payment !== session.storeCreditMode &&
      m.mode_of_payment !== session.giftCardMode
  )
)

// Detect the card scheme / wallet from the Mode of Payment name so the tile
// can show its real logo. Returns '' for plain methods (Cash, Bank Transfer…),
// which then fall back to a generic line icon.
function brandKey(name) {
  const n = (name || '').toLowerCase().replace(/[^a-z]/g, '')
  if (!n) return ''
  if (n.includes('mastercard') || n.includes('master') || n === 'mc') return 'mastercard'
  if (n.includes('visa')) return 'visa'
  if (n.includes('mada')) return 'mada'
  if (n.includes('americanexpress') || n.includes('amex')) return 'amex'
  if (n.includes('tamara')) return 'tamara'
  if (n.includes('tabby')) return 'tabby'
  if (n.includes('stcpay') || n.includes('stc')) return 'stcpay'
  if (n.includes('applepay') || n.includes('apple')) return 'applepay'
  return ''
}

const methodTiles = computed(() =>
  visibleModes.value.map((m) => ({ ...m, brand: brandKey(m.mode_of_payment) }))
)

const quickAmounts = computed(() => {
  const due = Math.max(remaining.value, 0)
  if (due <= 0) return []
  const exact = round2(due)
  const next5 = Math.ceil(due / 5) * 5
  const next10 = Math.ceil(due / 10) * 10
  const next50 = Math.ceil(due / 50) * 50
  return [...new Set([exact, next5, next10, next50])].slice(0, 4)
})

onMounted(async () => {
  amount.value = round2(Math.max(cart.total, 0))
  amountInput.value?.focus()
  amountInput.value?.select()
  // Pull the authoritative payable from the server (same math as submit). If it
  // differs from the client total by a rounding halfcent, snap the suggested
  // amount to it — but only while nothing has been entered yet.
  const payable = await cart.quoteTotal()
  if (payable != null) {
    serverTotal.value = payable
    if (!payments.value.length) amount.value = round2(Math.max(payable, 0))
  }
})

function addPayment(mode) {
  const value = round2(Number(amount.value) || 0)
  if (value <= 0) return
  const isCash = session.paymentModes.find((m) => m.mode_of_payment === mode)?.type === 'Cash'
  // Only cash can over-tender (change is given back)
  const capped = isCash ? value : Math.min(value, Math.max(remaining.value, 0))
  if (capped <= 0) return
  payments.value.push({ mode_of_payment: mode, amount: capped })
  amount.value = Math.max(round2(total.value - paid.value - loyaltyAmount.value), 0)
}

function addStoreCredit() {
  const used = payments.value
    .filter((p) => p.mode_of_payment === session.storeCreditMode)
    .reduce((sum, p) => sum + p.amount, 0)
  const available = round2((wallet.value?.store_credit || 0) - used)
  const capped = round2(Math.min(available, Math.max(remaining.value, 0)))
  if (capped <= 0) return
  payments.value.push({ mode_of_payment: session.storeCreditMode, amount: capped })
  amount.value = Math.max(round2(total.value - paid.value - loyaltyAmount.value), 0)
}

function payWithDefault() {
  const def = session.paymentModes.find((m) => m.default) || session.paymentModes[0]
  if (def) addPayment(def.mode_of_payment)
}

async function checkGiftCard() {
  if (!giftCardNo.value.trim() || giftCardChecking.value) return
  giftCardChecking.value = true
  giftCardInfo.value = null
  try {
    const info = await call('lumenpos.api.sales.gift_card_info', {
      card_no: giftCardNo.value,
    })
    if (info.status !== 'Active') {
      session.notify(t('Gift card {card} is {status}', { card: info.card_no, status: info.status }), true)
      return
    }
    const used = payments.value
      .filter((p) => p.card_no === info.card_no)
      .reduce((sum, p) => sum + p.amount, 0)
    info.balance = round2(info.balance - used)
    if (info.balance <= 0) {
      session.notify(t('This gift card is already fully applied to this sale'), true)
      return
    }
    giftCardInfo.value = info
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    giftCardChecking.value = false
  }
}

function applyGiftCard() {
  const info = giftCardInfo.value
  const capped = round2(Math.min(info.balance, Math.max(remaining.value, 0)))
  if (capped <= 0) return
  payments.value.push({
    mode_of_payment: session.giftCardMode,
    amount: capped,
    card_no: info.card_no,
  })
  giftCardInfo.value = null
  giftCardNo.value = ''
  giftCardOpen.value = false
  amount.value = Math.max(round2(total.value - paid.value - loyaltyAmount.value), 0)
}

async function complete() {
  try {
    const giftCards = payments.value
      .filter((p) => p.card_no)
      .map((p) => ({ card_no: p.card_no, amount: p.amount }))
    const receipt = await cart.submit(payments.value, redeemPoints.value, giftCards)
    session.notify(receipt.offline ? t('Sale queued (offline)') : t('Sale completed'))
    emit('done', receipt)
  } catch (e) {
    session.notify(e.message, true)
  }
}

function round2(n) {
  return Math.round((n + Number.EPSILON) * 100) / 100
}
</script>

<style scoped>
.pay-overlay {
  position: fixed;
  inset: 0;
  background: var(--page-bg);
  z-index: 40;
  display: flex;
  flex-direction: column;
}
.pay-header {
  height: 52px;
  background: var(--topbar-bg);
  color: #fff;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 18px;
}
.back { color: #cdd3df; font-size: 14px; justify-self: start; }
.back:hover { color: #fff; }
.pay-title { font-weight: 700; font-size: 16px; }
.pay-body {
  flex: 1;
  overflow-y: auto;
  width: min(640px, 94vw);
  margin: 0 auto;
  padding: 28px 0 40px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.amount-due { text-align: center; }
.due-label {
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
}
.due-value { font-size: 52px; font-weight: 800; }
.due-value.change { color: var(--brand); }
.wallet { padding: 6px 16px; }
.wallet-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.wallet-row:last-child { border-bottom: none; }
.redeem { display: flex; align-items: center; gap: 8px; }
.redeem input { width: 90px; text-align: center; padding: 7px 8px; }
.tender { display: flex; flex-direction: column; gap: 10px; }
.tender-input {
  font-size: 26px;
  text-align: center;
  padding: 14px;
  font-weight: 700;
}
.quick-cash { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }
.methods {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px;
}
.method {
  padding: 18px 14px;
  font-weight: 700;
  font-size: 15px;
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border);
}
.method:hover { border-color: var(--brand); }
.method.branded { justify-content: center; padding: 16px 14px; }
.method-icon { font-size: 20px; }
.giftcard-box { padding: 12px 16px; }
.giftcard-row { display: flex; gap: 8px; }
.giftcard-row input { flex: 1; text-transform: uppercase; }
.giftcard-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  font-size: 13.5px;
}
.splits { padding: 6px 16px; }
.split-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
  font-weight: 600;
}
.split-row:last-child { border-bottom: none; }
.split-row span:first-child { flex: 1; }
.complete { margin-top: 6px; }
.offline-note { text-align: center; margin: 0; }
</style>
