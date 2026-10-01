<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<!-- Sales by salesperson, as lumenpos.api.salespeople returns them: one row a
     person, sales nobody was named on last. The commission column shows only
     when the server sent it (whoever may see the salesperson report). -->
<template>
  <div class="sp-wrap">
    <table class="sp-table">
      <thead>
        <tr>
          <th>{{ t('Salesperson') }}</th>
          <th class="num">{{ t('Sales') }}</th>
          <th class="num">{{ t('Sales amount') }}</th>
          <th class="num">{{ t('Returns') }}</th>
          <th class="num">{{ t('Net') }}</th>
          <th v-if="withCommission" class="num">{{ t('Commission') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.sales_person || '-'" :class="{ none: !r.sales_person }">
          <td class="who">
            <bdi>{{ r.sales_person ? r.name : t('No salesperson') }}</bdi>
            <span v-if="r.number" class="muted small">&nbsp;#<bdi>{{ r.number }}</bdi></span>
          </td>
          <td class="num">{{ r.sales }}</td>
          <td class="num"><bdi>{{ money(r.sales_amount, currency) }}</bdi></td>
          <td class="num">
            <template v-if="r.returns">
              <bdi>{{ money(r.returns_amount, currency) }}</bdi>
              <span class="muted small">&nbsp;({{ r.returns }})</span>
            </template>
          </td>
          <td class="num strong"><bdi>{{ money(r.net, currency) }}</bdi></td>
          <td v-if="withCommission" class="num">
            <template v-if="r.sales_person">
              <bdi>{{ money(r.commission, currency) }}</bdi>
              <span v-if="r.commission_rate" class="muted small">&nbsp;({{ r.commission_rate }}%)</span>
            </template>
          </td>
        </tr>
      </tbody>
      <tfoot v-if="totals">
        <tr>
          <td>{{ t('Total') }}</td>
          <td class="num">{{ totals.sales }}</td>
          <td class="num"><bdi>{{ money(totals.sales_amount, currency) }}</bdi></td>
          <td class="num">
            <template v-if="totals.returns">
              <bdi>{{ money(totals.returns_amount, currency) }}</bdi>
              <span class="muted small">&nbsp;({{ totals.returns }})</span>
            </template>
          </td>
          <td class="num strong"><bdi>{{ money(totals.net, currency) }}</bdi></td>
          <td v-if="withCommission" class="num"><bdi>{{ money(totals.commission, currency) }}</bdi></td>
        </tr>
      </tfoot>
    </table>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { t } from '../i18n'
import { money } from '../format'

const props = defineProps({
  rows: { type: Array, required: true },
  currency: { type: String, default: '' },
  totals: { type: Object, default: null },
})
const withCommission = computed(() => props.rows.some((r) => 'commission' in r))
</script>

<style scoped>
.sp-wrap { overflow-x: auto; }
.sp-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.sp-table th {
  text-align: start;
  font-weight: 600;
  color: var(--text-muted);
  font-size: 12px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.sp-table td { padding: 9px 10px; border-bottom: 1px solid var(--border-subtle); vertical-align: top; }
.sp-table .num { text-align: end; white-space: nowrap; font-variant-numeric: tabular-nums; }
.sp-table .strong { font-weight: 700; }
.sp-table .who { min-width: 140px; }
.sp-table tr.none td { color: var(--text-muted); }
.sp-table tfoot td { font-weight: 700; border-top: 1px solid var(--border); border-bottom: 0; }
</style>
