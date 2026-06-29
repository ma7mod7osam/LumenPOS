<template>
  <div class="exchange-overlay">
    <header class="ex-header">
      <button class="btn-ghost back" @click="$emit('close')">‹ {{ t('Cancel') }}</button>
      <div class="ex-title"><Icon name="exchange" /> {{ t('Warranty Exchange') }}</div>
      <div />
    </header>

    <div class="ex-body">
      <!-- Launched from a specific invoice (History): skip the search. -->
      <div v-if="!chosen && invoiceNo" class="muted pad">{{ t('Loading…') }}</div>
      <!-- STEP 1: find the original sale -->
      <div v-else-if="!chosen" class="ex-step">
        <div class="step-label">{{ t('1 · Find the original sale (required for warranty)') }}</div>
        <input
          ref="searchInput"
          v-model="search"
          :placeholder="t('Invoice no, customer, mobile, or scan the serial…')"
          @input="debouncedLookup"
        />
        <div v-if="looking" class="muted pad">{{ t('Searching…') }}</div>
        <div v-else-if="searched && !results.length" class="muted pad">
          {{ t('No sale found. Warranty exchanges require the original invoice.') }}
        </div>
        <button
          v-for="inv in results"
          :key="inv.name"
          class="inv-row"
          :class="{ disabled: !inv.any_in_warranty }"
          :disabled="!inv.any_in_warranty"
          @click="chooseInvoice(inv)"
        >
          <div>
            <div class="inv-name">{{ inv.name }} · {{ inv.customer_name }}</div>
            <div class="muted small">
              {{ inv.posting_date }} ·
              <span :class="inv.any_in_warranty ? 'ok' : 'bad'">
                {{ inv.any_in_warranty ? t('has items in warranty') : t('all items out of warranty') }}
              </span>
            </div>
          </div>
          <span class="muted">{{ t('{count} item(s) ›', { count: inv.items.length }) }}</span>
        </button>
      </div>

      <!-- STEP 2: pick damaged + replacement -->
      <template v-else>
        <div class="ex-cols">
          <div class="ex-col">
            <div class="step-label">{{ t('2 · Damaged item(s) coming back') }}</div>
            <div class="muted small pad-sm">
              {{ t('From {name} · credited at the original price', { name: chosen.name }) }}
            </div>
            <div v-for="line in chosen.items" :key="line.item_code" class="dmg-row" :class="{ expired: !line.in_warranty }">
              <label class="dmg-pick">
                <input
                  type="checkbox"
                  :checked="isDamagedChecked(line)"
                  :disabled="!line.in_warranty"
                  @change="toggleDamaged(line, $event.target.checked)"
                />
                <span>
                  <span class="dmg-name">{{ line.item_name }}</span>
                  <span class="muted small"> {{ t('· {rate} · up to {qty}', { rate: money(line.rate), qty: line.returnable_qty }) }}</span>
                  <span class="wty" :class="line.in_warranty ? 'ok' : 'bad'">
                    <Icon name="shield" /> {{ line.warranty_days ? (line.in_warranty ? t('in warranty until {date}', { date: line.warranty_expiry }) : t('expired {date}', { date: line.warranty_expiry })) : t('no warranty') }}
                  </span>
                </span>
              </label>
              <input
                v-if="returnQty[line.item_code] > 0 && !line.has_serial_no"
                type="number" min="1" :max="line.returnable_qty"
                v-model.number="returnQty[line.item_code]"
                class="qty-in"
              />
              <div v-if="line.has_serial_no && returnSerials[line.item_code] !== undefined" class="serial-pick">
                <input
                  class="serial-in"
                  :placeholder="t('Scan or type serial…')"
                  @keydown.enter.prevent="addReturnSerial(line, $event)"
                />
                <button
                  v-for="s in (returnSerials[line.item_code] || [])"
                  :key="s"
                  class="serial-chip on"
                  :title="t('Remove')"
                  @click="removeReturnSerial(line.item_code, s)"
                >{{ s }} <Icon name="close" /></button>
              </div>
            </div>
          </div>

          <div class="ex-col">
            <div class="step-label">{{ t('3 · Replacement going out (optional)') }}</div>
            <div class="muted small pad-sm">{{ t('Leave empty to refund instead') }}</div>
            <div v-for="(row, i) in replacements" :key="i" class="rep-row">
              <LinkPicker
                doctype="Item"
                v-model="row.item_code"
                :label="row.label"
                :placeholder="t('Pick replacement…')"
                @picked="(o) => onReplacementPicked(row, o)"
              />
              <input type="number" min="1" v-model.number="row.qty" class="qty-in" @change="reprice" />
              <input v-if="row.has_serial_no" v-model="row.serials" class="serial-in" :placeholder="t('serial(s)')" />
              <input
                type="number"
                min="0"
                step="0.01"
                class="rep-price-in"
                :class="{ edited: row.priceEdited }"
                v-model.number="row.price"
                :title="t('Unit price — edit to override (e.g. give a pricier item at the same price)')"
                @input="row.priceEdited = true"
              />
              <button class="btn-ghost" @click="replacements.splice(i, 1); reprice()"><Icon name="close" /></button>
            </div>
            <button class="btn btn-outline add-rep" @click="replacements.push({ item_code: '', label: '', qty: 1, price: 0, has_serial_no: 0, serials: '' })">
              + {{ t('Add replacement item') }}
            </button>
          </div>
        </div>

        <!-- settlement -->
        <div class="ex-settle">
          <div class="settle-figures">
            <div><span class="muted">{{ t('Credit (damaged)') }}</span><b>{{ money(creditValue) }}</b></div>
            <div><span class="muted">{{ t('Replacement') }}</span><b>{{ money(replacementValue) }}</b></div>
            <div class="net" :class="net > 0 ? 'collect' : net < 0 ? 'refund' : 'even'">
              <span>{{ net > 0 ? t('Customer pays') : net < 0 ? t('Refund to customer') : t('Even exchange') }}</span>
              <b>{{ money(Math.abs(net)) }}</b>
            </div>
          </div>

          <div v-if="net > 0 && hasReplacement" class="even-swap-row">
            <button class="btn btn-outline" @click="evenSwap">
              {{ t('Give as even swap — charge only {amount}', { amount: money(creditValue) }) }}
            </button>
            <span class="muted small">{{ t('waives the {amount} difference', { amount: money(net) }) }}</span>
          </div>

          <div v-if="net !== 0" class="settle-mode">
            <span class="muted small">{{ net > 0 ? t('Collect via') : t('Refund via') }}</span>
            <select v-model="settleMode">
              <option v-for="m in settleModes" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>

          <div class="settle-mode reason-row">
            <span class="muted small">{{ t('Reason') }}</span>
            <select v-model="reason">
              <option v-for="r in reasonOptions" :key="r" :value="r">{{ r }}</option>
              <option value="__other__">{{ t('Other…') }}</option>
            </select>
            <input
              v-if="reason === '__other__'"
              v-model="otherReason"
              class="reason-other"
              :placeholder="t('Type the reason…')"
            />
          </div>

          <button
            class="btn btn-primary btn-lg confirm"
            :disabled="!canConfirm || submitting"
            @click="confirm"
          >
            {{ submitting ? t('Processing…') : confirmLabel }}
          </button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { useSessionStore } from '../stores/session'
import { money } from '../format'
import LinkPicker from './LinkPicker.vue'
import { t } from '../i18n'

const props = defineProps({ invoiceNo: { type: String, default: '' } })
const emit = defineEmits(['close', 'done'])
const session = useSessionStore()

const search = ref('')
const results = ref([])
const looking = ref(false)
const searched = ref(false)
const chosen = ref(null)
const searchInput = ref(null)
let timer = null

const returnQty = ref({})
const returnSerials = ref({})
const replacements = ref([])
const settleMode = ref(null)
const submitting = ref(false)
// Warranty exchanges default to the configured exchange reason, but the cashier
// can override it (other configured reasons, or a free-text "Other").
const reason = ref(session.exchangeReturnReason)
const otherReason = ref('')

const reasonOptions = computed(() => {
  const ex = session.exchangeReturnReason
  return [ex, ...session.returnReasons.filter((r) => r !== ex)]
})
const reasonValue = computed(() =>
  reason.value === '__other__' ? otherReason.value.trim() : reason.value || ''
)

onMounted(() => {
  if (props.invoiceNo) loadInvoice(props.invoiceNo)
  else searchInput.value?.focus()
})

// Launched from a specific invoice (History → Exchange): load it directly,
// skipping the search step.
async function loadInvoice(no) {
  looking.value = true
  try {
    const rows = await call('lumenpos.api.exchanges.lookup', {
      pos_profile: session.posProfile,
      search: no,
    })
    const inv = rows.find((r) => r.name === no) || rows[0]
    if (inv && inv.any_in_warranty) {
      chosen.value = inv
    } else {
      session.notify(
        inv
          ? t('No items on {invoice} are in warranty', { invoice: no })
          : t('No sale found. Warranty exchanges require the original invoice.'),
        true
      )
      emit('close')
    }
  } catch (e) {
    session.notify(e.message, true)
    emit('close')
  } finally {
    looking.value = false
  }
}

function isDamagedChecked(line) {
  return line.has_serial_no
    ? returnSerials.value[line.item_code] !== undefined
    : (returnQty.value[line.item_code] || 0) > 0
}

function debouncedLookup() {
  clearTimeout(timer)
  // Don't fire a heavy lookup on 1-2 characters; wait for a real query.
  if (search.value.trim().length < 3) {
    results.value = []
    searched.value = false
    return
  }
  timer = setTimeout(runLookup, 400)
}

async function runLookup() {
  if (search.value.trim().length < 3) return
  looking.value = true
  try {
    results.value = await call('lumenpos.api.exchanges.lookup', {
      pos_profile: session.posProfile,
      search: search.value,
    })
    searched.value = true
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    looking.value = false
  }
}

function chooseInvoice(inv) {
  if (!inv.any_in_warranty) return
  chosen.value = inv
}

function toggleDamaged(line, checked) {
  if (checked && !line.in_warranty) return
  if (checked) {
    returnQty.value[line.item_code] = line.has_serial_no ? 0 : 1
    if (line.has_serial_no) returnSerials.value[line.item_code] = []
    // Default the replacement to the SAME item at the original price — the usual
    // warranty swap (net zero). The cashier can change the item, qty or price,
    // or delete the row entirely.
    if (!replacements.value.some((r) => r.autoFor === line.item_code)) {
      replacements.value.push({
        item_code: line.item_code,
        label: line.item_name,
        qty: 1,
        price: line.rate,
        has_serial_no: line.has_serial_no,
        serials: '',
        priceEdited: true, // keep the original price so the swap nets to zero
        autoFor: line.item_code,
      })
    }
  } else {
    delete returnQty.value[line.item_code]
    delete returnSerials.value[line.item_code]
    // Drop the auto-added replacement for this damaged item.
    replacements.value = replacements.value.filter((r) => r.autoFor !== line.item_code)
  }
}

// Serialized damaged items: the cashier scans/types each serial (must read the
// actual unit), validated against the serials sold on this invoice.
function addReturnSerial(line, event) {
  const code = (event.target.value || '').trim()
  event.target.value = ''
  if (!code) return
  // Exchange is exempt from scan-only: the cashier may type the serial, but it
  // must be one of the serials sold on the original invoice (checked below).
  const list = returnSerials.value[line.item_code] || []
  if (list.includes(code)) {
    session.notify(t('Serial {serial} is already added', { serial: code }), true)
    return
  }
  if (!(line.returnable_serials || []).includes(code)) {
    session.notify(t('Serial {serial} was not sold on this invoice (or already returned)', { serial: code }), true)
    return
  }
  if (list.length >= line.returnable_qty) {
    session.notify(t('Only {qty} can be exchanged', { qty: line.returnable_qty }), true)
    return
  }
  returnSerials.value[line.item_code] = [...list, code]
  returnQty.value[line.item_code] = returnSerials.value[line.item_code].length
}

function removeReturnSerial(itemCode, s) {
  const list = (returnSerials.value[itemCode] || []).filter((x) => x !== s)
  returnSerials.value[itemCode] = list
  returnQty.value[itemCode] = list.length
}

async function onReplacementPicked(row, option) {
  row.label = option?.item_name || option?.name || ''
  row.has_serial_no = option?.has_serial_no || 0
  row.priceEdited = false // fetch a fresh price for the newly chosen item
  await reprice()
}

async function reprice() {
  const codes = replacements.value.filter((r) => r.item_code).map((r) => r.item_code)
  if (!codes.length) return
  try {
    const data = await call('lumenpos.api.catalog.get_prices', {
      pos_profile: session.posProfile,
      item_codes: codes,
    })
    for (const row of replacements.value) {
      // Never overwrite a manually overridden price.
      if (!row.priceEdited && data.prices[row.item_code] != null) row.price = data.prices[row.item_code]
    }
  } catch {
    /* keep prices */
  }
}

const creditValue = computed(() =>
  (chosen.value?.items || []).reduce(
    (sum, l) => sum + (returnQty.value[l.item_code] || 0) * l.rate,
    0
  )
)
const replacementValue = computed(() =>
  replacements.value.reduce((sum, r) => sum + (r.price || 0) * (r.qty || 1), 0)
)
const net = computed(() => Math.round((replacementValue.value - creditValue.value) * 100) / 100)
const hasReplacement = computed(() => replacements.value.some((r) => r.item_code))

// "Give the pricier item at the same price": scale replacement prices so the
// total equals the damaged credit (net 0), and mark them overridden so the
// server honours the agreed price.
function evenSwap() {
  const repTotal = replacementValue.value
  if (repTotal <= 0 || creditValue.value <= 0) return
  const factor = creditValue.value / repTotal
  for (const row of replacements.value) {
    if (!row.item_code) continue
    row.price = Math.round((row.price || 0) * factor * 100) / 100
    row.priceEdited = true
  }
}

const settleModes = computed(() => {
  const modes = session.paymentModes
    .map((m) => m.mode_of_payment)
    .filter((m) => m !== session.giftCardMode && m !== session.storeCreditMode)
  if (net.value < 0) modes.push(session.storeCreditMode) // refund can go to credit
  return modes
})

const confirmLabel = computed(() => {
  if (net.value > 0) return t('Collect {amount} & complete', { amount: money(net.value) })
  if (net.value < 0) return t('Refund {amount} & complete', { amount: money(-net.value) })
  return t('Complete even exchange')
})

const canConfirm = computed(() => {
  if (creditValue.value <= 0) return false
  // serial lines must have serials selected matching qty
  for (const l of chosen.value?.items || []) {
    if (returnQty.value[l.item_code] > 0 && l.has_serial_no) {
      if ((returnSerials.value[l.item_code] || []).length !== returnQty.value[l.item_code]) return false
    }
  }
  if (net.value !== 0 && !settleMode.value) return false
  if (!reasonValue.value) return false // "Other" picked but left blank
  return true
})

async function confirm() {
  submitting.value = true
  try {
    const returned_items = Object.entries(returnQty.value)
      .filter(([, q]) => q > 0)
      .map(([item_code, qty]) => ({
        item_code,
        qty,
        serial_nos: returnSerials.value[item_code] || [],
      }))
    const replacement_items = replacements.value
      .filter((r) => r.item_code)
      .map((r) => ({
        item_code: r.item_code,
        qty: r.qty || 1,
        // Send a manual price only when the cashier overrode it; otherwise the
        // server prices it (server stays authoritative for normal exchanges).
        rate: r.priceEdited ? Number(r.price) || 0 : null,
        serial_nos: (r.serials || '').split(/[\n,]/).map((s) => s.trim()).filter(Boolean),
      }))
    const receipt = await call('lumenpos.api.exchanges.submit_exchange', {
      payload: {
        pos_profile: session.posProfile,
        original_invoice: chosen.value.name,
        returned_items,
        replacement_items,
        settle_mode: settleMode.value,
        return_reason: reasonValue.value,
      },
    })
    session.notify(t('Exchange completed'))
    emit('done', receipt)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.exchange-overlay {
  position: fixed;
  inset: 0;
  background: var(--page-bg);
  z-index: 45;
  display: flex;
  flex-direction: column;
}
.ex-header {
  height: 52px;
  background: var(--topbar-bg);
  color: #fff;
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  padding: 0 18px;
}
.back { color: #cdd3df; justify-self: start; }
.ex-title { font-weight: 700; font-size: 16px; }
.ex-body { flex: 1; overflow-y: auto; width: min(900px, 96vw); margin: 0 auto; padding: 20px 0 40px; }
.step-label { font-weight: 800; font-size: 13px; margin-bottom: 8px; }
.ex-step input { width: 100%; padding: 12px; font-size: 15px; }
.pad { padding: 20px; text-align: center; }
.pad-sm { margin-bottom: 8px; }
.inv-row {
  display: flex; width: 100%; justify-content: space-between; align-items: center;
  text-align: left; padding: 12px 14px; border: 1px solid var(--border);
  border-radius: var(--radius); margin-top: 8px; background: var(--card-bg);
}
.inv-row:hover:not(.disabled) { border-color: var(--brand); }
.inv-row.disabled { opacity: 0.5; cursor: not-allowed; }
.inv-name { font-weight: 600; }
.small { font-size: 12px; }
.ok { color: var(--brand-dark); font-weight: 600; }
.bad { color: var(--red); font-weight: 600; }
.ex-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.ex-col { background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px; }
.dmg-row, .rep-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 8px 0; border-bottom: 1px solid var(--border-subtle); }
.dmg-pick { display: flex; align-items: flex-start; gap: 8px; flex: 1; cursor: pointer; }
.dmg-name { font-weight: 600; }
.dmg-row.expired { opacity: 0.6; }
.wty { display: block; font-size: 11px; font-weight: 600; margin-top: 2px; }
.wty.ok { color: var(--brand-dark); }
.wty.bad { color: var(--red); }
.qty-in { width: 64px; text-align: center; }
.serial-in { width: 120px; }
.serial-pick { display: flex; gap: 5px; flex-wrap: wrap; width: 100%; }
.serial-chip { font-size: 11px; font-weight: 700; font-family: ui-monospace, monospace; border: 1px solid var(--border); border-radius: 999px; padding: 3px 9px; }
.serial-chip.on { background: var(--brand-soft); border-color: var(--brand-soft); color: #fff; }
.rep-price-in { width: 84px; text-align: right; font-weight: 700; }
.rep-price-in.edited { border-color: var(--brand); color: var(--brand-dark); }
.even-swap-row { display: flex; align-items: center; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
.add-rep { margin-top: 8px; }
.ex-settle { margin-top: 18px; background: var(--card-bg); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; }
.settle-figures { display: flex; gap: 24px; flex-wrap: wrap; align-items: center; }
.settle-figures > div { display: flex; flex-direction: column; }
.settle-figures b { font-size: 18px; }
.net b { font-size: 24px; }
.net.collect b { color: var(--brand-dark); }
.net.refund b { color: var(--red); }
.settle-mode { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
.settle-mode select { padding: 8px 10px; }
.reason-row { flex-wrap: wrap; }
.reason-other { flex: 1; min-width: 180px; padding: 8px 10px; }
.confirm { width: 100%; margin-top: 14px; }
@media (max-width: 720px) { .ex-cols { grid-template-columns: 1fr; } }
</style>
