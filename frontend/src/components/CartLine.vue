<template>
  <div class="line" :class="{ expanded }">
    <button class="line-main" @click="expanded = !expanded">
      <div class="line-info">
        <div class="line-name">{{ line.item_name }}</div>
        <div class="line-code muted">
          {{ line.item_code }}<template v-if="line.barcode"> · <Icon name="barcode" /> {{ line.barcode }}</template>
        </div>
        <div v-if="line.warranty_days" class="line-warranty"><Icon name="shield" /> {{ warrantyLabel(line.warranty_days) }}</div>
        <div v-if="line.bundle_key" class="bundle-chip-row">
          <span class="bundle-chip"><Icon name="gift" /> {{ line.bundle_title }}</span>
        </div>
        <div v-if="line.has_serial_no" class="serial-chips">
          <span v-for="serial in line.serial_nos" :key="serial" class="serial-chip">
            {{ serial }}
            <button class="chip-x" @click.stop="cart.removeSerial(index, serial)"><Icon name="close" /></button>
          </span>
        </div>
        <div v-if="promoTitles.length" class="line-promos">
          <span v-for="title in promoTitles" :key="title" class="promo-badge"><Icon name="star" /> {{ title }}</span>
        </div>
        <div v-if="line.manual_discount_percent" class="muted small">
          {{ t('{percent}% manual discount', { percent: line.manual_discount_percent }) }}
        </div>
        <div v-if="suggestions.length" class="line-suggestions">
          <button
            v-for="(suggestion, i) in suggestions"
            :key="i"
            class="line-suggestion"
            :title="suggestion.title"
            @click.stop="$emit('suggestion', suggestion)"
          >
            <Icon name="bulb" /> {{ suggestion.message }}
          </button>
        </div>
      </div>
      <div class="line-qty">×{{ line.qty }}</div>
      <div class="line-amount">
        <div :class="{ struck: totalDiscount > 0 }">{{ money(line.price * line.qty) }}</div>
        <div v-if="totalDiscount > 0" class="discounted" :class="{ 'bundle-color': line.bundle_key }">
          {{ money(line.price * line.qty - totalDiscount) }}
        </div>
      </div>
    </button>

    <div v-if="expanded && line.bundle_key" class="line-edit">
      <span class="muted small" style="flex: 1">
        {{ t('Bundle pricing — items stay separate lines for individual returns.') }}
      </span>
      <button class="btn btn-ghost remove" @click="cart.removeBundle(line.bundle_key)">
        {{ t('Remove bundle') }}
      </button>
    </div>
    <div v-else-if="expanded" class="line-edit">
      <div class="edit-field">
        <label>{{ t('Quantity') }}</label>
        <div v-if="line.has_serial_no" class="stepper">
          <input type="number" :value="line.qty" disabled :title="t('Quantity follows scanned serials')" />
          <button class="btn btn-outline" @click="serialOpen = true">{{ t('+ Scan serial') }}</button>
        </div>
        <div v-else class="stepper">
          <button class="btn btn-outline" @click="cart.setQty(index, line.qty - 1)">−</button>
          <input
            type="number"
            min="0"
            step="1"
            :value="line.qty"
            @change="cart.setQty(index, $event.target.value)"
          />
          <button class="btn btn-outline" @click="cart.setQty(index, line.qty + 1)">+</button>
        </div>
      </div>
      <div class="edit-field">
        <label>{{ t('Discount %') }}</label>
        <input
          type="number"
          min="0"
          max="100"
          :value="line.manual_discount_percent"
          :disabled="!canEditPrice"
          :title="canEditPrice ? '' : t('You are not allowed to edit prices')"
          @input="setDiscount($event.target.value)"
          @change="setDiscount($event.target.value)"
        />
      </div>
      <button class="btn btn-ghost remove" @click="cart.removeLine(index)">{{ t('Remove') }}</button>
    </div>

    <SerialModal
      v-if="serialOpen"
      :item="line"
      @close="serialOpen = false"
      @add="onSerialAdded"
    />
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref } from 'vue'
import { t } from '../i18n'
import { useCartStore } from '../stores/cart'
import { useSessionStore } from '../stores/session'
import { money, warrantyLabel } from '../format'
import SerialModal from './SerialModal.vue'

import { computed } from 'vue'

const session = useSessionStore()
const canEditPrice = computed(() => session.permissions?.can_edit_price !== false)

const props = defineProps({
  line: Object,
  index: Number,
  promoDiscount: { type: Number, default: 0 },
  promoTitles: { type: Array, default: () => [] },
  bundleDiscount: { type: Number, default: 0 },
  suggestions: { type: Array, default: () => [] },
})

defineEmits(['suggestion'])

const cart = useCartStore()
const expanded = ref(false)
const serialOpen = ref(false)

const totalDiscount = computed(() => (props.promoDiscount || 0) + (props.bundleDiscount || 0))

function onSerialAdded(serial) {
  serialOpen.value = false
  cart.addItem(props.line, serial)
}

function setDiscount(value) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0))
  cart.lines[props.index].manual_discount_percent = pct
}
</script>

<style scoped>
.line { border-bottom: 1px solid var(--border); }
.line-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 11px 16px;
  text-align: left;
}
.line-main:hover { background: var(--surface-2); }
.line-info { flex: 1; min-width: 0; }
.line-name { font-weight: 600; font-size: 13.5px; }
.line-code {
  font-size: 11px;
  font-family: ui-monospace, monospace;
  margin-top: 1px;
}
.line-warranty {
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-soft);
  margin-top: 2px;
}
.line-promos { margin-top: 3px; display: flex; flex-wrap: wrap; gap: 4px; }
.serial-chips { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px; }
.serial-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  color: var(--brand-soft);
  background: rgba(0, 176, 185, 0.1);
  border-radius: 999px;
  padding: 2px 8px;
}
.chip-x { font-size: 10px; color: var(--text-muted); padding: 0 2px; }
.chip-x:hover { color: var(--red); }
.bundle-chip-row { margin-top: 3px; }
.bundle-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 700;
  color: var(--brand-dark);
  background: rgba(46, 91, 255, 0.1);
  border-radius: 999px;
  padding: 2px 9px;
}
.bundle-color { color: var(--brand-dark); }
.small { font-size: 12px; }
.line-suggestions {
  margin-top: 4px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.line-suggestion {
  text-align: start;
  font-size: 12px;
  font-weight: 700;
  color: var(--promo);
  background: rgba(123, 47, 242, 0.12);
  border: 1px solid rgba(123, 47, 242, 0.3);
  border-radius: 8px;
  padding: 5px 9px;
}
.line-suggestion:hover { background: rgba(123, 47, 242, 0.2); }
/* Dark mode: a lighter purple on a stronger tint stays legible. */
html[data-theme='dark'] .line-suggestion {
  color: #c9b0ff;
  background: rgba(150, 100, 255, 0.2);
  border-color: rgba(150, 100, 255, 0.42);
}
html[data-theme='dark'] .line-suggestion:hover { background: rgba(150, 100, 255, 0.3); }
.line-qty { color: var(--text-muted); font-weight: 600; }
.line-amount { text-align: right; font-weight: 600; }
.struck {
  text-decoration: line-through;
  color: var(--text-muted);
  font-weight: 400;
  font-size: 12px;
}
.discounted { color: var(--promo); }
.small { font-size: 12px; }
.line-edit {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 4px 16px 14px;
  background: var(--surface-2);
}
.edit-field label {
  display: block;
  font-size: 11.5px;
  font-weight: 700;
  color: var(--text-muted);
  margin-bottom: 4px;
}
.edit-field input {
  width: 70px;
  text-align: center;
  padding: 7px 8px;
}
.stepper { display: flex; gap: 4px; }
.stepper .btn { padding: 7px 12px; }
.remove { margin-left: auto; color: var(--red); }
</style>
