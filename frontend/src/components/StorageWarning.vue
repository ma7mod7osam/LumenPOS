<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div v-if="show" class="storage-warn" role="status">
    <Icon name="shield" :size="18" />
    <div class="sw-text">
      <b>{{ t('Offline sales are not protected on this device') }}</b>
      <span>{{ t('This browser may clear sales waiting to be sent when its storage runs low. Ask it to keep them.') }}</span>
      <span v-if="refused" class="sw-hint">
        {{ t('The browser said no. Install the till as an app (the install button in the address bar) or bookmark this page, then try again.') }}
      </span>
    </div>
    <div class="sw-actions">
      <button class="btn btn-primary btn-sm" :disabled="asking" @click="protect">{{ t('Protect') }}</button>
      <button class="btn btn-outline btn-sm" @click="later">{{ t('Later') }}</button>
    </div>
  </div>
</template>

<script setup>
// Working without a connection keeps the sales waiting to be sent in the
// browser's storage (offline.js). A browser that has not agreed to keep that
// storage for good may clear it when the device runs short of space, with the
// sales in it. The till asks at start (App.vue), and this says so when the
// browser did not agree, and asks again on a tap: Firefox shows its own
// question then, Chrome and Edge agree once the till is installed as an app
// or bookmarked. LumenPOS Settings.warn_unprotected_storage switches it off.
import { onMounted, ref, watch } from 'vue'
import Icon from './Icon.vue'
import { t } from '../i18n'
import { ensurePersistentStorage, storagePersisted } from '../offline'
import { useSessionStore } from '../stores/session'

const SNOOZE_KEY = 'lumenpos-storage-snooze'
const SNOOZE_MS = 24 * 3600 * 1000

const session = useSessionStore()
const show = ref(false)
const refused = ref(false)
const asking = ref(false)

function snoozed() {
  try {
    return Number(localStorage.getItem(SNOOZE_KEY) || 0) > Date.now()
  } catch {
    return false
  }
}

async function check() {
  // A browser that cannot say (no Storage API) is not warned about.
  if (!session.settings?.warn_unprotected_storage || !navigator.storage?.persisted || snoozed()) {
    show.value = false
    return
  }
  show.value = !(await storagePersisted())
}

async function protect() {
  asking.value = true
  try {
    if (await ensurePersistentStorage()) {
      show.value = false
      session.notify(t('Offline sales are protected on this device now'))
    } else {
      refused.value = true
    }
  } finally {
    asking.value = false
  }
}

function later() {
  try {
    localStorage.setItem(SNOOZE_KEY, String(Date.now() + SNOOZE_MS))
  } catch {
    /* private window: it asks again next time */
  }
  show.value = false
}

onMounted(check)
watch(() => session.settings?.warn_unprotected_storage, check)
</script>

<style scoped>
.storage-warn {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  padding: 10px 16px;
  background: rgba(245, 166, 35, 0.14);
  border-bottom: 1px solid rgba(245, 166, 35, 0.35);
  color: #7a5308;
  font-size: 13px;
}
html[data-theme='dark'] .storage-warn {
  background: rgba(245, 166, 35, 0.16);
  border-bottom-color: rgba(245, 166, 35, 0.3);
  color: #ffce85;
}
.sw-text { flex: 1; min-width: 240px; display: flex; flex-direction: column; gap: 2px; }
.sw-hint { font-weight: 600; }
.sw-actions { display: flex; gap: 8px; }
.btn-sm { padding: 6px 12px; font-size: 13px; }
</style>
