<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="variance-reason" :class="{ needed: required }" data-tour="register-variance">
    <div class="vr-title">
      <Icon name="warning" :size="16" />
      {{ known ? t('The count is short or over. Why?') : t('If the count is short or over, say why.') }}
    </div>
    <label class="vr-field">
      <span>{{ required ? t('Reason') : t('Reason (optional)') }}</span>
      <input
        :value="shown"
        maxlength="140"
        :placeholder="t('Write the reason, or tap one below')"
        @input="typed($event.target.value)"
      />
    </label>
    <div v-if="reasons.length" class="vr-chips">
      <button
        v-for="r in reasons"
        :key="r"
        type="button"
        class="vr-chip"
        :class="{ on: reason === r }"
        @click="$emit('update:reason', reason === r ? '' : r)"
      >
        {{ t(r) }}
      </button>
    </div>
    <label class="vr-field">
      <span>{{ t('Action taken (optional)') }}</span>
      <input
        :value="action"
        maxlength="500"
        :placeholder="t('For example: recounted, reported to the manager')"
        @input="$emit('update:action', $event.target.value)"
      />
    </label>
    <p v-if="missing" class="vr-missing">{{ t('Write a reason to close the register.') }}</p>
  </div>
</template>

<script setup>
// A reason for a short or over at the close (lumenpos.variance, 0.59.0). The
// cashier writes it in their own words, or taps one of the shop's reasons
// (kept as the shop wrote it, so it reads in each person's language), and can
// say what was done about it. Used for the cashier's own close and for a
// manager closing someone else's shift (RegisterView). The server checks
// Required again.
import { computed } from 'vue'
import Icon from './Icon.vue'
import { t } from '../i18n'

const props = defineProps({
  reasons: { type: Array, default: () => [] },
  reason: { type: String, default: '' },
  action: { type: String, default: '' },
  // The register does not close without a reason (Required, past the threshold).
  required: { type: Boolean, default: false },
  // The till knows the expected figures, so it knows there IS a difference.
  known: { type: Boolean, default: true },
  missing: { type: Boolean, default: false },
})
const emit = defineEmits(['update:reason', 'update:action'])

// A tapped reason shows in the till's language. Typing it out word for word
// picks the same reason, anything else is the cashier's own words.
const shown = computed(() => (props.reasons.includes(props.reason) ? t(props.reason) : props.reason))
function typed(value) {
  const hit = props.reasons.find((r) => r === value || t(r) === value)
  emit('update:reason', hit || value)
}
</script>

<style scoped>
.variance-reason {
  margin-top: 12px;
  padding: 12px;
  border-radius: var(--radius);
  border: 1px solid rgba(201, 130, 27, 0.4);
  background: rgba(245, 166, 35, 0.1);
  text-align: start;
}
.variance-reason.needed {
  border-color: rgba(201, 130, 27, 0.7);
}
.vr-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 700;
  font-size: 13px;
  margin-bottom: 8px;
}
.vr-title :deep(svg) {
  color: var(--amber);
  flex: none;
}
.vr-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
}
.vr-field + .vr-field,
.vr-chips + .vr-field {
  margin-top: 10px;
}
.vr-field input {
  width: 100%;
}
.vr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.vr-chip {
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--card-bg);
  color: var(--text);
  cursor: pointer;
}
.vr-chip.on {
  border-color: var(--brand);
  background: rgba(20, 99, 255, 0.1);
  color: var(--brand-dark);
}
html[data-theme='dark'] .vr-chip.on {
  color: #9fc0ff;
  background: rgba(47, 123, 255, 0.16);
}
.vr-missing {
  margin: 8px 0 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--red);
}
html[data-theme='dark'] .variance-reason {
  border-color: rgba(224, 165, 60, 0.45);
  background: rgba(224, 165, 60, 0.1);
}
</style>
