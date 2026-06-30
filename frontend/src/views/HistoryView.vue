<template>
  <div class="history">
    <div class="card list">
      <div class="list-head">
        <div class="search-box">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m21 21-4.3-4.3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <input
            v-model="filters.search"
            :placeholder="t('Invoice no, customer, mobile or order ID…')"
            @input="debouncedLoad"
          />
        </div>
        <button class="btn btn-outline" :class="{ 'filters-on': activeFilterCount }" @click="showFilters = !showFilters">
          {{ t('Filters') }}{{ activeFilterCount ? ` (${activeFilterCount})` : '' }} {{ showFilters ? '▴' : '▾' }}
        </button>
        <button class="btn btn-outline" @click="load"><Icon name="refresh" /></button>
      </div>

      <div v-if="showFilters" class="filter-grid">
        <label class="f-field">
          <span>{{ t('From date') }}</span>
          <input type="date" v-model="filters.date_from" @change="load" />
        </label>
        <label class="f-field">
          <span>{{ t('To date') }}</span>
          <input type="date" v-model="filters.date_to" @change="load" />
        </label>
        <label class="f-field">
          <span>{{ t('Status') }}</span>
          <select v-model="filters.status" @change="load">
            <option value="">{{ t('All') }}</option>
            <option>Paid</option>
            <option>Consolidated</option>
            <option>Return</option>
            <option>Draft</option>
            <option>Cancelled</option>
          </select>
        </label>
        <label class="f-field">
          <span>{{ t('Document status') }}</span>
          <select v-model="filters.docstatus" @change="load">
            <option>Submitted</option>
            <option>Draft</option>
            <option>Cancelled</option>
            <option>All</option>
          </select>
        </label>
        <label class="f-field">
          <span>{{ t('Channel') }}</span>
          <select v-model="filters.app_type" @change="load">
            <option value="">{{ t('All') }}</option>
            <option>Walk-in</option>
            <option v-for="app in session.settings.delivery_apps" :key="app.app_name" :value="app.app_name">
              {{ app.app_name }}
            </option>
          </select>
        </label>
        <label class="f-field">
          <span>{{ t('Online order') }}</span>
          <select v-model="filters.online_order" @change="load">
            <option value="">{{ t('Any') }}</option>
            <option value="1">{{ t('Online only') }}</option>
            <option value="0">{{ t('In-store only') }}</option>
          </select>
        </label>
        <label class="f-field">
          <span>{{ t('Payment method') }}</span>
          <select v-model="filters.payment_mode" @change="load">
            <option value="">{{ t('Any') }}</option>
            <option v-for="m in paymentModeOptions" :key="m" :value="m">{{ m }}</option>
          </select>
        </label>
        <label class="f-field">
          <span>{{ t('Outlet') }}</span>
          <select v-model="profileFilter" @change="load">
            <option value="">{{ session.posProfile }} {{ t('(this register)') }}</option>
            <option value="__all__">{{ t('All outlets') }}</option>
            <option v-for="profile in otherProfiles" :key="profile" :value="profile">{{ profile }}</option>
          </select>
        </label>
        <label class="f-field">
          <span>{{ t('Item') }}</span>
          <input v-model="filters.item" :placeholder="t('Code or name')" @input="debouncedLoad" />
        </label>
        <label class="f-field">
          <span>{{ t('Serial no') }}</span>
          <input v-model="filters.serial_no" :placeholder="t('Serial number')" @input="debouncedLoad" />
        </label>
        <label class="f-field">
          <span>{{ t('Total from') }}</span>
          <input type="number" min="0" v-model.number="filters.total_min" @change="load" />
        </label>
        <label class="f-field">
          <span>{{ t('Total to') }}</span>
          <input type="number" min="0" v-model.number="filters.total_max" @change="load" />
        </label>
        <div class="f-actions">
          <button class="btn btn-ghost" @click="clearFilters">{{ t('Clear filters') }}</button>
        </div>
      </div>

      <div v-if="session.offline" class="muted empty">{{ t('Sales history needs a connection.') }}</div>
      <div v-else-if="loading" class="muted empty">{{ t('Loading…') }}</div>
      <div v-else-if="!sales.length" class="muted empty">{{ t('No sales match') }}</div>
      <button
        v-for="sale in sales"
        :key="sale.name"
        class="sale-row"
        :class="{ active: receipt?.name === sale.name }"
        @click="show(sale.name)"
      >
        <div class="sale-info">
          <div class="sale-customer">
            {{ sale.customer_name }}
            <span v-if="sale.is_return" class="tag red">{{ t('REFUND') }}</span>
            <span v-if="sale.is_exchange" class="tag purple"><Icon name="exchange" /> {{ t('EXCHANGE') }}</span>
            <span v-if="sale.docstatus === 2" class="tag red">{{ t('CANCELLED') }}</span>
            <span v-else-if="sale.docstatus === 0" class="tag amber">{{ t('DRAFT') }}</span>
            <span v-if="sale.app_type" class="tag blue"><Icon name="bike" /> {{ sale.app_type }}</span>
            <span v-if="sale.online_order && !sale.app_type" class="tag blue">{{ t('ONLINE') }}</span>
          </div>
          <div class="muted small">
            {{ sale.name }} · {{ shortTime(sale.posting_date + ' ' + sale.posting_time) }}<span v-if="sale.owner_name"> · <Icon name="person" /> {{ sale.owner_name }}</span><span v-if="sale.mobile_no"> · {{ sale.mobile_no }}</span><span v-if="sale.order_id"> · {{ t('Order') }} {{ sale.order_id }}</span><span v-if="profileFilter"> · {{ sale.pos_profile }}</span>
          </div>
        </div>
        <div class="sale-right">
          <div class="sale-amount" :class="{ neg: sale.grand_total < 0 }">{{ money(sale.grand_total) }}</div>
          <div class="muted small status-line">{{ sale.status }}</div>
          <div v-if="sale.payment_modes" class="muted small pay-line"><Icon name="card" /> {{ sale.payment_modes }}</div>
        </div>
      </button>
    </div>

    <ReceiptModal
      v-if="receipt"
      :receipt="receipt"
      :can-refund="session.permissions.can_return !== false"
      @close="receipt = null"
      @refund="startRefund"
    />
    <RefundModal
      v-if="refundInvoice"
      :invoice="refundInvoice"
      @close="refundInvoice = null"
      @done="onRefundDone"
    />
  </div>
</template>

<script setup>
import Icon from '../components/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money, shortTime } from '../format'
import { t } from '../i18n'
import ReceiptModal from '../components/ReceiptModal.vue'
import RefundModal from '../components/RefundModal.vue'

const session = useSessionStore()
const sales = ref([])
const loading = ref(true)
const receipt = ref(null)
const refundInvoice = ref(null)
const showFilters = ref(false)
const profileFilter = ref('')
let timer = null

const emptyFilters = () => ({
  search: '',
  date_from: '',
  date_to: '',
  status: '',
  docstatus: 'Submitted',
  app_type: '',
  online_order: '',
  item: '',
  serial_no: '',
  payment_mode: '',
  total_min: null,
  total_max: null,
})
const filters = ref(emptyFilters())

const otherProfiles = computed(() =>
  session.availableProfiles.filter((profile) => profile !== session.posProfile)
)

// Payment methods offered in the filter: the outlet's modes plus Store Credit /
// Gift Card (refund/redeem tenders that also appear on invoices).
const paymentModeOptions = computed(() => {
  const modes = (session.paymentModes || []).map((m) => m.mode_of_payment)
  for (const extra of [session.storeCreditMode, session.giftCardMode]) {
    if (extra && !modes.includes(extra)) modes.push(extra)
  }
  return modes
})

const activeFilterCount = computed(() => {
  const f = filters.value
  let count = 0
  if (f.date_from || f.date_to) count++
  if (f.status) count++
  if (f.docstatus !== 'Submitted') count++
  if (f.app_type) count++
  if (f.online_order) count++
  if (f.item) count++
  if (f.serial_no) count++
  if (f.payment_mode) count++
  if (f.total_min != null && f.total_min !== '') count++
  if (f.total_max != null && f.total_max !== '') count++
  if (profileFilter.value) count++
  return count
})

onMounted(load)

function debouncedLoad() {
  clearTimeout(timer)
  timer = setTimeout(load, 300)
}

async function load() {
  if (session.offline) {
    loading.value = false
    return
  }
  loading.value = true
  try {
    // pos_profile is always sent (drives which backend table to read); a
    // specific filter overrides it, and all_profiles=1 ignores it as a filter.
    const payload = { ...filters.value, limit: 100, pos_profile: session.posProfile }
    if (profileFilter.value === '__all__') {
      payload.all_profiles = 1
    } else if (profileFilter.value) {
      payload.pos_profile = profileFilter.value
    }
    sales.value = await call('lumenpos.api.sales.search_sales', { filters: payload })
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

function clearFilters() {
  filters.value = emptyFilters()
  profileFilter.value = ''
  load()
}

async function show(name) {
  receipt.value = await call('lumenpos.api.sales.get_receipt', { invoice: name })
}

function startRefund(invoice) {
  receipt.value = null
  refundInvoice.value = invoice
}

async function onRefundDone(returnReceipt) {
  refundInvoice.value = null
  receipt.value = returnReceipt
  await load()
}
</script>

<style scoped>
.history {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}
.list { max-width: 860px; margin: 0 auto; }
.list-head {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.search-box {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}
.search-box svg {
  position: absolute;
  left: 11px;
  width: 16px;
  height: 16px;
  color: var(--text-muted);
}
.search-box input {
  width: 100%;
  padding: 9px 12px 9px 34px;
}
.filters-on { border-color: var(--brand); color: var(--brand); }
.filter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}
.f-field { display: flex; flex-direction: column; gap: 4px; }
.f-field span {
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
}
.f-field input, .f-field select { padding: 7px 9px; font-size: 13px; }
.f-actions { display: flex; align-items: flex-end; }
.sale-row {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 13px 18px;
  border-bottom: 1px solid var(--border);
  text-align: left;
}
.sale-row:hover, .sale-row.active { background: var(--surface-2); }
.sale-customer { font-weight: 600; }
.tag {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.06em;
  margin-left: 6px;
  border-radius: 999px;
  padding: 1px 8px;
}
.tag.red { color: #b5231f; background: rgba(226, 48, 48, 0.14); }
.tag.amber { color: #9a6a0a; background: rgba(245, 166, 35, 0.18); }
.tag.blue { color: var(--brand-dark); background: rgba(20, 99, 255, 0.12); }
.tag.purple { color: #5b2bbf; background: rgba(123, 47, 242, 0.14); }
/* Dark mode: faint tints + dark text are unreadable — brighten both. */
html[data-theme='dark'] .tag.red { color: #ff9b9b; background: rgba(226, 48, 48, 0.26); }
html[data-theme='dark'] .tag.amber { color: #ffce85; background: rgba(245, 166, 35, 0.26); }
html[data-theme='dark'] .tag.blue { color: #b8c7ff; background: rgba(20, 99, 255, 0.30); }
html[data-theme='dark'] .tag.purple { color: #cbb8ff; background: rgba(123, 47, 242, 0.34); }
.sale-right { text-align: right; }
.sale-amount { font-weight: 700; }
.sale-amount.neg { color: var(--red); }
.status-line { margin-top: 1px; }
.pay-line { margin-top: 1px; display: inline-flex; align-items: center; gap: 4px; justify-content: flex-end; max-width: 220px; }
.small { font-size: 12px; }
.empty { padding: 40px; text-align: center; }
</style>
