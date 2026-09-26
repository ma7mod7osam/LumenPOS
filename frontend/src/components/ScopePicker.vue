<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <!-- Where a rule applies (lumenpos.scope): the whole group, one company, or
       outlets chosen by name. A site with one company keeps the plain list. -->
  <div class="scope-picker">
    <div v-if="multi" class="segmented">
      <button
        v-for="m in MODES"
        :key="m.key"
        type="button"
        class="seg-btn"
        :class="{ on: mode === m.key }"
        @click="setMode(m.key)"
      >
        {{ t(m.label) }}
      </button>
    </div>
    <select v-if="multi && mode === 'company'" :value="company" class="scope-company" @change="setCompany($event.target.value)">
      <option v-for="c in session.companies" :key="c" :value="c">{{ c }}</option>
    </select>
    <div v-if="!multi || mode === 'outlets'" class="outlet-row">
      <label v-for="profile in session.availableProfiles" :key="profile" class="inline-check">
        <input type="checkbox" :value="profile" :checked="outlets.includes(profile)" @change="toggle(profile, $event.target.checked)" />
        {{ session.outletLabel(profile) }}
      </label>
      <span v-if="!multi" class="muted small">{{ t('(none ticked = all outlets)') }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { t } from '../i18n'
import { useSessionStore } from '../stores/session'

const props = defineProps({
  company: { type: String, default: '' },
  outlets: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:company', 'update:outlets'])
const session = useSessionStore()

const MODES = [
  { key: 'group', label: 'Whole group' },
  { key: 'company', label: 'One company' },
  { key: 'outlets', label: 'Chosen outlets' },
]
const multi = computed(() => session.multiCompany)
// "Chosen outlets" with none ticked yet must stay chosen while the manager
// ticks, so the picked mode is remembered, not only derived.
const picked = ref(null)
const mode = computed(() => {
  if (props.outlets.length) return 'outlets'
  if (props.company) return 'company'
  return picked.value === 'outlets' ? 'outlets' : 'group'
})

function setMode(key) {
  picked.value = key
  if (key === 'group') {
    emit('update:company', '')
    emit('update:outlets', [])
  } else if (key === 'company') {
    emit('update:outlets', [])
    emit('update:company', props.company || session.company || session.companies[0] || '')
  } else {
    emit('update:company', '')
  }
}
function setCompany(value) {
  emit('update:company', value)
}
function toggle(profile, on) {
  const next = props.outlets.filter((p) => p !== profile)
  if (on) next.push(profile)
  emit('update:outlets', next)
}
</script>

<style scoped>
.scope-picker { display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px; }
.segmented {
  display: inline-flex;
  align-self: flex-start;
  gap: 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 4px;
  flex-wrap: wrap;
}
.seg-btn {
  border-radius: calc(var(--radius) - 2px);
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
}
.seg-btn:hover { color: var(--text); }
.seg-btn.on { background: var(--brand); color: #fff; }
.scope-company { max-width: 320px; }
.outlet-row { display: flex; flex-wrap: wrap; gap: 6px 14px; align-items: center; }
.inline-check { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; }
</style>
