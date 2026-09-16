<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="insights">
    <!-- Loading -->
    <div v-if="loading" class="state-card">
      <div class="spinner" aria-hidden="true"></div>
      <p class="muted">{{ t('Loading…') }}</p>
    </div>

    <!-- Failed to read status -->
    <div v-else-if="error" class="state-card">
      <ChartMark />
      <h2>{{ t('Could not load the dashboard') }}</h2>
      <p class="muted">{{ error }}</p>
      <button class="btn btn-primary" @click="load">{{ t('Retry') }}</button>
    </div>

    <!-- The dashboard, embedded from Lumen Reports -->
    <div v-else-if="board" class="board">
      <div class="board-bar">
        <span class="board-title">{{ t('Sales dashboard') }}</span>
        <a class="btn small-btn" :href="board.open" target="_blank" rel="noopener">
          {{ t('Open in Lumen Reports') }}
        </a>
      </div>
      <iframe class="board-frame" :src="board.embed" :title="t('Sales dashboard')"></iframe>
    </div>

    <!-- Every other state is a card with a heading, a note, and maybe one action -->
    <div v-else class="state-card">
      <ChartMark />
      <h2>{{ view.title }}</h2>
      <p class="muted">{{ view.body }}</p>
      <p v-if="view.hint" class="muted small">{{ view.hint }}</p>
      <p v-if="actionError" class="neg small">{{ actionError }}</p>
      <button v-if="view.action" class="btn btn-primary" :disabled="working" @click="create">
        {{ working ? t('Creating…') : view.action }}
      </button>
      <button v-else-if="view.refresh" class="btn" @click="load">{{ t('Refresh') }}</button>
    </div>
  </div>
</template>

<script setup>
import { computed, h, onMounted, ref } from 'vue'
import { call } from '../api'
import { t, locale } from '../i18n'
import { theme } from '../theme'

const loading = ref(true)
const error = ref('')
const working = ref(false)
const actionError = ref('')
const info = ref(null)

const ChartMark = () =>
  h('svg', { viewBox: '0 0 24 24', class: 'mark', 'aria-hidden': 'true' }, [
    h('path', {
      d: 'M3 3v18h18M8 17v-6m5 6V7m5 10v-4',
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': '1.5',
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
    }),
  ])

// When Lumen Reports says the current user may view it, show the embedded
// dashboard. Its language and theme follow the till.
const board = computed(() => {
  const lr = info.value && info.value.lr
  if (!lr || !lr.can_view || lr.reason) return null
  const q = `?lang=${locale.value}&theme=${theme.value === 'dark' ? 'dark' : 'light'}`
  return { embed: lr.embed_url + q, open: lr.url }
})

// Everything that is not the dashboard is one explanatory card. Deciding it
// here keeps the template flat.
const view = computed(() => {
  const i = info.value || {}
  if (!i.compatible) {
    return {
      title: t('Sales dashboard'),
      body: t(
        'Lumen Reports needs Frappe v{version} or newer. This site runs an older version, so the dashboard is not available here.',
        { version: i.min_frappe || 14 },
      ),
    }
  }
  if (!i.installed) {
    return {
      title: t('Get the full picture of your sales'),
      body: t(
        'Install the Lumen Reports app to see a complete sales dashboard here: revenue by day and by outlet, payment mix, top items and more, with filters, all inside LumenPOS.',
      ),
      hint: t('Lumen Reports is available on the Frappe Cloud Marketplace, or through hello@lumen-solutions.co.'),
    }
  }
  if (!i.integration_ready) {
    return {
      title: t('Sales dashboard'),
      body: t(
        'Lumen Reports is installed, but this version does not include the LumenPOS dashboard yet. Update Lumen Reports, then come back.',
      ),
      refresh: true,
    }
  }
  const lr = i.lr || {}
  // Lumen Reports' own status call failed: say so, with its error as the detail.
  if (i.lr_error) {
    return {
      title: t('Sales dashboard'),
      body: t('Lumen Reports could not report its status on this site.'),
      hint: i.lr_error,
      refresh: true,
    }
  }
  const reason = lr.reason
  if (reason === 'needs_erpnext') {
    return {
      title: t('Sales dashboard'),
      body: t('The sales dashboard reads POS Invoice, which comes with ERPNext. Install ERPNext first.'),
      refresh: true,
    }
  }
  if (reason === 'needs_role' || reason === 'not_in_audience') {
    return {
      title: t('One permission away'),
      body: t(
        'The dashboard is ready. To open it, an administrator grants this user the Lumen Restricted Viewer role in Lumen Reports.',
      ),
      refresh: true,
    }
  }
  if (reason === 'not_set_up') {
    if (lr.can_create) {
      return {
        title: t('Sales dashboard'),
        body: t('Lumen Reports is installed. One step left: create the ready-made POS sales dashboard.'),
        action: t('Create the sales dashboard'),
      }
    }
    return {
      title: t('Sales dashboard'),
      body: t(
        'Lumen Reports is installed. An administrator with Lumen Builder or Lumen Manager opens this page once to create the dashboard.',
      ),
      refresh: true,
    }
  }
  // A reason this page does not know (a newer Lumen Reports may add one), or no
  // reason and still no access. Never a silent "Loading…": say it plainly and show
  // Lumen Reports' own message when it sends one.
  return {
    title: t('Sales dashboard'),
    body: t('Lumen Reports cannot show the dashboard on this site right now.'),
    hint: lr.message || null,
    refresh: true,
  }
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    info.value = await call('lumenpos.api.insights.status')
  } catch (e) {
    error.value = e.message || String(e)
  } finally {
    loading.value = false
  }
}

async function create() {
  working.value = true
  actionError.value = ''
  try {
    info.value = await call('lumenpos.api.insights.ensure_dashboard', { lang: locale.value })
  } catch (e) {
    actionError.value = e.message || String(e)
  } finally {
    working.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.insights {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow: hidden;
}
.state-card {
  margin: auto;
  max-width: 460px;
  text-align: center;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 36px 28px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.state-card h2 {
  margin: 0;
  font-size: 19px;
}
.mark {
  width: 52px;
  height: 52px;
  color: var(--brand);
  opacity: 0.85;
}
.muted {
  color: var(--muted);
  margin: 0;
  line-height: 1.55;
}
.small {
  font-size: 12.5px;
}
.neg {
  color: var(--danger, #d33);
  margin: 0;
}
.spinner {
  width: 30px;
  height: 30px;
  border: 3px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: ins-spin 0.8s linear infinite;
}
@keyframes ins-spin {
  to {
    transform: rotate(360deg);
  }
}
.board {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  background: var(--panel);
}
.board-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--border);
}
.board-title {
  font-weight: 600;
}
.small-btn {
  font-size: 12.5px;
  padding: 5px 10px;
}
.board-frame {
  flex: 1;
  width: 100%;
  border: 0;
  background: var(--bg);
}
</style>
