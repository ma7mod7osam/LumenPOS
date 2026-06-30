<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal price-check">
      <div class="modal-header">
        <Icon name="search" /> {{ t('Price & stock check') }}
        <button class="btn-ghost close" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <div class="pc-search">
          <input
            ref="input"
            v-model="query"
            :placeholder="t('Scan a barcode or type a name…')"
            @keydown="scanGuard.onKeydown"
            @keydown.enter="lookup"
            @input="onInput"
          />
          <button class="btn btn-primary" :disabled="!query.trim() || loading" @click="lookup">
            {{ loading ? t('Checking…') : t('Check') }}
          </button>
        </div>

        <div v-if="searched && !matches.length && !loading" class="pc-empty">
          {{ t('No item matches “{q}”.', { q: lastQuery }) }}
        </div>

        <ul v-else class="pc-list">
          <li v-for="m in matches" :key="m.item_code" class="pc-item">
            <div class="pc-main">
              <div class="pc-name">{{ m.item_name }}</div>
              <div class="pc-meta muted small">
                {{ m.item_code }}<span v-if="m.barcode"> · {{ m.barcode }}</span>
              </div>
            </div>
            <div class="pc-figures">
              <div class="pc-price">{{ money(m.price) }}</div>
              <div
                v-if="m.standard_price && m.standard_price > m.price"
                class="pc-compare muted small"
              >
                {{ money(m.standard_price) }}
              </div>
              <div class="pc-stock small" :class="stockClass(m)">
                <template v-if="!m.is_stock_item">{{ t('Non-stock') }}</template>
                <template v-else>
                  {{ t('{qty} in stock', { qty: fmtQty(m.stock_here) }) }}
                  <span v-if="m.stock_total !== m.stock_here" class="muted">
                    · {{ t('{qty} all stores', { qty: fmtQty(m.stock_total) }) }}
                  </span>
                </template>
              </div>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, onMounted } from 'vue'
import { t } from '../i18n'
import { call } from '../api'
import { money } from '../format'
import { useSessionStore } from '../stores/session'
import { createScanGuard } from '../scanGuard'

defineEmits(['close'])

const session = useSessionStore()
const scanGuard = createScanGuard()
const query = ref('')
const lastQuery = ref('')
const matches = ref([])
const loading = ref(false)
const searched = ref(false)
const input = ref(null)
let scanTimer = null

onMounted(() => input.value?.focus())

// A scanned barcode arrives as a fast burst — look it up immediately without
// waiting for Enter (typed queries still submit on Enter / the Check button).
function onInput() {
  clearTimeout(scanTimer)
  const value = query.value
  if (value.length >= 3 && scanGuard.isScan(value)) {
    scanTimer = setTimeout(() => {
      if (query.value === value) lookup()
    }, 80)
  }
}

async function lookup() {
  const q = query.value.trim()
  if (!q || loading.value) return
  loading.value = true
  lastQuery.value = q
  try {
    const res = await call('lumenpos.api.catalog.price_check', {
      pos_profile: session.posProfile,
      query: q,
    })
    matches.value = res.matches || []
    // A unique barcode/serial hit clears the box so the next scan is clean.
    if (matches.value.length === 1 && matches.value[0].barcode === q) query.value = ''
  } catch (e) {
    session.notify(e.message, true)
    matches.value = []
  } finally {
    loading.value = false
    searched.value = true
    scanGuard.reset()
  }
}

function fmtQty(n) {
  return Number.isInteger(n) ? n : Number(n).toFixed(2)
}

function stockClass(m) {
  if (!m.is_stock_item) return 'ok'
  if (m.stock_here <= 0) return 'out'
  if (m.stock_here < 5) return 'low'
  return 'ok'
}
</script>

<style scoped>
.price-check { width: 460px; max-width: 94vw; }
.modal-header { display: flex; align-items: center; gap: 8px; }
.close { margin-inline-start: auto; }
.pc-search { display: flex; gap: 8px; margin-bottom: 12px; }
.pc-search input { flex: 1; padding: 10px 12px; font-size: 15px; }
.pc-empty { padding: 24px; text-align: center; color: var(--text-muted); }
.pc-list { list-style: none; margin: 0; padding: 0; max-height: 50vh; overflow-y: auto; }
.pc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 4px;
  border-bottom: 1px solid var(--border);
}
.pc-item:last-child { border-bottom: none; }
.pc-main { min-width: 0; }
.pc-name { font-weight: 600; }
.pc-figures { text-align: end; flex-shrink: 0; }
.pc-price { font-weight: 800; font-size: 17px; }
.pc-compare { text-decoration: line-through; }
.pc-stock { margin-top: 2px; font-weight: 600; }
.pc-stock.ok { color: var(--text); }
.pc-stock.low { color: #b8860b; }
.pc-stock.out { color: var(--red, #d23f3f); }
.small { font-size: 12px; }
</style>
