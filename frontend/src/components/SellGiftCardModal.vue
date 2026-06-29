<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 440px">
      <div class="modal-header">
        <Icon name="gift" /> {{ t('Sell gift card') }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body form">
        <label class="field-label">{{ t('Amount *') }}</label>
        <input ref="amountInput" type="number" min="1" step="0.01" v-model.number="amount" />

        <label class="field-label">{{ t('Card number (leave empty to auto-generate)') }}</label>
        <input v-model="cardNo" :placeholder="t('Scan a physical card or leave empty')" style="text-transform: uppercase" />

        <label class="field-label">{{ t('Paid by *') }}</label>
        <select v-model="modeOfPayment">
          <option v-for="mode in modes" :key="mode.mode_of_payment" :value="mode.mode_of_payment">
            {{ mode.mode_of_payment }}
          </option>
        </select>

        <p class="muted small">
          {{ t('Sold to') }} {{ cart.customer?.customer_name || t('the walk-in customer') }} —
          {{ t('posts to the Gift Cards liability account (no tax; tax applies when the card is spent).') }}
        </p>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" @click="$emit('close')">{{ t('Cancel') }}</button>
        <button class="btn btn-primary" :disabled="!amount || amount <= 0 || !modeOfPayment || busy" @click="sell">
          {{ busy ? t('Selling…') : t('Sell {amount} card', { amount: money(amount || 0) }) }}
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
const cardNo = ref('')
const busy = ref(false)
const amountInput = ref(null)

const modes = computed(() =>
  session.paymentModes.filter(
    (m) =>
      m.mode_of_payment !== session.storeCreditMode &&
      m.mode_of_payment !== session.giftCardMode
  )
)
const modeOfPayment = ref(null)

onMounted(() => {
  modeOfPayment.value = (modes.value.find((m) => m.default) || modes.value[0])?.mode_of_payment
  amountInput.value?.focus()
})

async function sell() {
  busy.value = true
  try {
    const receipt = await call('lumenpos.api.sales.sell_gift_card', {
      payload: {
        pos_profile: session.posProfile,
        amount: amount.value,
        card_no: cardNo.value.trim() || null,
        customer: cart.customer?.name || null,
        sales_person: cart.salesPerson,
        payments: [{ mode_of_payment: modeOfPayment.value, amount: amount.value }],
      },
    })
    session.notify(t('Gift card {cardNo} sold', { cardNo: receipt.gift_card_no }))
    emit('done', receipt)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.form { display: flex; flex-direction: column; gap: 6px; }
.field-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  margin-top: 8px;
}
.small { font-size: 12px; margin: 10px 0 0; }
</style>
