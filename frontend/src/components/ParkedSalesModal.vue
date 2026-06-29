<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        {{ t('Parked sales') }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <div v-if="loading" class="muted empty">{{ t('Loading…') }}</div>
        <div v-else-if="!parked.length" class="muted empty">{{ t('No parked sales') }}</div>
        <div v-for="sale in parked" :key="sale.name" class="parked-row">
          <div class="parked-info">
            <div class="parked-name">{{ sale.customer_name || t('Walk-in') }}</div>
            <div class="muted small">
              {{ shortTime(sale.parked_at) }}<span v-if="sale.note"> · {{ sale.note }}</span>
            </div>
          </div>
          <button class="btn btn-outline" @click="discard(sale.name)">{{ t('Discard') }}</button>
          <button class="btn btn-primary" @click="retrieve(sale.name)">{{ t('Retrieve') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, onMounted } from 'vue'
import { call } from '../api'
import { useCartStore } from '../stores/cart'
import { useSessionStore } from '../stores/session'
import { shortTime } from '../format'
import { t } from '../i18n'

const emit = defineEmits(['close'])
const cart = useCartStore()
const session = useSessionStore()
const parked = ref([])
const loading = ref(true)

onMounted(load)

async function load() {
  loading.value = true
  try {
    parked.value = await call('lumenpos.api.sales.list_parked', {
      pos_profile: session.posProfile,
    })
  } finally {
    loading.value = false
  }
}

async function retrieve(name) {
  if (cart.lines.length && !confirm(t('Replace the current cart with this parked sale?'))) return
  try {
    await cart.retrieve(name)
    emit('close')
  } catch (e) {
    session.notify(e.message, true)
  }
}

async function discard(name) {
  if (!confirm(t('Discard this parked sale?'))) return
  await call('lumenpos.api.sales.discard_parked', { name })
  await load()
}
</script>

<style scoped>
.parked-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 4px;
  border-bottom: 1px solid var(--border);
}
.parked-row:last-child { border-bottom: none; }
.parked-info { flex: 1; }
.parked-name { font-weight: 600; }
.small { font-size: 12px; }
.empty { padding: 32px; text-align: center; }
</style>
