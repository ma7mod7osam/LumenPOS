<template>
  <div class="cdisplay">
    <header class="cd-head">
      <img v-if="snap.logo" :src="snap.logo" class="cd-logo" alt="" />
      <div class="cd-company">{{ snap.company || t('Welcome') }}</div>
      <div v-if="snap.customer" class="cd-customer">{{ snap.customer }}</div>
    </header>

    <div v-if="snap.items.length" class="cd-cart">
      <div class="cd-items">
        <div v-for="(it, i) in snap.items" :key="i" class="cd-item">
          <div class="cd-item-main">
            <div class="cd-item-name">{{ it.name }}</div>
            <div class="cd-item-qty">{{ it.qty }} × {{ it.rate }}</div>
          </div>
          <div class="cd-item-amt">{{ it.amount }}</div>
        </div>
      </div>
      <div class="cd-totals">
        <div v-if="snap.savings" class="cd-row cd-save">
          <span>{{ t('You save') }}</span><span>{{ snap.savings }}</span>
        </div>
        <div class="cd-row cd-grand">
          <span>{{ t('Total') }}</span><span>{{ snap.total }}</span>
        </div>
        <div class="cd-count">{{ t('{count} items', { count: snap.count }) }}</div>
      </div>
    </div>

    <div v-else class="cd-welcome">
      <div class="cd-welcome-mark">{{ (snap.company || 'L').slice(0, 1) }}</div>
      <div class="cd-welcome-text">{{ t('Welcome') }}</div>
      <div class="cd-welcome-sub">{{ snap.company }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { t } from '../i18n'
import { onCart } from '../customerDisplay'

const snap = ref({ company: '', logo: '', items: [], count: 0, total: '', savings: '', customer: '' })
let stop = null

onMounted(() => {
  stop = onCart((s) => {
    snap.value = { items: [], count: 0, total: '', savings: '', customer: '', company: '', logo: '', ...s }
  })
})
onBeforeUnmount(() => stop && stop())
</script>

<style scoped>
.cdisplay {
  position: fixed;
  inset: 0;
  background: var(--bg, #0a0e1a);
  color: var(--text, #fff);
  display: flex;
  flex-direction: column;
  padding: 4vh 4vw;
  font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
}
.cd-head {
  text-align: center;
  padding-bottom: 3vh;
  border-bottom: 2px solid var(--border, rgba(255, 255, 255, 0.12));
}
.cd-logo { max-height: 12vh; max-width: 60%; object-fit: contain; margin-bottom: 2vh; }
.cd-company { font-size: 4vh; font-weight: 800; letter-spacing: -0.01em; }
.cd-customer { font-size: 2.2vh; color: var(--brand, #1463ff); font-weight: 700; margin-top: 0.5vh; }
.cd-cart { flex: 1; display: flex; flex-direction: column; min-height: 0; padding-top: 2vh; }
.cd-items { flex: 1; overflow-y: auto; min-height: 0; }
.cd-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 3vw;
  padding: 2vh 0;
  border-bottom: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
}
.cd-item-name { font-size: 3vh; font-weight: 700; }
.cd-item-qty { font-size: 2.2vh; color: var(--text-muted, #9aa4bf); margin-top: 0.4vh; }
.cd-item-amt { font-size: 3.2vh; font-weight: 800; white-space: nowrap; }
.cd-totals { padding-top: 2vh; border-top: 3px solid var(--brand, #1463ff); }
.cd-row { display: flex; justify-content: space-between; }
.cd-save { color: var(--brand, #1463ff); font-size: 2.6vh; font-weight: 700; margin-bottom: 1vh; }
.cd-grand { font-size: 5.5vh; font-weight: 900; }
.cd-count { text-align: right; font-size: 2vh; color: var(--text-muted, #9aa4bf); margin-top: 1vh; }
.cd-welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2vh; }
.cd-welcome-mark {
  width: 16vh;
  height: 16vh;
  border-radius: 4vh;
  background: linear-gradient(135deg, #1463ff, #2f7bff);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 9vh;
  font-weight: 900;
  box-shadow: 0 1vh 4vh rgba(20, 99, 255, 0.4);
}
.cd-welcome-text { font-size: 5vh; font-weight: 800; }
.cd-welcome-sub { font-size: 2.6vh; color: var(--text-muted, #9aa4bf); }
</style>
