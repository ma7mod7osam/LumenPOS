<template>
  <nav class="rail">
    <div class="logo">
      <svg viewBox="0 0 100 100" width="32" height="32" aria-label="LumenPOS">
        <defs><linearGradient id="lp-logo" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2A7BFF"/><stop offset="1" stop-color="#0B43B8"/></linearGradient></defs>
        <rect width="100" height="100" rx="22" fill="url(#lp-logo)"/>
        <g transform="translate(30,30) scale(0.833)">
          <rect x="6" y="6" width="7.5" height="38" rx="3.75" fill="#fff"/>
          <rect x="18" y="25" width="4.5" height="19" rx="2.25" fill="rgba(255,255,255,.62)"/>
          <rect x="27" y="25" width="7.5" height="19" rx="3.75" fill="#fff"/>
          <rect x="39" y="25" width="4.5" height="19" rx="2.25" fill="#fff"/>
        </g>
      </svg>
    </div>
    <router-link to="/" class="rail-item" exact-active-class="active">
      <svg viewBox="0 0 24 24"><path d="M7 18a2 2 0 1 0 0 4 2 2 0 0 0 0-4zm10 0a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM3 2h2.5l3.1 11.6A2 2 0 0 0 10.5 15h8.2a2 2 0 0 0 1.9-1.4L23 6H6.1" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>{{ t('Sell') }}</span>
    </router-link>
    <router-link v-if="session.permissions.view_history !== false" to="/history" class="rail-item" active-class="active">
      <svg viewBox="0 0 24 24"><path d="M12 8v5l3.5 2M21 12a9 9 0 1 1-9-9 9 9 0 0 1 9 9z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>{{ t('History') }}</span>
    </router-link>
    <router-link v-if="session.permissions.customers" to="/customers" class="rail-item" active-class="active">
      <svg viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>{{ t('Customers') }}</span>
    </router-link>
    <router-link to="/register" class="rail-item" active-class="active">
      <svg viewBox="0 0 24 24"><path d="M3 9h18v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9zm3-5h12l2 5H4l2-5zm5 9h2" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>{{ t('Register') }}</span>
    </router-link>
    <button
      v-if="session.canApprove"
      type="button"
      class="rail-item"
      :class="{ active: approvalsOpen }"
      @click="approvalsOpen = true"
    >
      <span class="icon-wrap">
        <svg viewBox="0 0 24 24"><path d="M9 12l2 2 4-4M21 12a9 9 0 1 1-9-9 9 9 0 0 1 9 9z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span v-if="pendingCount" class="badge">{{ pendingCount }}</span>
      </span>
      <span>{{ t('Approvals') }}</span>
    </button>
    <router-link v-if="session.canManageAny" to="/settings" class="rail-item" active-class="active">
      <svg viewBox="0 0 24 24"><path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>{{ t('Settings') }}</span>
    </router-link>
    <button class="rail-item rail-bottom" type="button" @click="toggleTheme" :title="theme === 'dark' ? t('Switch to light mode') : t('Switch to dark mode')">
      <svg v-if="theme === 'dark'" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
      <svg v-else viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
      <span>{{ theme === 'dark' ? t('Light') : t('Dark') }}</span>
    </button>
    <a class="rail-item" href="/app" :title="t('Back to ERPNext')">
      <svg viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span>{{ t('ERP') }}</span>
    </a>
  </nav>
  <ApprovalsModal v-if="approvalsOpen" @close="onApprovalsClose" @changed="refreshPending" />
</template>

<script setup>
import { theme, toggleTheme } from '../theme'
import { ref, onMounted, onUnmounted } from 'vue'
import { useSessionStore } from '../stores/session'
import { call } from '../api'
import { t } from '../i18n'
import ApprovalsModal from './ApprovalsModal.vue'

const session = useSessionStore()
const approvalsOpen = ref(false)
const pendingCount = ref(0)
let timer = null

async function refreshPending() {
  if (!session.canApprove || session.offline) {
    pendingCount.value = 0
    return
  }
  try {
    // No profile scoping — an approver sees every open-shift request they can
    // act on, even when their till is on a different POS profile than the cashier.
    const rows = await call('lumenpos.api.approval_requests.pending_requests', {})
    pendingCount.value = rows.length
  } catch {
    /* ignore — the badge is best-effort */
  }
}

function onApprovalsClose() {
  approvalsOpen.value = false
  refreshPending()
}

onMounted(() => {
  if (!session.canApprove) return
  refreshPending()
  timer = setInterval(refreshPending, 10000)
  window.addEventListener('focus', refreshPending)
})
onUnmounted(() => {
  clearInterval(timer)
  window.removeEventListener('focus', refreshPending)
})
</script>

<style scoped>
.rail {
  width: 76px;
  background: var(--nav-bg);
  display: flex;
  flex-direction: column;
  align-items: stretch;
  padding-bottom: 10px;
  flex-shrink: 0;
}
.logo {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.logo svg { display: block; }
.rail-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 14px 0;
  color: #98a1b3;
  text-decoration: none;
  font-size: 11px;
  font-weight: 600;
  border-left: 3px solid transparent;
}
.rail-item svg {
  width: 22px;
  height: 22px;
}
.rail-item:hover { color: #fff; }
.rail-item.active {
  color: #fff;
  background: var(--nav-active);
  border-left-color: var(--brand);
}
.rail-bottom { margin-top: auto; }
.icon-wrap { position: relative; display: inline-flex; }
.badge {
  position: absolute;
  top: -6px;
  right: -9px;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--red);
  color: #fff;
  font-size: 10px;
  font-weight: 800;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
}
</style>
