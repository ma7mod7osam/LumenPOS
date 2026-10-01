<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="register">
    <!-- A shift that was closed but whose consolidation is still finishing or
         failed. Until it reaches Closed, the register stays locked. -->
    <div v-if="pending && !closedResult" class="card panel">
      <div class="panel-head">{{ t('Previous shift not finished') }}</div>
      <div class="panel-body">
        <p>
          {{ t('Session') }} <b>{{ pending.session }}</b> {{ t('was closed but its sales are still being consolidated') }}<span v-if="pending.closing_status === 'Failed'">&nbsp;{{ t('and the last attempt') }}
          <b class="neg">{{ t('failed') }}</b></span>.
        </p>
        <pre v-if="pending.closing_error" class="err-detail">{{ plainText(pending.closing_error) }}</pre>
        <PeriodHint v-if="pending.closing_hint" :hint="pending.closing_hint" />
        <button
          v-if="session.permissions.close_register !== false"
          class="btn btn-primary"
          :disabled="retrying === pending.session"
          @click="retryClosing(pending.session, true)"
        >
          <Icon name="refresh" /> {{ retrying === pending.session ? t('Finalising…') : t('Retry closing') }}
        </button>
        <p class="muted small" style="margin-top: 8px">
          {{ t('Safe to retry as often as needed. ERPNext rolls a failed attempt back fully, so nothing is ever double-posted.') }}
        </p>

        <!-- Closing keeps FAILING, let the store keep trading. Opens a fresh shift
             now; the failed one stays in the background and keeps retrying. -->
        <div
          v-if="pending.closing_status === 'Failed' && session.permissions.close_register !== false"
          class="force-new-block"
        >
          <div class="or-sep"><span>{{ t('or start a new shift anyway') }}</span></div>
          <label class="field-label">{{ t('Opening float for the new shift') }}</label>
          <input
            type="text"
            inputmode="decimal"
            v-model="openFloat"
            style="width: 200px"
            :disabled="opening"
          />
          <div style="margin-top: 10px">
            <button class="btn btn-outline" :disabled="opening" @click="openRegister()">
              <Icon name="play" /> {{ opening ? t('Opening…') : t('Start a new shift anyway') }}
            </button>
          </div>
          <p class="muted small" style="margin-top: 8px">
            {{ t('Keep selling now, the failed shift stays in the background and keeps retrying until its invoices consolidate.') }}
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
          <template v-if="closeState.status === 'Closed'">&nbsp;{{ t('closed.') }}
            <template v-if="closeState.pos_closing_entry">
              {{ t('POS Closing Entry') }}
              <a :href="`/app/pos-closing-entry/${closeState.pos_closing_entry}`" target="_blank" class="entry-link">
                {{ closeState.pos_closing_entry }}
              </a>
              {{ t('consolidated its invoices.') }}
            </template>
          </template>
          <template v-else-if="closeState.closing_status === 'Failed'">&nbsp;<span class="neg">{{ t('was closed, but consolidation failed.') }}</span>
            {{ t('No more sales can be added, but its invoices still need to post. Retry below.') }}
          </template>
          <template v-else>
            <span class="muted"><Icon name="hourglass" /> {{ t('Consolidating invoices in the background… this usually takes a few seconds.') }}</span>
          </template>
        </p>
        <pre v-if="closeState.closing_error" class="err-detail">{{ plainText(closeState.closing_error) }}</pre>
        <PeriodHint v-if="closeState.closing_hint" :hint="closeState.closing_hint" />
        <div v-if="closedResult.expected_pending" class="summary-error">
          {{ t("The expected takings could not be worked out at the close. They are filled in from the shift's POS Closing Entry when it consolidates.") }}
        </div>
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
              <td class="right">{{ closedResult.expected_pending ? '-' : money(row.expected_amount, row.currency) }}</td>
              <td class="right">{{ money(row.counted_amount, row.currency) }}</td>
              <td v-if="closedResult.expected_pending" class="right">-</td>
              <td v-else class="right" :class="row.difference < -0.005 ? 'neg' : row.difference > 0.005 ? 'pos' : ''">
                {{ money(row.difference, row.currency) }}
              </td>
            </tr>
          </tbody>
        </table>
        <button class="btn btn-outline" style="margin-top: 12px" @click="dismissClosed">{{ t('Done') }}</button>
      </div>
    </div>

    <div v-if="!session.registerOpen && !closedResult && !pending" class="card panel" data-tour="register-open">
      <div class="panel-head">{{ t('Open register') }}</div>
      <div class="panel-body">
        <p class="muted">{{ session.posProfile }}. {{ t('Enter the opening cash float to start selling.') }}</p>
        <label class="field-label">{{ t('Opening float') }}</label>
        <input type="text" inputmode="decimal" v-model="openFloat" style="width: 200px" :disabled="!canOpen" @keydown.enter="openRegister()" />
        <div style="margin-top: 14px">
          <button class="btn btn-primary btn-lg" :disabled="opening || !canOpen" @click="openRegister()">
            {{ opening ? t('Opening…') : t('Open Register') }}
          </button>
          <p v-if="!canOpen" class="muted small">{{ t("You don't have permission to open a register.") }}</p>
        </div>
      </div>
    </div>

    <template v-if="session.registerOpen">
      <div class="card panel" data-tour="register-summary">
        <div class="panel-head">{{ t('Session') }} {{ session.registerSession.name }}</div>
        <div class="panel-body" v-if="summary">
          <div class="stat-row">
            <div class="stat">
              <div class="stat-label">{{ t('Sales') }}</div>
              <div class="stat-value">{{ summary.sales_count }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">{{ t('Takings') }}</div>
              <div class="stat-value">{{ money(summary.total_sales, local) }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">{{ t('Discounts given') }}</div>
              <div class="stat-value">{{ money(summary.total_discounts, local) }}</div>
            </div>
            <div class="stat">
              <div class="stat-label">{{ t('Opening float') }}</div>
              <div class="stat-value">{{ money(summary.opening_float, local) }}</div>
              <div v-for="(amount, drawer) in summary.foreign_floats || {}" :key="drawer" class="muted small">
                {{ drawer }}: {{ money(amount, drawerCurrency(drawer)) }}
              </div>
            </div>
          </div>
          <!-- Who sold what on this shift (lumenpos.api.salespeople.shift_rows). -->
          <div v-if="summary.salespeople?.length" class="sp-block">
            <div class="days-title">{{ t('By salesperson') }}</div>
            <SalespeopleTable :rows="summary.salespeople" :currency="local" />
          </div>
          <!-- ERPNext 16 takes sales only on a POS Opening Entry opened the
               same day: the shift closed ERPNext's day at the first sale after
               midnight and sells on (register.roll_day). -->
          <div v-if="summary.erpnext_days?.length" class="days-block">
            <div class="days-title">{{ t('ERPNext days closed during this shift') }}</div>
            <p class="muted small">{{ t('ERPNext 16 takes sales only on a shift opened the same day, so at the first sale after midnight LumenPOS closed the day in ERPNext and opened the next one. Count the drawer once, when you close the shift.') }}</p>
            <div v-for="d in summary.erpnext_days" :key="d.pos_closing_entry" class="day-row">
              <span>{{ t('Until {time}', { time: shortTime(d.ended_at) }) }} · {{ t('Sales') }}: {{ d.sales_count }}</span>
              <a :href="`/app/pos-closing-entry/${d.pos_closing_entry}`" target="_blank" class="entry-link">{{ d.pos_closing_entry }}</a>
              <span v-if="d.closing_status === 'Submitted'" class="day-ok">{{ t('Posted') }}</span>
              <span v-else-if="d.closing_status === 'Failed'" class="neg">{{ t('Not posted yet') }}</span>
              <span v-else class="muted">{{ t('Posting…') }}</span>
            </div>
            <template v-if="failedDay">
              <pre class="err-detail">{{ plainText(failedDay.closing_error) }}</pre>
              <PeriodHint v-if="failedDay.closing_hint" :hint="failedDay.closing_hint" />
              <button v-if="canClose" class="btn btn-outline" :disabled="retryingDays" @click="retryDays">
                <Icon name="refresh" /> {{ t('Try again') }}
              </button>
            </template>
          </div>
        </div>
      </div>

      <div v-if="session.permissions.can_move_cash !== false" class="card panel" data-tour="register-cash">
        <div class="panel-head">{{ t('Cash in / out') }}</div>
        <div class="panel-body">
          <div class="cash-form" :class="{ 'with-drawer': foreignDrawers.length }">
            <select v-model="movement.movement_type">
              <option value="Cash In">{{ t('Cash In') }}</option>
              <option value="Cash Out">{{ t('Cash Out') }}</option>
            </select>
            <!-- A drawer in another currency keeps its own cash in and out. -->
            <select v-if="foreignDrawers.length" v-model="movement.mode_of_payment">
              <option :value="null">{{ t('Main drawer ({currency})', { currency: local }) }}</option>
              <option v-for="d in foreignDrawers" :key="d.mode_of_payment" :value="d.mode_of_payment">
                {{ d.mode_of_payment }} ({{ d.account_currency }})
              </option>
            </select>
            <input type="text" inputmode="decimal" v-model="movement.amount" :placeholder="t('Amount')" />
            <input v-model="movement.reason" :placeholder="t('Reason')" />
            <button class="btn btn-outline" :disabled="!movement.amount" @click="addMovement">{{ t('Add') }}</button>
          </div>
          <div v-for="(m, i) in summary?.cash_movements || []" :key="i" class="movement-row">
            <span :class="m.movement_type === 'Cash In' ? 'in' : 'out'">{{ t(m.movement_type) }}</span>
            <span class="muted">{{ m.reason }}<template v-if="m.currency && m.currency !== local"> · {{ m.mode_of_payment }}</template></span>
            <span class="right">{{ money(m.amount, m.currency || local) }}</span>
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
          <!-- Queued offline sales belong to THIS shift's drawer. Closing before
               they upload would push them onto the next shift and leave both
               counts wrong, so block the close until they're in. -->
          <div v-if="waitingCount > 0" class="queued-block">
            <div>
              <b>{{ t('{n} offline sales are still waiting to upload.', { n: waitingCount }) }}</b>
              <div class="muted small">{{ t('They belong to this shift. Upload them before closing, or they land on the next shift.') }}</div>
            </div>
            <button class="btn btn-primary" :disabled="uploading" @click="uploadQueued">
              <Icon name="upload" /> {{ uploading ? t('Uploading…') : t('Upload now') }}
            </button>
          </div>
          <!-- Sales the server refused never hold the close: one that can never
               go through on this shift kept it open for good (a shop's shift
               that ran past midnight on ERPNext 16, 2026-09-30). -->
          <div v-else-if="session.refusedCount > 0" class="queued-block refused">
            <div>
              <b>{{ t('{n} offline sales were refused by the server.', { n: session.refusedCount }) }}</b>
              <div v-if="session.refusedReason" class="muted small">{{ session.refusedReason }}</div>
              <div class="muted small">{{ t('You can still close. Take their cash out of the drawer before you count, and put it back once the next shift is open: they are sent again then.') }}</div>
            </div>
            <button class="btn btn-outline" :disabled="uploading" @click="uploadQueued">
              <Icon name="upload" /> {{ uploading ? t('Uploading…') : t('Try again') }}
            </button>
          </div>
          <div v-if="loadError" class="summary-error">
            {{ t('⚠ Couldn\'t load the expected takings') }} ({{ loadError }}). {{ t('You can still close the register. Enter the counted amounts below.') }}
          </div>
          <p class="muted small" style="margin: 0 0 10px">
            {{ t('Need to fix a wrong payment method? Do the return + corrected sale') }}
            <b>{{ t('before') }}</b> {{ t("closing, they're picked up automatically. Once you close, the shift can't be sold on again.") }}
          </p>
          <table class="count-table" data-tour="register-count">
            <thead>
              <tr><th>{{ t('Payment') }}</th><th class="right">{{ t('Expected') }}</th><th class="right">{{ t('Counted') }}</th><th class="right">{{ t('Difference') }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="row in countRows" :key="row.mode_of_payment">
                <td>
                  {{ row.mode_of_payment }}
                  <span v-if="row.currency && row.currency !== local" class="ccy-tag">{{ row.currency }}</span>
                </td>
                <td class="right">{{ row.expected_amount != null ? money(row.expected_amount, row.currency || local) : '-' }}</td>
                <td class="right">
                  <input
                    type="text"
                    inputmode="decimal"
                    class="count-input"
                    v-model="counted[row.mode_of_payment]"
                  />
                </td>
                <td class="right" :class="diffClass(row)">{{ money(diff(row), row.currency || local) }}</td>
              </tr>
              <tr v-if="!countRows.length">
                <td colspan="4" class="muted" style="text-align: center; padding: 14px">
                  {{ t('No takings recorded this session.') }}
                </td>
              </tr>
            </tbody>
          </table>
          <input v-model="closingNote" :placeholder="t('Closing note (optional)')" style="width: 100%; margin-top: 12px" />
          <button class="btn btn-danger btn-lg" data-tour="register-close" style="width: 100%; margin-top: 14px" :disabled="closing || !canClose" @click="close">
            {{ closing ? t('Closing…') : t('Close Register') }}
          </button>
          <p v-if="!canClose" class="muted small">{{ t("You don't have permission to close the register.") }}</p>
        </div>
      </div>
    </template>

    <!-- A manager closes a shift someone else left open at this outlet (each
         cashier's own in "Per cashier" scope): one whose cashier went home,
         may not close a register, or is held back elsewhere by "One open
         shift per person". -->
    <div v-if="otherShifts.length" class="card panel">
      <div class="panel-head">
        {{ t('Other open shifts here') }}
        <button class="btn btn-outline" :disabled="otherBusy" @click="loadOtherShifts"><Icon name="refresh" /></button>
      </div>
      <div class="panel-body">
        <p class="muted small" style="margin: 0 0 10px">
          {{ t('Shifts other people still have open at this outlet. Close one for a cashier who has gone home, who may not close a register, or whose shift will not close.') }}
        </p>
        <div v-for="r in otherShifts" :key="r.session" class="other-row">
          <div class="other-info">
            <b>{{ r.opened_by_name || r.opened_by }}</b>
            <span class="muted small">{{ r.session }} · {{ shortTime(r.opened_at) }}</span>
          </div>
          <button
            v-if="canClose && otherTarget?.session !== r.session"
            class="btn btn-outline"
            :disabled="otherBusy"
            @click="pickOther(r)"
          >
            {{ t('Close this shift') }}
          </button>
        </div>
        <div v-if="otherTarget" class="other-close">
          <div class="other-close-head">
            {{ t('Count the drawers of {name}, then close the shift.', { name: otherTarget.opened_by_name || otherTarget.opened_by }) }}
          </div>
          <p v-if="otherLoading" class="muted">{{ t('Loading session summary…') }}</p>
          <template v-else>
            <div v-if="otherError" class="summary-error">
              {{ t('⚠ Couldn\'t load the expected takings') }} ({{ otherError }}). {{ t('You can still close the register. Enter the counted amounts below.') }}
            </div>
            <table class="count-table">
              <thead>
                <tr><th>{{ t('Payment') }}</th><th class="right">{{ t('Expected') }}</th><th class="right">{{ t('Counted') }}</th><th class="right">{{ t('Difference') }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="row in otherRows" :key="row.mode_of_payment">
                  <td>
                    {{ row.mode_of_payment }}
                    <span v-if="row.currency && row.currency !== otherLocal" class="ccy-tag">{{ row.currency }}</span>
                  </td>
                  <td class="right">{{ row.expected_amount != null ? money(row.expected_amount, row.currency || otherLocal) : '-' }}</td>
                  <td class="right">
                    <input type="text" inputmode="decimal" class="count-input" v-model="otherCounted[row.mode_of_payment]" />
                  </td>
                  <td class="right" :class="otherDiffClass(row)">{{ money(otherDiff(row), row.currency || otherLocal) }}</td>
                </tr>
                <tr v-if="!otherRows.length">
                  <td colspan="4" class="muted" style="text-align: center; padding: 14px">
                    {{ t('No takings recorded this session.') }}
                  </td>
                </tr>
              </tbody>
            </table>
            <input v-model="otherNote" :placeholder="t('Closing note (optional)')" style="width: 100%; margin-top: 12px" />
            <div class="other-actions">
              <button class="btn btn-outline" :disabled="otherBusy" @click="otherTarget = null">{{ t('Cancel') }}</button>
              <button class="btn btn-danger" :disabled="otherBusy" @click="closeOther">
                {{ otherBusy ? t('Closing…') : t('Close this shift') }}
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>

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
            {{ past.sales_count }} {{ t('sales') }} · {{ t('takings') }} {{ money(past.total_sales, local) }} ·
            {{ t('discounts') }} {{ money(past.total_discounts, local) }} ·
            <span v-if="past.expected_pending" class="muted">{{ t('difference pending') }}</span>
            <span v-else :class="past.total_difference < -0.005 ? 'neg' : past.total_difference > 0.005 ? 'pos' : ''">
              {{ t('difference') }} {{ money(past.total_difference, local) }}
            </span>
          </div>
          <div class="muted small">
            <!-- The ERPNext days closed while the shift sold on past midnight. -->
            <template v-for="d in past.erpnext_days || []" :key="d.pos_closing_entry">
              <a :href="`/app/pos-closing-entry/${d.pos_closing_entry}`" target="_blank" class="entry-link">{{ d.pos_closing_entry }}</a>&nbsp;·
            </template>
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
import SalespeopleTable from '../components/SalespeopleTable.vue'
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money, shortTime, parseMoney, plainText } from '../format'
import PeriodHint from '../components/PeriodHint.vue'
import { t } from '../i18n'

const session = useSessionStore()
const summary = ref(null)
const counted = ref({})
const closingNote = ref('')
const closing = ref(false)
const uploading = ref(false)
const movement = ref({ movement_type: 'Cash In', amount: null, reason: '', mode_of_payment: null })

// Shift figures are in the company currency; each drawer in another currency
// ("Cash USD") keeps its own float, movements and count (lumenpos.currency).
const local = computed(() => summary.value?.company_currency || session.localCurrency)
const foreignDrawers = computed(() =>
  (session.paymentModes || []).filter(
    (m) => m.type === 'Cash' && m.account_currency && m.account_currency !== session.localCurrency
  )
)
function drawerCurrency(drawer) {
  const row = (summary.value?.expected || []).find((r) => r.mode_of_payment === drawer)
  const mode = (session.paymentModes || []).find((m) => m.mode_of_payment === drawer)
  return row?.currency || mode?.account_currency || local.value
}
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

async function openRegister() {
  // Read the float from the RAW text, never from a number input (which reports
  // empty for anything it can't parse in the browser's locale, e.g. "1,500").
  const float = parseMoney(openFloat.value)
  if (float === null) {
    session.notify(t('Enter the opening float as a number, e.g. 1500 or 1500.50'), true)
    return
  }
  // A genuine zero must be deliberate, this is the "opened with cash in the
  // drawer, recorded 0.00" case.
  if (float === 0 && !confirm(t('Open with an opening float of 0.00? Confirm the drawer is empty.'))) {
    return
  }
  opening.value = true
  try {
    // Always a fresh shift, no resume / force-new branches.
    await session.openRegister(float)
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
  loadOtherShifts()
  if (pending.value) pollCloseState(pending.value.session)
})

// --- a manager closes a shift someone else left open at this outlet ---
const otherShifts = ref([])
const otherTarget = ref(null)
const otherSummary = ref(null)
const otherCounted = ref({})
const otherNote = ref('')
const otherError = ref('')
const otherLoading = ref(false)
const otherBusy = ref(false)
const otherLocal = computed(() => otherSummary.value?.company_currency || session.localCurrency)

async function loadOtherShifts() {
  if (session.offline || !session.permissions.is_manager) {
    otherShifts.value = []
    return
  }
  otherShifts.value = await call('lumenpos.api.register.list_open_shifts', {
    pos_profile: session.posProfile,
  }).catch(() => [])
  if (otherTarget.value && !otherShifts.value.some((r) => r.session === otherTarget.value.session)) {
    otherTarget.value = null
  }
}

async function pickOther(row) {
  otherTarget.value = row
  otherSummary.value = null
  otherCounted.value = {}
  otherNote.value = ''
  otherError.value = ''
  otherLoading.value = true
  try {
    otherSummary.value = await call('lumenpos.api.register.get_session_summary', { session: row.session })
    for (const r of otherSummary.value.expected) otherCounted.value[r.mode_of_payment] = null
  } catch (e) {
    // The drawers can still be counted: the close goes through and the
    // expected figures come from ERPNext's closing entry at consolidation.
    otherError.value = e.message || t('request failed')
    for (const m of session.paymentModes) otherCounted.value[m.mode_of_payment] = null
  } finally {
    otherLoading.value = false
  }
}

const otherRows = computed(() => {
  if (otherSummary.value) return otherSummary.value.expected
  if (!otherError.value) return []
  return (session.paymentModes || []).map((m) => ({ mode_of_payment: m.mode_of_payment, expected_amount: null }))
})

function otherDiff(row) {
  const value = parseMoney(otherCounted.value[row.mode_of_payment])
  if (value == null || row.expected_amount == null) return 0
  return value - row.expected_amount
}

function otherDiffClass(row) {
  const d = otherDiff(row)
  return d < -0.005 ? 'neg' : d > 0.005 ? 'pos' : ''
}

async function closeOther() {
  const target = otherTarget.value
  if (!target) return
  const name = target.opened_by_name || target.opened_by
  if (!confirm(t('Close the shift of {name}? Nothing more can be sold on it.', { name }))) return
  otherBusy.value = true
  try {
    const countedClean = {}
    for (const [mode, value] of Object.entries(otherCounted.value)) {
      countedClean[mode] = parseMoney(value) || 0
    }
    await call('lumenpos.api.register.close_register', {
      session: target.session,
      counted: countedClean,
      closing_note: otherNote.value || null,
      // Stale-closing-screen guard, as for this page's own close.
      expected_invoice_count: otherSummary.value ? otherSummary.value.sales_count : null,
    })
    session.notify(t('Shift {session} is closing. Its sales are consolidated in the background.', { session: target.session }))
    otherTarget.value = null
    await loadOtherShifts()
    loadHistory()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    otherBusy.value = false
  }
}

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
          pending.value = { ...pending.value, closing_status: 'Failed', closing_error: res.closing_error, closing_hint: res.closing_hint }
        }
        session.notify(t('Consolidation failed. Check the error and retry'), true)
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
  const value = parseMoney(counted.value[row.mode_of_payment])
  if (value == null || row.expected_amount == null) return 0
  return value - row.expected_amount
}

function diffClass(row) {
  const d = diff(row)
  return d < -0.005 ? 'neg' : d > 0.005 ? 'pos' : ''
}

async function addMovement() {
  const amount = parseMoney(movement.value.amount)
  if (amount === null || amount <= 0) {
    session.notify(t('Enter the amount as a number, e.g. 250 or 250.50'), true)
    return
  }
  try {
    await call('lumenpos.api.register.add_cash_movement', {
      session: session.registerSession.name,
      movement_type: movement.value.movement_type,
      amount,
      reason: movement.value.reason,
      mode_of_payment: movement.value.mode_of_payment || null,
    })
    movement.value = { movement_type: 'Cash In', amount: null, reason: '', mode_of_payment: null }
    await load()
  } catch (e) {
    session.notify(e.message, true)
  }
}

function dismissClosed() {
  closedResult.value = null
  pending.value = session.pendingClosing
}

// Queued offline sales still to upload: the ones the server refused are
// apart, they never hold the close.
const waitingCount = computed(() => Math.max((session.queuedCount || 0) - (session.refusedCount || 0), 0))

// A closed ERPNext day that did not reach the books (register.roll_day).
const failedDay = computed(() => (summary.value?.erpnext_days || []).find((d) => d.closing_status === 'Failed'))
const retryingDays = ref(false)

async function retryDays() {
  retryingDays.value = true
  try {
    await call('lumenpos.api.register.retry_days', { session: session.registerSession.name })
    // It runs in the background: read the shift again in a moment.
    setTimeout(() => {
      retryingDays.value = false
      load()
    }, 5000)
  } catch (e) {
    retryingDays.value = false
    session.notify(e.message, true)
  }
}

async function uploadQueued() {
  uploading.value = true
  try {
    await session.flushQueue()
    await session.refreshQueueCount()
    await load()
    if (session.queuedCount === 0) session.notify(t('All offline sales uploaded'))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    uploading.value = false
  }
}

async function close() {
  // Queued offline sales belong to THIS shift's drawer. Closing before they
  // upload would push them onto the NEXT shift and leave both counts wrong.
  // Sales the server refused are the exception: they may never go through on
  // this shift, and must not keep it open for good.
  await session.refreshQueueCount()
  if (waitingCount.value > 0) {
    session.notify(
      t('{n} offline sales still need to upload. Press Upload now before closing.', {
        n: waitingCount.value,
      }),
      true
    )
    return
  }
  const question = session.refusedCount > 0
    ? t('{n} offline sales were refused and are not in this count. Take their cash out of the drawer before you count. Close the register?', {
        n: session.refusedCount,
      })
    : t('Close the register? This ends the current session. Make any corrections first.')
  if (!confirm(question)) return
  closing.value = true
  try {
    const countedClean = {}
    for (const [mode, value] of Object.entries(counted.value)) {
      countedClean[mode] = parseMoney(value) || 0
    }
    const closedSession = session.registerSession.name
    closedResult.value = await call('lumenpos.api.register.close_register', {
      session: closedSession,
      counted: countedClean,
      closing_note: closingNote.value || null,
      // Stale-closing-screen guard: the server rejects the close if more sales
      // landed after this screen loaded (see close_register).
      expected_invoice_count: summary.value ? summary.value.sales_count : null,
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
.queued-block {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  background: rgba(226, 48, 48, 0.10);
  border: 1px solid rgba(226, 48, 48, 0.28);
  border-radius: var(--radius);
  padding: 12px 14px;
  margin-bottom: 12px;
}
.queued-block > div { flex: 1; min-width: 220px; }
.queued-block.refused {
  background: rgba(214, 140, 16, 0.10);
  border-color: rgba(214, 140, 16, 0.32);
}
.days-block {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.days-title { font-weight: 600; margin-bottom: 4px; }
.sp-block { margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border-subtle); }
.days-block .muted.small { margin: 0 0 8px; }
.day-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 4px 0;
  font-size: 13px;
}
.day-ok { color: var(--brand); font-weight: 600; }
.ccy-tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 800;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.1);
  border-radius: 999px;
  padding: 1px 8px;
  margin-inline-start: 6px;
}
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
  /* The type picker grows to its longest option ("Entrée d'espèces"). */
  grid-template-columns: minmax(130px, max-content) 130px 1fr auto;
  gap: 8px;
  margin-bottom: 12px;
}
/* With a drawer in another currency the form gains a drawer picker. */
.cash-form.with-drawer { grid-template-columns: minmax(120px, max-content) minmax(150px, auto) 110px 1fr auto; }
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
.other-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.other-info { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.other-close { margin-top: 14px; padding-top: 12px; border-top: 2px solid var(--border); }
.other-close-head { font-weight: 700; margin-bottom: 10px; }
.other-actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
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
