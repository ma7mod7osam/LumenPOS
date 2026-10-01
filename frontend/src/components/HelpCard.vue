<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<!-- The card that greets (0.58.0): someone who has not seen the help yet is
     offered the tour, with what was added lately, and after an update each
     person sees once what is new for them. Both are switched in Settings,
     General, Help for staff. -->
<template>
  <div v-if="help.card" class="hc-backdrop" @click.self="help.dismissCard()">
    <div class="hc card" role="dialog" aria-modal="true" :aria-labelledby="'hc-title'">
      <template v-if="help.card === 'welcome'">
        <div class="hc-badge"><Icon name="help" :size="26" /></div>
        <h2 id="hc-title" class="hc-title">{{ t('Help on every screen') }}</h2>
        <p class="hc-lead">{{ t('Tap ? at the top of any screen for its help. A one-minute tour shows you around the till.') }}</p>
        <template v-if="help.switches.whats_new && items.length">
          <div class="hc-sub">{{ t('Recently added') }}</div>
          <ul class="hc-list compact">
            <li v-for="item in items.slice(0, 4)" :key="item.version + item.title">
              <b>{{ t(item.title) }}</b>
              <span class="muted">{{ t(item.text) }}</span>
            </li>
          </ul>
        </template>
        <div class="hc-actions">
          <button type="button" class="btn btn-outline" @click="help.dismissCard()">{{ t('Later') }}</button>
          <button type="button" class="btn btn-primary" @click="help.startTour('basics')">
            <Icon name="play" /> {{ t('Take the tour') }}
          </button>
        </div>
      </template>
      <template v-else>
        <div class="hc-badge"><Icon name="star" :size="26" /></div>
        <h2 id="hc-title" class="hc-title">{{ t('What is new in LumenPOS') }}</h2>
        <p class="hc-lead muted">LumenPOS {{ help.version }}</p>
        <ul class="hc-list">
          <li v-for="item in items" :key="item.version + item.title">
            <div class="hc-item-title">{{ t(item.title) }}</div>
            <div class="hc-item-text">{{ t(item.text) }}</div>
            <button
              v-if="canShow(item)"
              type="button"
              class="btn btn-outline btn-sm hc-show"
              @click="help.showMe(item, router)"
            >
              {{ t('Show me') }}
            </button>
          </li>
        </ul>
        <div class="hc-actions">
          <button type="button" class="btn btn-primary" @click="help.dismissCard()">{{ t('Got it') }}</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { t } from '../i18n'
import { TOURS } from '../help/content'
import { useHelpStore } from '../stores/help'
import Icon from './Icon.vue'

const help = useHelpStore()
const router = useRouter()

const items = computed(() => (help.card === 'all-news' ? help.allNews : help.news))
const canShow = (item) => Boolean((item.tour && help.inTill && TOURS[item.tour]) || item.route)
</script>

<style scoped>
.hc-backdrop {
  position: fixed;
  inset: 0;
  z-index: 950;
  background: rgba(10, 13, 20, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.hc {
  width: min(480px, 100%);
  max-height: calc(100vh - 32px);
  overflow-y: auto;
  padding: 22px 22px 18px;
}
.hc-badge {
  width: 46px;
  height: 46px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--brand-soft, var(--brand));
  color: #fff;
  margin-bottom: 12px;
}
.hc-title { margin: 0 0 6px; font-size: 20px; }
.hc-lead { margin: 0 0 14px; line-height: 1.55; }
.hc-sub {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  margin: 4px 0 6px;
}
.hc-list {
  list-style: none;
  margin: 0 0 14px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hc-list li {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 10px 12px;
  background: var(--surface-2);
}
.hc-list.compact li { padding: 8px 12px; font-size: 13px; line-height: 1.5; }
.hc-list.compact li b { display: block; }
.hc-item-title { font-weight: 700; margin-bottom: 2px; }
.hc-item-text { font-size: 13.5px; line-height: 1.5; color: var(--text); }
.hc-show { margin-top: 8px; }
.hc-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
