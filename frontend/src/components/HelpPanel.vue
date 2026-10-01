<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<!-- The help of the screen in use (0.58.0): what to do there, step by step,
     a "Show me" where a tour exists, every tour this person may take, and
     what is new. Texts: help/content.js. -->
<template>
  <div v-if="help.panelOpen" class="help-backdrop" @click.self="help.closePanel()">
    <aside class="help-panel" role="dialog" aria-modal="true" :aria-label="t('Help: {screen}', { screen: screenTitle })">
      <header class="help-head">
        <div class="help-head-text">
          <div class="help-kicker"><Icon name="help" /> {{ t('Help') }}</div>
          <div class="help-title">{{ screenTitle }}</div>
        </div>
        <button type="button" class="btn-ghost" :aria-label="t('Close')" @click="help.closePanel()"><Icon name="close" /></button>
      </header>
      <div class="help-body">
        <p v-if="!topics.length" class="muted">{{ t('This screen has no help of its own yet. The tours below show the basics.') }}</p>
        <details v-for="(topic, i) in topics" :key="topic.title" class="help-topic" :open="i === 0">
          <summary>{{ t(topic.title) }}</summary>
          <ol class="help-steps">
            <li v-for="(line, j) in topic.steps" :key="j">{{ say(line) }}</li>
          </ol>
          <button
            v-if="topic.tour && tourIds.includes(topic.tour)"
            type="button"
            class="btn btn-outline btn-sm show-me"
            @click="help.startTour(topic.tour)"
          >
            <Icon name="play" /> {{ t('Show me') }}
          </button>
        </details>

        <div class="help-section">{{ t('Short tours') }}</div>
        <div class="help-tours">
          <button v-for="tour in help.availableTours" :key="tour.id" type="button" class="help-tour" @click="help.startTour(tour.id)">
            <Icon :name="tour.done ? 'check' : 'play'" />
            <span>{{ t(tour.title) }}</span>
          </button>
        </div>

        <button v-if="help.allNews.length" type="button" class="help-news-link" @click="help.showAllNews()">
          <Icon name="star" /> {{ t('What is new in LumenPOS') }}
        </button>
        <p class="muted small help-version">LumenPOS {{ help.version }}</p>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { t } from '../i18n'
import { SCREENS } from '../help/content'
import { useHelpStore } from '../stores/help'
import Icon from './Icon.vue'

const help = useHelpStore()
const route = useRoute()

// Esc closes the panel, as it ends a tour.
function onKey(event) {
  if (event.key === 'Escape' && help.panelOpen && !help.tourId) help.closePanel()
}
window.addEventListener('keydown', onKey)
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

const screenTitle = computed(() => t(SCREENS[route.path] || 'Sell'))
const topics = computed(() => help.topicsFor(route.path))
const tourIds = computed(() => help.availableTours.map((tour) => tour.id))

// A step is a text, or a text and the labels it names, each in the till's
// own words for that button. A label's "…" (Refund…) stays on the button:
// inside a sentence it would read "Refund…."
function say(line) {
  if (!Array.isArray(line)) return t(line)
  const [text, labels] = line
  const params = {}
  for (const [key, label] of Object.entries(labels || {})) params[key] = t(label).replace(/\s*…$/, '')
  return t(text, params)
}
</script>

<style scoped>
.help-backdrop {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: rgba(10, 13, 20, 0.35);
  display: flex;
  justify-content: flex-end;
}
.help-panel {
  width: min(420px, 100vw);
  height: 100%;
  background: var(--card-bg);
  color: var(--text);
  border-inline-start: 1px solid var(--border);
  box-shadow: var(--shadow-md);
  display: flex;
  flex-direction: column;
}
.help-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 16px 16px 12px;
  border-bottom: 1px solid var(--border);
}
.help-head-text { min-width: 0; }
.help-kicker {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-dark, var(--brand));
}
.help-title { font-size: 18px; font-weight: 700; margin-top: 2px; }
.help-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px 20px;
}
.help-topic {
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 10px;
  background: var(--surface-2);
}
.help-topic summary {
  cursor: pointer;
  list-style: none;
  padding: 11px 14px;
  font-weight: 700;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.help-topic summary::-webkit-details-marker { display: none; }
.help-topic summary::after {
  content: '▾';
  color: var(--text-muted);
  font-size: 12px;
}
.help-topic[open] summary::after { content: '▴'; }
.help-steps {
  margin: 0;
  padding: 0 14px 4px;
  padding-inline-start: 34px;
  font-size: 13.5px;
  line-height: 1.55;
}
.help-steps li { margin-bottom: 6px; }
.show-me {
  margin: 4px 14px 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.help-section {
  margin: 18px 0 8px;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.help-tours { display: flex; flex-direction: column; gap: 6px; }
.help-tour {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  text-align: start;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--card-bg);
  color: var(--text);
  font-weight: 600;
  font-size: 13.5px;
}
.help-tour:hover { border-color: var(--brand); }
.help-news-link {
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--brand-dark, var(--brand));
  font-weight: 700;
  font-size: 13.5px;
  padding: 6px 0;
}
.help-version { margin-top: 10px; }
</style>
