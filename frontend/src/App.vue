<template>
  <div class="shell" v-if="session.loaded && !session.error">
    <NavRail />
    <div class="main">
      <header class="topbar">
        <div class="topbar-title">{{ pageTitle }}</div>
        <div class="topbar-right">
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
  </div>

  <div v-else-if="session.error" class="boot-error">
    <div class="card boot-card">
      <h2>{{ t('LumenPOS could not start') }}</h2>
      <p>{{ session.error }}</p>
      <button class="btn btn-primary" @click="session.bootstrap()">{{ t('Retry') }}</button>
    </div>
  </div>

  <div v-else class="boot-loading">{{ t('Loading LumenPOS…') }}</div>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useSessionStore } from './stores/session'
import { useCatalogStore } from './stores/catalog'
import { t, locale, toggleLocale } from './i18n'
import NavRail from './components/NavRail.vue'
import OpenRegisterOverlay from './components/OpenRegisterOverlay.vue'

const session = useSessionStore()
const catalog = useCatalogStore()
const route = useRoute()

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
  session.watchConnection()
  await session.bootstrap()
  if (session.loaded && !session.error) {
    catalog.fetch()
    catalog.cacheFullCatalog() // background fill of the offline cache
    if (session.queuedCount && !session.offline) session.flushQueue()
  }
})
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
  background: rgba(46, 91, 255, 0.28);
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
