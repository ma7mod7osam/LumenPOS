<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="pay-overlay">
    <header class="pay-header">
      <button class="btn-ghost back" @click="$emit('close')">‹ {{ t('Back to sale') }}</button>
      <div class="pay-title">{{ t('Amount to Pay') }}</div>
      <div />
    </header>

    <div class="pay-body">
      <!-- A walk-in who wants to pay in another currency: switch the sale to
           it here, where the question is usually asked. -->
      <div v-if="canSwitchCurrency" class="sell-in">
        <span class="muted small">{{ t('Sell in') }}</span>
        <div class="segmented">
          <button
            v-for="code in currencyChoices"
            :key="code"
            class="seg-btn"
            :class="{ on: code === sale.currency }"
            :disabled="switching || cart.submitting"
            @click="switchCurrency(code)"
          >
            {{ code }}
          </button>
        </div>
      </div>

      <div class="amount-due">
        <div class="due-label">{{ remaining > 0 ? t('Remaining') : t('Change') }}</div>
        <div class="due-value" :class="{ change: remaining < 0 }">
          {{ remaining < 0 && sale.foreign ? money(localChange, local) : money(Math.abs(remaining), sale.currency) }}
        </div>
        <!-- A sale in another currency: what is left in local money, and the
             change, which always comes back in local money (lumenpos.currency). -->
        <div v-if="sale.foreign" class="due-sub">
          <template v-if="remaining >= 0">= {{ money(fromSale(remaining, local), local) }}</template>
          <template v-else>{{ t('{amount} given back in {currency}', { amount: money(-remaining, sale.currency), currency: local }) }}</template>
        </div>
        <div v-if="sale.foreign" class="rate-note">
          {{ t('Rate for this shift: {rate}', { rate: rateLine(sale.currency, sale.rate, local) }) }}
        </div>
      </div>

      <div v-if="exchange" class="exchange-box card">
        <div class="ex-row">
          <span>{{ t('New items') }}</span>
          <strong>{{ money(total) }}</strong>
        </div>
        <div class="ex-row credit">
          <span>{{ t('Goods returned on {invoice}', { invoice: exchange.invoice }) }}</span>
          <strong>- {{ money(exchangeCredit) }}</strong>
        </div>
        <div class="ex-row net">
          <span>{{ exchangeRefund > 0 ? t('To give back') : t('To collect') }}</span>
          <strong>{{ money(exchangeRefund > 0 ? exchangeRefund : payable) }}</strong>
        </div>
        <div v-if="exchangeRefund > 0" class="ex-refund">
          <span class="muted small">{{ t('Give the difference back as') }}</span>
          <select v-model="refundMode">
            <option v-for="mode in refundModes" :key="mode" :value="mode">{{ mode }}</option>
          </select>
        </div>
      </div>

      <div v-if="wallet && (wallet.loyalty_points > 0 || wallet.store_credit > 0 || wallet.cashback > 0)" class="wallet card">
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
        <div v-if="wallet.cashback > 0" class="wallet-row">
          <span>{{ t('Cashback available:') }} <strong>{{ money(wallet.cashback) }}</strong></span>
          <button class="btn btn-outline" @click="addCashback">{{ t('Use cashback') }}</button>
        </div>
      </div>

      <div class="tender">
        <!-- Each amount is typed in the money actually handed over: dollars, or
             local cash and card. The till converts at the shift's rate. -->
        <div v-if="sale.foreign" class="tender-ccy">
          <span class="muted small">{{ t('Amount in') }}</span>
          <div class="segmented">
            <button
              v-for="code in tenderChoices"
              :key="code"
              class="seg-btn"
              :class="{ on: code === typedIn }"
              @click="setTenderCurrency(code)"
            >
              {{ code }}
            </button>
          </div>
        </div>
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
            {{ money(value, typedIn) }}
          </button>
        </div>
      </div>

      <div class="methods">
        <button
          v-for="mode in methodTiles"
          :key="mode.mode_of_payment"
          class="method card"
          :class="{ branded: mode.brand, blocked: !!blockedModes[mode.mode_of_payment] }"
          :disabled="!!blockedModes[mode.mode_of_payment]"
          :title="blockedModes[mode.mode_of_payment] || ''"
          @click="addPayment(mode.mode_of_payment)"
        >
          <PaymentBrand :brand="mode.brand" :type="mode.type" :size="mode.brand ? 30 : 22" />
          <span v-if="!mode.brand">{{ mode.mode_of_payment }}</span>
          <span v-if="sale.foreign" class="mode-ccy">{{ mode.currency }}</span>
        </button>
        <button v-if="!session.offline && !sale.foreign" class="method card" @click="giftCardOpen = !giftCardOpen">
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
            {{ giftCardInfo.card_no }}, {{ t('balance') }} <strong>{{ money(giftCardInfo.balance) }}</strong>
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
          <span class="split-amount">
            {{ money(payment.tender_amount, payment.tender_currency) }}
            <span v-if="payment.tender_currency !== sale.currency" class="muted small">
              = {{ money(payment.amount, sale.currency) }}
            </span>
          </span>
          <button class="btn-ghost" @click="payments.splice(i, 1)"><Icon name="close" /></button>
          <!-- Terminal / transfer reference, so a disputed card payment can be
               traced back later. Required when the shop configured it. -->
          <input
            v-if="refRule(payment.mode_of_payment)"
            v-model="payment.reference_no"
            class="split-ref"
            :class="{ missing: refRule(payment.mode_of_payment).require_reference && !(payment.reference_no || '').trim() }"
            :placeholder="refRule(payment.mode_of_payment).reference_label || t('Reference')"
          />
        </div>
      </div>

      <p v-if="cashbackEarn > 0" class="cashback-earn">
        <Icon name="gift" /> {{ t('This sale earns {amount} cashback', { amount: money(cashbackEarn) }) }}
      </p>

      <button
        class="btn btn-primary btn-lg complete"
        :disabled="!canComplete || cart.submitting || switching"
        @click="complete"
      >
        {{
          cart.submitting
            ? t('Processing…')
            : exchange
              ? exchangeRefund > 0
                ? t('Complete exchange, give back {amount}', { amount: money(exchangeRefund) })
                : t('Complete exchange {amount}', { amount: money(payable) })
              : t('Complete Sale {amount}', { amount: money(total, sale.currency) })
        }}
      </button>
      <p v-if="session.offline" class="muted offline-note">
        {{
          sale.foreign
            ? t('A sale in another currency needs a connection, it cannot be queued offline')
            : t('Offline, this sale will be queued and synced automatically.')
        }}
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
import { money, rateLine } from '../format'
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

// What the sale is in (lumenpos.currency). The server's quote has the final
// word (currency and the rate the shift sells at); until it answers, the
// cart's own estimate. `rate` turns the sale's currency into local money.
const quoted = ref(null)
const sale = computed(() => {
  if (quoted.value) return quoted.value
  const c = cart.saleCurrency
  const foreign = c.foreign && !c.blocked
  return {
    currency: foreign ? c.currency : session.multiCurrency?.outlet_currency || session.currency,
    rate: foreign ? c.rate : 1,
    foreign,
  }
})
// The money the main drawer holds, and that change is given in.
const local = computed(() => session.localCurrency)

// A sale in another currency takes no wallets: their ledgers are in the
// outlet's currency only.
const wallet = computed(() => (session.offline || sale.value.foreign ? null : cart.wallet))
const cashbackEarn = ref(0)

// Amount to collect. Authoritative from the SERVER (same math as submit), so the
// till charges exactly what the posted invoice shows, no phantom rounding
// "change" on VAT-inclusive promo lines. Falls back to the client cart total
// offline or until the quote returns.
const serverTotal = ref(null)
const total = computed(() => (serverTotal.value != null ? serverTotal.value : cart.inSale(cart.total)))

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

// Exchange: the goods coming back pay for the new ones, so only the difference
// is collected here (or handed back, when the new items are cheaper).
const exchange = computed(() => cart.exchange)
const exchangeCredit = ref(0)
const exchangeRefund = ref(0)
const refundModes = ref([])
const refundMode = ref(null)
const payable = computed(() => round2(Math.max(total.value - exchangeCredit.value, 0)))

// Every payment row carries `amount` in the SALE's currency (what the server
// posts) and what the tender really took, in its own money, for the screen.
const paid = computed(() => payments.value.reduce((sum, p) => sum + p.amount, 0))
const remaining = computed(() => round2(payable.value - paid.value - loyaltyAmount.value))

// Change always comes back in local money, from the main drawer. This is the
// figure ERPNext books for it: the tenders' local value less the sale's.
const localChange = computed(() => {
  if (remaining.value >= 0) return 0
  const rate = sale.value.rate || 1
  const paidLocal = payments.value.reduce((sum, p) => sum + round2(p.amount * rate), 0)
  return round2(paidLocal - round2(payable.value * rate))
})

const canComplete = computed(() => {
  if (!referencesOk.value) return false
  if (exchange.value) {
    if (!cart.lines.length) return false
    if (exchangeRefund.value > 0 && !refundMode.value) return false
    return paid.value + loyaltyAmount.value >= payable.value - 0.005
  }
  return (
    (payments.value.length || loyaltyAmount.value > 0) &&
    paid.value + loyaltyAmount.value >= total.value - 0.005
  )
})

// --- currencies -------------------------------------------------------------
function modeCurrency(mode) {
  const found = (session.paymentModes || []).find((m) => m.mode_of_payment === mode)
  return found?.account_currency || local.value
}

// Money typed in `code`, in the sale's currency, and back. Only the sale's own
// currency and the local one ever meet here.
function toSale(value, code) {
  if (!sale.value.foreign || code === sale.value.currency) return round2(value)
  return round2(value / (sale.value.rate || 1))
}
function fromSale(value, code) {
  if (!sale.value.foreign || code === sale.value.currency) return round2(value)
  return round2(value * (sale.value.rate || 1))
}

const tenderCurrency = ref(null)
const typedIn = computed(() => (sale.value.foreign && tenderCurrency.value) || sale.value.currency)
const tenderChoices = computed(() => [...new Set([sale.value.currency, local.value])])

function setTenderCurrency(code) {
  tenderCurrency.value = code
  refillAmount()
}

// The rest still to pay, in the money the cashier is typing.
function refillAmount() {
  amount.value = Math.max(fromSale(total.value - paid.value - loyaltyAmount.value, typedIn.value), 0)
}

const canSwitchCurrency = computed(
  () => !cart.exchange && cart.currencySwitchable && session.saleCurrencies.length > 0
)
const currencyChoices = computed(() => [
  session.multiCurrency?.outlet_currency || session.currency,
  ...session.saleCurrencies.map((c) => c.currency),
])
const switching = ref(false)

async function switchCurrency(code) {
  if (switching.value || code === sale.value.currency) return
  switching.value = true
  try {
    await cart.setSaleCurrency(code)
    payments.value = []
    redeemPoints.value = 0
    tenderCurrency.value = null
    giftCardOpen.value = false
    await loadQuote()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    switching.value = false
  }
}

// A tender ERPNext accepts for this sale at the close: one whose account is in
// the company currency or in the sale's own (lumenpos.currency). So a dollar
// drawer is offered on a dollar sale only.
const visibleModes = computed(() =>
  session.paymentModes.filter((m) => {
    if (
      m.mode_of_payment === session.storeCreditMode ||
      m.mode_of_payment === session.cashbackMode ||
      m.mode_of_payment === session.giftCardMode
    ) {
      return false
    }
    const code = m.account_currency || local.value
    return code === local.value || code === sale.value.currency
  })
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
  visibleModes.value.map((m) => ({
    ...m,
    brand: brandKey(m.mode_of_payment),
    currency: m.account_currency || local.value,
  }))
)

const quickAmounts = computed(() => {
  const due = Math.max(fromSale(remaining.value, typedIn.value), 0)
  if (due <= 0) return []
  const exact = round2(due)
  const next5 = Math.ceil(due / 5) * 5
  const next10 = Math.ceil(due / 10) * 10
  const next50 = Math.ceil(due / 50) * 50
  return [...new Set([exact, next5, next10, next50])].slice(0, 4)
})

onMounted(async () => {
  amount.value = round2(Math.max(cart.inSale(cart.total), 0))
  amountInput.value?.focus()
  amountInput.value?.select()
  if (cart.exchange) return loadExchange()
  await loadQuote()
})

// Pull the authoritative payable from the server (same math as submit). If it
// differs from the client total by a rounding halfcent, snap the suggested
// amount to it, but only while nothing has been entered yet. The same quote
// carries the sale's currency and rate, the cashback this sale will earn and
// the tenders this basket may not be paid with, so opening this screen costs
// one request, not two. The cart usually has the answer waiting already (it
// quotes ahead).
async function loadQuote() {
  const q = await cart.quote()
  if (q && typeof q.payable === 'number') {
    serverTotal.value = q.payable
    quoted.value = q.currency
      ? { currency: q.currency, rate: q.rate || 1, foreign: Boolean(q.foreign) }
      : null
    if (!payments.value.length) refillAmount()
  } else {
    serverTotal.value = null
    quoted.value = null
  }
  cashbackEarn.value = q && typeof q.cashback_earn === 'number' ? q.cashback_earn : 0
  if (q && q.blocked_modes) blockedModes.value = q.blocked_modes
  else loadBlockedModes() // quote failed (offline), ask on its own
}

const blockedModes = ref({})

function refRule(mode) {
  const m = (session.paymentModes || []).find((x) => x.mode_of_payment === mode)
  if (!m) return null
  return m.require_reference || m.reference_label ? m : null
}

// Every required reference must be filled before the sale can complete.
const referencesOk = computed(() =>
  payments.value.every((p) => {
    const rule = refRule(p.mode_of_payment)
    return !rule || !rule.require_reference || (p.reference_no || '').trim()
  })
)

async function loadBlockedModes() {
  if (session.offline) return
  try {
    blockedModes.value = await call('lumenpos.api.catalog.blocked_payment_modes', {
      pos_profile: session.posProfile,
      item_codes: JSON.stringify(cart.lines.map((l) => l.item_code)),
    })
  } catch {
    blockedModes.value = {}
  }
}

// A payment row: `amount` in the sale's currency, plus what the tender took in
// its own money (the same figure on a sale in the outlet's currency).
function pushPayment(mode, saleAmount, extra = {}) {
  payments.value.push({
    mode_of_payment: mode,
    amount: saleAmount,
    tender_currency: sale.value.currency,
    tender_amount: saleAmount,
    ...extra,
  })
}

function addPayment(mode) {
  if (blockedModes.value[mode]) {
    session.notify(
      t("{mode} can't be used for this sale ({why}).", {
        mode,
        why: blockedModes.value[mode],
      }),
      true
    )
    return
  }
  const typed = round2(Number(amount.value) || 0)
  if (typed <= 0) return
  const code = typedIn.value
  const value = toSale(typed, code)
  const isCash = session.paymentModes.find((m) => m.mode_of_payment === mode)?.type === 'Cash'
  // Only cash can over-tender (change is given back)
  const capped = isCash ? value : Math.min(value, Math.max(remaining.value, 0))
  if (capped <= 0) return
  // What the tender took in its own money: exactly what was typed when it was
  // typed in that money, else the sale amount at the shift's rate.
  const modeCode = sale.value.foreign ? modeCurrency(mode) : sale.value.currency
  const tenderAmount = capped === value && modeCode === code ? typed : fromSale(capped, modeCode)
  pushPayment(mode, capped, { tender_currency: modeCode, tender_amount: tenderAmount })
  refillAmount()
}

function addStoreCredit() {
  const used = payments.value
    .filter((p) => p.mode_of_payment === session.storeCreditMode)
    .reduce((sum, p) => sum + p.amount, 0)
  const available = round2((wallet.value?.store_credit || 0) - used)
  const capped = round2(Math.min(available, Math.max(remaining.value, 0)))
  if (capped <= 0) return
  pushPayment(session.storeCreditMode, capped)
  refillAmount()
}

function addCashback() {
  const used = payments.value
    .filter((p) => p.mode_of_payment === session.cashbackMode)
    .reduce((sum, p) => sum + p.amount, 0)
  const available = round2((wallet.value?.cashback || 0) - used)
  const capped = round2(Math.min(available, Math.max(remaining.value, 0)))
  if (capped <= 0) return
  pushPayment(session.cashbackMode, capped)
  refillAmount()
}

function payWithDefault() {
  const modes = visibleModes.value
  const def = modes.find((m) => m.default) || modes[0]
  if (def) addPayment(def.mode_of_payment)
}

async function checkGiftCard() {
  if (!giftCardNo.value.trim() || giftCardChecking.value) return
  giftCardChecking.value = true
  giftCardInfo.value = null
  try {
    const info = await call('lumenpos.api.sales.gift_card_info', {
      card_no: giftCardNo.value,
      pos_profile: session.posProfile,
    })
    // Issued by a company whose balances this outlet does not take
    // (separate per company, or another currency).
    if (info.usable_here === 0) {
      session.notify(t('Gift card {card} was issued by {company} and is used at its outlets only.', { card: info.card_no, company: info.company }), true)
      return
    }
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
  pushPayment(session.giftCardMode, capped, { card_no: info.card_no })
  giftCardInfo.value = null
  giftCardNo.value = ''
  giftCardOpen.value = false
  refillAmount()
}

// Both sides valued by the server, with the same code that will post them, so
// the figure on screen is the one that settles.
async function loadExchange() {
  try {
    // Quoted from the SAME payload that will post, so the figure on screen and
    // the figure that settles cannot drift apart.
    const q = await call('lumenpos.api.exchanges.quote_exchange', {
      payload: {
        ...cart._basePayload(),
        original_invoice: cart.exchange.invoice,
        return_items: cart.exchange.items,
        serials: cart.exchange.serials,
      },
    })
    serverTotal.value = q.new_total
    exchangeCredit.value = q.returned_value
    exchangeRefund.value = q.refund
    refundModes.value = q.allowed_refund_modes || []
    refundMode.value = refundModes.value.includes('Cash') ? 'Cash' : refundModes.value[0] || null
    amount.value = round2(Math.max(q.due, 0))
  } catch (e) {
    session.notify(e.message, true)
  }
}

async function complete() {
  try {
    const giftCards = payments.value
      .filter((p) => p.card_no)
      .map((p) => ({ card_no: p.card_no, amount: p.amount }))
    if (cart.exchange) {
      const result = await cart.submitExchange(
        payments.value,
        refundMode.value,
        redeemPoints.value,
        giftCards
      )
      session.notify(t('Exchange completed'))
      emit('done', result.sale)
      return
    }
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
.method.blocked { opacity: 0.4; cursor: not-allowed; }
.split-ref {
  grid-column: 1 / -1;
  margin-top: 4px;
  padding: 6px 9px;
  border: 1px solid var(--border);
  border-radius: 8px;
  font: inherit;
  font-size: 12.5px;
  width: 100%;
}
.split-ref.missing { border-color: var(--red, #e23030); background: rgba(226, 48, 48, 0.06); }
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
.sell-in,
.tender-ccy {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.segmented {
  display: inline-flex;
  gap: 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 4px;
}
.seg-btn {
  border-radius: calc(var(--radius) - 2px);
  padding: 7px 18px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-muted);
}
.seg-btn:hover:not(:disabled) { color: var(--text); }
.seg-btn.on { background: var(--brand); color: #fff; }
.seg-btn:disabled { opacity: 0.5; cursor: not-allowed; }
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
.due-sub { font-size: 17px; font-weight: 700; color: var(--text-muted); }
.rate-note { margin-top: 4px; font-size: 12px; color: var(--text-muted); }
.exchange-box { padding: 12px 16px; margin-bottom: 12px; }
.ex-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 14px;
}
.ex-row.credit { color: var(--pos); }
.ex-row.net {
  border-top: 1px solid var(--border);
  margin-top: 4px;
  padding-top: 10px;
  font-size: 16px;
}
.ex-refund {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding-top: 8px;
}
.ex-refund select { padding: 6px 9px; border: 1px solid var(--border); border-radius: 8px; font: inherit; }

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
.cashback-earn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(20, 99, 255, 0.1);
  color: var(--brand-dark);
  font-weight: 700;
  font-size: 14px;
}
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
  position: relative;
}
.method:hover { border-color: var(--brand); }
.method.branded { justify-content: center; padding: 16px 14px; }
.method-icon { font-size: 20px; }
.mode-ccy {
  position: absolute;
  top: 6px;
  inset-inline-end: 8px;
  font-size: 10.5px;
  font-weight: 800;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.1);
  border-radius: 999px;
  padding: 1px 7px;
}
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
  flex-wrap: wrap;
}
.split-row:last-child { border-bottom: none; }
.split-row span:first-child { flex: 1; }
.split-amount { display: inline-flex; align-items: baseline; gap: 6px; }
.small { font-size: 12px; }
.complete { margin-top: 6px; }
.offline-note { text-align: center; margin: 0; }
</style>
