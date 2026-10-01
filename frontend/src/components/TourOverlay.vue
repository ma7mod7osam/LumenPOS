<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<!-- A tour (0.58.0): one step at a time, the real button lit and the rest of
     the screen dimmed, with a card that says what it is for. It only shows:
     nothing is sold or changed, and the screen under it cannot be tapped
     while it is open. Steps and texts: help/content.js. -->
<template>
  <div v-if="help.tourId && step" class="tour-layer" role="dialog" aria-modal="true" :aria-label="t(help.tour.title)">
    <div v-if="rect" class="tour-spot" :style="spotStyle" />
    <div v-else class="tour-dim" />
    <div ref="cardEl" class="tour-card" :class="{ docked }" :style="cardStyle">
      <div class="tour-head">
        <span class="tour-count">{{ t('{n} of {total}', { n: help.stepIndex + 1, total: steps.length }) }}</span>
        <button type="button" class="btn-ghost tour-x" :aria-label="t('Close the tour')" @click="help.endTour(false)">
          <Icon name="close" />
        </button>
      </div>
      <div class="tour-title">{{ t(step.title) }}</div>
      <p class="tour-text">{{ t(step.text) }}</p>
      <div class="tour-actions">
        <button v-if="help.stepIndex > 0" type="button" class="btn btn-outline" @click="help.back()">{{ t('Back') }}</button>
        <button ref="nextEl" type="button" class="btn btn-primary" @click="last ? help.endTour(true) : help.next()">
          {{ last ? t('Done') : t('Next') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { t } from '../i18n'
import { useHelpStore } from '../stores/help'
import Icon from './Icon.vue'

const help = useHelpStore()
const router = useRouter()

const steps = computed(() => help.tourSteps)
const step = computed(() => steps.value[help.stepIndex] || null)
const last = computed(() => help.stepIndex >= steps.value.length - 1)

const rect = ref(null)
const cardEl = ref(null)
const nextEl = ref(null)
const cardPos = ref({ left: 12, top: 12 })
const docked = ref(false)
let target = null
let seq = 0

const PAD = 6
const GAP = 12
const MARGIN = 12

const spotStyle = computed(() => {
  const r = rect.value
  return {
    left: `${r.left - PAD}px`,
    top: `${r.top - PAD}px`,
    width: `${r.width + PAD * 2}px`,
    height: `${r.height + PAD * 2}px`,
  }
})
const cardStyle = computed(() => (docked.value ? {} : { left: `${cardPos.value.left}px`, top: `${cardPos.value.top}px` }))

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const shown = (el) => el && el.getClientRects().length > 0
const find = (name) => Array.from(document.querySelectorAll(`[data-tour="${name}"]`)).find(shown) || null

async function waitFor(name, ms) {
  const until = Date.now() + ms
  for (;;) {
    const el = find(name)
    if (el || Date.now() > until) return el
    await sleep(100)
  }
}

// Where the card goes: under the lit element when it fits, else above it,
// else beside it, always inside the screen. A phone docks it to the edge the
// lit element is not on.
function place() {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const card = cardEl.value
  const cw = card ? card.offsetWidth : 320
  const ch = card ? card.offsetHeight : 180
  const r = rect.value
  if (!r) {
    docked.value = false
    cardPos.value = { left: Math.max(MARGIN, (vw - cw) / 2), top: Math.max(MARGIN, (vh - ch) / 2) }
    return
  }
  if (vw < 600) {
    docked.value = true
    if (card) card.classList.toggle('dock-top', r.top + r.height / 2 > vh / 2)
    return
  }
  docked.value = false
  const rtl = document.documentElement.dir === 'rtl'
  const clampX = (x) => Math.min(Math.max(MARGIN, x), vw - cw - MARGIN)
  const clampY = (y) => Math.min(Math.max(MARGIN, y), vh - ch - MARGIN)
  const alignX = clampX(rtl ? r.right - cw : r.left)
  if (r.bottom + PAD + GAP + ch <= vh - MARGIN) {
    cardPos.value = { left: alignX, top: r.bottom + PAD + GAP }
  } else if (r.top - PAD - GAP - ch >= MARGIN) {
    cardPos.value = { left: alignX, top: r.top - PAD - GAP - ch }
  } else {
    // Tall element (a column): beside it, on the side with more room.
    const roomAfter = vw - r.right
    const left = roomAfter >= r.left ? r.right + PAD + GAP : r.left - PAD - GAP - cw
    cardPos.value = { left: clampX(left), top: clampY(r.top) }
  }
}

function measure() {
  if (!target || !shown(target)) {
    rect.value = null
  } else {
    const r = target.getBoundingClientRect()
    rect.value = { left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height }
  }
  place()
}

async function locate() {
  const mine = ++seq
  target = null
  rect.value = null
  const s = step.value
  if (!s) return
  const route = s.route || help.tour?.route
  if (route && router.currentRoute.value.path !== route) {
    await router.push(route)
  }
  if (s.click) {
    const opener = await waitFor(s.click, 1500)
    if (mine !== seq) return
    // Only when what the step points at is not open already (going back).
    if (opener && !find(s.target)) opener.click()
  }
  const el = await waitFor(s.target, s.click ? 2500 : 1500)
  if (mine !== seq) return
  if (!el && s.optional) {
    help.skip()
    return
  }
  target = el
  if (el) el.scrollIntoView({ block: 'nearest', inline: 'nearest' })
  await nextTick()
  measure()
  // The card's own size is known once it has rendered with its text.
  requestAnimationFrame(() => {
    if (mine === seq) measure()
  })
  nextEl.value?.focus({ preventScroll: true })
}

let frame = 0
function onViewport() {
  if (!help.tourId) return
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(measure)
}
function onKey(event) {
  if (!help.tourId) return
  if (event.key === 'Escape') {
    event.preventDefault()
    help.endTour(false)
  }
}
window.addEventListener('resize', onViewport)
window.addEventListener('scroll', onViewport, true)
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => {
  window.removeEventListener('resize', onViewport)
  window.removeEventListener('scroll', onViewport, true)
  window.removeEventListener('keydown', onKey)
  cancelAnimationFrame(frame)
})

// Declared after everything it reads (an immediate watcher above a computed
// it uses never runs: see CLAUDE.md, Known traps).
watch(
  () => [help.tourId, help.stepIndex, steps.value.length],
  () => {
    if (help.tourId) locate()
    else seq++
  },
  { immediate: true }
)
</script>

<style scoped>
.tour-layer {
  position: fixed;
  inset: 0;
  z-index: 5000;
}
.tour-dim {
  position: absolute;
  inset: 0;
  background: rgba(10, 13, 20, 0.62);
}
.tour-spot {
  position: absolute;
  border-radius: 12px;
  box-shadow: 0 0 0 9999px rgba(10, 13, 20, 0.62);
  outline: 2px solid var(--brand);
  outline-offset: 0;
  transition: left 0.18s ease, top 0.18s ease, width 0.18s ease, height 0.18s ease;
  pointer-events: none;
}
.tour-card {
  position: absolute;
  width: min(340px, calc(100vw - 24px));
  background: var(--card-bg);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 14px;
  box-shadow: var(--shadow-md);
  padding: 14px 16px 14px;
}
.tour-card.docked {
  inset-inline: 12px;
  bottom: 12px;
  width: auto;
}
.tour-card.docked.dock-top {
  bottom: auto;
  top: 12px;
}
.tour-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.tour-count {
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-dark, var(--brand));
}
.tour-x { padding: 4px; }
.tour-title {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 4px;
}
.tour-text {
  margin: 0 0 12px;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
}
.tour-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
