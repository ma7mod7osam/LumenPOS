<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<!-- A manager's approval for taking money out of the drawer (0.61.0,
     lumenpos.cash_out): their passcode at the till, or a request from the
     Approvals tray, the way an over-limit discount is approved. The server
     checks it again when the cash out is recorded. -->
<template>
  <div class="modal-backdrop">
    <div class="modal" style="width: 400px" data-tour="cash-out-approval">
      <div class="modal-header">
        {{ t('Cash out approval needed') }}
        <button class="btn-ghost" @click="onClose"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <p class="muted hint">
          {{ t("Taking {amount} out of the drawer needs a manager's approval.", { amount: money(amount, currency) }) }}
        </p>

        <div v-if="phase === 'waiting'" class="waiting">
          <div class="spinner"></div>
          <p class="wait-text">{{ t('Waiting for a manager to approve…') }}</p>
          <p class="muted small">{{ t('Request') }} {{ requestName }}</p>
          <button class="btn btn-outline" @click="cancelRequest">{{ t('Cancel request') }}</button>
        </div>

        <div v-else-if="phase === 'rejected'" class="rejected">
          <p class="error big">{{ rejectedMsg }}</p>
          <button class="btn btn-outline" @click="reset">{{ t('Try again') }}</button>
        </div>

        <template v-else>
          <div class="block">
            <label class="lbl">{{ t('Manager passcode') }}</label>
            <input
              ref="input"
              v-model="passcode"
              type="password"
              :placeholder="t('Passcode')"
              style="width: 100%"
              :disabled="checking"
              @keydown.enter="verify"
            />
            <div v-if="error" class="error">{{ error }}</div>
            <button class="btn btn-primary full" :disabled="!passcode || checking" @click="verify">
              {{ checking ? t('Checking…') : t('Approve with passcode') }}
            </button>
          </div>

          <div class="divider"><span>{{ t('or') }}</span></div>

          <div class="block">
            <label class="lbl">{{ t('Send the request to a manager') }}</label>
            <button class="btn btn-outline full" :disabled="sending" @click="sendRequest">
              {{ sending ? t('Sending…') : t('Send approval request') }}
            </button>
          </div>
        </template>
      </div>
      <div v-if="phase === 'idle'" class="modal-footer">
        <button class="btn btn-outline" @click="onClose">{{ t('Cancel') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, onMounted, onUnmounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money } from '../format'
import { t } from '../i18n'

const props = defineProps({
  amount: { type: Number, required: true },
  currency: { type: String, default: null },
  drawer: { type: String, default: null },
  reason: { type: String, default: '' },
})
const emit = defineEmits(['close', 'approved'])
const session = useSessionStore()

const passcode = ref('')
const error = ref('')
const checking = ref(false)
const sending = ref(false)
const input = ref(null)
const phase = ref('idle') // idle | waiting | rejected
const requestName = ref(null)
const rejectedMsg = ref('')
let pollTimer = null

onMounted(() => input.value?.focus())
onUnmounted(() => clearInterval(pollTimer))

async function verify() {
  if (!passcode.value || checking.value) return
  checking.value = true
  error.value = ''
  try {
    const result = await call('lumenpos.api.settings.verify_passcode', { passcode: passcode.value })
    if (result.valid) {
      emit('approved', { passcode: passcode.value })
    } else {
      error.value = t('Wrong passcode')
      passcode.value = ''
      input.value?.focus()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    checking.value = false
  }
}

async function sendRequest() {
  if (sending.value) return
  sending.value = true
  error.value = ''
  try {
    const res = await call('lumenpos.api.approval_requests.create_request', {
      request_type: 'Cash Out',
      pos_profile: session.posProfile,
      amount: props.amount,
      mode_of_payment: props.drawer || null,
      reason: props.reason || null,
    })
    requestName.value = res.name
    phase.value = 'waiting'
    pollTimer = setInterval(pollStatus, 3000)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    sending.value = false
  }
}

async function pollStatus() {
  try {
    const res = await call('lumenpos.api.approval_requests.request_status', { name: requestName.value })
    if (res.status === 'Approved') {
      clearInterval(pollTimer)
      emit('approved', { request: requestName.value })
    } else if (res.status === 'Rejected' || res.status === 'Expired') {
      clearInterval(pollTimer)
      phase.value = 'rejected'
      rejectedMsg.value =
        res.status === 'Rejected'
          ? res.decision_note
            ? t('Request rejected: {note}', { note: res.decision_note })
            : t('The manager rejected this cash out.')
          : t('The request expired, the register was closed.')
    }
  } catch {
    /* transient. Keep polling */
  }
}

async function cancelRequest() {
  clearInterval(pollTimer)
  if (requestName.value) {
    await call('lumenpos.api.approval_requests.cancel_request', { name: requestName.value }).catch(() => {})
  }
  reset()
}

function reset() {
  phase.value = 'idle'
  requestName.value = null
}

function onClose() {
  clearInterval(pollTimer)
  // Withdraw a still-pending request so it does not linger for approvers.
  if (phase.value === 'waiting' && requestName.value) {
    call('lumenpos.api.approval_requests.cancel_request', { name: requestName.value }).catch(() => {})
  }
  emit('close')
}
</script>

<style scoped>
.hint { margin: 0 0 14px; }
.lbl {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.block { display: flex; flex-direction: column; gap: 8px; }
.full { width: 100%; }
.divider {
  display: flex;
  align-items: center;
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 600;
  margin: 14px 0;
}
.divider::before,
.divider::after {
  content: '';
  flex: 1;
  border-bottom: 1px solid var(--border);
}
.divider span { padding: 0 12px; }
.error {
  color: var(--red);
  font-weight: 600;
  font-size: 13px;
}
.error.big { font-size: 14px; text-align: center; margin: 8px 0 16px; }
.waiting {
  text-align: center;
  padding: 18px 0 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.wait-text { font-weight: 600; margin: 4px 0 0; }
.small { font-size: 11.5px; }
.rejected { padding-top: 8px; text-align: center; }
.spinner {
  width: 34px;
  height: 34px;
  border: 3px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
