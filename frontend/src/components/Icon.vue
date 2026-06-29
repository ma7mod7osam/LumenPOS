<template>
  <span class="icon" :style="{ width: px, height: px }" v-html="svg" aria-hidden="true" />
</template>

<script setup>
// Lightweight inline-SVG icon set in the same line style as the nav rail
// (1.8 stroke, currentColor, 24x24). Replaces emojis so the UI stays
// professional and themed by the brand colour.
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
})

const STROKE = new Set([
  'close', 'shield', 'bulb', 'ticket', 'store', 'person', 'company', 'bank',
  'card', 'cash', 'hourglass', 'exchange', 'refresh', 'download', 'upload',
  'ban', 'barcode', 'gift', 'bike', 'plus', 'check', 'warning',
])

const PATHS = {
  close: '<path d="M6 6 18 18M18 6 6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M5 12l4.5 4.5L19 7"/>',
  warning: '<path d="M12 3 22 20H2z"/><path d="M12 10v4M12 17.5h.01"/>',
  gift:
    '<path d="M20 12v8a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-8"/>' +
    '<path d="M2.5 8h19v4h-19z"/><path d="M12 8v13"/>' +
    '<path d="M12 8S10.6 4 8 4a2 2 0 0 0 0 4z"/><path d="M12 8s1.4-4 4-4a2 2 0 0 1 0 4z"/>',
  bike:
    '<circle cx="6" cy="17" r="3"/><circle cx="18" cy="17" r="3"/>' +
    '<path d="M6 17 9.5 9H14l2.5 8M9.5 9 8 6H5.5M14 9l1 3"/>',
  shield: '<path d="M12 3 5 6v5c0 4.4 3 7.6 7 9 4-1.4 7-4.6 7-9V6z"/>',
  bulb:
    '<path d="M9 18h6M10 21h4"/>' +
    '<path d="M8.5 14a5 5 0 1 1 7 0c-.7.7-1 1.4-1 2.5h-5c0-1.1-.3-1.8-1-2.5z"/>',
  ticket:
    '<path d="M3 8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2 2 2 0 0 0 0 4 2 2 0 0 1-2 2H5a2 2 0 0 1-2-2 2 2 0 0 0 0-4z"/>' +
    '<path d="M14.5 6.5v11"/>',
  store:
    '<path d="M4 9h16v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/>' +
    '<path d="M3 9l1.8-5h14.4L21 9a3 3 0 0 1-6 0 3 3 0 0 1-6 0 3 3 0 0 1-6 0z"/>',
  person: '<circle cx="12" cy="8" r="3.5"/><path d="M5.5 20a6.5 6.5 0 0 1 13 0"/>',
  company:
    '<path d="M5 21V4a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v17"/>' +
    '<path d="M15 8h3a1 1 0 0 1 1 1v12M3 21h18M8 7h2M8 11h2M8 15h2"/>',
  bank:
    '<path d="M3 10 12 4l9 6M5 10v8M10 10v8M14 10v8M19 10v8M3 21h18M4 10h16"/>',
  card: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18"/>',
  cash:
    '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>' +
    '<path d="M6 12h.01M18 12h.01"/>',
  hourglass:
    '<path d="M6 3h12M6 21h12"/>' +
    '<path d="M8 3c0 4 4 5 4 6 0-1 4-2 4-6M8 21c0-4 4-5 4-6 0 1 4 2 4 6"/>',
  exchange: '<path d="M3 9h14l-3.5-3.5M21 15H7l3.5 3.5"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-2.6-6.3M21 4.5V9h-4.5"/>',
  download: '<path d="M12 3v12M8 11l4 4 4-4M5 21h14"/>',
  upload: '<path d="M12 21V9M8 13l4-4 4 4M5 3h14"/>',
  ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6 18.4 18.4"/>',
  barcode: '<path d="M4 5v14M7 5v14M10 5v14M13 5v14M17 5v14M20 5v14"/>',
  // filled
  star:
    '<path d="M12 3.5l2.6 5.3 5.9.9-4.25 4.15 1 5.85L12 17.05 6.75 19.6l1-5.85L3.5 9.7l5.9-.9z"/>',
  play: '<path d="M7 5l12 7-12 7z"/>',
}

const px = computed(() => (typeof props.size === 'number' ? `${props.size}px` : props.size))

const svg = computed(() => {
  const inner = PATHS[props.name]
  if (!inner) return ''
  const filled = !STROKE.has(props.name)
  const attrs = filled
    ? 'fill="currentColor"'
    : 'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'
  return `<svg viewBox="0 0 24 24" width="100%" height="100%" ${attrs}>${inner}</svg>`
})
</script>

<style scoped>
.icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  vertical-align: -0.15em;
  line-height: 0;
}
</style>
