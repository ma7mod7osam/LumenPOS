<!-- Copyright (c) 2026 Lumen Solutions
     SPDX-License-Identifier: AGPL-3.0-only
     "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md. -->
<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        {{ creating ? t('New customer') : t('Select customer') }}
        <button class="btn-ghost" @click="$emit('close')"><Icon name="close" /></button>
      </div>

      <div class="modal-body" v-if="!creating">
        <input
          ref="searchInput"
          v-model="search"
          :placeholder="t('Search by name, mobile or tax ID')"
          style="width: 100%"
          @input="debouncedSearch"
        />
        <div class="results">
          <button
            v-for="customer in results"
            :key="customer.name"
            class="result"
            @click="select(customer)"
          >
            <div>
              <div class="result-name">
                {{ customer.customer_name }}
                <span v-if="customer.customer_type === 'Company'" class="company-tag">{{ t('Company') }}</span>
                <!-- Billed in another currency: the sale will be in it. -->
                <span
                  v-if="customer.default_currency && customer.default_currency !== (session.multiCurrency.outlet_currency || session.currency)"
                  class="company-tag"
                  >{{ customer.default_currency }}</span
                >
              </div>
              <div class="muted small">
                {{ customer.customer_group }}<span v-if="customer.mobile_no"> · {{ customer.mobile_no }}</span><span v-if="customer.tax_id"> · {{ customer.tax_id }}</span>
              </div>
            </div>
          </button>
          <div v-if="searched && !results.length" class="muted empty">
            {{ session.offline ? t('No match in the offline cache, connect to search all customers.') : t('No customers found') }}
          </div>
        </div>
        <button class="btn btn-outline" style="width: 100%" @click="creating = true">
          + {{ t('Create new customer') }}
        </button>
      </div>

      <div class="modal-body form" v-else>
        <p v-if="session.offline" class="muted small offline-note">
          {{ t('Offline, saved on this device and synced (matched to an existing customer or created) when you reconnect.') }}
        </p>
        <div class="type-tabs">
          <button
            class="type-tab"
            :class="{ active: form.customer_type === 'Individual' }"
            @click="form.customer_type = 'Individual'"
          >
            <Icon name="person" /> {{ t('Individual') }}
          </button>
          <button
            class="type-tab"
            :class="{ active: form.customer_type === 'Company' }"
            @click="form.customer_type = 'Company'"
          >
            <Icon name="company" /> {{ t('Company') }}
          </button>
        </div>

        <input v-model="form.customer_name" :placeholder="form.customer_type === 'Company' ? t('Company name *') : t('Full name *')" />
        <!-- The rest is the shop's own form (Settings, General, Customers):
             each field hidden, optional or required per customer type. The
             built-in fields first, then the address, then the shop's own. -->
        <input
          v-for="field in topFields"
          :key="field.fieldname"
          v-model="form[field.fieldname]"
          :type="inputType(field)"
          :placeholder="placeholder(field)"
        />
        <template v-if="addressFields.length">
          <div class="section-label">{{ t(formRules.address_label || 'National address') }}</div>
          <div class="grid-2">
            <input
              v-for="field in addressFields"
              :key="field.fieldname"
              v-model="form[field.fieldname]"
              :placeholder="placeholder(field)"
            />
          </div>
        </template>
        <template v-for="field in extraFields" :key="field.fieldname">
          <label v-if="field.fieldtype === 'Check'" class="check-field">
            <input type="checkbox" v-model="form[field.fieldname]" :true-value="1" :false-value="0" />
            {{ placeholder(field) }}
          </label>
          <select v-else-if="field.fieldtype === 'Select'" v-model="form[field.fieldname]">
            <option value="">{{ placeholder(field) }}</option>
            <option v-for="opt in field.options || []" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <input
            v-else-if="field.fieldtype === 'Link'"
            v-model="form[field.fieldname]"
            :list="'cf-' + field.fieldname"
            :placeholder="placeholder(field)"
            @focus="loadLinkValues(field)"
            @input="loadLinkValues(field)"
          />
          <input
            v-else
            v-model="form[field.fieldname]"
            :type="inputType(field)"
            :inputmode="['Int', 'Float', 'Currency'].includes(field.fieldtype) ? 'decimal' : undefined"
            :placeholder="placeholder(field)"
          />
          <datalist v-if="field.fieldtype === 'Link'" :id="'cf-' + field.fieldname">
            <option v-for="v in linkValues[field.fieldname] || []" :key="v" :value="v" />
          </datalist>
        </template>
      </div>

      <div class="modal-footer" v-if="creating">
        <button class="btn btn-outline" @click="creating = false">{{ t('Back') }}</button>
        <button class="btn btn-primary" :disabled="!canCreate" @click="create">
          {{ t('Create & Select') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import Icon from './Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { searchCustomersOffline, savePendingCustomer, putCustomer, newId } from '../offline'
import { useCartStore } from '../stores/cart'
import { useSessionStore } from '../stores/session'
import { t } from '../i18n'

const emit = defineEmits(['close'])
const cart = useCartStore()
const session = useSessionStore()

const search = ref('')
const results = ref([])
const searched = ref(false)
const creating = ref(false)
const searchInput = ref(null)
const form = ref({
  customer_type: 'Individual',
  customer_name: '',
  mobile_no: '',
  email_id: '',
  tax_id: '',
  building_no: '',
  street: '',
  district: '',
  city: '',
  postal_code: '',
  additional_no: '',
})
let timer = null

// The shop's form (lumenpos.customer_form). Before a till has it (an old
// cached bootstrap), the built-in form as it always was.
const BUILT_IN = [
  ['mobile_no', 'Mobile', 'Required', 'Required'],
  ['email_id', 'Email', 'Optional', 'Optional'],
  ['tax_id', 'Tax ID', 'Hidden', 'Required'],
  ['building_no', 'Building no.', 'Hidden', 'Required'],
  ['street', 'Street', 'Hidden', 'Required'],
  ['district', 'District', 'Hidden', 'Required'],
  ['city', 'City', 'Hidden', 'Required'],
  ['postal_code', 'Postal code', 'Hidden', 'Required'],
  ['additional_no', 'Additional no.', 'Hidden', 'Optional'],
].map(([fieldname, label, individual, company]) => ({
  fieldname, label, individual, company, builtin: 1, fieldtype: 'Data',
}))
const ADDRESS = ['building_no', 'street', 'district', 'city', 'postal_code', 'additional_no']
const formRules = computed(() => session.settings?.customer_form || { fields: BUILT_IN })
const column = computed(() => (form.value.customer_type === 'Company' ? 'company' : 'individual'))
const visibleFields = computed(() =>
  (formRules.value.fields || []).filter((f) => f[column.value] && f[column.value] !== 'Hidden')
)
const topFields = computed(() =>
  visibleFields.value.filter((f) => f.builtin && !ADDRESS.includes(f.fieldname))
)
const addressFields = computed(() => visibleFields.value.filter((f) => ADDRESS.includes(f.fieldname)))
const extraFields = computed(() => visibleFields.value.filter((f) => !f.builtin))

function required(field) {
  return field[column.value] === 'Required'
}
function placeholder(field) {
  return t(field.label) + (required(field) ? ' *' : '')
}
function inputType(field) {
  if (field.fieldname === 'email_id') return 'email'
  if (field.fieldtype === 'Date') return 'date'
  if (field.fieldtype === 'Phone' || field.fieldname === 'mobile_no') return 'tel'
  return 'text'
}
function filled(value) {
  if (value === null || value === undefined) return false
  return typeof value === 'string' ? Boolean(value.trim()) : Boolean(value)
}

// Values for a Link field the shop put on the form, fetched as the cashier types.
const linkValues = ref({})
let linkTimer = null
function loadLinkValues(field) {
  if (session.offline) return
  clearTimeout(linkTimer)
  linkTimer = setTimeout(async () => {
    try {
      linkValues.value = {
        ...linkValues.value,
        [field.fieldname]: await call('lumenpos.customer_form.link_values', {
          fieldname: field.fieldname,
          search: form.value[field.fieldname] || '',
        }),
      }
    } catch {
      /* the cashier can still type the value */
    }
  }, 200)
}

const canCreate = computed(() => {
  const f = form.value
  if (!f.customer_name.trim()) return false
  return visibleFields.value.every((field) => !required(field) || filled(f[field.fieldname]))
})

onMounted(async () => {
  searchInput.value?.focus()
  await runSearch()
})

function debouncedSearch() {
  clearTimeout(timer)
  timer = setTimeout(runSearch, 250)
}

async function runSearch() {
  // Offline: search the cached recent-customers subset instead of the server.
  results.value = session.offline
    ? await searchCustomersOffline(search.value)
    : await call('lumenpos.api.catalog.search_customers', { search: search.value })
  searched.value = true
}

function select(customer) {
  cart.setCustomer(customer)
  emit('close')
}

async function create() {
  // Offline: save a LOCAL pending customer with a temp id. On reconnect the
  // flush resolves it (match existing by mobile, else create) and remaps the
  // queued sale. See session.flushQueue.
  if (session.offline) {
    const tempId = '__local__' + newId()
    await savePendingCustomer({
      temp_id: tempId,
      payload: { ...form.value },
      created_at: new Date().toISOString(),
    })
    const localCustomer = {
      name: tempId,
      customer_name: form.value.customer_name,
      customer_group: '',
      customer_type: form.value.customer_type,
      mobile_no: form.value.mobile_no,
      email_id: form.value.email_id,
      tax_id: form.value.tax_id,
      __local: true,
    }
    await putCustomer(localCustomer) // searchable for the next offline sale
    cart.setCustomer(localCustomer)
    session.notify(t('Customer saved offline, will sync when back online'))
    emit('close')
    return
  }
  try {
    const customer = await call('lumenpos.api.catalog.create_customer', { payload: form.value })
    cart.setCustomer(customer)
    emit('close')
  } catch (e) {
    session.notify(e.message, true)
  }
}
</script>

<style scoped>
.results {
  margin: 12px 0;
  max-height: 300px;
  overflow-y: auto;
}
.result {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  border-radius: var(--radius);
}
.result:hover { background: var(--surface-2); }
.result-name { font-weight: 600; }
.company-tag {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.05em;
  color: var(--brand-dark);
  background: rgba(20, 99, 255, 0.1);
  border-radius: 999px;
  padding: 1px 8px;
  margin-inline-start: 6px;
}
.small { font-size: 12px; }
.empty { padding: 24px; text-align: center; }
.offline-note { text-align: center; padding: 8px 0; }
.form { display: flex; flex-direction: column; gap: 10px; }
.type-tabs { display: flex; gap: 8px; margin-bottom: 4px; }
.type-tab {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 11px;
  font-weight: 700;
  color: var(--text-muted);
}
.type-tab.active {
  border-color: var(--brand);
  color: var(--brand);
  background: rgba(20, 99, 255, 0.06);
}
.section-label {
  font-size: 11.5px;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
  margin-top: 4px;
}
/* minmax(0, 1fr): an input's own minimum width must not push the grid wider
   than the modal (it did in Arabic, with a scrollbar under the address). */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.grid-2 input { width: 100%; min-width: 0; }
.form input,
.form select { width: 100%; min-width: 0; }
.check-field { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.check-field input { width: auto; }
</style>
