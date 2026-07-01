<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal" style="width: 660px; max-width: 94vw">
      <div class="modal-header">
        {{ t('Offline sales log') }}
        <button class="btn-ghost close" @click="$emit('close')"><Icon name="close" /></button>
      </div>
      <div class="modal-body">
        <p class="muted small intro">
          {{ t('Every sale made while offline, and what happened to it on reconnect. A sale stays here as Pending until it has uploaded — nothing is removed until the server confirms it.') }}
        </p>

        <div class="ol-summary">
          <span class="ol-chip pending"><b>{{ counts.pending }}</b> {{ t('Pending') }}</span>
          <span class="ol-chip synced"><b>{{ counts.synced }}</b> {{ t('Uploaded') }}</span>
          <span v-if="counts.failed" class="ol-chip failed"><b>{{ counts.failed }}</b> {{ t('Needs attention') }}</span>
        </div>

        <div v-if="!rows.length" class="muted small empty">{{ t('No offline sales recorded yet.') }}</div>
        <table v-else class="ol-table">
          <thead>
            <tr>
              <th>{{ t('Time') }}</th>
              <th>{{ t('Customer') }}</th>
              <th class="num">{{ t('Total') }}</th>
              <th>{{ t('Status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in rows" :key="r.key">
              <td class="muted small nowrap">{{ fmtTime(r.queued_at) }}</td>
              <td>
                {{ r.customer_name }}
                <span class="muted small"> · {{ t('{n} items', { n: r.item_count }) }}</span>
              </td>
              <td class="num">{{ money(r.total) }}</td>
              <td>
                <span class="ol-badge" :class="r.status">
                  <template v-if="r.status === 'synced'">✓ {{ r.receipt || t('Uploaded') }}</template>
                  <template v-else-if="r.status === 'failed'">⚠ {{ t('Rejected') }}</template>
                  <template v-else>◔ {{ t('Pending') }}</template>
                </span>
                <div v-if="r.status === 'failed' && r.error" class="ol-error">{{ r.error }}</div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="modal-footer">
        <span v-if="session.offline" class="muted small">{{ t('⚠ Offline — queued sales upload when the connection returns') }}</span>
        <span style="flex: 1" />
        <button class="btn btn-outline" @click="refresh"><Icon name="refresh" /> {{ t('Refresh') }}</button>
        <button
          v-if="counts.pending || counts.failed"
          class="btn btn-primary"
          :disabled="session.offline || session.syncing"
          @click="syncNow"
        >
          {{ session.syncing ? t('Syncing…') : t('Sync now') }}
        </button>
        <button v-else class="btn btn-primary" @click="$emit('close')">{{ t('Close') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { t } from '../i18n'
import { money } from '../format'
import { listSaleLog } from '../offline'
import { useSessionStore } from '../stores/session'

defineEmits(['close'])
const session = useSessionStore()
const rows = ref([])

const counts = computed(() => ({
  pending: rows.value.filter((r) => r.status === 'pending').length,
  synced: rows.value.filter((r) => r.status === 'synced').length,
  failed: rows.value.filter((r) => r.status === 'failed').length,
}))

async function refresh() {
  rows.value = await listSaleLog().catch(() => [])
}

async function syncNow() {
  await session.reconnect()
  await refresh()
}

function fmtTime(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

onMounted(refresh)
</script>

<style scoped>
.modal-header { display: flex; align-items: center; gap: 6px; }
.close { margin-inline-start: auto; }
.intro { margin: 0 0 12px; }
.ol-summary { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.ol-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 700;
  padding: 4px 11px;
  border-radius: 999px;
}
.ol-chip b { font-weight: 800; }
.ol-chip.pending { background: rgba(245, 166, 35, 0.16); color: #b9791a; }
.ol-chip.synced { background: rgba(34, 197, 94, 0.16); color: #1a8f4c; }
.ol-chip.failed { background: rgba(226, 48, 48, 0.14); color: #c23434; }
.empty { padding: 20px 0; text-align: center; }
.ol-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ol-table th {
  text-align: start;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
.ol-table td { padding: 8px; border-bottom: 1px solid var(--border-subtle); vertical-align: top; }
.ol-table .num { text-align: end; font-variant-numeric: tabular-nums; }
.nowrap { white-space: nowrap; }
.ol-badge {
  display: inline-flex;
  align-items: center;
  font-size: 11.5px;
  font-weight: 700;
  padding: 2px 9px;
  border-radius: 999px;
  white-space: nowrap;
}
.ol-badge.pending { background: rgba(245, 166, 35, 0.16); color: #b9791a; }
.ol-badge.synced { background: rgba(34, 197, 94, 0.16); color: #1a8f4c; }
.ol-badge.failed { background: rgba(226, 48, 48, 0.14); color: #c23434; }
.ol-error { margin-top: 3px; color: #c23434; font-size: 11.5px; max-width: 220px; }
</style>
