<template>
  <!-- Customer-facing display: a chrome-free second screen, no app shell and
       no bootstrap — it only listens for cart snapshots over BroadcastChannel. -->
  <router-view v-if="isDisplay" />

  <div class="shell" v-else-if="session.loaded && !session.error">
    <NavRail />
    <div class="main">
      <header class="topbar">
        <div class="topbar-title">{{ pageTitle }}</div>
        <div class="topbar-right">
          <button
            v-if="session.settings.enable_xreport && session.registerOpen"
            class="lang-pill"
            :title="t('X-report (mid-shift read)')"
            :disabled="xreportLoading"
            @click="openXReport"
          >
            <Icon name="report" /> {{ t('X-report') }}
          </button>
          <button
            v-if="session.settings.enable_till_lock"
            class="lang-pill"
            :title="t('Lock the till')"
            @click="session.lockTill()"
          >
            <Icon name="shield" /> {{ t('Lock') }}
          </button>
          <button
            class="lang-pill"
            :title="t('Language')"
            @click="toggleLocale()"
          >
            {{ locale === 'ar' ? 'English' : 'العربية' }}
          </button>
          <button v-if="session.offline" class="offline-pill" @click="session.reconnect()">
            ⚠ {{ t('Offline') }}{{ session.queuedCount ? ` — ${session.queuedCount}` : '' }}
          </button>
          <span v-else-if="session.queuedCount" class="offline-pill syncing">
            {{ t('Syncing') }} {{ session.queuedCount }}…
          </span>
          <button
            class="register-pill"
            :class="{ open: session.registerOpen }"
            :title="session.registerOpen ? t('Go to the Register page to close it') : t('Open the register')"
            @click="$router.push('/register')"
          >
            {{ session.registerOpen ? t('Register open ▸ close') : t('Register closed') }}
          </button>
          <span class="topbar-user">{{ session.userFullname }} · {{ session.posProfile }}</span>
        </div>
      </header>
      <main class="content">
        <router-view />
        <!-- The open-register prompt only blocks the Sell screen; the nav
             rail and other tabs (Register, History, Settings) stay usable. -->
        <OpenRegisterOverlay v-if="!session.registerOpen && route.path === '/'" />
      </main>
    </div>
    <div v-if="session.toast" class="toast" :class="{ error: session.toast.isError }">
      {{ session.toast.message }}
    </div>
    <LockOverlay v-if="session.locked" />
    <XReportModal v-if="xreportOpen && xreportSummary" :summary="xreportSummary" @close="xreportOpen = false" />
  </div>

  <div v-else-if="!isDisplay && session.error" class="boot-error">
    <div class="card boot-card">
      <h2>{{ t('LumenPOS could not start') }}</h2>
      <p>{{ session.error }}</p>
      <button class="btn btn-primary" @click="session.bootstrap()">{{ t('Retry') }}</button>
    </div>
  </div>

  <div v-else class="boot-loading">{{ t('Loading LumenPOS…') }}</div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { call } from './api'
import { useSessionStore } from './stores/session'
import { useCatalogStore } from './stores/catalog'
import { useCartStore } from './stores/cart'
import { money } from './format'
import { publishCart, onDisplayRequest } from './customerDisplay'
import { ensurePersistentStorage } from './offline'
import { t, locale, toggleLocale } from './i18n'
import Icon from './components/Icon.vue'
import NavRail from './components/NavRail.vue'
import OpenRegisterOverlay from './components/OpenRegisterOverlay.vue'
import LockOverlay from './components/LockOverlay.vue'
import XReportModal from './components/XReportModal.vue'

const session = useSessionStore()
const catalog = useCatalogStore()
const cart = useCartStore()
const route = useRoute()
const isDisplay = computed(() => route.path === '/display')

// X-report — reachable from the top bar all shift. Fetches a fresh read-only
// session summary on demand (no register-page visit needed).
const xreportOpen = ref(false)
const xreportSummary = ref(null)
const xreportLoading = ref(false)
async function openXReport() {
  if (!session.registerSession || xreportLoading.value) return
  xreportLoading.value = true
  try {
    xreportSummary.value = await call('lumenpos.api.register.get_session_summary', {
      session: session.registerSession.name,
    })
    xreportOpen.value = true
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    xreportLoading.value = false
  }
}

// Push a fully-formatted cart snapshot to any open customer display.
function publishDisplaySnapshot() {
  if (!session.settings?.enable_customer_display) return
  const saved =
    cart.promoSavings + cart.bundleSavings + cart.manualDiscountTotal + cart.orderDiscountTotal
  publishCart({
    company: session.company,
    logo: session.settings?.receipt_logo || '',
    customer: cart.customer?.customer_name || '',
    items: cart.lines.map((l) => ({
      name: l.item_name,
      qty: l.qty,
      rate: money(l.price),
      amount: money(l.price * l.qty),
    })),
    count: cart.itemCount,
    subtotal: money(cart.subtotal),
    total: money(cart.total),
    savings: saved > 0.005 ? money(saved) : '',
  })
}

const pageTitle = computed(
  () =>
    ({
      '/': t('Sell'),
      '/history': t('Sales History'),
      '/customers': t('Customers'),
      '/register': t('Register'),
      '/settings': t('Settings'),
    })[route.path] || t('Sell')
)

onMounted(async () => {
  // The display window is a passive mirror — no bootstrap, no catalog, no shell.
  if (isDisplay.value) return

  // Make offline storage persistent so a queued sale can't be evicted under
  // disk pressure / LRU (fire-and-forget; grant is heuristic).
  ensurePersistentStorage()
  session.watchConnection()
  await session.bootstrap()
  if (session.loaded && !session.error) {
    catalog.fetch()
    catalog.cacheFullCatalog() // background fill of the offline cache
    catalog.cacheCustomers() // recent-customers subset for offline select
    if (session.queuedCount && !session.offline) session.flushQueue()
    // Mirror the cart to any open customer display, and answer a display that
    // opens later and asks for the current state.
    cart.$subscribe(() => publishDisplaySnapshot())
    onDisplayRequest(publishDisplaySnapshot)
    watch(() => session.settings?.enable_customer_display, publishDisplaySnapshot)
    setupAutoLock()
  }
})

// Auto-lock the till after a configured idle period (0 = manual lock only).
let idleTimer = null
function setupAutoLock() {
  const reset = () => {
    clearTimeout(idleTimer)
    const mins = session.settings?.auto_lock_minutes || 0
    if (!session.settings?.enable_till_lock || mins <= 0 || session.locked) return
    idleTimer = setTimeout(() => session.lockTill(), mins * 60000)
  }
  for (const ev of ['mousemove', 'keydown', 'click', 'touchstart']) {
    window.addEventListener(ev, reset, { passive: true })
  }
  reset()
}
</script>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
}
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  height: 52px;
  background: var(--topbar-bg);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
}
.topbar-title {
  font-size: 17px;
  font-weight: 700;
}
.topbar-right {
  display: flex;
  align-items: center;
  gap: 14px;
}
.topbar-user {
  font-size: 12.5px;
  opacity: 0.75;
}
.register-pill {
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 11px;
  border-radius: 999px;
  background: rgba(226, 48, 48, 0.25);
  color: #ffb3b3;
  cursor: pointer;
}
.register-pill:hover { filter: brightness(1.2); }
.register-pill.open {
  background: rgba(20, 99, 255, 0.28);
  color: #aebfff;
}
.lang-pill {
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 11px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
  cursor: pointer;
}
.lang-pill:hover { background: rgba(255, 255, 255, 0.26); }
.offline-pill {
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 11px;
  border-radius: 999px;
  background: rgba(245, 166, 35, 0.25);
  color: #ffd591;
  cursor: pointer;
}
.offline-pill.syncing {
  background: rgba(0, 176, 185, 0.22);
  color: #8fe3e8;
  cursor: default;
}
.content {
  flex: 1;
  min-height: 0;
  display: flex;
  position: relative; /* scopes the open-register overlay to this area */
}
.boot-loading,
.boot-error {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 16px;
}
.boot-card {
  padding: 36px;
  max-width: 460px;
  text-align: center;
}
.boot-card h2 { margin-top: 0; }
.boot-card p { color: var(--text-muted); }
</style>
