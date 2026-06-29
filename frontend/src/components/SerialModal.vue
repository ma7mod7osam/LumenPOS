<template>
  <div class="modal-backdrop">
    <div class="modal" style="width: 440px">
      <div class="modal-header">
        {{ t('Scan serial number') }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <div class="item-name">{{ item.item_name }}</div>
        <p class="muted hint">
          {{ t("This item is serialized — scan or type the unit's serial number. It must match stock in this register's warehouse.") }}
        </p>
        <input
          ref="input"
          v-model="serial"
          :placeholder="scanOnly ? t('Scan the serial…') : t('Serial number')"
          style="width: 100%"
          :disabled="checking"
          @keydown="scan.onKeydown"
          @keydown.enter="confirm"
          @paste.prevent
        />
        <div v-if="error" class="serial-error">{{ error }}</div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" @click="$emit('close')">{{ t('Cancel') }}</button>
        <button class="btn btn-primary" :disabled="!serial.trim() || checking" @click="confirm">
          {{ checking ? t('Checking…') : t('Add to sale') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { useCartStore } from '../stores/cart'
import { createScanGuard } from '../scanGuard'
import { t } from '../i18n'

const props = defineProps({ item: Object })
const emit = defineEmits(['close', 'add'])

const session = useSessionStore()
const cart = useCartStore()
const serial = ref('')
const error = ref('')
const checking = ref(false)
const input = ref(null)
const scan = createScanGuard()
const scanOnly = computed(() => Boolean(session.settings?.serial_scan_only))

onMounted(() => input.value?.focus())

async function confirm() {
  const value = serial.value.trim()
  if (!value || checking.value) return
  error.value = ''
  if (scanOnly.value && !scan.isScan(serial.value)) {
    error.value = t('Manual entry is off — scan the serial with the scanner.')
    serial.value = ''
    scan.reset()
    input.value?.focus()
    return
  }
  if (cart.hasSerial(value)) {
    error.value = t('Serial {serial} is already in this sale', { serial: value })
    return
  }
  checking.value = true
  try {
    const result = await call('lumenpos.api.catalog.validate_serial', {
      pos_profile: session.posProfile,
      item_code: props.item.item_code,
      serial_no: value,
    })
    if (!result.valid) {
      error.value = result.message
      serial.value = ''
      scan.reset()
      input.value?.focus()
      return
    }
    emit('add', result.serial_no)
  } catch (e) {
    error.value = e.message
  } finally {
    checking.value = false
  }
}
</script>

<style scoped>
.item-name { font-weight: 700; font-size: 15px; margin-bottom: 4px; }
.hint { margin: 4px 0 12px; font-size: 12.5px; }
.serial-error {
  margin-top: 10px;
  background: rgba(226, 48, 48, 0.08);
  color: var(--red);
  border-radius: var(--radius);
  padding: 9px 12px;
  font-weight: 600;
  font-size: 13px;
}
</style>
