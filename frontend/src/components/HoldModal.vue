<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 460px">
      <div class="modal-header">
        <Icon name="bookmark" /> {{ t('Hold these goods') }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body form">
        <div class="hold-lines">
          <div v-for="line in cart.lines" :key="line.item_code" class="hold-line">
            <span>{{ line.qty }} × {{ line.item_name }}</span>
            <span>{{ money(line.qty * line.price) }}</span>
          </div>
          <div class="hold-line total">
            <span>{{ t('Total') }}</span>
            <span>{{ money(cart.total) }}</span>
          </div>
        </div>

        <p v-if="!cart.customer" class="muted small warn-row">
          {{ t('Pick the customer on the sale screen first: a hold belongs to somebody.') }}
        </p>
        <p v-else class="muted small">
          {{ t('Held for') }} <strong>{{ cart.customer.customer_name }}</strong>
        </p>

        <label class="field-label">{{ t('Deposit now *') }}</label>
        <input ref="amountInput" type="number" min="0" step="0.01" v-model.number="amount" />
        <p v-if="minimum > 0" class="muted small">
          {{ t('This shop asks for at least {amount}', { amount: money(minimum) }) }}
        </p>

        <label class="field-label">{{ t('Paid by *') }}</label>
        <select v-model="modeOfPayment">
          <option v-for="mode in modes" :key="mode.mode_of_payment" :value="mode.mode_of_payment">
            {{ mode.mode_of_payment }}
          </option>
        </select>

        <label class="field-label">{{ t('Hold until') }}</label>
        <input type="date" v-model="expiry" />

        <label class="field-label">{{ t('Note') }}</label>
        <input v-model="note" :placeholder="t('Anything the next cashier should know')" />

        <p class="muted small">
          {{ t('The deposit is money the shop is holding, not a sale: it posts to the deposits account and comes off the bill when the goods are handed over.') }}
        </p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" @click="$emit('close')">{{ t('Cancel') }}</button>
        <button
          class="btn btn-primary"
          :disabled="!canHold || busy"
          @click="hold"
        >
          {{ busy ? t('Holding…') : t('Hold and take {amount}', { amount: money(amount || 0) }) }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { useCartStore } from '../stores/cart'
import { useSessionStore } from '../stores/session'
import { money } from '../format'
import { t } from '../i18n'

const emit = defineEmits(['close', 'done'])
const cart = useCartStore()
const session = useSessionStore()

const amount = ref(null)
const modeOfPayment = ref(null)
const expiry = ref('')
const note = ref('')
const busy = ref(false)
const amountInput = ref(null)

// A deposit is money coming IN, so the tenders that only spend a balance
// (store credit, cashback, a gift card) are not offered here.
const modes = computed(() =>
  session.paymentModes.filter(
    (m) =>
      m.mode_of_payment !== session.storeCreditMode &&
      m.mode_of_payment !== session.cashbackMode &&
      m.mode_of_payment !== session.giftCardMode
  )
)

const minimum = computed(() => {
  const percent = Number(session.settings?.layaway_min_percent || 0)
  return percent > 0 ? Math.round(cart.total * percent) / 100 : 0
})

const canHold = computed(
  () =>
    cart.lines.length &&
    cart.customer &&
    modeOfPayment.value &&
    Number(amount.value) > 0 &&
    Number(amount.value) >= minimum.value - 0.005
)

onMounted(() => {
  modeOfPayment.value = (modes.value.find((m) => m.default) || modes.value[0])?.mode_of_payment
  amount.value = minimum.value || null
  const days = Number(session.settings?.layaway_days || 0)
  if (days > 0) {
    const until = new Date()
    until.setDate(until.getDate() + days)
    expiry.value = until.toISOString().slice(0, 10)
  }
  amountInput.value?.focus()
})

async function hold() {
  busy.value = true
  try {
    const res = await call('lumenpos.api.layaway.create_layaway', {
      payload: {
        pos_profile: session.posProfile,
        customer: cart.customer.name,
        items: cart.lines.map((line) => ({
          item_code: line.item_code,
          item_name: line.item_name,
          qty: line.qty,
          // The price agreed today is the price the customer comes back to.
          rate: line.price,
        })),
        payments: [{ mode_of_payment: modeOfPayment.value, amount: Number(amount.value) }],
        expiry_date: expiry.value || null,
        note: note.value || null,
      },
    })
    session.notify(t('Held for {name}', { name: cart.customer.customer_name }))
    cart.clear()
    emit('done', res)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.hold-lines {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 12px;
  margin-bottom: 10px;
}
.hold-line {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0;
  font-size: 13px;
}
.hold-line.total {
  border-top: 1px solid var(--border);
  margin-top: 4px;
  padding-top: 8px;
  font-weight: 700;
}
.warn-row { color: var(--neg, #c23434); }
</style>
