<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <!-- A customer's account (lumenpos.api.credit, 0.60.0): what they owe sale by
       sale, a payment of it into this till's drawer, and a manager's switch and
       limit on their card. Shown only while the shop sells on account. -->
  <section v-if="facts && facts.enabled" class="credit-card card" data-tour="customer-credit">
    <div class="cr-head">
      <h3><Icon name="clock" /> {{ t('On account') }}</h3>
      <span v-if="facts.reason" class="badge amber">{{ t('Not on account') }}</span>
    </div>

    <div class="cr-stats">
      <div class="cr-stat">
        <div class="cr-v">{{ money(facts.owed, facts.currency) }}</div>
        <div class="cr-l">{{ t('Owes') }}</div>
      </div>
      <!-- Holds and orders not invoiced (0.61.1): not owed, but ERPNext
           counts them against the limit, so "Left to use" takes them off. -->
      <div v-if="facts.held > 0" class="cr-stat" data-tour="customer-credit-held">
        <div class="cr-v">{{ money(facts.held, facts.currency) }}</div>
        <div class="cr-l">{{ t('Holds and orders not invoiced') }}</div>
      </div>
      <div class="cr-stat">
        <div class="cr-v">{{ facts.limit > 0 ? money(facts.limit, facts.currency) : t('No limit') }}</div>
        <div class="cr-l">{{ facts.limit_source === 'default' ? t('Credit limit (shop default)') : t('Credit limit') }}</div>
      </div>
      <div v-if="facts.available != null" class="cr-stat">
        <div class="cr-v">{{ money(facts.available, facts.currency) }}</div>
        <div class="cr-l">{{ t('Left to use') }}</div>
      </div>
    </div>
    <p v-if="facts.held > 0" class="muted small cr-held">{{ t('Not owed yet, but ERPNext counts them against the credit limit.') }}</p>
    <p v-if="facts.reason" class="muted small cr-why">{{ facts.reason }}</p>

    <!-- A manager's switch and limit (Who can do what: Set a customer's credit). -->
    <div v-if="facts.can_set" class="cr-set">
      <label v-if="facts.who === ALLOWED_ONLY" class="setting-row">
        <input v-model="allow" type="checkbox" class="setting-toggle" />
        <span class="setting-text">
          <span class="setting-title">{{ t('Allowed to buy on account') }}</span>
          <span class="setting-desc">{{ t('Only customers allowed here may buy on account (Settings, General, Sales on account).') }}</span>
        </span>
      </label>
      <label class="field cr-limit">
        <span>{{ t("Credit limit of their own (0 = the group's, the company's or the shop's default)") }}</span>
        <input v-model.number="limit" type="number" min="0" step="0.01" />
      </label>
      <button class="btn btn-outline" :disabled="saving || !changed" @click="saveCredit">
        {{ saving ? t('Saving…') : t('Save') }}
      </button>
    </div>

    <table v-if="facts.items.length" class="cr-items">
      <thead>
        <tr>
          <th v-if="taking" class="cr-pick"></th>
          <th>{{ t('Sale') }}</th>
          <th>{{ t('Date') }}</th>
          <th class="right">{{ t('Still owed') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in facts.items" :key="item.name">
          <td v-if="taking" class="cr-pick">
            <input v-model="chosen" type="checkbox" :value="item.name" :aria-label="item.invoice" />
          </td>
          <td class="mono">{{ item.invoice }}</td>
          <td class="muted small">{{ item.posting_date }}</td>
          <td class="right">{{ money(item.outstanding, facts.currency) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="muted small">{{ t('Nothing owed.') }}</p>

    <!-- Taking a payment (Who can do what: Take customer payments). -->
    <div v-if="facts.can_take_payment && facts.items.length && !taking" class="cr-actions">
      <button class="btn btn-primary" :disabled="!canTake" data-tour="customer-take-payment" @click="startTaking">
        <Icon name="cash" /> {{ t('Take a payment') }}
      </button>
      <span v-if="!session.registerOpen" class="muted small">{{ t('Open the register first: the payment goes into its drawer.') }}</span>
      <span v-else-if="session.offline" class="muted small">{{ t('A payment needs a connection.') }}</span>
    </div>
    <div v-if="taking" class="cr-form">
      <p class="muted small">
        {{ chosen.length ? t('It settles the sales ticked above, oldest first.') : t('It settles the oldest sales first. Tick sales above to settle those instead.') }}
      </p>
      <div class="cr-row">
        <label class="field">
          <span>{{ t('Amount') }}</span>
          <input v-model="amount" type="text" inputmode="decimal" />
        </label>
        <label class="field">
          <span>{{ t('Paid by') }}</span>
          <select v-model="mode">
            <option v-for="m in payModes" :key="m.mode_of_payment" :value="m.mode_of_payment">{{ m.mode_of_payment }}</option>
          </select>
        </label>
        <label v-if="needsReference" class="field">
          <span>{{ t('Reference') }}</span>
          <input v-model="reference" />
        </label>
      </div>
      <p v-if="tooMuch" class="cr-warn small">{{ t('The customer owes {amount} on these sales: take at most that.', { amount: money(open, facts.currency) }) }}</p>
      <div class="cr-actions">
        <button class="btn btn-outline" :disabled="busy" @click="stopTaking">{{ t('Cancel') }}</button>
        <button class="btn btn-primary" :disabled="busy || !valid" @click="take">
          {{ busy ? t('Taking…') : t('Take {amount}', { amount: money(parsed || 0, facts.currency) }) }}
        </button>
      </div>
    </div>

    <!-- The payment's receipt, printable on its own (#payment-print). -->
    <div v-if="paid" class="cr-receipt">
      <div id="payment-print" class="payment-receipt">
        <div class="pr-title">{{ t('Payment received') }}</div>
        <div class="pr-row"><span>{{ paid.customer_name }}</span><span class="mono">{{ paid.name }}</span></div>
        <div class="pr-row muted small"><span>{{ paid.posting_date }}</span><span>{{ paid.mode_of_payment }}<template v-if="paid.reference_no"> · {{ paid.reference_no }}</template></span></div>
        <div v-for="row in paid.allocations" :key="row.name" class="pr-row">
          <span class="mono">{{ row.invoice }}</span><span>{{ money(row.allocated, paid.currency) }}</span>
        </div>
        <div class="pr-row pr-total"><span>{{ t('Paid') }}</span><span>{{ money(paid.amount, paid.currency) }}</span></div>
        <div class="pr-row"><span>{{ t('Still owed') }}</span><span>{{ money(paid.owed_after, paid.currency) }}</span></div>
      </div>
      <div class="cr-actions">
        <button class="btn btn-outline" @click="printPayment"><Icon name="download" /> {{ t('Print') }}</button>
        <button class="btn btn-outline" @click="paid = null">{{ t('Done') }}</button>
      </div>
    </div>
  </section>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, watch } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money, parseMoney } from '../format'
import { t } from '../i18n'
import { newId } from '../offline'

const props = defineProps({
  customer: { type: String, required: true },
  company: { type: String, default: null },
})
const emit = defineEmits(['changed'])
const session = useSessionStore()
const ALLOWED_ONLY = 'Customers allowed on their card'

const facts = ref(null)
const allow = ref(false)
const limit = ref(0)
const saving = ref(false)

const taking = ref(false)
const chosen = ref([])
const amount = ref('')
const mode = ref(null)
const reference = ref('')
const busy = ref(false)
const paid = ref(null)
let key = null

async function load() {
  facts.value = null
  if (!props.customer || !(session.settings?.credit_sales_enabled)) return
  try {
    facts.value = await call('lumenpos.api.credit.customer_credit', {
      customer: props.customer,
      company: props.company || session.company,
    })
    allow.value = Boolean(facts.value.allowed_on_card)
    limit.value = Number(facts.value.erpnext_limit) || 0
  } catch {
    facts.value = null // the card is optional; the profile still shows
  }
}

const changed = computed(
  () =>
    facts.value &&
    (Boolean(facts.value.allowed_on_card) !== Boolean(allow.value) ||
      (Number(facts.value.erpnext_limit) || 0) !== (Number(limit.value) || 0))
)

async function saveCredit() {
  saving.value = true
  try {
    facts.value = await call('lumenpos.api.credit.set_customer_credit', {
      customer: props.customer,
      company: props.company || session.company,
      allow: allow.value ? 1 : 0,
      limit: Number(limit.value) || 0,
    })
    allow.value = Boolean(facts.value.allowed_on_card)
    limit.value = Number(facts.value.erpnext_limit) || 0
    session.notify(t('Saved'))
    emit('changed')
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

// Money the till may take a debt in: the outlet's own tenders in the company's
// currency, never LumenPOS's internal ones.
const payModes = computed(() => {
  const internal = [session.storeCreditMode, session.cashbackMode, session.giftCardMode, session.creditMode, 'Exchange']
  return (session.paymentModes || []).filter(
    (m) => !internal.includes(m.mode_of_payment) && (!m.account_currency || m.account_currency === facts.value?.currency)
  )
})
const canTake = computed(() => session.registerOpen && !session.offline && payModes.value.length > 0)
const needsReference = computed(() => {
  const m = payModes.value.find((x) => x.mode_of_payment === mode.value)
  return Boolean(m && (m.type === 'Bank' || m.require_reference))
})
const open = computed(() => {
  const items = facts.value?.items || []
  const pick = chosen.value.length ? items.filter((i) => chosen.value.includes(i.name)) : items
  return Math.round(pick.reduce((sum, i) => sum + i.outstanding, 0) * 100) / 100
})
const parsed = computed(() => parseMoney(amount.value))
const tooMuch = computed(() => (parsed.value || 0) > open.value + 0.005)
const valid = computed(() => (parsed.value || 0) > 0 && !tooMuch.value && Boolean(mode.value))

function startTaking() {
  taking.value = true
  chosen.value = []
  amount.value = open.value.toFixed(2)
  const cash = payModes.value.find((m) => m.type === 'Cash')
  mode.value = (cash || payModes.value[0])?.mode_of_payment || null
  reference.value = ''
  // One key per payment from its first attempt: a retry after a lost answer
  // finds the payment that posted instead of taking the money twice.
  key = newId()
}
function stopTaking() {
  taking.value = false
  chosen.value = []
}
// The amount follows the sales ticked until the cashier types their own.
watch(chosen, () => {
  if (taking.value) amount.value = open.value.toFixed(2)
})

async function take() {
  busy.value = true
  try {
    const items = (facts.value.items || [])
      .filter((i) => chosen.value.includes(i.name))
      .map((i) => ({ doctype: i.doctype, name: i.name }))
    paid.value = await call('lumenpos.api.credit.receive_payment', {
      customer: props.customer,
      pos_profile: session.posProfile,
      amount: parsed.value,
      mode_of_payment: mode.value,
      items: JSON.stringify(items),
      reference_no: reference.value || null,
      idempotency_key: key,
    })
    session.notify(t('Payment taken'))
    taking.value = false
    chosen.value = []
    await load()
    emit('changed')
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

function printPayment() {
  window.print()
}

watch(() => [props.customer, props.company], load, { immediate: true })
</script>

<style scoped>
.credit-card { padding: 14px 16px; margin: 14px 0; display: flex; flex-direction: column; gap: 10px; }
.cr-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.cr-head h3 { margin: 0; font-size: 15px; display: inline-flex; align-items: center; gap: 6px; }
.cr-stats { display: flex; gap: 10px; flex-wrap: wrap; }
.cr-stat {
  flex: 1 1 140px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
}
.cr-v { font-size: 17px; font-weight: 800; }
.cr-l { font-size: 12px; color: var(--text-muted); }
.cr-why { margin: 0; }
.cr-held { margin: 0; }
.cr-set { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border); padding-top: 10px; }
.cr-set .btn { align-self: flex-start; }
.cr-limit { max-width: 360px; }
.cr-items { width: 100%; border-collapse: collapse; font-size: 13px; }
.cr-items th {
  text-align: start;
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  padding: 6px 4px;
}
.cr-items td { padding: 7px 4px; border-top: 1px solid var(--border); }
.cr-items .right { text-align: end; }
.cr-pick { width: 28px; }
.cr-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.cr-form { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border); padding-top: 10px; }
.cr-form p { margin: 0; }
.cr-row { display: flex; gap: 10px; flex-wrap: wrap; }
.cr-row .field { flex: 1 1 150px; }
.cr-warn { color: var(--red); margin: 0; font-weight: 600; }
.cr-receipt { border-top: 1px solid var(--border); padding-top: 10px; display: flex; flex-direction: column; gap: 10px; }
.payment-receipt {
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 12px;
  font-size: 13px;
  max-width: 360px;
}
.pr-title { font-weight: 800; text-align: center; margin-bottom: 6px; }
.pr-row { display: flex; justify-content: space-between; gap: 10px; padding: 3px 0; }
.pr-total { font-weight: 800; border-top: 1px solid var(--border); margin-top: 4px; padding-top: 6px; }
.badge {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}
.badge.amber { background: rgba(245, 166, 35, 0.16); color: #9a6a0a; }
.mono { font-family: var(--mono); }
/* The Settings screen's own row and field, copied: those styles are scoped. */
.setting-row { display: flex; align-items: flex-start; gap: 12px; cursor: pointer; }
.setting-toggle { margin-top: 2px; width: 17px; height: 17px; flex-shrink: 0; cursor: pointer; }
.setting-text { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.setting-title { font-weight: 600; font-size: 13.5px; color: var(--text); }
.setting-desc { font-size: 12.75px; color: var(--text-muted); line-height: 1.55; }
.field { display: flex; flex-direction: column; gap: 5px; }
.field span { font-size: 12.25px; font-weight: 500; line-height: 1.5; color: var(--text-muted); }
:global(html[data-theme='dark']) .badge.amber { color: #f0b54a; }
</style>
