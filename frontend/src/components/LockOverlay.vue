<template>
  <div class="lock-overlay">
    <div class="lock-card">
      <div class="lock-mark"><Icon name="shield" :size="32" /></div>

      <!-- enter: your own PIN. create: you don't have one yet. forgot: emailed code. -->
      <template v-if="mode === 'enter'">
        <div class="lock-title">{{ t('Till locked') }}</div>
        <div class="lock-sub">{{ t('Enter your PIN to unlock.') }}</div>
        <form @submit.prevent="unlock">
          <input
            ref="input"
            v-model="pin"
            type="password"
            inputmode="numeric"
            class="lock-input"
            :placeholder="t('Your PIN')"
            autocomplete="off"
            @input="error = ''"
          />
          <div v-if="error" class="lock-error">{{ error }}</div>
          <button class="btn btn-primary btn-lg lock-btn" :disabled="checking">
            {{ checking ? t('Checking…') : t('Unlock') }}
          </button>
        </form>
        <button class="lock-link" @click="startForgot">{{ t('Forgot your PIN?') }}</button>
      </template>

      <template v-else-if="mode === 'create'">
        <div class="lock-title">{{ t('Create your PIN') }}</div>
        <div class="lock-sub">{{ t('4 to 8 digits. It unlocks this till for you only.') }}</div>
        <form @submit.prevent="createPin">
          <input ref="input" v-model="pin" type="password" inputmode="numeric" class="lock-input"
                 :placeholder="t('New PIN')" autocomplete="off" @input="error = ''" />
          <input v-model="pin2" type="password" inputmode="numeric" class="lock-input"
                 :placeholder="t('Repeat PIN')" autocomplete="off" @input="error = ''" />
          <div v-if="error" class="lock-error">{{ error }}</div>
          <button class="btn btn-primary btn-lg lock-btn" :disabled="checking">
            {{ checking ? t('Saving…') : t('Set PIN') }}
          </button>
        </form>
      </template>

      <template v-else>
        <div class="lock-title">{{ t('Reset your PIN') }}</div>
        <div class="lock-sub">
          {{ sentTo ? t('We emailed a code to {email}.', { email: sentTo }) : t('We will email you a 6-digit code.') }}
        </div>
        <form @submit.prevent="sentTo ? applyReset() : sendCode()">
          <template v-if="sentTo">
            <input ref="input" v-model="code" inputmode="numeric" class="lock-input"
                   :placeholder="t('6-digit code')" autocomplete="off" @input="error = ''" />
            <input v-model="pin" type="password" inputmode="numeric" class="lock-input"
                   :placeholder="t('New PIN')" autocomplete="off" @input="error = ''" />
          </template>
          <div v-if="error" class="lock-error">{{ error }}</div>
          <button class="btn btn-primary btn-lg lock-btn" :disabled="checking">
            {{ checking ? t('Working…') : sentTo ? t('Set PIN') : t('Email me a code') }}
          </button>
        </form>
        <button class="lock-link" @click="mode = 'enter'; error = ''">{{ t('‹ Back') }}</button>
      </template>

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
const pin2 = ref('')
const code = ref('')
const error = ref('')
const sentTo = ref('')
const checking = ref(false)
const input = ref(null)
// A user with no PIN yet must create one before the till can be unlocked —
// there is nothing to check against, and no shared code to fall back on.
const mode = ref(session.pinSet === false ? 'create' : 'enter')

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
    } else if (res.no_pin) {
      mode.value = 'create'
      pin.value = ''
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

async function createPin() {
  if (checking.value) return
  if (pin.value !== pin2.value) {
    error.value = t('The two PINs do not match.')
    return
  }
  checking.value = true
  error.value = ''
  try {
    await call('lumenpos.api.pin.set_pin', { pin: pin.value })
    session.pinSet = true
    pin.value = ''
    pin2.value = ''
    session.locked = false
  } catch (e) {
    error.value = e.message
  } finally {
    checking.value = false
  }
}

function startForgot() {
  mode.value = 'forgot'
  error.value = ''
  sentTo.value = ''
}

async function sendCode() {
  checking.value = true
  error.value = ''
  try {
    const res = await call('lumenpos.api.pin.request_pin_reset')
    sentTo.value = res.email
  } catch (e) {
    error.value = e.message
  } finally {
    checking.value = false
  }
}

async function applyReset() {
  checking.value = true
  error.value = ''
  try {
    await call('lumenpos.api.pin.reset_pin_with_code', { code: code.value, new_pin: pin.value })
    session.pinSet = true
    session.locked = false
    pin.value = ''
    code.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    checking.value = false
  }
}
</script>

<style scoped>
.lock-link {
  background: none;
  border: none;
  color: var(--brand);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  margin-top: 10px;
}
.lock-input + .lock-input { margin-top: 8px; }
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
