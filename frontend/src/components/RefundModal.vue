<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 520px">
      <div class="modal-header">
        {{ isExchange ? t('Exchange {invoice}', { invoice }) : t('Refund {invoice}', { invoice }) }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="muted empty">{{ t('Loading…') }}</div>
        <template v-else>
          <!-- Products the shop never takes back. No request clears these. -->
          <div v-if="blockedOutright.length" class="approval-box rejected">
            <div class="ap-warn">
              {{ t('These items are never taken back: {items}', { items: blockedNames }) }}
            </div>
          </div>
          <div v-if="overWindow && canExceed" class="approval-box authorized">
            <div class="ap-ok">
              <Icon name="check" />
              {{ t('This sale is {age} days old (past the {n}-day window), you are authorized to return it.', { age: returnWindow.age_days, n: returnWindow.window_days }) }}
            </div>
          </div>
          <div v-else-if="overWindow || restrictedNeedingApproval.length" class="approval-box" :class="reqPhase">
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
              <div v-if="restrictedNeedingApproval.length" class="ap-warn">
                {{ t('These items come back only with approval: {items}', { items: restrictedNames }) }}
              </div>
              <div v-else class="ap-warn">
                {{ t('This sale is {age} days old. Returns are limited to {n} days, a manager must approve this return.', { age: returnWindow.age_days, n: returnWindow.window_days }) }}
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
                <span v-if="row.return_group" class="set-badge">{{ t('Set, return together') }}</span>
                <span v-if="restrictions[row.item_code]" class="no-return-badge">
                  {{ restrictions[row.item_code].needs_approval ? t('Needs approval') : t('Not returnable') }}
                </span>
              </div>
              <div v-if="restrictions[row.item_code]" class="muted small no-return-why">
                {{ restrictions[row.item_code].note || restrictions[row.item_code].title }}
              </div>
              <div class="muted small">
                {{ t('Sold {qty} × {rate} · {returnable} returnable', { qty: row.qty, rate: m(row.rate), returnable: row.returnable_qty }) }}
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
              {{ isExchange ? t('Coming back ≈') : t('Refund ≈') }} <strong>{{ m(refundTotal) }}</strong>
              <span v-if="foreign" class="muted small">= {{ money(refundTotal * sold.rate, sold.company_currency) }}</span>
              <span class="muted small">{{ t('(final amount includes taxes, computed on submit)') }}</span>
            </div>
            <label class="field-label">{{ t('Return reason') }}</label>
            <select v-model="reason" style="width: 100%">
              <option :value="null" disabled>{{ t('Select a reason…') }}</option>
              <!-- The value posted is the stored wording, so the invoice keeps one
                   canonical reason. Only the label is translated, and a reason an
                   admin typed falls through t() unchanged. -->
              <option v-for="r in reasons" :key="r" :value="r">{{ t(r) }}</option>
              <option value="__other__">{{ t('Other (write a reason)…') }}</option>
            </select>
            <input
              v-if="reason === '__other__'"
              v-model="otherReason"
              :placeholder="t('Type the reason…')"
              style="width: 100%; margin-top: 6px"
            />
            <!-- An exchange settles at the payment screen, against the new
                 items, so there is nothing to allocate here. -->
            <template v-if="!isExchange">
            <label class="field-label">{{ t('Refund to') }}</label>
            <!-- Split a refund across tenders (the customer may have paid two
                 ways). DIRECTION matters: refunding is limited to the allowed
                 refund methods, unlike collecting. -->
            <div v-for="(row, i) in refundSplits" :key="'rs' + i" class="refund-split">
              <select v-model="row.mode_of_payment" class="rs-mode">
                <option v-for="mode in refundModes" :key="mode" :value="mode">{{ mode }}</option>
              </select>
              <input class="rs-amt" type="text" inputmode="decimal" v-model="row.amount" :placeholder="t('Amount')" />
              <!-- A sale in another currency is refunded in it; local cash and
                   card go back at the sale's own rate. -->
              <span v-if="foreign && localMode(row.mode_of_payment)" class="muted small rs-local">
                = {{ money((parseMoney(row.amount) || 0) * sold.rate, sold.company_currency) }}
              </span>
              <input
                v-if="refRule(row.mode_of_payment)"
                class="rs-ref"
                v-model="row.reference_no"
                :placeholder="refRule(row.mode_of_payment).reference_label || t('Reference')"
              />
              <button v-if="refundSplits.length > 1" class="btn-ghost" @click="refundSplits.splice(i, 1)">
                <Icon name="close" />
              </button>
            </div>
            <div class="rs-foot">
              <button class="btn btn-outline btn-sm" @click="addSplit">
                <Icon name="plus" /> {{ t('Split') }}
              </button>
              <span class="muted small" :class="{ neg: !splitCovered }">
                {{ splitCovered
                    ? t('Fully covered')
                    : t('{amount} left to allocate', { amount: m(Math.max(refundTotal - splitTotal, 0)) }) }}
              </span>
            </div>
            <p v-if="allowedModes" class="muted small refund-rule-note">
              {{ t('Limited to how this sale was paid (Settings → Refunds).') }}
            </p>
            </template>
            <p v-else class="muted small refund-rule-note">
              {{ t('Next you pick what the customer takes instead. Only the difference is paid or refunded.') }}
            </p>
          </div>
        </template>
      </div>

      <div class="modal-footer">
        <button class="btn btn-outline" @click="$emit('close')">{{ t('Cancel') }}</button>
        <button
          v-if="isExchange"
          class="btn btn-primary"
          :disabled="refundTotal <= 0 || !reasonValue || busy || needsApproval"
          @click="continueExchange"
        >
          {{ t('Pick the new items') }}
        </button>
        <button
          v-else
          class="btn btn-danger"
          :disabled="refundTotal <= 0 || !reasonValue || busy || needsApproval || !splitCovered"
          @click="submit"
        >
          {{ busy ? t('Refunding…') : t('Refund') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { useCatalogStore } from '../stores/catalog'
import { createScanGuard } from '../scanGuard'
import { money, parseMoney } from '../format'
import { t } from '../i18n'

// mode "exchange" reuses everything a return needs (line picking, serials, the
// restriction and window approvals, the reason) and then hands the selection to
// the sell screen instead of refunding: the money is settled once the customer
// has chosen what they are taking instead.
const props = defineProps({ invoice: String, mode: { type: String, default: 'refund' } })
const emit = defineEmits(['close', 'done', 'exchange'])
const isExchange = computed(() => props.mode === 'exchange')
const session = useSessionStore()
const scan = createScanGuard()
const scanOnly = computed(() => Boolean(session.settings?.serial_scan_only))

const loading = ref(true)
const busy = ref(false)
const returnable = ref([])
const quantities = ref({})
const selectedSerials = ref({}) // item_code -> [serials]
const refundMode = ref(null)
const refundSplits = ref([])

function refRule(mode) {
  const m = (session.paymentModes || []).find((x) => x.mode_of_payment === mode)
  return m && (m.require_reference || m.reference_label) ? m : null
}
const splitTotal = computed(() =>
  refundSplits.value.reduce((sum, r) => sum + (parseMoney(r.amount) || 0), 0)
)
// To the cent, a refund that doesn't add up must not post.
const splitCovered = computed(() => Math.abs(splitTotal.value - refundTotal.value) < 0.005)
function addSplit() {
  const left = Math.max(refundTotal.value - splitTotal.value, 0)
  refundSplits.value.push({
    mode_of_payment: refundMode.value || refundModes.value[0],
    amount: left ? left.toFixed(2) : '',
    reference_no: '',
  })
}
const allowedModes = ref(null) // null = no restriction; else array from the server
// item_code -> {title, note, needs_approval} from POS Return Restriction
const restrictions = ref({})
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

// The sale being returned: its currency and the rate it was sold at
// (lumenpos.currency). Everything here is in that currency.
const sold = ref({ currency: null, company_currency: null, rate: 1 })
const foreign = computed(
  () => Boolean(sold.value.currency && sold.value.company_currency) && sold.value.currency !== sold.value.company_currency
)
const m = (amount) => money(amount, sold.value.currency)

function modeCurrency(mode) {
  const found = (session.paymentModes || []).find((x) => x.mode_of_payment === mode)
  return found?.account_currency || sold.value.company_currency
}
function localMode(mode) {
  return modeCurrency(mode) !== sold.value.currency
}

const refundModes = computed(() => {
  // When the original sale restricts refund tenders, offer only those;
  // otherwise every payment method (plus store credit).
  let modes = allowedModes.value
    ? [...allowedModes.value]
    : session.paymentModes.map((x) => x.mode_of_payment)
  if (!allowedModes.value && !modes.includes(session.storeCreditMode)) modes.push(session.storeCreditMode)
  // A sale in another currency goes back through tenders ERPNext accepts for
  // it (its own currency or the local one), never onto a wallet: their
  // ledgers hold the outlet's currency only.
  if (foreign.value) {
    const wallets = [session.storeCreditMode, session.cashbackMode, session.giftCardMode]
    modes = modes.filter(
      (mode) =>
        !wallets.includes(mode) &&
        [sold.value.currency, sold.value.company_currency].includes(modeCurrency(mode))
    )
  } else {
    // ...and a local sale never through a drawer in another currency.
    modes = modes.filter((mode) => {
      const code = modeCurrency(mode)
      return !code || code === sold.value.company_currency || code === sold.value.currency
    })
  }
  return modes
})

const refundTotal = computed(() =>
  returnable.value.reduce(
    (sum, row) => sum + (quantities.value[row.item_code] || 0) * row.rate,
    0
  )
)

// Declared after everything it reads: an immediate watcher runs at setup, and
// placed above refundTotal it threw on its first read and never tracked
// anything, so the refund row never filled itself in (since 0.36.0).
// Keep ONE row tracking the full refund until the cashier deliberately splits;
// after that their allocation is left alone.
watch(
  () => [refundTotal.value, refundMode.value],
  () => {
    if (refundTotal.value <= 0) {
      refundSplits.value = []
      return
    }
    if (refundSplits.value.length <= 1) {
      refundSplits.value = [
        {
          mode_of_payment: refundMode.value || refundModes.value[0],
          amount: refundTotal.value.toFixed(2),
          reference_no: refundSplits.value[0]?.reference_no || '',
        },
      ]
    }
  },
  { immediate: true }
)

// Over the regular-return window and not yet approved → the refund is blocked
// until a manager approves a Return request, unless this user is allowed to
// exceed the window (the "exceed return window" role, or a manager).
const overWindow = computed(() => returnWindow.value && !returnWindow.value.within)
const canExceed = computed(() => session.permissions?.can_exceed_return_window === true)

// What the shop refuses to take back, for the lines actually being returned.
// Rules marked "an approved request can still return it" clear with the SAME
// Return request as an over-window return; the others never clear.
const pickedRestricted = computed(() =>
  returnable.value
    .filter((row) => (quantities.value[row.item_code] || 0) > 0 && restrictions.value[row.item_code])
    .map((row) => ({ ...restrictions.value[row.item_code], item_name: row.item_name }))
)
const blockedOutright = computed(() => pickedRestricted.value.filter((r) => !r.needs_approval))
const restrictedNeedingApproval = computed(() => pickedRestricted.value.filter((r) => r.needs_approval))
const blockedNames = computed(() => blockedOutright.value.map(describeRestriction).join(', '))
const restrictedNames = computed(() =>
  restrictedNeedingApproval.value.map(describeRestriction).join(', ')
)
function describeRestriction(r) {
  return r.note ? `${r.item_name} (${r.note})` : r.item_name
}

const needsApproval = computed(() => {
  if (blockedOutright.value.length) return true
  if (restrictedNeedingApproval.value.length && !returnRequest.value) return true
  return overWindow.value && !returnRequest.value && !canExceed.value
})

onMounted(async () => {
  try {
    const data = await call('lumenpos.api.sales.get_returnable', {
      invoice: props.invoice,
      pos_profile: session.posProfile,
    })
    returnable.value = (data.items || []).filter((row) => row.returnable_qty > 0)
    allowedModes.value = data.allowed_refund_modes || null
    sold.value = {
      currency: data.currency || session.currency,
      company_currency: data.company_currency || session.localCurrency,
      rate: data.conversion_rate || 1,
    }
    returnWindow.value = data.return_window || null
    restrictions.value = data.restrictions || {}
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
      // What is actually being returned, so the approver can judge it.
      details: returnable.value
        .filter((r) => (quantities.value[r.item_code] || 0) > 0)
        .map((r) => quantities.value[r.item_code] + ' x ' + r.item_name)
        .join(String.fromCharCode(10)),
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
          : t('The request expired, the register was closed.')
    }
  } catch {
    /* transient. Keep polling */
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
// still returnable, no blind tapping from a list.
function addSerial(row, event) {
  const raw = event.target.value || ''
  const code = raw.trim()
  event.target.value = ''
  if (!code) return
  if (scanOnly.value && !scan.isScan(raw)) {
    scan.reset()
    session.notify(t('Manual entry is off. Scan the serial with the scanner.'), true)
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

function pickedItems() {
  const items = {}
  const serials = {}
  for (const [code, qty] of Object.entries(quantities.value)) {
    if (qty > 0) {
      items[code] = qty
      if (selectedSerials.value[code]?.length) serials[code] = selectedSerials.value[code]
    }
  }
  return { items, serials }
}

// Exchange: nothing posts here. The till carries the selection to the sell
// screen, and the pair (credit note + new sale) posts together at payment.
function continueExchange() {
  const { items, serials } = pickedItems()
  emit('exchange', {
    invoice: props.invoice,
    items,
    serials,
    reason: reasonValue.value,
    request: returnRequest.value,
    value: refundTotal.value,
    customer: customer.value,
    customer_name: customerName.value,
  })
}

async function submit() {
  busy.value = true
  try {
    const { items, serials } = pickedItems()
    const receipt = await call('lumenpos.api.sales.create_return', {
      invoice: props.invoice,
      items,
      serials,
      refund_mode: refundMode.value,
      refund_payments: JSON.stringify(
        refundSplits.value
          .filter((r) => r.mode_of_payment && (parseMoney(r.amount) || 0) > 0)
          .map((r) => ({
            mode_of_payment: r.mode_of_payment,
            amount: parseMoney(r.amount),
            reference_no: r.reference_no || null,
          }))
      ),
      return_reason: reasonValue.value,
      return_request: returnRequest.value,
      // The return posts on the outlet HANDLING it, not the one that sold, 
      // otherwise the refund leaves this drawer under another outlet's name.
      pos_profile: session.posProfile,
    })
    session.notify(t('Refund completed'))
    useCatalogStore().applyStock(receipt?.stock_after) // returned goods go back on the tiles
    emit('done', receipt)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.refund-split { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.rs-mode { flex: 1; min-width: 120px; }
.rs-amt { width: 110px; }
.rs-ref { flex: 1; min-width: 110px; }
.rs-foot { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.rs-foot .neg { color: var(--red, #e23030); font-weight: 700; }
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
/* A line the shop restricts: amber when an approver can still let it through,
   red when it never comes back. */
.no-return-badge {
  font-size: 10.5px;
  font-weight: 700;
  padding: 2px 8px;
  margin-inline-start: 6px;
  border-radius: 999px;
  background: rgba(245, 166, 35, 0.16);
  color: #9a6a0a;
  white-space: nowrap;
}
.no-return-why {
  margin-top: 2px;
  color: #9a6a0a;
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
