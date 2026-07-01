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

        <ReceiptView :receipt="receipt" printable />
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
import ReceiptView from './ReceiptView.vue'
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
    // Use the sale's ACTUAL doctype (POS Invoice or Sales Invoice, per the
    // profile's mode) — hardcoding "POS Invoice" broke custom Print Formats in
    // Sales-Invoice mode.
    const doctype = props.receipt.doctype || session.invoiceMode || 'POS Invoice'
    const url =
      `/printview?doctype=${encodeURIComponent(doctype)}` +
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
  background: rgba(20, 99, 255, 0.08);
  color: var(--brand-dark);
  border-radius: var(--radius);
  padding: 12px 16px;
  text-align: center;
  margin-bottom: 16px;
  font-weight: 600;
}
.change-banner {
  background: rgba(20, 99, 255, 0.1);
  color: var(--brand-dark);
  border-radius: var(--radius);
  padding: 12px 16px;
  font-size: 16px;
  text-align: center;
  margin-bottom: 16px;
}
.refund-btn { margin-right: auto; color: var(--red); }
</style>
