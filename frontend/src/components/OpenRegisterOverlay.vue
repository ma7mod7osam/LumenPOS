<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
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
              {{ t('Session') }} <b>{{ pending.session }}</b> {{ t('was closed but its sales are still being finalised') }}<span v-if="pending.closing_status === 'Failed'">&nbsp;{{ t('and the last attempt') }} <b>{{ t('failed') }}</b></span>. {{ t('You can open a new shift now, it keeps finalising in the background.') }}
            </div>
            <div v-if="pending.closing_error" class="err-detail">{{ plainText(pending.closing_error) }}</div>
          </div>
          <PeriodHint v-if="pending.closing_hint" :hint="pending.closing_hint" />
          <button
            v-if="canClose"
            class="btn btn-outline choice-btn"
            :disabled="busy"
            @click="retry"
          >
            <Icon name="refresh" /> {{ busy ? t('Retrying…') : t('Retry closing') }}
            <span class="choice-hint">{{ t('Consolidate the previous shift now instead of waiting for the background retry') }}</span>
          </button>
          <p class="muted small">
            {{ t("This runs in the background and usually takes a few seconds. It's safe to retry as often as needed, nothing is double-posted.") }}
          </p>

          <!-- The register is closed the moment the cashier closes it, the POS
               Closing consolidation is a background task (Pending / Queued /
               Failed) that must NEVER block the next shift. So a fresh shift can
               always be opened here, whatever the closing status; the previous
               shift keeps finalising / self-healing in the background. -->
          <div v-if="canClose" class="force-new-block">
            <div class="or-sep"><span>{{ t('or open a new shift now') }}</span></div>
            <label class="field-label">{{ t('Opening float for the new shift') }}</label>
            <input
              class="float-input"
              type="text"
              inputmode="decimal"
              v-model="openingFloat"
              :disabled="busy"
            />
            <label v-for="d in foreignDrawers" :key="d.mode_of_payment" class="field-label">
              {{ t('{drawer} float ({currency})', { drawer: d.mode_of_payment, currency: d.account_currency }) }}
              <input
                class="float-input"
                type="text"
                inputmode="decimal"
                v-model="floats[d.mode_of_payment]"
                :disabled="busy"
              />
            </label>
            <button class="btn btn-primary choice-btn" :disabled="busy" @click="forceNew">
              <Icon name="play" /> {{ busy ? t('Opening…') : t('Open a new shift') }}
              <span class="choice-hint"
                >{{ t('Keep selling now, the previous shift keeps finalising in the background until it consolidates') }}</span
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
      <template v-else>
        <div class="modal-body">
          <!-- An ERPNext accounting period locks sales invoices today: the
               shift can sell, but its close would fail (0.58.1). -->
          <PeriodHint
            v-if="session.periodLock"
            :hint="session.periodLock"
            when="today"
            :invoice-mode="session.invoiceMode"
          />
          <!-- Shifts this person still holds at other outlets. A reminder, or,
               when the shop allows one open shift per person, the reason this
               one cannot open yet, with a way to get to the open one. -->
          <div v-if="others.length" class="shift-banner warn oe-warn" :class="{ 'oe-block': oneShiftBlocked }">
            <div>
              <Icon name="warning" />
              {{
                oneShiftBlocked
                  ? t('Close your open shift first')
                  : others.length > 1
                    ? t('You still have {n} other registers open:', { n: others.length })
                    : t('You still have another register open:')
              }}
            </div>
            <div v-for="r in others" :key="r.session" class="oe-item">
              {{ r.pos_profile }} <span class="oe-sess">({{ r.session }})</span>
              <button
                v-if="r.reachable !== false && session.availableProfiles.includes(r.pos_profile)"
                type="button"
                class="oe-go"
                :disabled="busy"
                @click="goClose(r.pos_profile)"
              >
                {{ t('Go to its Register page') }}
              </button>
              <span v-else class="oe-ask">{{ t('Not open to you any more: ask a manager to close it.') }}</span>
            </div>
            <div v-if="oneShiftBlocked || anyReachable" class="choice-hint">
              {{
                oneShiftBlocked
                  ? t('This shop allows one open shift per person at a time. Close it, then open this one.')
                  : others.length > 1
                    ? t('Remember to close each one when its shift ends.')
                    : t('Remember to close it when its shift ends.')
              }}
            </div>
            <div v-if="oneShiftBlocked" class="choice-hint">
              {{ t("If you cannot close it, a manager can close it for you from that outlet's Register page.") }}
            </div>
          </div>
          <template v-if="session.availableProfiles.length > 1">
            <label class="field-label">{{ t('Outlet') }}</label>
            <select
              class="outlet-select"
              :value="session.posProfile"
              :disabled="busy"
              @change="onSwitchOutlet($event.target.value)"
            >
              <option v-for="p in session.availableProfiles" :key="p" :value="p">{{ session.outletLabel(p) }}</option>
            </select>
            <p class="muted" style="margin-top: 12px">
              {{ t('Enter the opening cash float to start selling.') }}
            </p>
          </template>
          <p v-else class="muted">
            {{ session.posProfile }}. {{ t('Enter the opening cash float to start selling.') }}
          </p>
          <label class="field-label">{{ t('Opening float') }}</label>
          <input
            ref="floatInput"
            type="text"
            inputmode="decimal"
            v-model="openingFloat"
            style="width: 100%"
            :disabled="!canOpen || oneShiftBlocked"
            @keydown.enter="open"
          />
          <!-- A drawer in another currency (Settings, General, Other
               currencies) starts with its own float, in its own money. -->
          <label v-for="d in foreignDrawers" :key="d.mode_of_payment" class="field-label">
            {{ t('{drawer} float ({currency})', { drawer: d.mode_of_payment, currency: d.account_currency }) }}
            <input
              type="text"
              inputmode="decimal"
              v-model="floats[d.mode_of_payment]"
              style="width: 100%"
              :disabled="!canOpen"
              @keydown.enter="open"
            />
          </label>
        </div>
        <div class="modal-footer">
          <button
            class="btn btn-primary btn-lg"
            style="width: 100%"
            :disabled="busy || !canOpen || oneShiftBlocked"
            @click="open"
          >
            {{ busy ? t('Opening…') : t('Open Register') }}
          </button>
          <p v-if="!canOpen" class="muted small dead-end" style="text-align: center">
            {{ t("You don't have permission to open a register.") }}
          </p>
        </div>
      </template>

    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useSessionStore } from '../stores/session'
import { useCatalogStore } from '../stores/catalog'
import { call } from '../api'
import { t } from '../i18n'
import { parseMoney, plainText } from '../format'
import PeriodHint from './PeriodHint.vue'

const session = useSessionStore()
const catalog = useCatalogStore()
const openingFloat = ref('0')
const busy = ref(false)
const floatInput = ref(null)
const pending = ref(session.pendingClosing)
let poll = null

// Cash drawers in another currency ("Cash USD"): each counts its own money.
// None while selling in other currencies is off, though the drawers stay on
// the outlet (the server ignores such a float too).
const foreignDrawers = computed(() =>
  session.multiCurrency?.enabled
    ? (session.paymentModes || []).filter(
        (m) => m.type === 'Cash' && m.account_currency && m.account_currency !== session.localCurrency
      )
    : []
)
const floats = ref({})

// {drawer: amount} for the drawers in another currency, as the server takes it.
function foreignFloats() {
  const out = {}
  for (const d of foreignDrawers.value) {
    const value = parseMoney(floats.value[d.mode_of_payment])
    if (value && value > 0) out[d.mode_of_payment] = value
  }
  return JSON.stringify(out)
}

const canOpen = computed(() => session.permissions.open_register !== false)

// Shifts this person still holds at other outlets, and whether the shop's
// "one open shift per person" setting stops this one until they are closed
// (the server refuses it too, lumenpos.api.register).
const router = useRouter()
const others = computed(() => session.otherOpenRegisters || [])
// Only a shift this person can still reach blocks; one at an outlet they
// cannot reach any more is for a manager, and never locks them out.
const anyReachable = computed(() => others.value.some((r) => r.reachable !== false))
const oneShiftBlocked = computed(() => !!session.settings?.one_shift_per_user && anyReachable.value)
async function goClose(profile) {
  await onSwitchOutlet(profile)
  router.push('/register')
}
const canClose = computed(() => session.permissions.close_register !== false)

onMounted(() => {
  if (!pending.value) floatInput.value?.focus()
})
onBeforeUnmount(() => clearInterval(poll))

// Choose which outlet to open the register for (users assigned to more than one
// POS Profile). Switching reloads that outlet, if it's already open the dialog
// closes and you're selling on it; if closed, the dialog now opens that outlet.
async function onSwitchOutlet(name) {
  if (!name || name === session.posProfile) return
  await session.switchProfile(name)
  catalog.fetch()
  catalog.cacheFullCatalog()
  catalog.cacheCustomers()
  pending.value = session.pendingClosing
  openingFloat.value = '0'
  floats.value = {}
}

async function open() {
  busy.value = true
  try {
    // Opening is always a fresh shift, there is no resume/retry branch.
    await session.openRegister(openingFloat.value || 0, { floats: foreignFloats() })
    session.notify(t('Register opened'))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}

async function forceNew() {
  busy.value = true
  try {
    await session.openRegister(openingFloat.value || 0, { floats: foreignFloats() })
    session.notify(t('New shift opened, the previous one keeps finalising in the background'))
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
        session.notify(t('Previous shift closed, you can open the register now'))
        await session.bootstrap(session.posProfile)
        pending.value = session.pendingClosing
        busy.value = false
      } else if (res.closing_status === 'Failed') {
        clearInterval(poll)
        pending.value = { ...pending.value, closing_status: 'Failed', closing_error: res.closing_error, closing_hint: res.closing_hint }
        session.notify(t('Closing failed again. Check the error and retry'), true)
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
.oe-item { display: flex; align-items: center; flex-wrap: wrap; gap: 6px 8px; }
.oe-go {
  margin-inline-start: auto;
  font-size: 12px;
  font-weight: 700;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.08);
  border: 1px solid rgba(20, 99, 255, 0.3);
  border-radius: 999px;
  padding: 3px 10px;
  cursor: pointer;
}
html[data-theme='dark'] .oe-go { color: #9fc0ff; background: rgba(47, 123, 255, 0.16); }
.oe-block { border-color: var(--red); }
.oe-ask { flex-basis: 100%; font-size: 12px; font-weight: 600; opacity: 0.85; }
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
