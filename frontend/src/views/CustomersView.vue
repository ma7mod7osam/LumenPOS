<template>
  <div class="customers">
    <!-- Left: searchable, paginated customer list -->
    <aside class="cust-list">
      <div class="list-head">
        <div class="search-box">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m21 21-4.3-4.3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <input
            :value="search"
            :placeholder="t('Search name, phone, code, email…')"
            @input="onSearch($event.target.value)"
          />
          <button v-if="search" class="btn-ghost clear" @click="onSearch('')"><Icon name="close" /></button>
        </div>
        <select v-model="group" class="group-select" @change="reload">
          <option value="">{{ t('All groups') }}</option>
          <option v-for="g in groups" :key="g" :value="g">{{ g }}</option>
        </select>
      </div>
      <div class="list-body">
        <button
          v-for="c in customers"
          :key="c.name"
          class="cust-row"
          :class="{ active: selected && selected.name === c.name }"
          @click="select(c)"
        >
          <div class="cust-name">{{ c.customer_name }}</div>
          <div class="muted small">
            <span v-if="c.mobile_no">{{ c.mobile_no }}</span>
            <span v-if="c.customer_group"> · {{ c.customer_group }}</span>
          </div>
        </button>
        <div v-if="loadingList" class="muted center pad">{{ t('Loading…') }}</div>
        <div v-else-if="!customers.length" class="muted center pad">{{ t('No customers found') }}</div>
        <button v-if="hasMore && !loadingList" class="btn btn-outline load-more" @click="loadMore">
          {{ t('Load more') }}
        </button>
      </div>
    </aside>

    <!-- Right: selected customer's profile + transactions -->
    <section class="cust-detail">
      <div v-if="!selected" class="empty-detail muted">
        <svg viewBox="0 0 24 24" width="46" height="46"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <p>{{ t('Select a customer to see their profile and transactions') }}</p>
      </div>
      <div v-else-if="loadingDetail" class="muted center pad">{{ t('Loading…') }}</div>
      <template v-else-if="detail">
        <header class="detail-head">
          <div>
            <h2>{{ detail.customer_name }}</h2>
            <div class="muted">{{ detail.name }}<span v-if="detail.customer_group"> · {{ detail.customer_group }}</span></div>
          </div>
        </header>

        <div class="profile-grid">
          <div v-if="detail.mobile_no"><span class="lbl">{{ t('Phone') }}</span>{{ detail.mobile_no }}</div>
          <div v-if="detail.email_id"><span class="lbl">{{ t('Email') }}</span>{{ detail.email_id }}</div>
          <div v-if="detail.tax_id"><span class="lbl">{{ t('Tax ID') }}</span>{{ detail.tax_id }}</div>
          <div v-if="detail.customer_type"><span class="lbl">{{ t('Type') }}</span>{{ detail.customer_type }}</div>
          <div v-if="detail.member_since"><span class="lbl">{{ t('Member since') }}</span>{{ detail.member_since }}</div>
          <div v-if="detail.stats.last_purchase"><span class="lbl">{{ t('Last purchase') }}</span>{{ detail.stats.last_purchase }}</div>
        </div>

        <div class="stat-cards">
          <div class="stat"><div class="stat-v">{{ detail.stats.sales_count }}</div><div class="stat-l">{{ t('Sales') }}</div></div>
          <div class="stat"><div class="stat-v">{{ money(detail.stats.net_spent) }}</div><div class="stat-l">{{ t('Net spent') }}</div></div>
          <div class="stat"><div class="stat-v">{{ detail.stats.returns_count }}</div><div class="stat-l">{{ t('Returns') }}</div></div>
          <div class="stat"><div class="stat-v">{{ detail.wallet.loyalty_points }}</div><div class="stat-l">{{ t('Loyalty points') }}</div></div>
          <div class="stat"><div class="stat-v">{{ money(detail.wallet.store_credit) }}</div><div class="stat-l">{{ t('Store credit') }}</div></div>
        </div>

        <div class="txn-head">
          <h3>{{ t('Transactions') }}</h3>
          <div class="txn-filters">
            <select v-model="txnType" @change="reloadTxns">
              <option value="">{{ t('All') }}</option>
              <option value="0">{{ t('Sales') }}</option>
              <option value="1">{{ t('Returns') }}</option>
            </select>
            <input type="date" v-model="dateFrom" :title="t('From')" @change="reloadTxns" />
            <input type="date" v-model="dateTo" :title="t('To')" @change="reloadTxns" />
          </div>
        </div>
        <table class="txn-table">
          <thead>
            <tr>
              <th>{{ t('Invoice') }}</th>
              <th>{{ t('Date') }}</th>
              <th>{{ t('Type') }}</th>
              <th class="right">{{ t('Total') }}</th>
              <th>{{ t('Payment') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="tx in txns" :key="tx.name" class="txn-row" @click="openReceipt(tx)">
              <td class="mono">{{ tx.name }}</td>
              <td class="muted small">{{ tx.posting_date }} {{ shortTime(tx.posting_time) }}</td>
              <td>
                <span v-if="tx.is_return" class="badge red">{{ t('Return') }}</span>
                <span v-else-if="tx.is_exchange" class="badge amber">{{ t('Exchange') }}</span>
                <span v-else class="badge">{{ t('Sale') }}</span>
              </td>
              <td class="right">{{ money(tx.grand_total) }}</td>
              <td class="muted small">{{ tx.payment_modes }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="loadingTxns" class="muted center pad">{{ t('Loading…') }}</div>
        <div v-else-if="!txns.length" class="muted center pad">{{ t('No transactions') }}</div>
        <button v-if="txnsMore && !loadingTxns" class="btn btn-outline load-more" @click="loadMoreTxns">
          {{ t('Load more') }}
        </button>
      </template>
    </section>

    <ReceiptModal v-if="receipt" :receipt="receipt" :can-refund="false" @close="receipt = null" />
  </div>
</template>

<script setup>
import Icon from '../components/Icon.vue'
import ReceiptModal from '../components/ReceiptModal.vue'
import { ref, onMounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money, shortTime } from '../format'
import { t } from '../i18n'

const LIST_LIMIT = 30
const TXN_LIMIT = 25

const session = useSessionStore()

const search = ref('')
const group = ref('')
const groups = ref([])
const customers = ref([])
const hasMore = ref(false)
const listStart = ref(0)
const loadingList = ref(false)
let searchTimer = null

const selected = ref(null)
const detail = ref(null)
const loadingDetail = ref(false)

const txns = ref([])
const txnType = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const txnsMore = ref(false)
const txnStart = ref(0)
const loadingTxns = ref(false)

const receipt = ref(null)

onMounted(async () => {
  groups.value = await call('lumenpos.api.customers.customer_groups').catch(() => [])
  reload()
})

function onSearch(value) {
  search.value = value
  clearTimeout(searchTimer)
  searchTimer = setTimeout(reload, 300) // debounce — one query per pause, not per keystroke
}

async function reload() {
  listStart.value = 0
  loadingList.value = true
  try {
    const res = await call('lumenpos.api.customers.search_customers', {
      search: search.value || null,
      customer_group: group.value || null,
      start: 0,
      limit: LIST_LIMIT,
    })
    customers.value = res.items || []
    hasMore.value = res.has_more
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loadingList.value = false
  }
}

async function loadMore() {
  listStart.value += LIST_LIMIT
  loadingList.value = true
  try {
    const res = await call('lumenpos.api.customers.search_customers', {
      search: search.value || null,
      customer_group: group.value || null,
      start: listStart.value,
      limit: LIST_LIMIT,
    })
    customers.value = customers.value.concat(res.items || [])
    hasMore.value = res.has_more
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loadingList.value = false
  }
}

async function select(c) {
  selected.value = c
  detail.value = null
  loadingDetail.value = true
  try {
    detail.value = await call('lumenpos.api.customers.customer_detail', { customer: c.name })
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loadingDetail.value = false
  }
  reloadTxns()
}

function txnFilters(start) {
  return {
    filters: {
      customer: selected.value.name,
      all_profiles: 1,
      pos_profile: session.posProfile,
      is_return: txnType.value || null,
      date_from: dateFrom.value || null,
      date_to: dateTo.value || null,
      start,
      limit: TXN_LIMIT,
    },
  }
}

async function reloadTxns() {
  if (!selected.value) return
  txnStart.value = 0
  loadingTxns.value = true
  try {
    const rows = await call('lumenpos.api.sales.search_sales', txnFilters(0))
    txns.value = rows || []
    txnsMore.value = (rows || []).length === TXN_LIMIT
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loadingTxns.value = false
  }
}

async function loadMoreTxns() {
  txnStart.value += TXN_LIMIT
  loadingTxns.value = true
  try {
    const rows = await call('lumenpos.api.sales.search_sales', txnFilters(txnStart.value))
    txns.value = txns.value.concat(rows || [])
    txnsMore.value = (rows || []).length === TXN_LIMIT
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loadingTxns.value = false
  }
}

async function openReceipt(tx) {
  try {
    receipt.value = await call('lumenpos.api.sales.get_receipt', { invoice: tx.name })
  } catch (e) {
    session.notify(e.message, true)
  }
}
</script>

<style scoped>
.customers {
  flex: 1;
  display: flex;
  min-width: 0;
}
.cust-list {
  width: 320px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.list-head { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.search-box { position: relative; display: flex; align-items: center; }
.search-box svg { position: absolute; left: 11px; width: 16px; height: 16px; color: var(--text-muted); }
.search-box input { width: 100%; padding: 9px 32px 9px 34px; border-radius: 9px; }
.search-box .clear { position: absolute; right: 6px; padding: 3px 6px; }
.group-select { width: 100%; }
.list-body { flex: 1; overflow-y: auto; padding: 0 8px 12px; }
.cust-row {
  display: block;
  width: 100%;
  text-align: start;
  padding: 9px 10px;
  border-radius: 9px;
  border: 1px solid transparent;
}
.cust-row:hover { background: var(--hover-bg, rgba(46,91,255,0.06)); }
.cust-row.active { background: var(--brand-soft, rgba(46,91,255,0.12)); border-color: var(--brand); }
.cust-name { font-weight: 600; }
.cust-detail { flex: 1; overflow-y: auto; padding: 20px 24px; min-width: 0; }
.empty-detail {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  text-align: center;
}
.detail-head h2 { margin: 0 0 2px; }
.profile-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px 18px;
  margin: 18px 0;
}
.profile-grid .lbl { display: block; font-size: 11px; font-weight: 700; color: var(--text-muted); }
.stat-cards { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 22px; }
.stat {
  flex: 1;
  min-width: 110px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
}
.stat-v { font-size: 20px; font-weight: 800; }
.stat-l { font-size: 11.5px; color: var(--text-muted); margin-top: 2px; }
.txn-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.txn-head h3 { margin: 0; }
.txn-filters { display: flex; gap: 8px; flex-wrap: wrap; }
.txn-table { width: 100%; border-collapse: collapse; margin-top: 10px; }
.txn-table th {
  text-align: start;
  font-size: 11.5px;
  color: var(--text-muted);
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
.txn-row { cursor: pointer; }
.txn-row:hover { background: var(--hover-bg, rgba(46,91,255,0.06)); }
.txn-row td { padding: 9px 8px; border-bottom: 1px solid var(--border-subtle); }
.right { text-align: end; }
.mono { font-family: ui-monospace, monospace; font-size: 12.5px; }
.small { font-size: 12px; }
.center { text-align: center; }
.pad { padding: 22px 0; }
.load-more { width: 100%; margin-top: 12px; }
.badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 999px;
  background: var(--border-subtle);
  color: var(--text-muted);
}
.badge.red { background: rgba(226, 48, 48, 0.14); color: var(--red); }
.badge.amber { background: rgba(245, 166, 35, 0.18); color: #9a6a0a; }
html[data-theme='dark'] .badge.red { background: rgba(255, 120, 120, 0.2); color: #ff9b9b; }
html[data-theme='dark'] .badge.amber { background: rgba(245, 190, 90, 0.2); color: #ffd27a; }
</style>
