<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="period-hint" role="note">
    <Icon name="warning" :size="16" />
    <div class="ph-text">
      <template v-if="when === 'today'">
        <p v-if="invoiceMode === 'Sales Invoice'">
          {{ t("ERPNext's accounting period {period} ({from} to {to}) locks sales invoices today, so no sale can be posted. Tell whoever looks after the accounts.", vars) }}
        </p>
        <p v-else>
          {{ t("ERPNext's accounting period {period} ({from} to {to}) locks sales invoices today. You can sell, but this shift will not be able to close until the period is changed in ERPNext. Tell whoever looks after the accounts.", vars) }}
        </p>
      </template>
      <template v-else>
        <p>{{ t("ERPNext's accounting period {period} ({from} to {to}) locks sales invoices, so the sales of this shift cannot be posted.", vars) }}</p>
        <p v-if="hint.ended">
          {{ t('In ERPNext, open this period (Accounting Period), untick Sales Invoice and press Retry closing, then tick it again.') }}
        </p>
        <p v-else>
          {{ t('An accounting period is meant to lock a month that is over. Delete this one in ERPNext (Accounting Period), then press Retry closing.') }}
        </p>
      </template>
    </div>
  </div>
</template>

<script setup>
// An ERPNext Accounting Period that locks Sales Invoices
// (lumenpos.accounting_periods, 0.58.1): why a close failed ("failed"), or,
// as a shift opens, why its close would fail ("today"). A shop that made a
// period ahead of time "to open" a month sells all day and then cannot close
// the shift, because the close posts the shift's sales as a Sales Invoice.
// The server sends `hint` only while the shop's "Warn about locked accounting
// periods" is on.
import { computed } from 'vue'
import Icon from './Icon.vue'
import { t } from '../i18n'
import { isolate } from '../format'

const props = defineProps({
  hint: { type: Object, required: true },
  when: { type: String, default: 'failed' },
  invoiceMode: { type: String, default: 'POS Invoice' },
})

// The period's name and dates stay in one piece on an Arabic or Persian screen.
const vars = computed(() => ({
  period: isolate(props.hint.period),
  from: isolate(props.hint.from),
  to: isolate(props.hint.to),
}))
</script>

<style scoped>
.period-hint {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 8px 0;
  padding: 10px 12px;
  border-radius: var(--radius);
  border: 1px solid rgba(201, 130, 27, 0.45);
  background: rgba(245, 166, 35, 0.12);
  color: var(--text);
  font-size: 12.5px;
  font-weight: 600;
  line-height: 1.5;
  text-align: start;
}
.period-hint :deep(svg) {
  flex: none;
  margin-top: 2px;
  color: var(--amber);
}
.ph-text p {
  margin: 0;
}
.ph-text p + p {
  margin-top: 4px;
  font-weight: 500;
}
html[data-theme='dark'] .period-hint {
  border-color: rgba(224, 165, 60, 0.45);
  background: rgba(224, 165, 60, 0.12);
}
</style>
