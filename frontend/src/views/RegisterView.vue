<template>
  <div class="register">
    <!-- A shift that was closed but whose consolidation is still finishing or
         failed. Until it reaches Closed, the register stays locked. -->
    <div v-if="pending && !closedResult" class="card panel">
      <div class="panel-head">{{ t('Previous shift not finished') }}</div>
      <div class="panel-body">
        <p>
          {{ t('Session') }} <b>{{ pending.session }}</b> {{ t('was closed but its sales are still being consolidated') }}<span v-if="pending.closing_status === 'Failed'"> {{ t('— the last attempt') }}
          <b class="neg">{{ t('failed') }}</b></span>.
        </p>
        <pre v-if="pending.closing_error" class="err-detail">{{ pending.closing_error }}</pre>
        <button
          v-if="session.permissions.close_register !== false"
          class="btn btn-primary"
          :disabled="retrying === pending.session"
          @click="retryClosing(pending.session, true)"
        >
          <Icon name="refresh" /> {{ retrying === pending.session ? t('Finalising…') : t('Retry closing') }}
        </button>
        <p class="muted small" style="margin-top: 8px">
          {{ t('Safe to retry as often as needed — ERPNext rolls a failed attempt back fully, so nothing is ever double-posted.') }}
        </p>

        <!-- Closing keeps FAILING — let the store keep trading. Opens a fresh shift
             now; the failed one stays in the background and keeps retrying. -->
        <div
          v-if="pending.closing_status === 'Failed' && session.permissions.close_register !== false"
          class="force-new-block"
        >
          <div class="or-sep"><span>{{ t('or start a new shift anyway') }}</span></div>
          <label class="field-label">{{ t('Opening float for the new shift') }}</label>
          <input
            type="number"
            min="0"
            step="0.01"
            v-model.number="openFloat"
            style="width: 200px"
            :disabled="opening"
          />
          <div style="margin-top: 10px">
            <button class="btn btn-outline" :disabled="opening" @click="openRegister(null, true)">
              <Icon name="play" /> {{ opening ? t('Opening…') : t('Start a new shift anyway') }}
            </button>
          </div>
          <p class="muted small" style="margin-top: 8px">
            {{ t('Keep selling now — the failed shift stays in the background and keeps retrying until its invoices consolidate.') }}
          </p>
        </div>
      </div>
    </div>

    <div v-if="closedResult" class="card panel">
      <div class="panel-head">
        <span v-if="closeState.status === 'Closed'">{{ t('Register closed ✓') }}</span>
        <span v-else-if="closeState.closing_status === 'Failed'">{{ t('Closing needs attention') }}</span>
        <span v-else>{{ t('Closing…') }}</span>
      </div>
      <div class="panel-body">
        <p>
          {{ t('Session') }} <b>{{ closedResult.name }}</b>
          <template v-if="closeState.status === 'Closed'">
            {{ t('closed.') }}
            <template v-if="closeState.pos_closing_entry">
              {{ t('POS Closing Entry') }}
              <a :href="`/app/pos-closing-entry/${closeState.pos_closing_entry}`" target="_blank" class="entry-link">
                {{ closeState.pos_closing_entry }}
              </a>
              {{ t('— invoices consolidated.') }}
            </template>
          </template>
          <template v-else-if="closeState.closing_status === 'Failed'">
            <span class="neg">{{ t('— consolidation failed.') }}</span> {{ t('The shift is safely closed (no more sales) but its invoices still need to post. Retry below.') }}
          </template>
          <template v-else>
            <span class="muted"><Icon name="hourglass" /> {{ t('Consolidating invoices in the background… this usually takes a few seconds.') }}</span>
          </template>
        </p>
        <pre v-if="closeState.closing_error" class="err-detail">{{ closeState.closing_error }}</pre>
        <button
          v-if="closeState.closing_status === 'Failed' && session.permissions.close_register !== false"
          class="btn btn-primary"
          :disabled="retrying === closedResult.name"
          @click="retryClosing(closedResult.name)"
        >
          <Icon name="refresh" /> {{ retrying === closedResult.name ? t('Retrying…') : t('Retry closing') }}
        </button>
        <table class="count-table">
          <thead>
            <tr><th>{{ t('Payment') }}</th><th class="right">{{ t('Expected') }}</th><th class="right">{{ t('Counted') }}</th><th class="right">{{ t('Difference') }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in closedResult.counts" :key="row.mode_of_payment">
              <td>{{ row.mode_of_payment }}</td>
              <td class="right">{{ money(row.expected_amount) }}</td>
              <td class="right">{{ money(row.counted_amount) }}</td>
              <td class="right" :class="row.difference < -0.005 ? 'neg' : row.difference > 0.005 ? 'pos' : ''">
                {{ money(row.difference) }}
              </td>
            </tr>
          </tbody>
        </table>
        <button class="btn btn-outline" style="margin-top: 12px" @click="dismissClosed">{{ t('Done') }}</button>
      </div>
    </div>

    <div v-if="!session.registerOpen && !closedResult && !pending" class="card panel">
      <div class="panel-head">{{ t('Open register') }}</div>
      <div class="panel-body">
        <p class="muted">{{ session.posProfile }} {{ t('— enter the opening cash float to start selling.') }}</p>
        <label class="field-label">{{ t('Opening float') }}</label>
        <input type="number" min="0" step="0.01" v-model.number="openFloat" style="width: 200px" :disabled="!canOpen" @keydown.enter="openRegister()" />
        <div v-if="openChoice" class="open-choice">
          <div class="muted small" style="margin-bottom: 8px">
            {{ t('You already have an open shift:') }} <b>{{ openChoice.name }}</b> ({{ openChoice.pos_profile }}, {{ t('since') }} {{ openChoice.period_start_date }}).
          </div>
          <button v-if="openChoice.same_profile" class="btn btn-primary" :disabled="opening" @click="openRegister(openChoice.name)"><Icon name="play" /> {{ t('Continue that shift') }}</button>
          <button v-if="openChoice.can_force_new" class="btn btn-outline" :disabled="opening" @click="openRegister(null, true)">{{ t('+ Open a new register anyway') }}</button>
        </div>
        <div style="margin-top: 14px">
          <button class="btn btn-primary btn-lg" :disabled="opening || !canOpen" @click="openRegister()">
            {{ opening ? t('Opening…') : t('Open Register') }}
          </button>
          <p v-if="!canOpen" class="muted small">{{ t("You don't have permission to open a register.") }}</p>
        </div>
      </div>
    </div>

    <template v-if="session.registerOpen">
      <div class="card panel">
        <div class="panel-head">{{ t('Session') }} {{ session.registerSession.name }}</div>
        <div class="panel-body" v-if="summary">
          <div class="stat-row">
            <div class="stat">
              <div class="stat-label">{{ t('Sales') }}</div>
              <div class="stat-value">{{ summary.sales_count }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">{{ t('Takings') }}</div>
              <div class="stat-value">{{ money(summary.total_sales) }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">{{ t('Discounts given') }}</div>
              <div class="stat-value">{{ money(summary.total_discounts) }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">{{ t('Opening float') }}</div>
              <div class="stat-value">{{ money(summary.opening_float) }}</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card panel">
        <div class="panel-head">{{ t('Cash in / out') }}</div>
        <div class="panel-body">
          <div class="cash-form">
            <select v-model="movement.movement_type">
              <option value="Cash In">{{ t('Cash In') }}</option>
              <option value="Cash Out">{{ t('Cash Out') }}</option>
            </select>
            <input type="number" min="0" step="0.01" v-model.number="movement.amount" :placeholder="t('Amount')" />
            <input v-model="movement.reason" :placeholder="t('Reason')" />
            <button class="btn btn-outline" :disabled="!movement.amount" @click="addMovement">{{ t('Add') }}</button>
          </div>
          <div v-for="(m, i) in summary?.cash_movements || []" :key="i" class="movement-row">
            <span :class="m.movement_type === 'Cash In' ? 'in' : 'out'">{{ m.movement_type }}</span>
            <span class="muted">{{ m.reason }}</span>
            <span class="right">{{ money(m.amount) }}</span>
          </div>
        </div>
      </div>

      <div class="card panel">
        <div class="panel-head">
          {{ t('Close register') }}
          <button v-if="!loadingSummary" class="btn btn-outline" @click="load"><Icon name="refresh" /> {{ t('Refresh') }}</button>
        </div>
        <div class="panel-body" v-if="loadingSummary">
          <p class="muted">{{ t('Loading session summary…') }}</p>
        </div>
        <div class="panel-body" v-else>
          <div v-if="loadError" class="summary-error">
            {{ t('⚠ Couldn\'t load the expected takings') }} ({{ loadError }}). {{ t('You can still close the register — enter the counted amounts below.') }}
          </div>
          <p class="muted small" style="margin: 0 0 10px">
            {{ t('Need to fix a wrong payment method? Do the return + corrected sale') }}
            <b>{{ t('before') }}</b> {{ t("closing — they're picked up automatically. Once you close, the shift can't be sold on again.") }}
          </p>
          <table class="count-table">
            <thead>
              <tr><th>{{ t('Payment') }}</th><th class="right">{{ t('Expected') }}</th><th class="right">{{ t('Counted') }}</th><th class="right">{{ t('Difference') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in countRows" :key="row.mode_of_payment">
                <td>{{ row.mode_of_payment }}</td>
                <td class="right">{{ row.expected_amount != null ? money(row.expected_amount) : '—' }}</td>
                <td class="right">
                  <input
                    type="number"
                    step="0.01"
                    class="count-input"
                    v-model.number="counted[row.mode_of_payment]"
                  />
                </td>
                <td class="right" :class="diffClass(row)">{{ money(diff(row)) }}</td>
              </tr>
              <tr v-if="!countRows.length">
                <td colspan="4" class="muted" style="text-align: center; padding: 14px">
                  {{ t('No takings recorded this session.') }}
                </td>
              </tr>
            </tbody>
          </table>
          <input v-model="closingNote" :placeholder="t('Closing note (optional)')" style="width: 100%; margin-top: 12px" />
          <button class="btn btn-danger btn-lg" style="width: 100%; margin-top: 14px" :disabled="closing || !canClose" @click="close">
            {{ closing ? t('Closing…') : t('Close Register') }}
          </button>
          <p v-if="!canClose" class="muted small">{{ t("You don't have permission to close the register.") }}</p>
        </div>
      </div>
    </template>

    <!-- Previous sessions (Z-report history, linked to ERPNext entries) -->
    <div class="card panel" v-if="!session.offline">
      <div class="panel-head">
        {{ t('Previous sessions') }}
        <button class="btn btn-outline" @click="loadHistory"><Icon name="refresh" /></button>
      </div>
      <div v-if="!history.length" class="muted empty-sm">{{ t('No closed sessions yet') }}</div>
      <div v-for="past in history" :key="past.name" class="session-row">
        <div class="session-info">
          <div class="session-title">
            {{ past.name }}
            <span class="muted small">· {{ shortTime(past.opened_at) }} → {{ shortTime(past.closed_at) }} · {{ past.opened_by }}</span>
            <span v-if="past.status === 'Closing'" class="pill-warn">
              {{ past.closing_status === 'Failed' ? t('closing failed') : t('finalising') }}
            </span>
          </div>
          <div class="muted small">
            {{ past.sales_count }} {{ t('sales') }} · {{ t('takings') }} {{ money(past.total_sales) }} ·
            {{ t('discounts') }} {{ money(past.total_discounts) }} ·
            <span :class="past.total_difference < -0.005 ? 'neg' : past.total_difference > 0.005 ? 'pos' : ''">
              {{ t('difference') }} {{ money(past.total_difference) }}
            </span>
          </div>
          <div class="muted small">
            <a v-if="past.pos_opening_entry" :href="`/app/pos-opening-entry/${past.pos_opening_entry}`" target="_blank" class="entry-link">
              {{ past.pos_opening_entry }}
            </a>
            <template v-if="past.pos_closing_entry && past.status === 'Closed'">
              →
              <a :href="`/app/pos-closing-entry/${past.pos_closing_entry}`" target="_blank" class="entry-link">
                {{ past.pos_closing_entry }}
              </a>
            </template>
            <button
              v-else-if="past.status === 'Closing' && session.permissions.close_register !== false"
              class="btn btn-outline retry-closing"
              :disabled="retrying === past.name"
              @click="retryClosing(past.name)"
            >
              <Icon name="refresh" /> {{ retrying === past.name ? t('Finalising…') : t('Retry closing') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from '../components/Icon.vue'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money, shortTime } from '../format'
import { t } from '../i18n'

const session = useSessionStore()
const summary = ref(null)
const counted = ref({})
const closingNote = ref('')
const closing = ref(false)
const movement = ref({ movement_type: 'Cash In', amount: null, reason: '' })
const history = ref([])
const closedResult = ref(null)
const closeState = ref({ status: 'Closing', closing_status: 'Pending', pos_closing_entry: null, closing_error: null })
const retrying = ref(null)
const pending = ref(session.pendingClosing)
let closingPoll = null

const canOpen = computed(() => session.permissions.open_register !== false)
const canClose = computed(() => session.permissions.close_register !== false)

// --- open register from this page (closed state) ---
const openFloat = ref(0)
const opening = ref(false)
const openChoice = ref(null)

async function openRegister(resumeEntry = null, forceNew = false) {
  opening.value = true
  try {
    const extra = {}
    if (resumeEntry) extra.resume_opening_entry = resumeEntry
    if (forceNew) extra.force_new = 1
    const result = await session.openRegister(openFloat.value || 0, extra)
    if (result?.requires_retry) {
      pending.value = result
      return
    }
    if (result?.requires_choice) {
      openChoice.value = result.open_entry
      return
    }
    openChoice.value = null
    pending.value = null
    session.notify(t('Register opened'))
    load()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    opening.value = false
  }
}

async function retryClosing(sessionName, isPending = false) {
  retrying.value = sessionName
  try {
    await call('lumenpos.api.register.retry_closing', { session: sessionName })
    session.notify(t('Finalising the shift…'))
    pollCloseState(sessionName)
  } catch (e) {
    session.notify(e.message, true)
    retrying.value = null
  }
}

onMounted(() => {
  load()
  loadHistory()
  if (pending.value) pollCloseState(pending.value.session)
})

async function loadHistory() {
  if (session.offline) return
  history.value = await call('lumenpos.api.register.list_sessions', {
    pos_profile: session.posProfile,
  }).catch(() => [])
}

// Poll the close/consolidation state until the shift reaches Closed or Failed.
function pollCloseState(sessionName) {
  clearInterval(closingPoll)
  let tries = 0
  closingPoll = setInterval(async () => {
    tries += 1
    try {
      const res = await call('lumenpos.api.register.closing_entry_status', { session: sessionName })
      // keep the visible close panel in sync if it's this session
      if (closedResult.value && closedResult.value.name === sessionName) {
        closeState.value = res
      }
      if (res.status === 'Closed') {
        clearInterval(closingPoll)
        retrying.value = null
        if (pending.value && pending.value.session === sessionName) {
          pending.value = null
          await session.bootstrap(session.posProfile)
        }
        session.notify(t('Shift closed and consolidated'))
        loadHistory()
      } else if (res.closing_status === 'Failed') {
        clearInterval(closingPoll)
        retrying.value = null
        if (pending.value && pending.value.session === sessionName) {
          pending.value = { ...pending.value, closing_status: 'Failed', closing_error: res.closing_error }
        }
        session.notify(t('Consolidation failed — check the error and retry'), true)
        loadHistory()
      }
    } catch {
      /* keep polling */
    }
    if (tries >= 60) {
      clearInterval(closingPoll)
      retrying.value = null
    }
  }, 3000)
}

onBeforeUnmount(() => clearInterval(closingPoll))

const loadError = ref('')
const loadingSummary = ref(true)

const countRows = computed(() => {
  const rows = []
  const seen = new Set()
  for (const row of summary.value?.expected || []) {
    rows.push(row)
    seen.add(row.mode_of_payment)
  }
  if (loadError.value) {
    for (const mode of session.paymentModes) {
      if (!seen.has(mode.mode_of_payment)) {
        rows.push({ mode_of_payment: mode.mode_of_payment, expected_amount: null })
        seen.add(mode.mode_of_payment)
      }
    }
  }
  return rows
})

async function load() {
  if (!session.registerOpen) return
  loadError.value = ''
  loadingSummary.value = true
  try {
    summary.value = await call('lumenpos.api.register.get_session_summary', {
      session: session.registerSession.name,
    })
    for (const row of summary.value.expected) {
      if (!(row.mode_of_payment in counted.value)) counted.value[row.mode_of_payment] = null
    }
  } catch (e) {
    loadError.value = e.message || t('request failed')
    summary.value = null
  } finally {
    loadingSummary.value = false
  }
}

function diff(row) {
  const value = counted.value[row.mode_of_payment]
  if (value == null || row.expected_amount == null) return 0
  return value - row.expected_amount
}

function diffClass(row) {
  const d = diff(row)
  return d < -0.005 ? 'neg' : d > 0.005 ? 'pos' : ''
}

async function addMovement() {
  try {
    await call('lumenpos.api.register.add_cash_movement', {
      session: session.registerSession.name,
      movement_type: movement.value.movement_type,
      amount: movement.value.amount,
      reason: movement.value.reason,
    })
    movement.value = { movement_type: 'Cash In', amount: null, reason: '' }
    await load()
  } catch (e) {
    session.notify(e.message, true)
  }
}

function dismissClosed() {
  closedResult.value = null
  pending.value = session.pendingClosing
}

async function close() {
  if (!confirm(t('Close the register? This ends the current session — make any corrections first.'))) return
  closing.value = true
  try {
    const countedClean = {}
    for (const [mode, value] of Object.entries(counted.value)) {
      countedClean[mode] = value || 0
    }
    const closedSession = session.registerSession.name
    closedResult.value = await call('lumenpos.api.register.close_register', {
      session: closedSession,
      counted: countedClean,
      closing_note: closingNote.value || null,
    })
    closeState.value = {
      status: closedResult.value.status || 'Closing',
      closing_status: 'Pending',
      pos_closing_entry: null,
      closing_error: null,
    }
    session.registerSession = null
    session.notify(t('Register closing…'))
    if (closedResult.value.closing_entry_queued) pollCloseState(closedSession)
    else closeState.value.status = 'Closed'
    loadHistory()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    closing.value = false
  }
}
</script>

<style scoped>
.register {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 860px;
  margin: 0 auto;
  width: 100%;
}
.panel-head {
  padding: 14px 18px;
  font-weight: 700;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.panel-head .btn { font-weight: 600; }
.panel-body { padding: 16px 18px; }
.stat-row { display: flex; gap: 28px; flex-wrap: wrap; }
.stat-label {
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.stat-value { font-size: 22px; font-weight: 800; margin-top: 2px; }
.cash-form {
  display: grid;
  grid-template-columns: 130px 130px 1fr auto;
  gap: 8px;
  margin-bottom: 12px;
}
.movement-row {
  display: grid;
  grid-template-columns: 90px 1fr auto;
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.movement-row .in { color: var(--brand-dark); font-weight: 700; }
.movement-row .out { color: var(--red); font-weight: 700; }
.count-table { width: 100%; border-collapse: collapse; }
.count-table th {
  text-align: left;
  font-size: 11.5px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  padding: 6px 8px;
}
.count-table th.right { text-align: right; }
.count-table td {
  padding: 8px;
  border-top: 1px solid var(--border);
  font-weight: 600;
}
.count-input { width: 110px; text-align: right; padding: 7px 9px; }
.neg { color: var(--red); }
.pos { color: var(--amber); }
.empty { padding: 60px; text-align: center; }
.empty-sm { padding: 24px; text-align: center; }
.session-row {
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
}
.session-row:last-child { border-bottom: none; }
.session-title { font-weight: 700; }
.small { font-size: 12px; }
.entry-link {
  color: var(--brand);
  font-weight: 600;
  text-decoration: none;
}
.entry-link:hover { text-decoration: underline; }
.summary-error {
  background: rgba(245, 166, 35, 0.14);
  color: #9a6a0a;
  border-radius: var(--radius);
  padding: 10px 14px;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 13px;
}
.retry-closing { padding: 3px 10px; font-size: 11.5px; color: var(--amber); margin-left: 4px; }
.field-label { display: block; font-size: 12px; font-weight: 700; color: var(--text-muted); margin: 10px 0 6px; }
.open-choice { margin-top: 14px; display: flex; flex-direction: column; gap: 8px; align-items: flex-start; }
.pill-warn {
  font-size: 10.5px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--red);
  background: rgba(226, 48, 48, 0.12);
  border-radius: 999px;
  padding: 2px 8px;
  margin-left: 6px;
}
.err-detail {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 8px 10px;
  font-size: 11.5px;
  color: var(--red);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
  margin: 8px 0;
}
.force-new-block { margin-top: 10px; }
.or-sep {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 16px 0 8px;
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
