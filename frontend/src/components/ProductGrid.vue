<template>
  <div class="grid-wrap">
    <div v-if="catalog.loading" class="grid-empty">{{ t('Loading…') }}</div>
    <div v-else-if="!visibleItems.length" class="grid-empty">
      {{ t('No products found') }}
    </div>
    <div v-else class="grid">
      <button
        v-for="item in visibleItems"
        :key="item.item_code"
        class="tile card"
        @click="$emit('select', item)"
      >
        <div class="tile-img">
          <img v-if="item.image" :src="item.image" :alt="item.item_name" loading="lazy" />
          <span v-else>{{ initials(item.item_name) }}</span>
        </div>
        <div class="tile-name">{{ item.item_name }}</div>
        <div class="tile-foot">
          <span class="tile-price">{{ money(item.price) }}</span>
          <span class="tile-tags">
            <span v-if="item.has_serial_no" class="tile-serial" :title="t('Serialized — serial number required')">{{ t('S/N') }}</span>
            <span
              v-if="item.is_stock_item"
              class="tile-stock"
              :class="{ low: item.actual_qty <= 0 }"
            >{{ item.actual_qty }}</span>
          </span>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useCatalogStore } from '../stores/catalog'
import { useSessionStore } from '../stores/session'
import { money } from '../format'
import { t } from '../i18n'

defineEmits(['select'])
const catalog = useCatalogStore()
const session = useSessionStore()

// Hide out-of-stock stock items unless the outlet opts in (Settings → General).
// Non-stock items (services, gift cards) always show.
const visibleItems = computed(() => {
  if (session.settings?.show_out_of_stock) return catalog.items
  return catalog.items.filter((i) => !i.is_stock_item || (i.actual_qty || 0) > 0)
})

function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
}
</script>

<style scoped>
.grid-wrap {
  flex: 1;
  overflow-y: auto;
  margin-top: 10px;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  padding-bottom: 20px;
}
.tile {
  display: flex;
  flex-direction: column;
  text-align: left;
  padding: 0 0 10px;
  overflow: hidden;
  border: 1px solid transparent;
  transition: border-color 0.1s, transform 0.05s;
}
.tile:hover { border-color: var(--brand-soft); }
.tile:active { transform: scale(0.98); }
.tile-img {
  height: 92px;
  background: linear-gradient(135deg, var(--surface-2), var(--border-subtle));
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-weight: 800;
  font-size: 24px;
}
.tile-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.tile-name {
  padding: 8px 10px 2px;
  font-weight: 600;
  font-size: 13px;
  line-height: 1.3;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 36px;
}
.tile-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 10px;
}
.tile-price {
  font-weight: 700;
  font-size: 13.5px;
}
.tile-stock {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  background: var(--surface-2);
  border-radius: 999px;
  padding: 1px 8px;
}
.tile-stock.low {
  color: var(--red);
  background: rgba(226, 48, 48, 0.1);
}
.tile-tags { display: flex; gap: 4px; align-items: center; }
.tile-serial {
  font-size: 10px;
  font-weight: 800;
  color: var(--brand-soft);
  background: rgba(0, 176, 185, 0.12);
  border-radius: 999px;
  padding: 1px 7px;
  letter-spacing: 0.04em;
}
.grid-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--text-muted);
}
</style>
