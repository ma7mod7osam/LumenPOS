<template>
  <div class="sell">
    <section class="catalog">
      <div class="search-row">
        <div class="search-box">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" stroke-width="2"/><path d="m21 21-4.3-4.3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          <input
            ref="searchInput"
            :value="catalog.search"
            :placeholder="t('Search products or scan a barcode')"
            @input="onSearchInput($event.target.value)"
            @keydown="scanGuard.onKeydown"
            @keydown.enter="onSearchEnter"
          />
          <button v-if="catalog.search" class="btn-ghost clear" @click="catalog.clearSearch()"><Icon name="close" /></button>
        </div>
        <button
          v-if="session.settings.enable_price_checker"
          class="btn btn-outline"
          :title="t('Look up a price without selling')"
          @click="priceCheckOpen = true"
        >
          <Icon name="search" /> {{ t('Price check') }}
        </button>
        <button
          v-if="session.settings.enable_customer_display"
          class="btn btn-outline"
          :title="t('Open the customer-facing display')"
          @click="openCustomerDisplay"
        >
          <Icon name="store" /> {{ t('Display') }}
        </button>
        <button class="btn btn-outline" @click="parkedOpen = true">
          {{ t('Retrieve Sale') }}
        </button>
      </div>

      <div class="group-bar">
        <button
          v-if="session.settings.enable_quick_keys"
          class="chip chip-fav"
          :class="{ active: showFavourites }"
          @click="toggleFavourites"
        >
          <Icon name="star" /> {{ t('Favourites') }}
        </button>
        <button
          v-if="session.bundles.length"
          class="chip chip-bundle"
          :class="{ active: showBundles }"
          @click="showBundles = !showBundles; showFavourites = false"
        >
          <Icon name="gift" /> {{ t('Bundles') }}
        </button>
        <button
          class="chip"
          :class="{ active: !catalog.itemGroup && !showBundles && !showFavourites }"
          @click="showBundles = false; showFavourites = false; catalog.itemGroup = ''; catalog.fetch()"
        >
          {{ t('All') }}
        </button>
        <div class="group-scroll">
          <button
            v-for="group in session.itemGroups"
            :key="group"
            class="chip"
            :class="{ active: catalog.itemGroup === group }"
            @click="catalog.setGroup(group)"
          >
            {{ group }}
          </button>
        </div>
      </div>

      <div v-if="showBundles" class="bundle-grid">
        <div v-for="bundle in session.bundles" :key="bundle.name" class="bundle-card card">
          <div class="bundle-badge"><Icon name="gift" /> {{ t('BUNDLE') }}</div>
          <div class="bundle-title">{{ bundle.title }}</div>
          <ul class="bundle-list">
            <li v-for="component in bundle.items" :key="component.item_code">
              {{ component.qty }} × {{ component.item_name }}
            </li>
          </ul>
          <div class="bundle-foot">
            <span class="bundle-price">{{ money(bundle.bundle_price) }}</span>
            <button class="btn btn-primary" @click="addBundleToCart(bundle)">{{ t('Add') }}</button>
          </div>
        </div>
        <div v-if="!session.bundles.length" class="muted">{{ t('No bundles configured') }}</div>
      </div>
      <div v-else-if="showFavourites" class="fav-grid">
        <button
          v-for="fav in favourites"
          :key="fav.item_code"
          class="fav-card card"
          @click="addToCart(fav)"
        >
          <div class="fav-name">{{ fav.quick_label || fav.item_name }}</div>
          <div class="fav-price">{{ money(fav.price) }}</div>
          <div v-if="fav.is_stock_item" class="muted small">{{ t('{qty} in stock', { qty: fav.actual_qty }) }}</div>
        </button>
        <div v-if="!favourites.length" class="muted">{{ favLoading ? t('Loading…') : t('No favourites configured — add some in Settings → Features.') }}</div>
      </div>
      <ProductGrid v-else @select="addToCart" />
    </section>

    <CartPanel @pay="onPay" @park="parkOpen = true" @receipt="receipt = $event" />

    <PaymentOverlay v-if="paymentOpen" @close="paymentOpen = false" @done="onSaleDone" />
    <ParkedSalesModal v-if="parkedOpen" @close="parkedOpen = false" />
    <ReceiptModal v-if="receipt" :receipt="receipt" @close="receipt = null" />
    <SerialModal
      v-if="serialItem"
      :item="serialItem"
      @close="serialItem = null"
      @add="onSerialScanned"
    />
    <PasscodeModal
      v-if="passcodeOpen"
      @close="passcodeOpen = false"
      @approved="onDiscountApproved"
    />
    <PriceCheckModal v-if="priceCheckOpen" @close="priceCheckOpen = false" />

    <div v-if="parkOpen" class="modal-backdrop" @click.self="parkOpen = false">
      <div class="modal" style="width: 420px">
        <div class="modal-header">{{ t('Park this sale') }}</div>
        <div class="modal-body">
          <input v-model="parkNote" :placeholder="t('Note (e.g. customer\'s name)')" style="width: 100%" />
        </div>
        <div class="modal-footer">
          <button class="btn btn-outline" @click="parkOpen = false">{{ t('Cancel') }}</button>
          <button class="btn btn-primary" @click="parkSale">{{ t('Park Sale') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from '../components/Icon.vue'
import { ref, onMounted } from 'vue'
import { t } from '../i18n'
import { call } from '../api'
import { money } from '../format'
import { useSessionStore } from '../stores/session'
import { useCatalogStore } from '../stores/catalog'
import { useCartStore } from '../stores/cart'
import ProductGrid from '../components/ProductGrid.vue'
import CartPanel from '../components/CartPanel.vue'
import PaymentOverlay from '../components/PaymentOverlay.vue'
import ParkedSalesModal from '../components/ParkedSalesModal.vue'
import ReceiptModal from '../components/ReceiptModal.vue'
import SerialModal from '../components/SerialModal.vue'
import PasscodeModal from '../components/PasscodeModal.vue'
import PriceCheckModal from '../components/PriceCheckModal.vue'
import { createScanGuard } from '../scanGuard'

const session = useSessionStore()
const scanGuard = createScanGuard()
let scanTimer = null

// A barcode scanner fires characters as a fast burst — add the item the instant
// it's scanned, without waiting for an Enter key (typed searches still need it).
function onSearchInput(value) {
  catalog.setSearch(value)
  clearTimeout(scanTimer)
  if (!value) {
    scanGuard.reset()
    return
  }
  if (value.length >= 3 && scanGuard.isScan(value)) {
    scanTimer = setTimeout(() => {
      if (catalog.search === value) onSearchEnter()
    }, 80)
  }
}
const catalog = useCatalogStore()
const cart = useCartStore()

const paymentOpen = ref(false)
const parkedOpen = ref(false)
const parkOpen = ref(false)
const parkNote = ref('')
const receipt = ref(null)
const searchInput = ref(null)
const serialItem = ref(null)
const priceCheckOpen = ref(false)

onMounted(() => searchInput.value?.focus())

function addToCart(item, serial = null) {
  // Stock guard: no overselling stock items when negative stock is disallowed
  // (serialized items are covered by per-serial validation instead)
  if (!item.has_serial_no && item.is_stock_item && !session.allowNegativeStock && !session.offline) {
    const inCart = cart.lines.find((l) => l.item_code === item.item_code)?.qty || 0
    if (inCart + 1 > (item.actual_qty || 0)) {
      session.notify(t('{item}: only {qty} in stock', { item: item.item_name, qty: item.actual_qty || 0 }), true)
      return
    }
  }
  if (item.has_serial_no && !serial) {
    // Strict: a serialized item can only enter the cart with a scanned serial
    if (session.offline) {
      session.notify(t('Serialized items cannot be sold offline'), true)
      return
    }
    serialItem.value = item
    return
  }
  if (serial && cart.hasSerial(serial)) {
    session.notify(t('Serial {serial} is already in this sale', { serial }), true)
    return
  }
  cart.addItem(item, serial)
}

function onSerialScanned(serial) {
  const item = serialItem.value
  serialItem.value = null
  cart.addItem(item, serial)
}

const showBundles = ref(false)
const showFavourites = ref(false)
const favourites = ref([])
const favLoading = ref(false)

async function toggleFavourites() {
  showFavourites.value = !showFavourites.value
  showBundles.value = false
  if (showFavourites.value && !favourites.value.length) await loadFavourites()
}

function openCustomerDisplay() {
  // Same SPA, hash route — opens (or focuses) a dedicated second-screen window.
  const url = window.location.href.replace(/#.*$/, '') + '#/display'
  window.open(url, 'lumenpos-customer-display', 'width=1024,height=720')
}

async function loadFavourites() {
  favLoading.value = true
  try {
    const res = await call('lumenpos.api.catalog.get_quick_keys', {
      pos_profile: session.posProfile,
    })
    favourites.value = res.items || []
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    favLoading.value = false
  }
}

async function addBundleToCart(bundle) {
  try {
    await cart.addBundle(bundle)
    session.notify(t('{title} added to cart', { title: bundle.title }))
  } catch (e) {
    session.notify(e.message, true)
  }
}

async function onSearchEnter() {
  clearTimeout(scanTimer)
  // Was this entry SCANNED (fast burst) or typed? Capture before resetting the
  // guard — it's needed to enforce "scan only" on a serial entered here.
  const wasScan = scanGuard.isScan(catalog.search)
  scanGuard.reset()
  const term = catalog.search.trim()
  if (!term) return
  // Scanner fast path: barcodes and serial numbers resolve server-side
  if (!session.offline) {
    try {
      const result = await call('lumenpos.api.catalog.resolve_scan', {
        pos_profile: session.posProfile,
        code: term,
        customer_group: cart.customer?.customer_group || null,
        app_type: cart.appType,
      })
      if (result.found) {
        // Scan-only: a serial TYPED into the search box must not bypass the rule
        // (same guard as the serial modal). A scanned serial (burst) is allowed.
        if (result.serial && session.settings.serial_scan_only && !wasScan) {
          session.notify(t('Manual entry is off — scan the serial with the scanner.'), true)
          catalog.clearSearch()
          return
        }
        addToCart(result.item, result.serial)
        catalog.clearSearch()
        return
      }
    } catch {
      /* fall back to the grid below */
    }
  }
  if (catalog.items.length === 1) {
    addToCart(catalog.items[0])
    catalog.clearSearch()
  }
}

async function parkSale() {
  try {
    await cart.park(parkNote.value)
    parkOpen.value = false
    parkNote.value = ''
    session.notify(t('Sale parked'))
  } catch (e) {
    session.notify(e.message, true)
  }
}

function onSaleDone(saleReceipt) {
  paymentOpen.value = false
  receipt.value = saleReceipt
}

const passcodeOpen = ref(false)

function onPay() {
  if (cart.appType && cart.activeApp?.require_order_id && !cart.orderId.trim()) {
    session.notify(t('Enter the {channel} order ID first', { channel: cart.appType }), true)
    return
  }
  if (cart.needsDiscountApproval) {
    passcodeOpen.value = true
    return
  }
  paymentOpen.value = true
}

function onDiscountApproved(result) {
  // Either a manager passcode or an approved discount-request name clears the
  // over-limit gate; the server re-checks whichever was used.
  if (result.passcode) cart.discountPasscode = result.passcode
  if (result.request) cart.discountRequest = result.request
  passcodeOpen.value = false
  paymentOpen.value = true
}
</script>

<style scoped>
.sell {
  flex: 1;
  display: flex;
  min-width: 0;
}
.catalog {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  min-width: 0;
}
.search-row {
  display: flex;
  gap: 10px;
}
.search-box {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}
.search-box svg {
  position: absolute;
  left: 12px;
  width: 18px;
  height: 18px;
  color: var(--text-muted);
}
.search-box input {
  width: 100%;
  padding: 12px 38px 12px 40px;
  font-size: 15px;
  border-radius: 10px;
}
.search-box .clear {
  position: absolute;
  right: 8px;
  padding: 4px 8px;
}
.group-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0 4px;
  min-height: 36px;
}
.group-scroll {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  flex: 1;
  padding-bottom: 2px;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}
.group-scroll::-webkit-scrollbar { display: none; }
.chip {
  flex-shrink: 0;
  border: 1px solid var(--border);
  background: var(--card-bg);
  border-radius: 999px;
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-muted);
  white-space: nowrap;
  transition: all 0.1s;
}
.chip:hover { border-color: var(--brand); color: var(--brand); }
.chip.active {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
}
.chip-bundle { font-weight: 700; }
.chip-fav { font-weight: 700; }
.chip-fav.active { background: var(--brand); border-color: var(--brand); color: #fff; }
.fav-grid {
  flex: 1;
  overflow-y: auto;
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  align-content: start;
  padding-bottom: 20px;
}
.fav-card {
  padding: 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  text-align: start;
  border: 1px solid var(--border);
  transition: border-color 0.1s, transform 0.05s;
}
.fav-card:hover { border-color: var(--brand); }
.fav-card:active { transform: scale(0.98); }
.fav-name { font-weight: 700; font-size: 14px; }
.fav-price { font-weight: 800; font-size: 16px; color: var(--brand-dark); }
.bundle-grid {
  flex: 1;
  overflow-y: auto;
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
  gap: 12px;
  align-content: start;
  padding-bottom: 20px;
}
.bundle-card {
  padding: 14px 16px;
  border: 1.5px solid rgba(20, 99, 255, 0.35);
  display: flex;
  flex-direction: column;
}
.bundle-badge {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
  color: var(--brand-dark);
}
.bundle-title { font-weight: 700; font-size: 15px; margin: 4px 0 8px; }
.bundle-list {
  margin: 0 0 10px;
  padding-left: 18px;
  font-size: 12.5px;
  color: var(--text-muted);
  flex: 1;
}
.bundle-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.bundle-price { font-weight: 800; font-size: 16px; color: var(--brand-dark); }
</style>
