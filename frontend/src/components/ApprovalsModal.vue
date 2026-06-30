<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 540px">
      <div class="modal-header">
        {{ t('Approvals') }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <div v-if="loading && !requests.length" class="muted center pad">{{ t('Loading…') }}</div>
        <div v-else-if="!requests.length" class="muted center pad">
          {{ t('No pending requests') }}
        </div>
        <div v-else class="req-list">
          <div v-for="r in requests" :key="r.name" class="req card">
            <div class="req-top">
              <span class="type-chip" :class="r.request_type === 'Return' ? 'ret' : 'disc'">
                {{ r.request_type === 'Return' ? t('Return') : t('Discount') }}
              </span>
              <span class="muted small">{{ clock(r.creation) }}</span>
            </div>
            <div class="req-meta">
              <div>{{ t('Cashier') }}: <strong>{{ r.cashier_name || r.cashier }}</strong></div>
              <div v-if="r.request_type === 'Discount'" class="headline">
                {{ r.discount_percent }}%<span v-if="r.cart_total" class="muted"> · {{ money(r.cart_total) }}</span>
              </div>
              <div v-else class="headline">
                {{ r.return_invoice }}<span v-if="r.invoice_age_days != null" class="muted"> · {{ t('{n} days old', { n: r.invoice_age_days }) }}</span>
              </div>
              <div v-if="r.customer_name" class="muted">{{ t('Customer') }}: {{ r.customer_name }}</div>
              <div v-if="r.reason" class="reason">"{{ r.reason }}"</div>
            </div>
            <div class="req-actions">
              <button class="btn btn-outline danger" :disabled="busy === r.name" @click="reject(r)">
                {{ t('Reject') }}
              </button>
              <button class="btn btn-primary" :disabled="busy === r.name" @click="approve(r)">
                {{ busy === r.name ? t('…') : t('Approve') }}
              </button>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-outline" :disabled="loading" @click="refresh">{{ t('Refresh') }}</button>
        <button class="btn btn-primary" @click="$emit('close')">{{ t('Done') }}</button>
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

const emit = defineEmits(['close', 'changed'])
const session = useSessionStore()

const requests = ref([])
const loading = ref(false)
const busy = ref(null)
let timer = null

function clock(creation) {
  return (String(creation || '').split(' ')[1] || '').slice(0, 5)
}

async function refresh() {
  loading.value = true
  try {
    requests.value = await call('lumenpos.api.approval_requests.pending_requests', {})
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    loading.value = false
  }
}

async function approve(r) {
  busy.value = r.name
  try {
    await call('lumenpos.api.approval_requests.approve_request', { name: r.name })
    session.notify(t('Request approved'))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = null
    await refresh()
    emit('changed')
  }
}

async function reject(r) {
  busy.value = r.name
  try {
    await call('lumenpos.api.approval_requests.reject_request', { name: r.name })
    session.notify(t('Request rejected'))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    busy.value = null
    await refresh()
    emit('changed')
  }
}

onMounted(() => {
  refresh()
  timer = setInterval(refresh, 5000) // keep the queue live while open
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.center { text-align: center; }
.pad { padding: 28px 0; }
.req-list { display: flex; flex-direction: column; gap: 10px; }
.req { padding: 12px 14px; }
.req-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.type-chip {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
  padding: 3px 10px;
  border-radius: 999px;
}
.type-chip.disc { background: rgba(20, 99, 255, 0.14); color: var(--brand-dark); }
.type-chip.ret { background: rgba(245, 166, 35, 0.16); color: #9a6a0a; }
.headline { font-size: 18px; font-weight: 800; margin: 2px 0; }
.req-meta { font-size: 13px; line-height: 1.5; }
.reason { font-style: italic; color: var(--text-muted); margin-top: 4px; }
.req-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 10px;
}
.btn.danger { color: var(--red); }
.small { font-size: 11.5px; }
</style>
