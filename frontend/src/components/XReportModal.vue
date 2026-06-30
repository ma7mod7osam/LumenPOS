<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 420px">
      <div class="modal-header">
        {{ t('X-report') }} <span class="muted small">{{ t('(mid-shift read)') }}</span>
        <button class="btn-ghost close" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <p class="muted small intro">
          {{ t('A read-only snapshot of the shift so far. It does NOT close the register or post anything.') }}
        </p>

        <div id="xreport-print" class="xreport">
          <div class="xr-head">
            <img
              v-if="session.settings.receipt_logo"
              :src="session.settings.receipt_logo"
              class="xr-logo"
              alt=""
            />
            <div class="xr-company">{{ session.company }}</div>
            <div class="xr-title">{{ t('X-REPORT') }}</div>
            <div class="muted small">{{ s.session }}</div>
            <div class="muted small">{{ session.userFullname || session.user }}</div>
            <div class="muted small">{{ t('Opened') }} {{ s.opened_at }}</div>
            <div class="muted small">{{ t('Printed') }} {{ printedAt }}</div>
          </div>

          <div class="xr-section">
            <div class="row"><span>{{ t('Sales') }}</span><span>{{ s.sales_count }}</span></div>
            <div class="row"><span>{{ t('Takings') }}</span><span>{{ money(s.total_sales) }}</span></div>
            <div class="row"><span>{{ t('Discounts given') }}</span><span>{{ money(s.total_discounts) }}</span></div>
          </div>

          <div class="xr-section">
            <div class="xr-sub">{{ t('Expected by payment') }}</div>
            <div v-for="row in s.expected" :key="row.mode_of_payment" class="row">
              <span>{{ row.mode_of_payment }}<span v-if="row.is_cash" class="muted"> ({{ t('drawer') }})</span></span>
              <span>{{ money(row.expected_amount) }}</span>
            </div>
            <div v-if="!s.expected.length" class="muted small">{{ t('No takings recorded yet.') }}</div>
          </div>

          <div class="xr-section">
            <div class="xr-sub">{{ t('Cash drawer') }}</div>
            <div class="row"><span>{{ t('Opening float') }}</span><span>{{ money(s.opening_float) }}</span></div>
            <div class="row"><span>{{ t('Cash in') }}</span><span>{{ money(s.cash_in) }}</span></div>
            <div class="row"><span>{{ t('Cash out') }}</span><span>-{{ money(s.cash_out) }}</span></div>
          </div>

          <div class="xr-foot muted small">{{ t('Continues — not a Z-report.') }}</div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" @click="print">{{ t('Print') }}</button>
        <button class="btn btn-primary" @click="$emit('close')">{{ t('Close') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { computed } from 'vue'
import { t } from '../i18n'
import { money } from '../format'
import { useSessionStore } from '../stores/session'

const props = defineProps({ summary: { type: Object, required: true } })
defineEmits(['close'])

const session = useSessionStore()
const s = computed(() => props.summary)
const printedAt = new Date().toLocaleString()

function print() {
  window.print()
}
</script>

<style scoped>
.modal-header { display: flex; align-items: center; gap: 6px; }
.close { margin-inline-start: auto; }
.intro { margin: 0 0 12px; }
.xreport {
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 16px;
  font-size: 13px;
}
.xr-head { text-align: center; margin-bottom: 12px; }
.xr-logo { max-height: 56px; max-width: 70%; object-fit: contain; margin: 0 auto 8px; display: block; }
.xr-company { font-weight: 800; font-size: 15px; }
.xr-title { font-weight: 800; letter-spacing: 0.18em; margin: 2px 0 6px; }
.xr-section {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
}
.xr-sub {
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.row { display: flex; justify-content: space-between; padding: 2.5px 0; }
.xr-foot { text-align: center; margin-top: 12px; }
.small { font-size: 11.5px; }
</style>
