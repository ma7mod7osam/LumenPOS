<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 520px">
      <div class="modal-header">
        {{ t('Refund {invoice}', { invoice }) }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="muted empty">{{ t('Loading…') }}</div>
        <template v-else>
          <div v-if="overWindow && canExceed" class="approval-box authorized">
            <div class="ap-ok">
              <Icon name="check" />
              {{ t('This sale is {age} days old (past the {n}-day window) — you are authorized to return it.', { age: returnWindow.age_days, n: returnWindow.window_days }) }}
            </div>
          </div>
          <div v-else-if="overWindow" class="approval-box" :class="reqPhase">
            <template v-if="returnRequest">
              <div class="ap-ok"><Icon name="check" /> {{ t('Return approved') }}<span v-if="approverName"> · {{ approverName }}</span></div>
            </template>
            <template v-else-if="reqPhase === 'waiting'">
              <div class="spinner-sm"></div>
              <span class="ap-text">{{ t('Waiting for a manager to approve…') }}</span>
              <button class="btn btn-outline btn-sm" @click="cancelReturnRequest">{{ t('Cancel request') }}</button>
            </template>
            <template v-else-if="reqPhase === 'rejected'">
              <div class="ap-warn">{{ reqRejected }}</div>
              <button class="btn btn-outline btn-sm" @click="resetReturnReq">{{ t('Try again') }}</button>
            </template>
            <template v-else>
              <div class="ap-warn">
                {{ t('This sale is {age} days old. Returns are limited to {n} days — a manager must approve this return.', { age: returnWindow.age_days, n: returnWindow.window_days }) }}
              </div>
              <button class="btn btn-primary btn-sm" :disabled="reqBusy" @click="sendReturnRequest">
                {{ reqBusy ? t('Sending…') : t('Send return approval request') }}
              </button>
            </template>
          </div>

          <div v-if="!returnable.length" class="muted empty">
            {{ t('Everything on this sale has already been returned.') }}
          </div>
          <div v-for="row in returnable" :key="row.item_code" class="return-row" :class="{ serialized: row.has_serial_no }">
            <div class="return-info">
              <div class="return-name">
                {{ row.item_name }}
                <span v-if="row.return_group" class="set-badge">{{ t('Set — return together') }}</span>
              </div>
              <div class="muted small">
                {{ t('Sold {qty} × {rate} · {returnable} returnable', { qty: row.qty, rate: money(row.rate), returnable: row.returnable_qty }) }}
              </div>
              <div v-if="row.has_serial_no" class="serial-pick">
                <div class="muted small pick-hint">{{ t('Scan or type each returned serial ({n} returnable)', { n: row.returnable_serials.length }) }}</div>
                <input
                  class="serial-in"
                  :placeholder="t('Scan serial…')"
                  @focus="scan.reset()"
                  @keydown="scan.onKeydown"
                  @keydown.enter.prevent="addSerial(row, $event)"
                  @paste.prevent
                />
                <div class="serial-chips">
                  <button
                    v-for="serial in (selectedSerials[row.item_code] || [])"
                    :key="serial"
                    class="serial-chip selected"
                    :title="t('Remove')"
                    @click="removeSerial(row.item_code, serial)"
                  >{{ serial }} <Icon name="close" /></button>
                </div>
              </div>
            </div>
            <div v-if="!row.has_serial_no" class="stepper">
              <button class="btn btn-outline" @click="dec(row)">−</button>
              <input type="number" min="0" :max="row.returnable_qty" :readonly="!!row.return_group" v-model.number="quantities[row.item_code]" />
              <button class="btn btn-outline" @click="inc(row)">+</button>
            </div>
            <div v-else class="serial-count">{{ quantities[row.item_code] || 0 }}</div>
          </div>

          <div v-if="refundTotal > 0" class="refund-summary">
            <div class="refund-amount">
              {{ t('Refund ≈') }} <strong>{{ money(refundTotal) }}</strong>
              <span class="muted small">{{ t('(final amount includes taxes, computed on submit)') }}</span>
            </div>
            <label class="field-label">{{ t('Return reason') }}</label>
            <select v-model="reason" style="width: 100%">
              <option :value="null" disabled>{{ t('Select a reason…') }}</option>
              <option v-for="r in reasons" :key="r" :value="r">{{ r }}</option>
              <option value="__other__">{{ t('Other (write a reason)…') }}</option>
            </select>
            <input
              v-if="reason === '__other__'"
              v-model="otherReason"
              :placeholder="t('Type the reason…')"
              style="width: 100%; margin-top: 6px"
            />
            <label class="field-label">{{ t('Refund to') }}</label>
            <select v-model="refundMode" style="width: 100%">
              <option v-for="mode in refundModes" :key="mode" :value="mode">{{ mode }}</option>
            </select>
            <p v-if="allowedModes" class="muted small refund-rule-note">
              {{ t('Limited to how this sale was paid (Settings → Refunds).') }}
            </p>
          </div>
        </template>
      </div>

      <div class="modal-footer">
        <button class="btn btn-outline" @click="$emit('close')">{{ t('Cancel') }}</button>
        <button class="btn btn-danger" :disabled="refundTotal <= 0 || !reasonValue || busy || needsApproval" @click="submit">
          {{ busy ? t('Refunding…') : t('Refund') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { createScanGuard } from '../scanGuard'
import { money } from '../format'
import { t } from '../i18n'

const props = defineProps({ invoice: String })
const emit = defineEmits(['close', 'done'])
const session = useSessionStore()
const scan = createScanGuard()
const scanOnly = computed(() => Boolean(session.settings?.serial_scan_only))

const loading = ref(true)
const busy = ref(false)
const returnable = ref([])
const quantities = ref({})
const selectedSerials = ref({}) // item_code -> [serials]
const refundMode = ref(null)
const allowedModes = ref(null) // null = no restriction; else array from the server
const reason = ref(null)
const otherReason = ref('')

// Return window: a sale older than the configured window can only be returned
// with an approved Return request (same role-approval flow as discounts).
const returnWindow = ref(null) // {restrict, window_days, age_days, within}
const returnRequest = ref(null) // approved request name once granted
const reqPhase = ref('idle') // idle | waiting | rejected
const reqName = ref(null)
const reqRejected = ref('')
const reqBusy = ref(false)
const approverName = ref('')
const customer = ref(null)
const customerName = ref(null)
let pollTimer = null

const reasons = computed(() => session.returnReasons)
// The reason actually sent: the typed text for "Other", else the picked reason.
const reasonValue = computed(() =>
  reason.value === '__other__' ? otherReason.value.trim() : reason.value || ''
)

const refundModes = computed(() => {
  // When the original sale restricts refund tenders, offer only those;
  // otherwise every payment method (plus store credit).
  if (allowedModes.value) return allowedModes.value
  const modes = session.paymentModes.map((m) => m.mode_of_payment)
  if (!modes.includes(session.storeCreditMode)) modes.push(session.storeCreditMode)
  return modes
})

const refundTotal = computed(() =>
  returnable.value.reduce(
    (sum, row) => sum + (quantities.value[row.item_code] || 0) * row.rate,
    0
  )
)

// Over the regular-return window and not yet approved → the refund is blocked
// until a manager approves a Return request — unless this user is allowed to
// exceed the window (the "exceed return window" role, or a manager).
const overWindow = computed(() => returnWindow.value && !returnWindow.value.within)
const canExceed = computed(() => session.permissions?.can_exceed_return_window === true)
const needsApproval = computed(
  () => overWindow.value && !returnRequest.value && !canExceed.value
)

onMounted(async () => {
  try {
    const data = await call('lumenpos.api.sales.get_returnable', { invoice: props.invoice })
    returnable.value = (data.items || []).filter((row) => row.returnable_qty > 0)
    allowedModes.value = data.allowed_refund_modes || null
    returnWindow.value = data.return_window || null
    customer.value = data.customer || null
    customerName.value = data.customer_name || null
    for (const row of returnable.value) quantities.value[row.item_code] = 0
    refundMode.value = refundModes.value[0] || null
  } catch (e) {
    session.notify(e.message, true)
    emit('close')
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  clearInterval(pollTimer)
  // Withdraw a still-pending request so it doesn't linger for approvers.
  if (reqPhase.value === 'waiting' && reqName.value) {
    call('lumenpos.api.approval_requests.cancel_request', { name: reqName.value }).catch(() => {})
  }
})

async function sendReturnRequest() {
  if (reqBusy.value) return
  reqBusy.value = true
  try {
    const res = await call('lumenpos.api.approval_requests.create_request', {
      request_type: 'Return',
      pos_profile: session.posProfile,
      return_invoice: props.invoice,
      reason: reasonValue.value || null,
      customer: customer.value || null,
      customer_name: customerName.value || null,
    })
    reqName.value = res.name
    reqPhase.value = 'waiting'
    pollTimer = setInterval(pollReturnStatus, 3000)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    reqBusy.value = false
  }
}

async function pollReturnStatus() {
  try {
    const res = await call('lumenpos.api.approval_requests.request_status', { name: reqName.value })
    if (res.status === 'Approved') {
      clearInterval(pollTimer)
      returnRequest.value = reqName.value
      approverName.value = res.approver_name || ''
      reqPhase.value = 'approved'
    } else if (res.status === 'Rejected' || res.status === 'Expired') {
      clearInterval(pollTimer)
      reqPhase.value = 'rejected'
      reqRejected.value =
        res.status === 'Rejected'
          ? res.decision_note
            ? t('Request rejected: {note}', { note: res.decision_note })
            : t('The manager rejected this return.')
          : t('The request expired — the register was closed.')
    }
  } catch {
    /* transient — keep polling */
  }
}

async function cancelReturnRequest() {
  clearInterval(pollTimer)
  if (reqName.value) {
    await call('lumenpos.api.approval_requests.cancel_request', { name: reqName.value }).catch(() => {})
  }
  resetReturnReq()
}

function resetReturnReq() {
  reqPhase.value = 'idle'
  reqName.value = null
  reqRejected.value = ''
}

// Items sold together (bundle / buy-x-get-y) must come back together, so the
// stepper acts on the whole group at once: non-serialized members all go to
// their full returnable qty (or zero). Serialized members are still scanned
// individually; the server rejects an incomplete set either way.
const groupMembers = computed(() => {
  const map = {}
  for (const r of returnable.value) {
    if (r.return_group) (map[r.return_group] ||= []).push(r)
  }
  return map
})

function setGroup(group, full) {
  for (const r of groupMembers.value[group] || []) {
    if (r.has_serial_no) continue
    quantities.value[r.item_code] = full ? r.returnable_qty : 0
  }
}

function inc(row) {
  if (row.return_group) return setGroup(row.return_group, true)
  const current = quantities.value[row.item_code] || 0
  quantities.value[row.item_code] = Math.min(row.returnable_qty, current + 1)
}

function dec(row) {
  if (row.return_group) return setGroup(row.return_group, false)
  const current = quantities.value[row.item_code] || 0
  quantities.value[row.item_code] = Math.max(0, current - 1)
}

// Serialized returns: the cashier must scan/type each serial (forcing them to
// read the actual unit), and it must be one that was sold on this invoice and is
// still returnable — no blind tapping from a list.
function addSerial(row, event) {
  const raw = event.target.value || ''
  const code = raw.trim()
  event.target.value = ''
  if (!code) return
  if (scanOnly.value && !scan.isScan(raw)) {
    scan.reset()
    session.notify(t('Manual entry is off — scan the serial with the scanner.'), true)
    return
  }
  scan.reset()
  const list = selectedSerials.value[row.item_code] || []
  if (list.includes(code)) {
    session.notify(t('Serial {serial} is already added', { serial: code }), true)
    return
  }
  if (!(row.returnable_serials || []).includes(code)) {
    session.notify(t('Serial {serial} was not sold on this invoice (or already returned)', { serial: code }), true)
    return
  }
  selectedSerials.value[row.item_code] = [...list, code]
  quantities.value[row.item_code] = selectedSerials.value[row.item_code].length
}

function removeSerial(itemCode, serial) {
  const list = (selectedSerials.value[itemCode] || []).filter((s) => s !== serial)
  selectedSerials.value[itemCode] = list
  quantities.value[itemCode] = list.length
}

async function submit() {
  busy.value = true
  try {
    const items = {}
    const serials = {}
    for (const [code, qty] of Object.entries(quantities.value)) {
      if (qty > 0) {
        items[code] = qty
        if (selectedSerials.value[code]?.length) serials[code] = selectedSerials.value[code]
      }
    }
    const receipt = await call('lumenpos.api.sales.create_return', {
      invoice: props.invoice,
      items,
      serials,
      refund_mode: refundMode.value,
      return_reason: reasonValue.value,
      return_request: returnRequest.value,
    })
    session.notify(t('Refund completed'))
    emit('done', receipt)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.return-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid var(--border);
}
.return-info { flex: 1; min-width: 0; }
.return-name { font-weight: 600; }
.set-badge {
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 8px;
  margin-inline-start: 6px;
  border-radius: 999px;
  background: rgba(20, 99, 255, 0.12);
  color: var(--brand-dark);
  white-space: nowrap;
}
.small { font-size: 12px; }
.stepper { display: flex; gap: 4px; }
.serial-pick { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.pick-hint { width: 100%; }
.serial-in { width: 180px; }
.serial-chips { width: 100%; display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.serial-chip {
  font-size: 11.5px;
  font-weight: 700;
  font-family: ui-monospace, monospace;
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 10px;
  color: var(--text-muted);
}
.serial-chip.selected {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}
.serial-count {
  font-weight: 800;
  font-size: 17px;
  min-width: 32px;
  text-align: center;
}
.stepper input { width: 64px; text-align: center; padding: 7px 6px; }
.stepper .btn { padding: 7px 12px; }
.refund-summary { margin-top: 16px; }
.refund-amount { margin-bottom: 10px; font-size: 15px; }
.field-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  margin: 8px 0 6px;
}
.refund-rule-note { margin: 6px 0 0; }
.empty { padding: 28px; text-align: center; }
.approval-box {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
  border-radius: var(--radius);
  background: rgba(245, 166, 35, 0.12);
}
.approval-box.approved,
.approval-box:has(.ap-ok) { background: rgba(20, 99, 255, 0.1); }
.ap-warn { flex: 1; min-width: 220px; font-weight: 600; color: #9a6a0a; }
.ap-text { flex: 1; min-width: 160px; font-weight: 600; }
.ap-ok { flex: 1; font-weight: 700; color: var(--brand-dark); display: flex; align-items: center; gap: 6px; }
.btn-sm { padding: 6px 12px; font-size: 13px; }
.spinner-sm {
  width: 20px;
  height: 20px;
  border: 2.5px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
