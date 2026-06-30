<template>
  <div class="picker" ref="root">
    <input
      :value="display"
      :placeholder="placeholder"
      :class="{ valid: modelValue }"
      @input="onType($event.target.value)"
      @focus="onFocus"
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
      @keydown.enter.prevent="pick(highlighted)"
      @keydown.esc="open = false"
    />
    <button v-if="modelValue" class="clear" @click="clear" tabindex="-1"><Icon name="close" /></button>
    <div v-if="open && results.length" class="dropdown">
      <button
        v-for="(option, i) in results"
        :key="option.name"
        class="option"
        :class="{ hl: i === highlighted }"
        @mousedown.prevent="pick(i)"
        @mousemove="highlighted = i"
      >
        <span class="option-label">{{ option.item_name || option.name }}</span>
        <span v-if="(option.item_name && option.item_name !== option.name) || option.barcode" class="option-code">
          <span v-if="option.item_name && option.item_name !== option.name">{{ option.name }}</span>
          <span v-if="option.barcode" class="option-bc"><Icon name="barcode" /> {{ option.barcode }}</span>
        </span>
      </button>
    </div>
    <div v-else-if="open && typed && !loading" class="dropdown">
      <div class="option muted">{{ t('No match — pick from the list, free text is not allowed') }}</div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
// Strict link autocomplete: the value is ONLY set by choosing a real record
// from the dropdown (typed free text never becomes the value).
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { call } from '../api'
import { t } from '../i18n'

const props = defineProps({
  doctype: { type: String, required: true },
  modelValue: { type: String, default: '' },
  label: { type: String, default: '' }, // display label when value preset
  placeholder: { type: String, default: () => t('Search…') },
  // Extra server-side filters merged into the lookup (e.g. { company }).
  filters: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['update:modelValue', 'picked'])

const root = ref(null)
const open = ref(false)
const typed = ref('')
const results = ref([])
const highlighted = ref(0)
const loading = ref(false)
let timer = null

const display = computed(() => {
  if (open.value) return typed.value
  return props.label || props.modelValue || ''
})

function onFocus() {
  typed.value = ''
  open.value = true
  search('')
}

function onType(value) {
  typed.value = value
  open.value = true
  clearTimeout(timer)
  timer = setTimeout(() => search(value), 200)
}

async function search(term) {
  loading.value = true
  try {
    results.value = await call('lumenpos.api.settings.link_options', {
      doctype: props.doctype,
      search: term,
      ...props.filters,
    })
    highlighted.value = 0
  } catch {
    results.value = []
  } finally {
    loading.value = false
  }
}

function move(delta) {
  if (!results.value.length) return
  highlighted.value =
    (highlighted.value + delta + results.value.length) % results.value.length
}

function pick(index) {
  const option = results.value[index]
  if (!option) return
  emit('update:modelValue', option.name)
  emit('picked', option)
  open.value = false
  typed.value = ''
}

function clear() {
  emit('update:modelValue', '')
  emit('picked', null)
  typed.value = ''
}

function onClickOutside(event) {
  if (root.value && !root.value.contains(event.target)) open.value = false
}
onMounted(() => document.addEventListener('mousedown', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', onClickOutside))
watch(() => props.doctype, () => clear())
</script>

<style scoped>
.picker { position: relative; flex: 1; min-width: 160px; }
.picker input { width: 100%; padding-right: 28px; }
.picker input.valid { border-color: var(--brand); }
.clear {
  position: absolute;
  right: 7px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--text-muted);
  font-size: 11px;
  padding: 2px 4px;
}
.clear:hover { color: var(--red); }
.dropdown {
  position: absolute;
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 10px 28px rgba(10, 16, 30, 0.16);
  max-height: 260px;
  overflow-y: auto;
  z-index: 60;
}
.option {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  width: 100%;
  text-align: left;
  padding: 9px 12px;
  border-bottom: 1px solid var(--border-subtle);
}
.option:last-child { border-bottom: none; }
.option.hl, .option:hover { background: rgba(20, 99, 255, 0.06); }
.option-label { font-weight: 600; font-size: 13px; }
.option-code { font-size: 11px; color: var(--text-muted); font-family: ui-monospace, monospace; display: flex; gap: 10px; }
.option-bc { color: var(--brand-dark); }
</style>
