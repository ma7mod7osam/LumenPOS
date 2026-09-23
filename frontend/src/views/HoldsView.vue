<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="holds">
    <div class="card list">
      <div class="list-head">
        <div class="search-box">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m21 21-4.3-4.3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <input v-model="search" :placeholder="t('Customer or hold number…')" @input="debouncedLoad" />
        </div>
        <select v-model="status" @change="load">
          <option value="Open">{{ t('Open') }}</option>
          <option value="Completed">{{ t('Completed') }}</option>
          <option value="Cancelled">{{ t('Cancelled') }}</option>
          <option value="All">{{ t('All') }}</option>
        </select>
        <button class="btn btn-outline" @click="load"><Icon name="refresh" /></button>
      </div>

      <div v-if="session.offline" class="muted empty">{{ t('Holds need a connection.') }}</div>
      <div v-else-if="loading" class="muted empty">{{ t('Loading…') }}</div>
      <div v-else-if="!holds.length" class="muted empty">{{ t('Nothing is on hold right now.') }}</div>
      <button
        v-for="hold in holds"
        :key="hold.name"
        class="hold-row"
        :class="{ active: open?.name === hold.name }"
        @click="show(hold.name)"
      >
        <div class="hold-info">
          <div class="hold-customer">
            {{ hold.customer_name }}
            <span v-if="hold.overdue" class="tag amber">{{ t('Past the date') }}</span>
            <span v-if="hold.status !== 'Open'" class="tag">{{ t(hold.status) }}</span>
          </div>
          <div class="muted small">
            {{ hold.name }}<span v-if="hold.expiry_date"> · {{ t('until') }} {{ hold.expiry_date }}</span>
          </div>
        </div>
        <div class="hold-right">
          <div class="hold-balance" :class="{ paid: hold.balance <= 0 }">{{ money(hold.balance) }}</div>
          <div class="muted small">{{ t('{paid} of {total}', { paid: money(hold.paid), total: money(hold.total) }) }}</div>
        </div>
      </button>
    </div>

    <div v-if="open" class="card detail">
      <div class="detail-head">
        <div>
          <div class="detail-title">{{ open.customer_name }}</div>
          <div class="muted small">{{ open.name }} · {{ t(open.status) }}</div>
        </div>
        <button class="btn-ghost" @click="open = null"><Icon name="close" /></button>
      </div>

      <div class="detail-body">
        <table class="mini">
          <tr v-for="row in open.items" :key="row.item_code">
            <td>{{ row.qty }} × {{ row.item_name }}</td>
            <td class="right">{{ money(row.amount) }}</td>
          </tr>
          <tr class="sum">
            <td>{{ t('Total') }}</td>
            <td class="right">{{ money(open.total) }}</td>
          </tr>
          <tr>
            <td>{{ t('Paid so far') }}</td>
            <td class="right">{{ money(open.paid) }}</td>
          </tr>
          <tr class="sum">
            <td>{{ t('Still to pay') }}</td>
            <td class="right">{{ money(open.balance) }}</td>
          </tr>
        </table>

        <div v-if="open.payments.length" class="instalments">
          <div class="muted small">{{ t('Instalments') }}</div>
          <div v-for="(row, i) in open.payments" :key="i" class="instalment">
            <span>{{ (row.paid_at || '').slice(0, 16) }}</span>
            <span>{{ row.mode_of_payment }}</span>
            <span :class="{ refunded: row.refunded }">{{ money(row.amount) }}</span>
          </div>
        </div>

        <template v-if="open.status === 'Open' && canHold">
          <div class="pay-row">
            <input type="number" min="0" step="0.01" v-model.number="payAmount" :placeholder="t('Amount')" />
            <select v-model="payMode">
              <option v-for="mode in modes" :key="mode.mode_of_payment" :value="mode.mode_of_payment">
                {{ mode.mode_of_payment }}
              </option>
            </select>
            <button class="btn btn-outline" :disabled="busy || !payAmount || !payMode" @click="takePayment">
              {{ t('Take payment') }}
            </button>
          </div>
          <div class="actions">
            <button class="btn btn-primary" :disabled="busy" @click="handOver">
              {{ t('Hand over, collect {amount}', { amount: money(open.balance) }) }}
            </button>
            <button class="btn btn-outline danger" :disabled="busy" @click="cancelHold">
              {{ t('Cancel hold and refund {amount}', { amount: money(open.paid) }) }}
            </button>
          </div>
          <p class="muted small">
            {{ t('Handing over sells the goods at the price agreed on the day of the hold. What is already paid comes off the bill.') }}
          </p>
        </template>
        <p v-else-if="open.completed_invoice" class="muted small">
          {{ t('Handed over on {invoice}', { invoice: open.completed_invoice }) }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from '../components/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money } from '../format'
import { t } from '../i18n'

const session = useSessionStore()
const holds = ref([])
const open = ref(null)
const loading = ref(true)
const busy = ref(false)
const search = ref('')
const status = ref('Open')
const payAmount = ref(null)
const payMode = ref(null)
let timer = null

const canHold = computed(() => session.permissions.can_hold_goods !== false)
const modes = computed(() =>
  session.paymentModes.filter(
    (m) =>
      m.mode_of_payment !== session.storeCreditMode &&
      m.mode_of_payment !== session.cashbackMode &&
      m.mode_of_payment !== session.giftCardMode
  )
)

function debouncedLoad() {
  clearTimeout(timer)
  timer = setTimeout(load, 250)
}

async function load() {
  if (session.offline) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    const data = await call('lumenpos.api.layaway.list_layaways', {
      pos_profile: session.posProfile,
      status: status.value,
      search: search.value,
    })
    holds.value = data.layaways
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function show(name) {
  open.value = await call('lumenpos.api.layaway.get_layaway', { name })
  payAmount.value = open.value.balance || null
  payMode.value = (modes.value.find((m) => m.default) || modes.value[0])?.mode_of_payment
}

async function takePayment() {
  busy.value = true
  try {
    const res = await call('lumenpos.api.layaway.add_instalment', {
      layaway: open.value.name,
      payments: [{ mode_of_payment: payMode.value, amount: Number(payAmount.value) }],
    })
    open.value = res.layaway
    payAmount.value = open.value.balance || null
    session.notify(t('Payment taken'))
    load()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function handOver() {
  const due = open.value.balance
  const payments = due > 0 ? [{ mode_of_payment: payMode.value, amount: due }] : []
  busy.value = true
  try {
    const res = await call('lumenpos.api.layaway.complete_layaway', {
      layaway: open.value.name,
      payments,
    })
    open.value = res.layaway
    session.notify(t('Goods handed over'))
    load()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function cancelHold() {
  busy.value = true
  try {
    const res = await call('lumenpos.api.layaway.cancel_layaway', {
      layaway: open.value.name,
      refund_mode: payMode.value,
    })
    open.value = res.layaway
    session.notify(t('Hold cancelled and refunded'))
    load()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.holds { flex: 1; display: flex; gap: 14px; padding: 14px; overflow: hidden; }
.list { flex: 1; display: flex; flex-direction: column; overflow: auto; }
.detail { width: 380px; display: flex; flex-direction: column; overflow: auto; }
.list-head { display: flex; gap: 8px; padding: 12px; border-bottom: 1px solid var(--border); }
.list-head select { padding: 7px 9px; border: 1px solid var(--border); border-radius: 8px; font: inherit; }
.search-box { flex: 1; display: flex; align-items: center; gap: 6px; border: 1px solid var(--border); border-radius: 8px; padding: 0 9px; }
.search-box svg { width: 16px; height: 16px; color: var(--muted); }
.search-box input { flex: 1; border: 0; padding: 8px 0; font: inherit; background: transparent; outline: none; }
.hold-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 11px 14px;
  border: 0;
  border-bottom: 1px solid var(--border);
  background: transparent;
  font: inherit;
  text-align: start;
  cursor: pointer;
  width: 100%;
}
.hold-row:hover, .hold-row.active { background: var(--surface-2); }
.hold-customer { font-weight: 600; display: flex; align-items: center; gap: 6px; }
.hold-right { text-align: end; }
.hold-balance { font-weight: 700; }
.hold-balance.paid { color: var(--pos, #1d9a6c); }
.empty { padding: 26px; text-align: center; }
.detail-head { display: flex; justify-content: space-between; align-items: flex-start; padding: 14px; border-bottom: 1px solid var(--border); }
.detail-title { font-weight: 700; font-size: 15px; }
.detail-body { padding: 14px; display: flex; flex-direction: column; gap: 12px; }
.mini { width: 100%; font-size: 13px; }
.mini td { padding: 3px 0; }
.mini .right { text-align: end; }
.mini .sum td { border-top: 1px solid var(--border); font-weight: 700; padding-top: 6px; }
.instalments { display: flex; flex-direction: column; gap: 4px; }
.instalment { display: flex; justify-content: space-between; gap: 8px; font-size: 12.5px; }
.instalment .refunded { text-decoration: line-through; opacity: 0.6; }
.pay-row { display: grid; grid-template-columns: 1fr 1fr auto; gap: 8px; }
.pay-row input, .pay-row select { padding: 7px 9px; border: 1px solid var(--border); border-radius: 8px; font: inherit; }
.actions { display: flex; flex-direction: column; gap: 8px; }
.actions .danger { color: var(--neg, #c23434); }
.tag { font-size: 11px; padding: 1px 6px; border-radius: 6px; background: var(--surface-2); }
.tag.amber { background: rgba(230, 160, 20, 0.18); color: #a06a00; }
</style>
