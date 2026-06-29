<template>
  <div class="modal-backdrop">
    <div class="modal" style="width: 400px">
      <div class="modal-header">
        {{ t('Discount approval needed') }}
        <button class="btn-ghost" @click="onClose"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <p class="muted hint">
          {{ t('A discount on this sale is above the allowed limit ({percent}%).', { percent: session.settings.discount_limit_percent }) }}
        </p>

        <!-- Waiting for an approver to act on the request -->
        <div v-if="phase === 'waiting'" class="waiting">
          <div class="spinner"></div>
          <p class="wait-text">{{ t('Waiting for a manager to approve…') }}</p>
          <p class="muted small">{{ t('Request') }} {{ requestName }}</p>
          <button class="btn btn-outline" @click="cancelRequest">{{ t('Cancel request') }}</button>
        </div>

        <!-- The request was turned down or expired -->
        <div v-else-if="phase === 'rejected'" class="rejected">
          <p class="error big">{{ rejectedMsg }}</p>
          <button class="btn btn-outline" @click="reset">{{ t('Try again') }}</button>
        </div>

        <!-- Idle: offer passcode and/or request per the configured mode -->
        <template v-else>
          <div v-if="allowPasscode" class="block">
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

          <div v-if="allowPasscode && allowRequest" class="divider"><span>{{ t('or') }}</span></div>

          <div v-if="allowRequest" class="block">
            <label class="lbl">{{ t('Send the request to a manager') }}</label>
            <textarea
              v-model="reason"
              :placeholder="t('Reason (optional)')"
              rows="2"
              style="width: 100%"
            ></textarea>
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { useCartStore } from '../stores/cart'
import { t } from '../i18n'

const emit = defineEmits(['close', 'approved'])
const session = useSessionStore()
const cart = useCartStore()

const mode = computed(() => session.discountApprovalMode)
const allowPasscode = computed(() =>
  ['Passcode only', 'Passcode or request'].includes(mode.value)
)
const allowRequest = computed(() =>
  ['Request only', 'Passcode or request'].includes(mode.value)
)

const passcode = ref('')
const reason = ref('')
const error = ref('')
const checking = ref(false)
const sending = ref(false)
const input = ref(null)
const phase = ref('idle') // idle | waiting | rejected
const requestName = ref(null)
const rejectedMsg = ref('')
let pollTimer = null

onMounted(() => {
  if (allowPasscode.value) input.value?.focus()
})
onUnmounted(() => clearInterval(pollTimer))

async function verify() {
  if (!passcode.value || checking.value) return
  checking.value = true
  error.value = ''
  try {
    const result = await call('lumenpos.api.settings.verify_passcode', {
      passcode: passcode.value,
    })
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
      request_type: 'Discount',
      pos_profile: session.posProfile,
      discount_percent: cart.maxManualDiscount,
      reason: reason.value || null,
      customer: cart.customer?.name || null,
      customer_name: cart.customer?.customer_name || null,
      cart_total: cart.total,
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
    const res = await call('lumenpos.api.approval_requests.request_status', {
      name: requestName.value,
    })
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
            : t('The manager rejected this discount.')
          : t('The request expired — the register was closed.')
    }
  } catch {
    /* transient — keep polling */
  }
}

async function cancelRequest() {
  clearInterval(pollTimer)
  if (requestName.value) {
    await call('lumenpos.api.approval_requests.cancel_request', {
      name: requestName.value,
    }).catch(() => {})
  }
  reset()
}

function reset() {
  phase.value = 'idle'
  requestName.value = null
  reason.value = ''
}

function onClose() {
  clearInterval(pollTimer)
  // Withdraw a still-pending request so it doesn't linger for approvers.
  if (phase.value === 'waiting' && requestName.value) {
    call('lumenpos.api.approval_requests.cancel_request', {
      name: requestName.value,
    }).catch(() => {})
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
