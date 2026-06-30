<template>
  <div class="lock-overlay">
    <div class="lock-card">
      <div class="lock-mark"><Icon name="shield" :size="32" /></div>
      <div class="lock-title">{{ t('Till locked') }}</div>
      <div class="lock-sub">{{ t('Enter a manager PIN to unlock.') }}</div>
      <form @submit.prevent="unlock">
        <input
          ref="input"
          v-model="pin"
          type="password"
          inputmode="numeric"
          class="lock-input"
          :placeholder="t('PIN')"
          autocomplete="off"
          @input="error = ''"
        />
        <div v-if="error" class="lock-error">{{ error }}</div>
        <button class="btn btn-primary btn-lg lock-btn" :disabled="checking">
          {{ checking ? t('Checking…') : t('Unlock') }}
        </button>
      </form>
      <div class="lock-user">{{ session.userFullname }} · {{ session.posProfile }}</div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, onMounted } from 'vue'
import { t } from '../i18n'
import { call } from '../api'
import { useSessionStore } from '../stores/session'

const session = useSessionStore()
const pin = ref('')
const error = ref('')
const checking = ref(false)
const input = ref(null)

onMounted(() => input.value?.focus())

async function unlock() {
  if (checking.value) return
  checking.value = true
  error.value = ''
  try {
    const res = await call('lumenpos.api.session.unlock_till', { passcode: pin.value })
    if (res.ok) {
      pin.value = ''
      session.locked = false
    } else {
      error.value = t('Wrong PIN')
      pin.value = ''
      input.value?.focus()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    checking.value = false
  }
}
</script>

<style scoped>
.lock-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: var(--topbar-bg, #0a0e1a);
  display: flex;
  align-items: center;
  justify-content: center;
}
.lock-card {
  background: var(--card-bg, #fff);
  border-radius: var(--radius-lg, 20px);
  padding: 40px 36px;
  width: 340px;
  max-width: 90vw;
  text-align: center;
  box-shadow: var(--shadow-brand, 0 20px 60px rgba(20, 99, 255, 0.35));
}
.lock-mark {
  width: 64px;
  height: 64px;
  border-radius: 18px;
  margin: 0 auto 16px;
  background: var(--brand-soft, rgba(20, 99, 255, 0.12));
  color: var(--brand, #1463ff);
  display: flex;
  align-items: center;
  justify-content: center;
}
.lock-title { font-size: 20px; font-weight: 800; }
.lock-sub { color: var(--text-muted); margin: 6px 0 20px; font-size: 13.5px; }
.lock-input {
  width: 100%;
  padding: 12px 14px;
  font-size: 20px;
  text-align: center;
  letter-spacing: 0.3em;
  border-radius: 12px;
  margin-bottom: 12px;
}
.lock-error { color: var(--red); font-size: 13px; margin-bottom: 10px; font-weight: 600; }
.lock-btn { width: 100%; border-radius: 12px; }
.lock-user { margin-top: 18px; font-size: 12px; color: var(--text-muted); }
</style>
