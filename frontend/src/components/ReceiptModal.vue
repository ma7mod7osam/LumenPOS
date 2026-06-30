<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 440px">
      <div class="modal-header">
        {{ receipt.is_return ? t('Refund complete') : receipt.offline ? t('Sale queued (offline)') : t('Sale complete') }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <div v-if="receipt.offline" class="offline-banner">
          {{ t('Saved offline — it will post to ERPNext automatically when the connection returns.') }}
        </div>
        <div v-if="receipt.change_amount > 0" class="change-banner">
          {{ t('Change due:') }} <strong>{{ money(receipt.change_amount) }}</strong>
        </div>
        <div v-if="receipt.gift_card_no" class="giftcard-banner">
          <Icon name="gift" /> {{ t('Gift card') }} <strong>{{ receipt.gift_card_no }}</strong> —
          {{ t('balance') }} {{ money(receipt.gift_card_balance) }}<span v-if="receipt.gift_card_expiry"> · {{ t('expires') }} {{ receipt.gift_card_expiry }}</span>
        </div>

        <div id="receipt-print" class="receipt">
          <div class="receipt-head">
            <img
              v-if="session.settings.receipt_logo"
              :src="session.settings.receipt_logo"
              class="receipt-logo"
              alt=""
            />
            <div class="receipt-company">{{ receipt.company }}</div>
            <div v-if="session.settings.receipt_header" class="muted small receipt-extra">
              {{ session.settings.receipt_header }}
            </div>
            <div v-if="receipt.is_return" class="return-stamp">{{ t('REFUND') }}</div>
            <div class="muted small">
              {{ receipt.name }} · {{ receipt.posting_date }} {{ String(receipt.posting_time || '').split('.')[0] }}
            </div>
            <div class="muted small" v-if="receipt.return_against">{{ t('against') }} {{ receipt.return_against }}</div>
            <div class="muted small">{{ receipt.customer_name }}</div>
            <div class="muted small" v-if="receipt.sales_person">{{ t('Served by') }} {{ receipt.sales_person }}</div>
            <div class="muted small" v-if="receipt.app_type">
              <Icon name="bike" /> {{ receipt.app_type }}<span v-if="receipt.order_id"> · {{ t('Order') }} {{ receipt.order_id }}</span>
            </div>
          </div>
          <table class="receipt-table">
            <tbody>
              <tr v-for="item in receipt.items" :key="item.item_code">
                <td>
                  {{ item.item_name }}
                  <div class="muted small">{{ item.qty }} × {{ money(item.rate) }}</div>
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
            <div v-for="payment in receipt.payments" :key="payment.mode_of_payment" class="row">
              <span>{{ payment.mode_of_payment }}</span><span>{{ money(payment.amount) }}</span>
            </div>
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
              <Icon name="star" /> {{ promo.title }} ({{ t('saved') }} {{ money(promo.savings) }})
            </div>
          </div>
          <div v-if="receipt.loyalty_points_earned" class="receipt-promos muted small">
            {{ t('Points earned:') }} {{ receipt.loyalty_points_earned }}
          </div>
          <div class="receipt-foot muted small">
            <div v-if="session.settings.receipt_footer" class="receipt-extra">
              {{ session.settings.receipt_footer }}
            </div>
            {{ t('Thank you!') }}
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button
          v-if="!receipt.is_return && !receipt.offline && canRefund"
          class="btn btn-outline refund-btn"
          @click="$emit('refund', receipt.name)"
        >
          {{ t('Refund…') }}
        </button>
        <button
          v-if="session.settings.enable_email_receipt && !receipt.offline"
          class="btn btn-outline"
          :disabled="emailing"
          @click="emailReceipt"
        >
          {{ emailing ? t('Sending…') : t('Email receipt') }}
        </button>
        <button class="btn btn-outline" :disabled="printing" @click="print">
          {{ printing ? t('Printing…') : t('Print receipt') }}
        </button>
        <button class="btn btn-primary" @click="$emit('close')">
          {{ receipt.is_return ? t('Done') : t('New Sale') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money } from '../format'
import { t } from '../i18n'

const props = defineProps({
  receipt: Object,
  canRefund: { type: Boolean, default: false },
})
defineEmits(['close', 'refund'])

const session = useSessionStore()
const printing = ref(false)
const emailing = ref(false)

async function emailReceipt() {
  emailing.value = true
  try {
    // Try the address on file first; if there is none (or it fails), ask once.
    const res = await call('lumenpos.api.sales.email_receipt', { invoice: props.receipt.name })
    session.notify(t('Receipt emailed to {email}', { email: res.email }))
  } catch (e) {
    const typed = (window.prompt(t('Email the receipt to:'), '') || '').trim()
    if (!typed) {
      if (e.message) session.notify(e.message, true)
      return
    }
    try {
      const res = await call('lumenpos.api.sales.email_receipt', {
        invoice: props.receipt.name,
        email: typed,
      })
      session.notify(t('Receipt emailed to {email}', { email: res.email }))
    } catch (e2) {
      session.notify(e2.message, true)
    }
  } finally {
    emailing.value = false
  }
}

async function print() {
  // Priority: ESC/POS network printer -> the POS Profile's Print Format
  // (ERPNext print view) -> the built-in receipt via the browser dialog.
  if (session.printerConfigured && !props.receipt.offline && !session.offline) {
    printing.value = true
    try {
      await call('lumenpos.api.printing.print_receipt', { invoice: props.receipt.name })
      session.notify(t('Receipt sent to printer'))
      return
    } catch (e) {
      session.notify(t('Printer failed ({error}) — using browser print', { error: e.message }), true)
    } finally {
      printing.value = false
    }
  }
  if (session.printFormat && !props.receipt.offline && !session.offline) {
    const url =
      `/printview?doctype=${encodeURIComponent('POS Invoice')}` +
      `&name=${encodeURIComponent(props.receipt.name)}` +
      `&format=${encodeURIComponent(session.printFormat)}` +
      `&no_letterhead=0&trigger_print=1`
    window.open(url, '_blank')
    return
  }
  window.print()
}
</script>

<style scoped>
.offline-banner {
  background: rgba(245, 166, 35, 0.14);
  color: #9a6a0a;
  border-radius: var(--radius);
  padding: 12px 16px;
  text-align: center;
  margin-bottom: 16px;
  font-weight: 600;
}
.giftcard-banner {
  background: rgba(46, 91, 255, 0.08);
  color: var(--brand-dark);
  border-radius: var(--radius);
  padding: 12px 16px;
  text-align: center;
  margin-bottom: 16px;
  font-weight: 600;
}
.change-banner {
  background: rgba(46, 91, 255, 0.1);
  color: var(--brand-dark);
  border-radius: var(--radius);
  padding: 12px 16px;
  font-size: 16px;
  text-align: center;
  margin-bottom: 16px;
}
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
.return-stamp {
  color: var(--red);
  font-weight: 800;
  letter-spacing: 0.2em;
}
.receipt-table { width: 100%; border-collapse: collapse; }
.receipt-table td {
  padding: 5px 0;
  border-bottom: 1px solid var(--border-subtle);
  vertical-align: top;
}
.receipt-totals { margin-top: 10px; }
.row { display: flex; justify-content: space-between; padding: 2.5px 0; }
.row.total { font-weight: 800; font-size: 15px; padding: 6px 0; }
.receipt-promos {
  margin-top: 8px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 8px;
}
.receipt-foot { text-align: center; margin-top: 12px; }
.small { font-size: 11.5px; }
.refund-btn { margin-right: auto; color: var(--red); }
</style>
