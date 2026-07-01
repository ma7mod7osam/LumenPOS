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
              </div>
              <div class="muted small">
                {{ customer.customer_group }}<span v-if="customer.mobile_no"> · {{ customer.mobile_no }}</span><span v-if="customer.tax_id"> · {{ customer.tax_id }}</span>
              </div>
            </div>
          </button>
          <div v-if="searched && !results.length" class="muted empty">
            {{ session.offline ? t('No match in the offline cache — connect to search all customers.') : t('No customers found') }}
          </div>
        </div>
        <button
          v-if="!session.offline"
          class="btn btn-outline"
          style="width: 100%"
          @click="creating = true"
        >
          + {{ t('Create new customer') }}
        </button>
        <p v-else class="muted small offline-note">
          {{ t('Creating a new customer needs a connection.') }}
        </p>
      </div>

      <div class="modal-body form" v-else>
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
        <input v-model="form.mobile_no" :placeholder="t('Mobile *')" />
        <input v-model="form.email_id" :placeholder="t('Email')" type="email" />

        <template v-if="form.customer_type === 'Company'">
          <input v-model="form.tax_id" :placeholder="t('Tax ID *')" />
          <div class="section-label">{{ t('National address') }}</div>
          <div class="grid-2">
            <input v-model="form.building_no" :placeholder="t('Building no. *')" />
            <input v-model="form.street" :placeholder="t('Street *')" />
            <input v-model="form.district" :placeholder="t('District *')" />
            <input v-model="form.city" :placeholder="t('City *')" />
            <input v-model="form.postal_code" :placeholder="t('Postal code *')" />
            <input v-model="form.additional_no" :placeholder="t('Additional no.')" />
          </div>
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
import { searchCustomersOffline } from '../offline'
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

const canCreate = computed(() => {
  const f = form.value
  if (!f.customer_name.trim() || !f.mobile_no.trim()) return false
  if (f.customer_type === 'Company') {
    return Boolean(
      f.tax_id.trim() &&
        f.building_no.trim() &&
        f.street.trim() &&
        f.district.trim() &&
        f.city.trim() &&
        f.postal_code.trim()
    )
  }
  return true
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
  margin-left: 6px;
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
.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
</style>
