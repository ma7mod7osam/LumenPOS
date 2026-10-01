<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<!-- The Salespeople tab of Insights (0.57.0): sales by salesperson over a
     period, one outlet or every outlet of its company, with the commission
     ERPNext works out. The server decides who may see it
     (lumenpos.api.salespeople.report). -->
<template>
  <div class="salespeople">
    <div class="card sp-card">
      <div class="sp-head">
        <div>
          <div class="sp-title">{{ t('Sales by salesperson') }}</div>
          <div class="muted small">{{ t('Before tax, in {currency}. Returns are taken off the salesperson of the sale.', { currency: report?.currency || session.localCurrency }) }}</div>
        </div>
        <span style="flex: 1" />
        <button class="btn btn-outline" :disabled="!report?.rows?.length" @click="download">
          <Icon name="download" /> {{ t('Download CSV') }}
        </button>
      </div>

      <div class="sp-filters">
        <div class="seg">
          <button v-for="p in PERIODS" :key="p.key" class="seg-btn" :class="{ on: period === p.key }" @click="pick(p.key)">
            {{ t(p.label) }}
          </button>
        </div>
        <template v-if="period === 'custom'">
          <input v-model="fromDate" type="date" class="cf-in" @change="load" />
          <input v-model="toDate" type="date" class="cf-in" @change="load" />
        </template>
        <select v-model="scope" class="cf-in" @change="load">
          <option value="outlet">{{ t('This outlet') }}: {{ session.posProfile }}</option>
          <option value="company">{{ t('Every outlet of {company}', { company: session.company }) }}</option>
        </select>
      </div>

      <div v-if="session.offline" class="muted empty">{{ t('This report needs a connection.') }}</div>
      <div v-else-if="loading" class="muted empty">{{ t('Loading…') }}</div>
      <div v-else-if="error" class="empty neg">{{ error }}</div>
      <div v-else-if="!report || !report.rows.length" class="muted empty">{{ t('No sales in this period.') }}</div>
      <template v-else>
        <div class="muted small range">
          <bdi>{{ report.from_date }}</bdi> <span v-if="report.to_date !== report.from_date">&nbsp;{{ t('to') }}&nbsp;<bdi>{{ report.to_date }}</bdi></span>
        </div>
        <SalespeopleTable :rows="report.rows" :totals="report.totals" :currency="report.currency" />
        <p class="muted small note">
          {{ t('Each sale counts for the salesperson picked at the till. ERPNext works out the commission at each salesperson\'s rate (Sales Person, Commission Rate).') }}
        </p>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import Icon from './Icon.vue'
import SalespeopleTable from './SalespeopleTable.vue'
import { call } from '../api'
import { t } from '../i18n'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const PERIODS = [
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: 'week', label: 'Last 7 days' },
  { key: 'month', label: 'This month' },
  { key: 'custom', label: 'Custom' },
]
const period = ref('today')
const scope = ref('outlet')
const fromDate = ref('')
const toDate = ref('')
const report = ref(null)
const loading = ref(false)
const error = ref('')

const iso = (d) => {
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

function range(key) {
  const today = new Date()
  const back = (days) => {
    const d = new Date(today)
    d.setDate(d.getDate() - days)
    return d
  }
  if (key === 'yesterday') return [iso(back(1)), iso(back(1))]
  if (key === 'week') return [iso(back(6)), iso(today)]
  if (key === 'month') return [iso(new Date(today.getFullYear(), today.getMonth(), 1)), iso(today)]
  return [iso(today), iso(today)]
}

function pick(key) {
  period.value = key
  if (key === 'custom') {
    if (!fromDate.value) [fromDate.value, toDate.value] = range('week')
  } else {
    ;[fromDate.value, toDate.value] = range(key)
  }
  load()
}

async function load() {
  if (session.offline) return
  loading.value = true
  error.value = ''
  try {
    report.value = await call('lumenpos.api.salespeople.report', {
      from_date: fromDate.value,
      to_date: toDate.value || fromDate.value,
      pos_profile: scope.value === 'outlet' ? session.posProfile : null,
      company: scope.value === 'company' ? session.company : null,
    })
  } catch (e) {
    report.value = null
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

// A spreadsheet of what is on screen. The byte order mark lets Excel read the
// Arabic names right.
function download() {
  const rows = report.value?.rows || []
  const head = [t('Salesperson'), t('Sales'), t('Sales amount'), t('Returns'), t('Returns amount'), t('Net'), t('Commission rate'), t('Commission')]
  const cell = (v) => {
    const text = String(v ?? '')
    return /[",\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text
  }
  const lines = [head.map(cell).join(',')]
  for (const r of rows) {
    lines.push(
      [r.sales_person ? r.name : t('No salesperson'), r.sales, r.sales_amount, r.returns, r.returns_amount, r.net,
        r.sales_person ? r.commission_rate : '', r.sales_person ? r.commission : ''].map(cell).join(',')
    )
  }
  const blob = new Blob([String.fromCharCode(0xfeff) + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = `sales-by-salesperson-${report.value.from_date}-${report.value.to_date}.csv`
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

onMounted(() => pick('today'))
</script>

<style scoped>
/* The card keeps its own height and the tab scrolls as one: stretched to the
   tab, the table shrank to a box of two rows on a phone. */
.salespeople { flex: 1; display: flex; align-items: flex-start; min-height: 0; overflow: auto; }
.sp-card { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.sp-head { display: flex; align-items: center; gap: 10px; padding: 14px; border-bottom: 1px solid var(--border); }
.sp-title { font-weight: 700; font-size: 16px; }
.sp-filters { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.seg { display: inline-flex; flex-wrap: wrap; border: 1px solid var(--border); border-radius: 9px; overflow: hidden; }
.seg-btn { background: transparent; border: 0; padding: 7px 12px; font: inherit; font-size: 13px; color: var(--text); cursor: pointer; }
.seg-btn + .seg-btn { border-inline-start: 1px solid var(--border); }
.seg-btn.on { background: var(--brand); color: #fff; }
.sp-filters select.cf-in { max-width: 100%; }
.range { padding: 10px 14px 0; }
.empty { padding: 26px; text-align: center; }
.note { padding: 10px 14px 14px; }
@media (max-width: 600px) {
  .sp-head { flex-wrap: wrap; }
}
</style>
