<template>
  <div class="open-backdrop">
    <div class="modal" style="width: 460px">
      <div class="modal-header">{{ t('Open register') }}</div>

      <!-- A previous shift's closing hasn't finished (or failed): must be
           resolved before anyone can open or sell again. -->
      <template v-if="pending">
        <div class="modal-body">
          <div class="shift-banner warn">
            <div class="shift-name">{{ t('⚠ Previous shift not finished') }}</div>
            <div class="muted small" style="margin-top: 4px">
              {{ t('Session') }} <b>{{ pending.session }}</b> {{ t('was closed but its sales are still being finalised') }}<span v-if="pending.closing_status === 'Failed'"> {{ t('— the last attempt') }} <b>{{ t('failed') }}</b></span>. {{ t('You can open a new shift now — it keeps finalising in the background.') }}
            </div>
            <div v-if="pending.closing_error" class="err-detail">{{ pending.closing_error }}</div>
          </div>
          <button
            v-if="canClose"
            class="btn btn-outline choice-btn"
            :disabled="busy"
            @click="retry"
          >
            <Icon name="refresh" /> {{ busy ? t('Retrying…') : t('Retry closing') }}
            <span class="choice-hint">{{ t('consolidate the previous shift now instead of waiting for the background retry') }}</span>
          </button>
          <p class="muted small">
            {{ t("This runs in the background and usually takes a few seconds. It's safe to retry as often as needed — nothing is double-posted.") }}
          </p>

          <!-- The register is closed the moment the cashier closes it — the POS
               Closing consolidation is a background task (Pending / Queued /
               Failed) that must NEVER block the next shift. So a fresh shift can
               always be opened here, whatever the closing status; the previous
               shift keeps finalising / self-healing in the background. -->
          <div v-if="canClose" class="force-new-block">
            <div class="or-sep"><span>{{ t('or open a new shift now') }}</span></div>
            <label class="field-label">{{ t('Opening float for the new shift') }}</label>
            <input
              class="float-input"
              type="number"
              inputmode="decimal"
              min="0"
              step="0.01"
              v-model.number="openingFloat"
              :disabled="busy"
            />
            <button class="btn btn-primary choice-btn" :disabled="busy" @click="forceNew">
              <Icon name="play" /> {{ busy ? t('Opening…') : t('Open a new shift') }}
              <span class="choice-hint"
                >{{ t('keep selling now — the previous shift keeps finalising in the background until it consolidates') }}</span
              >
            </button>
          </div>

          <p v-if="!canClose" class="muted small dead-end">
            {{ t("You don't have permission to close registers. Ask a manager to retry the closing of") }} {{ pending.session }}.
          </p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" style="width: 100%" @click="$router.push('/register')">
            {{ t('Open the Register page') }}
          </button>
        </div>
      </template>

      <!-- Step 1: float entry -->
      <template v-else-if="!choice">
        <div class="modal-body">
          <div v-if="session.otherOpenRegisters.length" class="shift-banner warn oe-warn">
            <div><Icon name="warning" /> {{ t('You still have another register open:') }}</div>
            <div v-for="r in session.otherOpenRegisters" :key="r.session" class="oe-item">
              {{ r.pos_profile }} <span class="oe-sess">({{ r.session }})</span>
            </div>
            <div class="choice-hint">{{ t('Remember to close it when its shift ends.') }}</div>
          </div>
          <template v-if="session.availableProfiles.length > 1">
            <label class="field-label">{{ t('Outlet') }}</label>
            <select
              class="outlet-select"
              :value="session.posProfile"
              :disabled="busy"
              @change="onSwitchOutlet($event.target.value)"
            >
              <option v-for="p in session.availableProfiles" :key="p" :value="p">{{ p }}</option>
            </select>
            <p class="muted" style="margin-top: 12px">
              {{ t('Enter the opening cash float to start selling.') }}
            </p>
          </template>
          <p v-else class="muted">
            {{ session.posProfile }} {{ t('— enter the opening cash float to start selling.') }}
          </p>
          <label class="field-label">{{ t('Opening float') }}</label>
          <input
            ref="floatInput"
            type="number"
            min="0"
            step="0.01"
            v-model.number="openingFloat"
            style="width: 100%"
            :disabled="!canOpen"
            @keydown.enter="open"
          />
        </div>
        <div class="modal-footer">
          <button
            class="btn btn-primary btn-lg"
            style="width: 100%"
            :disabled="busy || !canOpen"
            @click="open"
          >
            {{ busy ? t('Opening…') : t('Open Register') }}
          </button>
          <p v-if="!canOpen" class="muted small dead-end" style="text-align: center">
            {{ t("You don't have permission to open a register.") }}
          </p>
        </div>
      </template>

      <!-- Step 2: an orphan open shift exists — let the cashier decide -->
      <template v-else>
        <div class="modal-body">
          <div class="shift-banner">
            {{ t('You already have an open shift:') }}
            <div class="shift-name">{{ choice.name }}</div>
            <div class="muted small">
              {{ choice.pos_profile }} · {{ t('since') }} {{ choice.period_start_date }}
            </div>
          </div>

          <button
            v-if="choice.same_profile"
            class="btn btn-primary choice-btn"
            :disabled="busy"
            @click="resume"
          >
            <Icon name="play" /> {{ t('Continue that shift') }}
            <span class="choice-hint">{{ t('keep selling on the existing opening entry') }}</span>
          </button>

          <button
            v-if="choice.can_force_new"
            class="btn btn-outline choice-btn"
            :disabled="busy"
            @click="forceNew"
          >
            {{ t('+ Open a new register anyway') }}
            <span class="choice-hint">{{ t('testing mode — leaves the old shift open') }}</span>
          </button>

          <p v-if="!choice.same_profile && !choice.can_force_new" class="muted small dead-end">
            {{ t('That shift is on a different register') }} ({{ choice.pos_profile }}). {{ t('Close it there, or cancel the entry from the ERPNext desk (POS Opening Entry list). To allow opening anyway, enable it in Settings → General.') }}
          </p>
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" style="width: 100%" @click="choice = null">
            {{ t('‹ Back') }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSessionStore } from '../stores/session'
import { useCatalogStore } from '../stores/catalog'
import { call } from '../api'
import { t } from '../i18n'

const session = useSessionStore()
const catalog = useCatalogStore()
const openingFloat = ref(0)
const busy = ref(false)
const floatInput = ref(null)
const choice = ref(null)
const pending = ref(session.pendingClosing)
let poll = null

const canOpen = computed(() => session.permissions.open_register !== false)
const canClose = computed(() => session.permissions.close_register !== false)

onMounted(() => {
  if (!pending.value) floatInput.value?.focus()
})
onBeforeUnmount(() => clearInterval(poll))

// Choose which outlet to open the register for (users assigned to more than one
// POS Profile). Switching reloads that outlet — if it's already open the dialog
// closes and you're selling on it; if closed, the dialog now opens that outlet.
async function onSwitchOutlet(name) {
  if (!name || name === session.posProfile) return
  await session.switchProfile(name)
  catalog.fetch()
  catalog.cacheFullCatalog()
  catalog.cacheCustomers()
  pending.value = session.pendingClosing
  choice.value = null
  openingFloat.value = 0
}

async function open() {
  busy.value = true
  try {
    const result = await session.openRegister(openingFloat.value || 0)
    if (result?.requires_retry) {
      pending.value = result
      pending.value.session = result.session
      return
    }
    if (result?.requires_choice) {
      choice.value = result.open_entry
      return
    }
    session.notify(t('Register opened'))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function resume() {
  busy.value = true
  try {
    const result = await session.openRegister(0, { resume_opening_entry: choice.value.name })
    if (result?.requires_retry) {
      pending.value = result
      return
    }
    session.notify(t('Shift {name} resumed', { name: choice.value.name }))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function forceNew() {
  busy.value = true
  try {
    const result = await session.openRegister(openingFloat.value || 0, { force_new: 1 })
    if (result?.requires_choice || result?.requires_retry) {
      session.notify(t('Could not open a new register'), true)
      return
    }
    session.notify(t('New shift opened — the previous one keeps finalising in the background'))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function retry() {
  busy.value = true
  try {
    await call('lumenpos.api.register.retry_closing', { session: pending.value.session })
    session.notify(t('Finalising the previous shift…'))
    startPoll(pending.value.session)
  } catch (e) {
    session.notify(e.message, true)
    busy.value = false
  }
}

function startPoll(sessionName) {
  clearInterval(poll)
  let tries = 0
  poll = setInterval(async () => {
    tries += 1
    try {
      const res = await call('lumenpos.api.register.closing_entry_status', { session: sessionName })
      if (res.status === 'Closed') {
        clearInterval(poll)
        session.notify(t('Previous shift closed — you can open the register now'))
        await session.bootstrap(session.posProfile)
        pending.value = session.pendingClosing
        busy.value = false
      } else if (res.closing_status === 'Failed') {
        clearInterval(poll)
        pending.value = { ...pending.value, closing_status: 'Failed', closing_error: res.closing_error }
        session.notify(t('Closing failed again — check the error and retry'), true)
        busy.value = false
      }
    } catch {
      /* keep polling */
    }
    if (tries >= 40) {
      clearInterval(poll)
      busy.value = false
    }
  }, 3000)
}
</script>

<style scoped>
/* Covers only the content area (not the nav rail) so the cashier can still
   reach Register, History and Settings while the register is closed. */
.open-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(24, 30, 44, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 30;
}
.field-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  margin: 10px 0 6px;
}
.shift-banner {
  background: rgba(245, 166, 35, 0.12);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 14px;
  font-weight: 600;
}
.shift-banner.warn { background: rgba(226, 48, 48, 0.12); }
.shift-name {
  font-size: 16px;
  font-weight: 800;
  margin-top: 4px;
}
.err-detail {
  margin-top: 8px;
  font-size: 11.5px;
  font-weight: 500;
  color: var(--red);
  font-family: ui-monospace, monospace;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 90px;
  overflow-y: auto;
}
.small { font-size: 12px; }
.choice-btn {
  width: 100%;
  flex-direction: column;
  gap: 2px;
  padding: 14px;
  margin-bottom: 10px;
}
.choice-hint {
  font-size: 11.5px;
  font-weight: 500;
  opacity: 0.8;
}
.dead-end { margin: 4px 0 0; }
.force-new-block { margin-top: 6px; }
.float-input { width: 100%; }
.oe-warn { text-align: start; }
.oe-item { font-weight: 800; margin-top: 4px; }
.oe-sess { font-weight: 500; opacity: 0.7; font-size: 12px; }
.outlet-select {
  width: 100%;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}
.or-sep {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 6px;
  color: var(--text-muted);
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.or-sep::before,
.or-sep::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}
</style>
