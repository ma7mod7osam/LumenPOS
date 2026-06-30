<template>
  <div :id="printable ? 'receipt-print' : null" class="receipt" :class="`tpl-${tpl}`">
    <div class="receipt-head">
      <img v-if="s.receipt_logo" :src="s.receipt_logo" class="receipt-logo" alt="" />
      <div class="receipt-company">{{ receipt.company }}</div>
      <div v-if="s.receipt_header" class="muted small receipt-extra">{{ s.receipt_header }}</div>
      <div v-if="s.receipt_show_address && s.receipt_address" class="muted small receipt-extra">
        {{ s.receipt_address }}
      </div>
      <div v-if="s.receipt_show_tax_id && s.receipt_tax_id" class="muted small">
        {{ t('Tax ID') }}: {{ s.receipt_tax_id }}
      </div>
      <div v-if="receipt.is_return" class="return-stamp">{{ t('REFUND') }}</div>
      <div class="muted small">
        {{ receipt.name }} · {{ receipt.posting_date }} {{ String(receipt.posting_time || '').split('.')[0] }}
      </div>
      <div class="muted small" v-if="receipt.return_against">{{ t('against') }} {{ receipt.return_against }}</div>
      <div class="muted small">{{ receipt.customer_name }}</div>
      <div class="muted small" v-if="receipt.sales_person">{{ t('Served by') }} {{ receipt.sales_person }}</div>
      <div class="muted small" v-if="receipt.app_type">
        {{ receipt.app_type }}<span v-if="receipt.order_id"> · {{ t('Order') }} {{ receipt.order_id }}</span>
      </div>
    </div>

    <table class="receipt-table">
      <tbody>
        <tr v-for="(item, i) in receipt.items" :key="i">
          <td>
            <div class="ritem-name">{{ item.item_name }}</div>
            <div
              v-if="(s.receipt_show_item_code && item.item_code) || (s.receipt_show_barcode && item.barcode)"
              class="muted small ritem-meta"
            >
              <span v-if="s.receipt_show_item_code">{{ item.item_code }}</span>
              <span v-if="s.receipt_show_barcode && item.barcode"> · {{ item.barcode }}</span>
            </div>
            <div v-if="s.receipt_show_serial && item.serial_no" class="muted small ritem-meta">
              {{ t('SN') }}: {{ String(item.serial_no).split('\n').join(', ') }}
            </div>
            <div v-if="s.receipt_show_unit_price" class="muted small">
              {{ item.qty }} × {{ money(item.rate) }}
            </div>
            <div v-else class="muted small">{{ t('Qty') }} {{ item.qty }}</div>
          </td>
          <td class="right">{{ money(item.amount) }}</td>
        </tr>
      </tbody>
    </table>

    <div class="receipt-totals">
      <div v-if="receipt.discount_amount" class="row">
        <span>{{ t('Discount') }}</span><span>-{{ money(receipt.discount_amount) }}</span>
      </div>
      <div v-for="tax in receipt.taxes" :key="tax.description" class="row">
        <span>{{ tax.description }}</span><span>{{ money(tax.tax_amount) }}</span>
      </div>
      <div class="row total">
        <span>{{ t('Total') }}</span><span>{{ money(receipt.rounded_total || receipt.grand_total) }}</span>
      </div>
      <template v-if="s.receipt_show_payments">
        <div v-for="payment in receipt.payments" :key="payment.mode_of_payment" class="row">
          <span>{{ payment.mode_of_payment }}</span><span>{{ money(payment.amount) }}</span>
        </div>
      </template>
      <div v-if="receipt.loyalty_amount" class="row">
        <span>{{ t('Loyalty points') }} ({{ receipt.loyalty_points_redeemed }})</span>
        <span>{{ money(receipt.loyalty_amount) }}</span>
      </div>
      <div v-if="receipt.change_amount" class="row">
        <span>{{ t('Change') }}</span><span>{{ money(receipt.change_amount) }}</span>
      </div>
    </div>

    <div v-if="receipt.applied_promotions?.length" class="receipt-promos">
      <div v-for="promo in receipt.applied_promotions" :key="promo.name" class="muted small">
        ★ {{ promo.title }} ({{ t('saved') }} {{ money(promo.savings) }})
      </div>
    </div>
    <div v-if="receipt.loyalty_points_earned" class="receipt-promos muted small">
      {{ t('Points earned:') }} {{ receipt.loyalty_points_earned }}
    </div>

    <div v-if="s.receipt_show_note && receipt.note" class="receipt-note small">
      <strong>{{ t('Note') }}:</strong> {{ receipt.note }}
    </div>
    <div v-if="s.receipt_show_terms && s.receipt_terms" class="receipt-terms small">
      {{ s.receipt_terms }}
    </div>

    <div class="receipt-foot muted small">
      <div v-if="s.receipt_footer" class="receipt-extra">{{ s.receipt_footer }}</div>
      {{ t('Thank you!') }}
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { t } from '../i18n'
import { money } from '../format'
import { useSessionStore } from '../stores/session'

const props = defineProps({
  receipt: { type: Object, required: true },
  // Optional settings override (for the live Settings preview); defaults to the
  // session's saved settings.
  settings: { type: Object, default: null },
  // Only the real receipt gets id="receipt-print" so the print stylesheet
  // targets it (the Settings preview must never be the print target).
  printable: { type: Boolean, default: false },
})

const session = useSessionStore()
const s = computed(() => props.settings || session.settings || {})
const tpl = computed(() => (s.value.receipt_template || 'Standard').toLowerCase())
</script>

<style scoped>
.receipt {
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  padding: 16px;
  font-size: 13px;
}
.receipt-head { text-align: center; margin-bottom: 12px; }
.receipt-logo {
  max-height: 64px;
  max-width: 70%;
  object-fit: contain;
  margin: 0 auto 8px;
  display: block;
}
.receipt-company { font-weight: 800; font-size: 15px; }
.receipt-extra { white-space: pre-line; margin: 3px 0; }
.return-stamp { color: var(--red); font-weight: 800; letter-spacing: 0.2em; }
.receipt-table { width: 100%; border-collapse: collapse; }
.receipt-table td {
  padding: 5px 0;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: top;
}
.ritem-name { font-weight: 600; }
.ritem-meta { font-family: var(--mono); }
.receipt-totals { margin-top: 10px; }
.row { display: flex; justify-content: space-between; padding: 2.5px 0; }
.row.total { font-weight: 800; font-size: 15px; padding: 6px 0; }
.receipt-promos {
  margin-top: 8px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 8px;
}
.receipt-note {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-subtle);
  white-space: pre-line;
}
.receipt-terms {
  margin-top: 10px;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-muted);
  white-space: pre-line;
}
.receipt-foot { text-align: center; margin-top: 12px; }
.small { font-size: 11.5px; }

/* ---- Templates ---- */
.tpl-compact { font-size: 11.5px; padding: 12px; border: none; }
.tpl-compact .receipt-company { font-size: 13.5px; }
.tpl-compact .receipt-head { margin-bottom: 8px; }
.tpl-compact .receipt-table td { padding: 3px 0; }
.tpl-compact .row.total { font-size: 13.5px; }

.tpl-detailed { font-size: 13px; padding: 22px; }
.tpl-detailed .receipt-head {
  padding-bottom: 12px;
  margin-bottom: 14px;
  border-bottom: 2px solid var(--border);
}
.tpl-detailed .receipt-company { font-size: 18px; }
.tpl-detailed .receipt-table td { padding: 7px 0; }
.tpl-detailed .row { padding: 4px 0; }
</style>
