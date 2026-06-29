<template>
  <div class="ple">
    <div class="ple-head">
      <span class="ple-count">
        {{ t('Search to edit existing prices on') }} <b>{{ priceList }}</b>{{ t(', or add / import below — changes apply immediately') }}
      </span>
      <div class="ple-actions">
        <button class="btn btn-outline" :disabled="exporting" @click="doExport">
          <Icon name="download" /> {{ exporting ? t('Exporting…') : t('Export') }}
        </button>
        <button class="btn btn-outline" :disabled="importing || !canManage" @click="fileInput?.click()">
          <Icon name="upload" /> {{ importing ? t('Importing…') : t('Import Excel/CSV') }}
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".csv,.xlsx,.xlsm,.xls"
          class="hidden-file"
          @change="onImportFile"
        />
      </div>
    </div>

    <div class="item-row">
      <input
        v-model="search"
        :placeholder="t('Search priced items by name, code or barcode…')"
        @input="debouncedLoad"
        class="search-box"
      />
      <LinkPicker
        v-if="canManage"
        doctype="Item"
        v-model="addPick"
        :placeholder="t('+ Add item (name, code or barcode)…')"
        @picked="addRow"
      />
    </div>

    <div v-if="importReport" class="import-report">
      <div class="gate-ok">
        ✓ {{ t('Imported — {created} added, {updated} updated', { created: importReport.created, updated: importReport.updated }) }}
      </div>
      <div v-for="(err, i) in importReport.errors" :key="i" class="gate-bad">⚠ {{ err }}</div>
      <button class="btn-ghost dismiss" @click="importReport = null">{{ t('Dismiss') }}</button>
    </div>

    <table class="price-table" v-if="rows.length">
      <thead>
        <tr>
          <th>{{ t('Item') }}</th>
          <th class="right" v-if="compareList">{{ t('Default') }} ({{ compareList }})</th>
          <th class="right">{{ t('Book price') }}</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.item_code">
          <td>
            <div class="price-item-name">{{ row.item_name }}</div>
            <div class="muted small mono">{{ row.item_code }}</div>
          </td>
          <td class="right muted" v-if="compareList">
            {{ row.default_rate != null ? money(row.default_rate) : '—' }}
          </td>
          <td class="right">
            <input
              type="number"
              min="0"
              step="0.01"
              class="price-input"
              :class="{ dirty: row._dirty }"
              :disabled="!canManage"
              v-model.number="row.rate"
              @input="row._dirty = true"
              @keydown.enter="savePrice(row)"
              @blur="row._dirty && savePrice(row)"
            />
          </td>
          <td>
            <button v-if="canManage" class="btn-ghost" :title="t('Remove from this price list')" @click="removePrice(row)"><Icon name="close" /></button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-else-if="!loading" class="muted empty-note">
      {{ search
        ? t('No matching priced items.')
        : t('No items priced in this book yet — add an item or import a file. Items not priced here have no price (0).') }}
    </div>
    <button v-if="rows.length && rows.length < total" class="btn btn-outline add-row" @click="load(true)">
      {{ t('Load more ({count} remaining)', { count: total - rows.length }) }}
    </button>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
// Editable Item Price table for one price list, reused by Price Books and by
// each delivery app's channel price list. Includes Excel/CSV import + export.
import { ref, watch, onMounted } from 'vue'
import { call } from '../api'
import { money } from '../format'
import { t } from '../i18n'
import { useSessionStore } from '../stores/session'
import LinkPicker from './LinkPicker.vue'

const props = defineProps({
  priceList: { type: String, required: true },
  compareList: { type: String, default: '' },
  canManage: { type: Boolean, default: false },
})

const session = useSessionStore()
const rows = ref([])
const total = ref(0)
const search = ref('')
const addPick = ref('')
const loading = ref(false)
const exporting = ref(false)
const importing = ref(false)
const importReport = ref(null)
const fileInput = ref(null)
let timer = null

// Show the items priced on this (dedicated) list: load on open and whenever
// the list changes. Base selling lists are blocked elsewhere, so this only
// ever loads a small per-book/app list — never the whole catalogue.
onMounted(() => {
  if (props.priceList) load()
})
watch(
  () => props.priceList,
  () => {
    rows.value = []
    total.value = 0
    search.value = ''
    importReport.value = null
    if (props.priceList) load()
  }
)

function debouncedLoad() {
  clearTimeout(timer)
  timer = setTimeout(() => load(), 300)
}

async function load(append = false) {
  if (!props.priceList) return
  loading.value = true
  try {
    const data = await call('lumenpos.api.settings.list_price_book_prices', {
      price_list: props.priceList,
      search: search.value,
      start: append ? rows.value.length : 0,
      limit: 50,
      compare_price_list: props.compareList || undefined,
    })
    const fresh = data.items.map((row) => ({ ...row, _dirty: false }))
    rows.value = append ? [...rows.value, ...fresh] : fresh
    total.value = data.total
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function savePrice(row) {
  try {
    await call('lumenpos.api.settings.set_price_book_price', {
      price_list: props.priceList,
      item_code: row.item_code,
      rate: row.rate || 0,
    })
    row._dirty = false
    session.notify(`${row.item_name}: ${money(row.rate || 0)}`)
  } catch (e) {
    session.notify(e.message, true)
  }
}

async function removePrice(row) {
  if (!confirm(t('Remove {item} from "{list}"?', { item: row.item_name, list: props.priceList }))) return
  try {
    await call('lumenpos.api.settings.remove_price_book_price', {
      price_list: props.priceList,
      item_code: row.item_code,
    })
    rows.value = rows.value.filter((r) => r.item_code !== row.item_code)
    total.value = Math.max(0, total.value - 1)
  } catch (e) {
    session.notify(e.message, true)
  }
}

function addRow(option) {
  addPick.value = ''
  if (!option?.name) return
  if (rows.value.some((row) => row.item_code === option.name)) {
    session.notify(t('{item} is already in the list', { item: option.item_name || option.name }), true)
    return
  }
  rows.value.unshift({
    item_code: option.name,
    item_name: option.item_name || option.name,
    rate: null,
    default_rate: null,
    _dirty: true,
  })
  total.value += 1
}

async function doExport() {
  exporting.value = true
  try {
    const res = await call('lumenpos.api.settings.export_price_book_prices', {
      price_list: props.priceList,
      compare_price_list: props.compareList || undefined,
    })
    const blob = new Blob([res.csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = res.filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    exporting.value = false
  }
}

function onImportFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = async () => {
    importing.value = true
    importReport.value = null
    try {
      const res = await call('lumenpos.api.settings.import_price_book_prices', {
        price_list: props.priceList,
        filename: file.name,
        content: reader.result,
      })
      importReport.value = res
      session.notify(t('Imported: {created} added, {updated} updated', { created: res.created, updated: res.updated }))
      await load()
    } catch (e) {
      session.notify(e.message, true)
    } finally {
      importing.value = false
      event.target.value = ''
    }
  }
  reader.readAsDataURL(file)
}
</script>

<style scoped>
.ple { margin: 4px 0 8px; }
.ple-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.ple-count { font-size: 12px; color: var(--text-muted); }
.ple-actions { display: flex; gap: 8px; }
.hidden-file { display: none; }
.item-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.item-row input, .search-box { flex: 1; min-width: 180px; }
.search-box { max-width: 280px; }
.price-table { width: 100%; border-collapse: collapse; margin: 4px 0 8px; }
.price-table th {
  text-align: left;
  font-size: 10.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  padding: 6px 8px;
}
.price-table th.right, .price-table td.right { text-align: right; }
.price-table td { padding: 7px 8px; border-top: 1px solid var(--border); }
.price-item-name { font-weight: 600; font-size: 13px; }
.mono { font-family: ui-monospace, monospace; }
.small { font-size: 12px; }
.price-input { width: 110px; text-align: right; padding: 6px 9px; }
.price-input.dirty { border-color: var(--amber); }
.add-row { margin-top: 2px; }
.empty-note { padding: 8px 0 4px; }
.import-report {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
  margin-bottom: 10px;
  font-size: 12.5px;
  display: flex;
  flex-direction: column;
  gap: 3px;
  position: relative;
}
.gate-ok { color: var(--brand-dark); font-weight: 600; }
.gate-bad { color: var(--red); font-weight: 600; }
.dismiss { align-self: flex-start; margin-top: 4px; color: var(--text-muted); }
</style>
