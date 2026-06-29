<template>
  <div class="settings">
    <!-- Segmented pill tab bar -->
    <nav class="tabs">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="tab"
        :class="{ active: activeTab === tab }"
        @click="activeTab = tab"
      >
        {{ t(tab) }}
      </button>
    </nav>

    <!-- ============ PROMOTIONS ============ -->
    <section v-if="activeTab === 'Promotions'" class="tab-body">
      <!-- LIST -->
      <div v-if="!editingPromo" class="list-view">
        <div class="list-head">
          <input v-model="promoSearch" class="list-search" :placeholder="t('Search promotions…')" />
          <button v-if="perms.promotions?.create" class="btn btn-primary" @click="newPromotion">{{ t('+ New Promotion') }}</button>
        </div>
        <div v-if="!promotions.length" class="muted empty">{{ t('No promotions yet') }}</div>
        <div v-else class="card-list">
          <button
            v-for="promo in filteredPromotions"
            :key="promo.name"
            class="entity-card"
            @click="editPromotion(promo.name)"
          >
            <span class="status-dot" :class="{ on: promo.status === 'Active' }" />
            <div class="entity-main">
              <div class="entity-title">{{ promo.title }}</div>
              <div class="muted small entity-sub">
                {{ t(promo.promotion_type) }}
                <span v-if="promo.start_date || promo.end_date"> · {{ promo.start_date || '…' }} → {{ promo.end_date || '…' }}</span>
              </div>
            </div>
            <span v-if="promo.requires_coupon" class="entity-meta"><Icon name="ticket" /> {{ promo.coupon_code }}</span>
            <span v-if="promo.expired" class="status-pill expired">{{ t('Expired') }}</span>
            <span class="status-pill" :class="{ on: promo.status === 'Active' }">{{ t(promo.status) }}</span>
          </button>
        </div>
      </div>

      <!-- EDITOR -->
      <div v-else class="editor">
        <!-- Basics -->
        <div class="sec-card">
          <div class="sec-title"><Icon name="bulb" /> {{ t('Basics') }}</div>
          <div class="field-grid">
            <label class="field span-2">
              <span>{{ t('Name *') }}</span>
              <input v-model="promoForm.title" :placeholder="t('e.g. Buy 2 Get 1 Free')" />
            </label>
            <label class="field">
              <span>{{ t('Priority') }}</span>
              <input type="number" v-model.number="promoForm.priority" />
            </label>
          </div>
          <div class="seg-field">
            <span class="seg-label">{{ t('Type') }}</span>
            <div class="segmented">
              <button
                v-for="opt in PROMO_TYPES"
                :key="opt"
                class="seg-btn"
                :class="{ on: promoForm.promotion_type === opt }"
                @click="promoForm.promotion_type = opt"
              >
                {{ t(opt) }}
              </button>
            </div>
          </div>
          <div class="toggle-row">
            <label class="inline-check">
              <input type="checkbox" v-model="promoForm.status" true-value="Active" false-value="Inactive" />
              {{ t('Active') }}
            </label>
            <label class="inline-check">
              <input type="checkbox" v-model="promoForm.stackable" :true-value="1" :false-value="0" />
              {{ t('Can combine with other promotions') }}
            </label>
          </div>
        </div>

        <!-- The offer -->
        <div class="sec-card">
          <div class="sec-title"><Icon name="gift" /> {{ t('Offer') }}</div>
          <label class="field" style="max-width: 360px; margin-bottom: 14px">
            <span>{{ t('Calculate discount on') }}</span>
            <select v-model="promoForm.price_basis">
              <option value="Price Book Price">{{ t('Price book price (stacks on an active price book)') }}</option>
              <option value="Standard Price">{{ t('Standard price (lowest of book vs standard − promo)') }}</option>
            </select>
          </label>
          <div class="field-grid" v-if="promoForm.promotion_type === 'Simple Discount'">
            <label class="field">
              <span>{{ t('Discount type') }}</span>
              <select v-model="promoForm.discount_type">
                <option value="Percentage">{{ t('Percentage') }}</option><option value="Amount">{{ t('Amount') }}</option><option value="Fixed Price">{{ t('Fixed Price') }}</option>
              </select>
            </label>
            <label class="field"><span>{{ t('Value') }}</span><input type="number" min="0" v-model.number="promoForm.discount_value" /></label>
          </div>
          <template v-else-if="promoForm.promotion_type === 'Buy X Get Y'">
            <p class="muted small" style="margin: 0 0 10px">
              {{ t('Multiple') }} <b>{{ t('Buy') }}</b> {{ t('rows = the customer can buy') }} <b>{{ t('any') }}</b> {{ t('of them (mix & match counts).') }}
              {{ t('Multiple') }} <b>{{ t('Get') }}</b> {{ t('rows = any of them can receive the reward (cheapest first).') }}
            </p>
            <div class="field-grid">
              <label class="field"><span>{{ t('Buy qty') }}</span><input type="number" min="1" v-model.number="promoForm.buy_qty" /></label>
              <label class="field"><span>{{ t('Get qty') }}</span><input type="number" min="1" v-model.number="promoForm.get_qty" /></label>
              <label class="field">
                <span>{{ t('Reward') }}</span>
                <select v-model="promoForm.get_discount_type">
                  <option value="Free">{{ t('Free') }}</option><option value="Percentage">{{ t('Percentage') }}</option><option value="Amount">{{ t('Amount') }}</option><option value="Fixed Price">{{ t('Fixed Price') }}</option>
                </select>
              </label>
              <label class="field" v-if="promoForm.get_discount_type !== 'Free'">
                <span>{{ t('Reward value') }}</span><input type="number" min="0" v-model.number="promoForm.get_discount_value" />
              </label>
              <label class="field"><span>{{ t('Max uses/sale (0=∞)') }}</span><input type="number" min="0" v-model.number="promoForm.max_applications" /></label>
            </div>
          </template>
          <div class="field-grid" v-else-if="promoForm.promotion_type === 'Spend and Save'">
            <label class="field"><span>{{ t('Minimum spend') }}</span><input type="number" min="0" v-model.number="promoForm.min_spend" /></label>
            <label class="field">
              <span>{{ t('Discount type') }}</span>
              <select v-model="promoForm.basket_discount_type"><option value="Percentage">{{ t('Percentage') }}</option><option value="Amount">{{ t('Amount') }}</option></select>
            </label>
            <label class="field"><span>{{ t('Value') }}</span><input type="number" min="0" v-model.number="promoForm.basket_discount_value" /></label>
          </div>
        </div>

        <!-- Products -->
        <div class="sec-card">
          <div class="sec-title">
            <span><Icon name="store" /> {{ t('Products') }}</span>
            <label class="inline-check">
              <input type="checkbox" v-model="promoForm.apply_on_all" :true-value="1" :false-value="0" />
              {{ t('Apply on all products') }}
            </label>
          </div>
          <p v-if="promoForm.apply_on_all" class="muted small" style="margin: 0 0 10px">
            {{ t('All products are included — add rows below to') }} <b>{{ t('exclude') }}</b> {{ t('items, groups or brands.') }}
          </p>
          <div v-if="promoForm.items && promoForm.items.length" class="prod-head">
            <span class="ph-mode">{{ t('Include') }} / {{ t('Exclude') }}</span>
            <span class="ph-type">{{ t('Type') }}</span>
            <span class="ph-pick">{{ t('Item') }}</span>
          </div>
          <div v-for="(row, i) in promoForm.items" :key="i" class="item-row">
            <select
              v-model="row.exclude"
              class="mode-select"
              :class="{ excluding: row.exclude }"
            >
              <option :value="0">{{ t('Include') }}</option>
              <option :value="1">{{ t('Exclude') }}</option>
            </select>
            <select v-model="row.applies_to" style="width: 110px" @change="row.value = ''; row.label = ''">
              <option value="Item">{{ t('Item') }}</option><option value="Item Group">{{ t('Item Group') }}</option><option value="Brand">{{ t('Brand') }}</option><option value="Tag">{{ t('Tag') }}</option>
            </select>
            <LinkPicker
              :doctype="row.applies_to"
              v-model="row.value"
              :label="row.label"
              :placeholder="row.applies_to === 'Item' ? t('Search by name, code or barcode…') : t('Search and pick from the list…')"
              @picked="(option) => (row.label = option?.item_name || option?.name || '')"
            />
            <select
              v-if="promoForm.promotion_type === 'Buy X Get Y' && !row.exclude"
              v-model="row.role"
              style="width: 84px"
            >
              <option value="Buy">{{ t('Buy') }}</option><option value="Get">{{ t('Get') }}</option>
            </select>
            <button class="btn-ghost" @click="promoForm.items.splice(i, 1)"><Icon name="close" /></button>
          </div>
          <button
            class="btn btn-outline add-row"
            @click="promoForm.items.push({ applies_to: 'Item', value: '', label: '', role: 'Buy', qty: 1, exclude: promoForm.apply_on_all ? 1 : 0 })"
          >
            {{ t('+ Add product row') }}
          </button>
          <p v-if="hasInvalidRows" class="row-warning">
            {{ t('⚠ Pick every product from the dropdown — rows without a valid selection can\'t be saved.') }}
          </p>
        </div>

        <!-- When & where -->
        <div class="sec-card">
          <div class="sec-title"><Icon name="store" /> {{ t('When & where') }}</div>
          <div class="field-grid">
            <label class="field">
              <span>{{ t('Start date (optional — empty = always)') }}</span>
              <input type="date" v-model="promoForm.start_date" />
            </label>
            <label class="field">
              <span>{{ t('End date (optional)') }}</span>
              <input type="date" v-model="promoForm.end_date" />
            </label>
            <label class="field">
              <span>{{ t('Daily from (optional — empty = all day)') }}</span>
              <input type="time" v-model="promoForm.start_time" />
            </label>
            <label class="field">
              <span>{{ t('Daily until (optional)') }}</span>
              <input type="time" v-model="promoForm.end_time" />
            </label>
          </div>
          <div class="day-row">
            <button
              v-for="day in DAYS"
              :key="day"
              class="day-chip"
              :class="{ on: promoForm[day] }"
              @click="promoForm[day] = promoForm[day] ? 0 : 1"
            >
              {{ day.slice(0, 3) }}
            </button>
          </div>
          <div class="sub-label">{{ t('Outlets & customers') }}</div>
          <div class="outlet-row">
            <label v-for="profile in session.availableProfiles" :key="profile" class="inline-check">
              <input type="checkbox" :value="profile" v-model="promoForm.pos_profiles" />
              {{ profile }}
            </label>
            <span class="muted small">{{ t('(none ticked = all outlets)') }}</span>
          </div>
          <div class="item-row">
            <LinkPicker
              doctype="Customer Group"
              v-model="groupPick"
              :placeholder="t('Limit to customer group… (empty = everyone)')"
              @picked="(option) => addGroup(promoForm, option)"
            />
            <span v-for="(group, i) in promoForm.customer_groups" :key="group" class="chip-sm">
              {{ group }} <button class="btn-ghost" @click="promoForm.customer_groups.splice(i, 1)"><Icon name="close" /></button>
            </span>
          </div>
        </div>

        <!-- Coupons (only when required) -->
        <div class="sec-card">
          <div class="sec-title">
            <span><Icon name="ticket" /> {{ t('Coupons') }}</span>
            <label class="inline-check">
              <input type="checkbox" v-model="promoForm.requires_coupon" :true-value="1" :false-value="0" />
              {{ t('Requires coupon code') }}
            </label>
          </div>
          <template v-if="promoForm.requires_coupon">
            <label class="field" style="max-width: 360px; margin-bottom: 12px">
              <span>{{ t('Shared code (optional)') }}</span>
              <input
                v-model="promoForm.coupon_code"
                :placeholder="t('Shared code (optional)')"
                :title="t('An optional master code that always works (no limit). Leave empty to allow only the unique codes below.')"
              />
            </label>
            <div class="coupon-pool">
              <div class="muted small" style="margin-bottom: 10px">
                {{ t('The shared code above is optional and has no limit — it keeps working even after the codes below run out. The codes you generate/import here are unique and limited; when they\'re all used up, only the shared code still works (or none, if you left it empty).') }}
              </div>
              <template v-if="promoForm.name">
                <div v-if="couponStats" class="coupon-stats">
                  {{ t('Coupons: {total} total · {available} available · {redemptions} redemptions', couponStats) }}
                </div>
                <div class="item-row">
                  <input type="number" min="1" max="5000" v-model.number="couponGen.count" :placeholder="t('How many')" style="width: 110px" />
                  <input v-model="couponGen.prefix" :placeholder="t('Prefix (optional)')" style="width: 140px" />
                  <label class="inline-num" :title="t('How many times each code can be used (0 = unlimited)')">{{ t('Uses/code') }}<input type="number" min="0" v-model.number="couponGen.usage_limit" style="width: 64px" /></label>
                  <input type="date" v-model="couponGen.valid_until" :title="t('Valid until (optional)')" />
                  <button class="btn btn-outline" :disabled="couponBusy || !couponGen.count" @click="generateCoupons">{{ couponBusy ? t('Working…') : t('Generate') }}</button>
                </div>
                <div class="item-row">
                  <label class="inline-num" :title="t('How many times each code can be used (0 = unlimited)')">{{ t('Uses/code') }}<input type="number" min="0" v-model.number="couponImp.usage_limit" style="width: 64px" /></label>
                  <input type="date" v-model="couponImp.valid_until" :title="t('Valid until (optional)')" />
                  <button class="btn btn-outline" :disabled="couponBusy" @click="couponFileInput?.click()"><Icon name="upload" /> {{ t('Import codes (Excel/CSV)') }}</button>
                  <input ref="couponFileInput" type="file" accept=".csv,.xlsx,.xlsm,.xls" style="display: none" @change="importCoupons" />
                  <button class="btn btn-outline" :disabled="couponBusy || !couponStats?.total" @click="exportCoupons"><Icon name="download" /> {{ t('Export codes') }}</button>
                  <button v-if="couponStats?.available" class="btn-ghost danger" @click="deleteUnusedCoupons">{{ t('Delete unused') }}</button>
                </div>
                <div v-if="couponMsg" class="gate-ok">{{ couponMsg }}</div>
              </template>
              <div v-else class="muted small">{{ t('Save the promotion first, then generate or import coupon codes here.') }}</div>
            </div>
          </template>
        </div>

        <!-- Test (collapsible) -->
        <div v-if="promoForm.name" class="sec-card">
          <button class="sec-title collapsible" @click="showTest = !showTest">
            <span><Icon name="play" /> {{ t('Test this promotion (saved version)') }}</span>
            <span class="muted small">{{ showTest ? '−' : '+' }}</span>
          </button>
          <template v-if="showTest">
            <div v-for="(row, i) in testBasket" :key="i" class="item-row">
              <LinkPicker
                doctype="Item"
                v-model="row.item_code"
                :label="row.label"
                :placeholder="t('Test item…')"
                @picked="(option) => (row.label = option?.item_name || option?.name || '')"
              />
              <input type="number" min="1" v-model.number="row.qty" style="width: 70px" />
              <button class="btn-ghost" @click="testBasket.splice(i, 1)"><Icon name="close" /></button>
            </div>
            <div class="item-row">
              <button class="btn btn-outline" @click="testBasket.push({ item_code: '', label: '', qty: 1 })">
                {{ t('+ Add test item') }}
              </button>
              <button class="btn btn-primary" :disabled="testing || !testBasket.some((row) => row.item_code)" @click="runTest">
                <Icon name="play" /> {{ testing ? t('Testing…') : t('Run test') }}
              </button>
            </div>

            <div v-if="testResult" class="test-report">
              <div v-for="gate in testResult.gates" :key="gate.label" :class="gate.ok ? 'gate-ok' : 'gate-bad'">
                {{ gate.ok ? '✓' : '✗' }} {{ gate.label }}
              </div>
              <div v-for="(row, i) in testResult.row_matches" :key="'m' + i"
                   :class="row.matches.length ? 'gate-ok' : 'gate-bad'">
                {{ row.matches.length ? '✓' : '✗' }}
                {{ row.role }} {{ t('row') }} “{{ row.value }}” ({{ row.applies_to }}) —
                {{ row.matches.length ? t('matches {list}', { list: row.matches.join(', ') }) : t('matches NOTHING in the basket') }}
              </div>
              <div v-for="(warning, i) in testResult.price_warnings" :key="'w' + i" class="gate-bad">
                ⚠ {{ warning }}
              </div>
              <div class="test-verdict" :class="testResult.result.total_savings > 0 ? 'gate-ok' : 'gate-bad'">
                {{ testResult.result.total_savings > 0
                  ? t('✓ APPLIES — saves {amount}', { amount: testResult.result.total_savings })
                  : t('✗ Does not apply to this basket') }}
              </div>
            </div>
          </template>
        </div>

        <!-- Sticky footer -->
        <div class="editor-footer">
          <button v-if="promoForm.name && perms.promotions?.delete" class="btn btn-outline danger" @click="deletePromotion">{{ t('Delete') }}</button>
          <span style="flex: 1" />
          <button class="btn btn-outline" @click="editingPromo = false">{{ t('Cancel') }}</button>
          <button class="btn btn-primary" :disabled="saving" @click="savePromotion">
            {{ saving ? t('Saving…') : t('Save Promotion') }}
          </button>
        </div>
      </div>
    </section>

    <!-- ============ BUNDLES ============ -->
    <section v-if="activeTab === 'Bundles'" class="tab-body">
      <!-- LIST -->
      <div v-if="!editingBundle" class="list-view">
        <div class="list-head">
          <input v-model="bundleSearch" class="list-search" :placeholder="t('Search bundles…')" />
          <button v-if="perms.bundles?.create" class="btn btn-primary" @click="newBundle">{{ t('+ New Bundle') }}</button>
        </div>
        <p class="muted hint-row">
          {{ t('A bundle is sold from the sell screen with one tap: its items land in the cart as separate lines (each individually returnable) priced together at the bundle price.') }}
        </p>
        <div v-if="!bundles.length" class="muted empty">{{ t('No bundles yet') }}</div>
        <div v-else class="card-list">
          <button v-for="bundle in filteredBundles" :key="bundle.name" class="entity-card" @click="editBundle(bundle)">
            <span class="status-dot" :class="{ on: bundle.status === 'Active' }" />
            <div class="entity-main">
              <div class="entity-title"><Icon name="gift" /> {{ bundle.title }}</div>
              <div class="muted small entity-sub">
                {{ bundle.items.map((c) => `${c.qty} × ${c.item_name || c.item_code}`).join(', ') }}
                <span v-if="bundle.valid_from || bundle.valid_to"> · {{ bundle.valid_from || '…' }} → {{ bundle.valid_to || '…' }}</span>
              </div>
            </div>
            <span v-if="bundle.expired" class="status-pill expired">{{ t('Expired') }}</span>
            <span class="status-pill" :class="{ on: bundle.status === 'Active' }">
              {{ money(bundle.bundle_price) }}
            </span>
          </button>
        </div>
      </div>

      <!-- EDITOR -->
      <div v-else class="editor">
        <!-- Basics -->
        <div class="sec-card">
          <div class="sec-title"><Icon name="bulb" /> {{ t('Basics') }}</div>
          <div class="field-grid">
            <label class="field span-2"><span>{{ t('Name *') }}</span><input v-model="bundleForm.title" :placeholder="t('e.g. Starter Combo')" /></label>
            <label class="field"><span>{{ t('Bundle price *') }}</span><input type="number" min="0" v-model.number="bundleForm.bundle_price" /></label>
            <label class="field"><span>{{ t('Valid from') }}</span><input type="date" v-model="bundleForm.valid_from" /></label>
            <label class="field"><span>{{ t('Valid to') }}</span><input type="date" v-model="bundleForm.valid_to" /></label>
          </div>
          <label class="inline-check">
            <input type="checkbox" v-model="bundleForm.status" true-value="Active" false-value="Inactive" />
            {{ t('Active') }}
          </label>
        </div>

        <!-- Items -->
        <div class="sec-card">
          <div class="sec-title"><Icon name="store" /> {{ t('Items in the bundle') }}</div>
          <p class="muted small" style="margin: 0 0 10px">
            <b>{{ t('Allocated price') }}</b> {{ t('(optional) sets each component\'s share of the bundle price — useful to control margins per item. Fill all rows or none; they must sum exactly to the bundle price. Empty = split proportionally to regular prices.') }}
          </p>
          <div v-for="(row, i) in bundleForm.items" :key="i" class="item-row">
            <LinkPicker
              doctype="Item"
              v-model="row.item_code"
              :label="row.label"
              :placeholder="t('Search by name, code or barcode…')"
              @picked="(option) => (row.label = option?.item_name || option?.name || '')"
            />
            <input type="number" min="1" v-model.number="row.qty" style="width: 70px" :title="t('Qty')" />
            <input
              type="number"
              min="0"
              step="0.01"
              v-model.number="row.allocated_amount"
              style="width: 120px"
              :placeholder="t('Alloc. price')"
              :title="t('Allocated share of the bundle price (whole row)')"
            />
            <button class="btn-ghost" @click="bundleForm.items.splice(i, 1)"><Icon name="close" /></button>
          </div>
          <button class="btn btn-outline add-row" @click="bundleForm.items.push({ item_code: '', label: '', qty: 1, allocated_amount: null })">
            {{ t('+ Add item') }}
          </button>
          <p v-if="allocationState === 'partial'" class="row-warning">
            {{ t('⚠ Fill an allocated price on every row, or clear them all.') }}
          </p>
          <p v-else-if="allocationState === 'mismatch'" class="row-warning">
            {{ t('⚠ Allocated prices sum to {sum} but the bundle price is {price} — they must match exactly.', { sum: money(allocationTotal), price: money(bundleForm.bundle_price || 0) }) }}
          </p>
          <p v-else-if="allocationState === 'ok'" class="muted small" style="color: var(--brand-dark)">
            {{ t('✓ Allocations match the bundle price.') }}
          </p>

          <div class="sub-label">{{ t('Outlets') }}</div>
          <div class="outlet-row">
            <label v-for="profile in session.availableProfiles" :key="profile" class="inline-check">
              <input type="checkbox" :value="profile" v-model="bundleForm.pos_profiles" />
              {{ profile }}
            </label>
            <span class="muted small">{{ t('(none ticked = all outlets)') }}</span>
          </div>
        </div>

        <!-- Sticky footer -->
        <div class="editor-footer">
          <button v-if="bundleForm.name && perms.bundles?.delete" class="btn btn-outline danger" @click="deleteBundle">{{ t('Delete') }}</button>
          <span style="flex: 1" />
          <button class="btn btn-outline" @click="editingBundle = false">{{ t('Cancel') }}</button>
          <button
            class="btn btn-primary"
            :disabled="saving || !bundleForm.items.some((r) => r.item_code) || allocationState === 'partial' || allocationState === 'mismatch'"
            @click="saveBundle"
          >
            {{ saving ? t('Saving…') : t('Save Bundle') }}
          </button>
        </div>
      </div>
    </section>

    <!-- ============ PRICE BOOKS ============ -->
    <section v-if="activeTab === 'Price Books'" class="tab-body">
      <!-- LIST -->
      <div v-if="!editingBook" class="list-view">
        <div class="list-head">
          <input v-model="bookSearch" class="list-search" :placeholder="t('Search price books…')" />
          <button v-if="perms.price_books?.create" class="btn btn-primary" @click="newBook">{{ t('+ New Price Book') }}</button>
        </div>
        <p class="muted hint-row">
          {{ t('A price book gives a set of items a special price for a period — a discount off your normal selling price — for chosen outlets/customer groups. Highest priority wins; delivery-app prices override price books.') }}
        </p>
        <div v-if="!priceBooks.length" class="muted empty">{{ t('No price books yet') }}</div>
        <div v-else class="card-list">
          <button v-for="book in filteredBooks" :key="book.name" class="entity-card" @click="editBook(book)">
            <span class="status-dot" :class="{ on: book.status === 'Active' }" />
            <div class="entity-main">
              <div class="entity-title">{{ book.title }}</div>
              <div class="muted small entity-sub">
                {{ t('{n} items · priority {p}', { n: (book.items || []).length, p: book.priority }) }}
                <span v-if="book.customer_groups.length"> · {{ book.customer_groups.join(', ') }}</span>
                <span v-if="book.valid_from || book.valid_to"> · {{ book.valid_from || '…' }} → {{ book.valid_to || '…' }}</span>
              </div>
            </div>
            <span v-if="book.expired" class="status-pill expired">{{ t('Expired') }}</span>
            <span class="status-pill" :class="{ on: book.status === 'Active' }">{{ t(book.status) }}</span>
          </button>
        </div>
      </div>

      <!-- EDITOR -->
      <div v-else class="editor">
        <!-- Validity & scope -->
        <div class="sec-card">
          <div class="sec-title"><Icon name="bulb" /> {{ t('Validity & scope') }}</div>
          <div class="field-grid">
            <label class="field span-2"><span>{{ t('Name *') }}</span><input v-model="bookForm.title" /></label>
            <label class="field"><span>{{ t('Priority') }}</span><input type="number" v-model.number="bookForm.priority" /></label>
            <label class="field"><span>{{ t('Valid from') }}</span><input type="date" v-model="bookForm.valid_from" /></label>
            <label class="field"><span>{{ t('Valid to') }}</span><input type="date" v-model="bookForm.valid_to" /></label>
          </div>
          <label class="inline-check" style="margin-bottom: 14px">
            <input type="checkbox" v-model="bookForm.status" true-value="Active" false-value="Inactive" />
            {{ t('Active') }}
          </label>
          <div class="sub-label">{{ t('Outlets & customers') }}</div>
          <div class="outlet-row">
            <label v-for="profile in session.availableProfiles" :key="profile" class="inline-check">
              <input type="checkbox" :value="profile" v-model="bookForm.pos_profiles" />
              {{ profile }}
            </label>
          </div>
          <div class="item-row">
            <LinkPicker
              doctype="Customer Group"
              v-model="groupPick"
              :placeholder="t('Customer group… (empty = everyone)')"
              @picked="(option) => addGroup(bookForm, option)"
            />
            <span v-for="(group, i) in bookForm.customer_groups" :key="group" class="chip-sm">
              {{ group }} <button class="btn-ghost" @click="bookForm.customer_groups.splice(i, 1)"><Icon name="close" /></button>
            </span>
          </div>
        </div>

        <!-- Items -->
        <div class="sec-card">
          <div class="sec-title">
            <span><Icon name="store" /> {{ t('Item prices') }}</span>
          </div>
          <p class="muted small" style="margin: 0 0 10px">
            {{ t('— these items sell at the price you set while the book is active; everything else keeps its normal price') }}
          </p>
          <div class="item-row">
            <LinkPicker
              doctype="Item"
              v-model="bookItemPick"
              :placeholder="t('+ Add item (name, code or barcode)…')"
              @picked="addBookItem"
            />
            <button class="btn btn-outline" :disabled="!(bookForm.items || []).length" @click="exportBookItems">
              <Icon name="download" /> {{ t('Export') }}
            </button>
            <button class="btn btn-outline" :disabled="bookImporting" @click="bookFileInput?.click()">
              <Icon name="upload" /> {{ bookImporting ? t('Importing…') : t('Import Excel/CSV') }}
            </button>
            <input ref="bookFileInput" type="file" accept=".csv,.xlsx,.xlsm,.xls" style="display: none" @change="importBookItems" />
          </div>
          <!-- Bulk-add every item in a brand / item group / tag in one click -->
          <div class="item-row">
            <span class="muted small" style="white-space: nowrap">{{ t('Add all by') }}</span>
            <select v-model="bookFetch.by" style="width: 120px" @change="bookFetch.value = ''; bookFetch.label = ''">
              <option value="Brand">{{ t('Brand') }}</option>
              <option value="Item Group">{{ t('Item Group') }}</option>
              <option value="Tag">{{ t('Tag') }}</option>
            </select>
            <LinkPicker
              :doctype="bookFetch.by"
              v-model="bookFetch.value"
              :label="bookFetch.label"
              :placeholder="t('Pick a brand / group / tag…')"
              @picked="(option) => (bookFetch.label = option?.name || option?.item_name || '')"
            />
            <button class="btn btn-outline" :disabled="!bookFetch.value || bookFetching" @click="fetchBookItems">
              {{ bookFetching ? t('Adding…') : t('Add matching') }}
            </button>
          </div>
          <div v-if="bookImportReport" class="import-report">
            <div class="gate-ok">{{ t('✓ Imported {n} item(s)', { n: bookImportReport.added }) }}</div>
            <div v-for="(err, i) in bookImportReport.errors" :key="i" class="gate-bad">⚠ {{ err }}</div>
            <button class="btn-ghost dismiss" @click="bookImportReport = null">{{ t('Dismiss') }}</button>
          </div>
          <!-- Discount every book price at once, with optional rounding -->
          <div v-if="(bookForm.items || []).length" class="item-row bulk-adjust">
            <span class="muted small" style="white-space: nowrap">{{ t('Discount all prices by') }}</span>
            <input type="number" min="0" max="100" step="0.5" v-model.number="bookBulk.percent" style="width: 80px" />
            <span class="muted small">%</span>
            <span class="muted small">{{ t('round to') }}</span>
            <select v-model="bookBulk.round" style="width: 120px">
              <option value="0">{{ t('No rounding') }}</option>
              <option value="0.05">0.05</option>
              <option value="0.25">0.25</option>
              <option value="0.5">0.50</option>
              <option value="1">1</option>
              <option value="5">5</option>
            </select>
            <button class="btn btn-outline" @click="applyBulkDiscount">{{ t('Apply to all') }}</button>
          </div>
          <table class="price-table" v-if="(bookForm.items || []).length">
            <thead>
              <tr><th>{{ t('Item') }}</th><th class="right">{{ t('Book price') }}</th><th></th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in bookForm.items" :key="i">
                <td>
                  <div class="price-item-name">{{ row.item_name || row.item_code }}</div>
                  <div class="muted small mono">{{ row.item_code }}</div>
                </td>
                <td class="right">
                  <input type="number" min="0" step="0.01" class="price-input" v-model.number="row.rate" />
                </td>
                <td><button class="btn-ghost" :title="t('Remove')" @click="bookForm.items.splice(i, 1)"><Icon name="close" /></button></td>
              </tr>
            </tbody>
          </table>
          <div v-else class="muted" style="padding: 8px 0 4px">
            {{ t('No items yet — add an item above or import an Excel/CSV file. Items not listed keep their normal selling price.') }}
          </div>
        </div>

        <!-- Sticky footer -->
        <div class="editor-footer">
          <button v-if="bookForm.name && perms.price_books?.delete" class="btn btn-outline danger" @click="deleteBook">{{ t('Delete') }}</button>
          <span style="flex: 1" />
          <button class="btn btn-outline" @click="editingBook = false">{{ t('Cancel') }}</button>
          <button class="btn btn-primary" :disabled="saving" @click="saveBook">
            {{ saving ? t('Saving…') : t('Save Price Book') }}
          </button>
        </div>
      </div>
    </section>

    <!-- ============ LOYALTY & GIFT CARDS ============ -->
    <section v-if="activeTab === 'Loyalty & Gift Cards'" class="tab-body">
      <!-- Loyalty -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="star" /> {{ t('Loyalty program') }}</div>
        <p class="muted hint-row" style="padding: 0">
          {{ t('Earning is automatic on every sale once a program exists (auto opt-in covers all customers). Redemption appears in the payment screen when the customer has points. Points expense posts to the configured expense account.') }}
        </p>
        <div v-if="!loyaltyPrograms.length && !creatingLoyalty" class="muted empty">
          {{ t('No loyalty program yet') }}
          <div style="margin-top: 10px">
            <button v-if="perms.loyalty" class="btn btn-primary" @click="creatingLoyalty = true">{{ t('+ Create program') }}</button>
          </div>
        </div>
        <div v-for="program in loyaltyPrograms" :key="program.name" class="info-row">
          <div class="row-title"><Icon name="star" /> {{ program.loyalty_program_name }}</div>
          <div class="muted small">
            {{ t('Earn 1 point per {factor} spent', { factor: program.collection_factor }) }} ·
            {{ t('1 point = {value}', { value: program.conversion_factor }) }} ·
            {{ program.expiry_duration ? t('points expire after {days} days', { days: program.expiry_duration }) : t('points never expire') }} ·
            {{ program.auto_opt_in ? t('all customers') : t('manual enrollment') }}
          </div>
        </div>
        <div v-if="loyaltyPrograms.length && perms.loyalty && !creatingLoyalty" class="editor-actions">
          <button class="btn btn-outline" @click="creatingLoyalty = true">{{ t('+ Another program') }}</button>
          <span style="flex: 1" />
        </div>

        <div v-if="creatingLoyalty" class="loyalty-editor">
          <div class="field-grid">
            <label class="field span-2"><span>{{ t('Program name *') }}</span><input v-model="loyaltyForm.name" :placeholder="t('e.g. Rewards')" /></label>
            <label class="field">
              <span>{{ t('Earn: 1 point per … spent *') }}</span>
              <input type="number" min="0.01" step="0.01" v-model.number="loyaltyForm.spend_per_point" />
            </label>
            <label class="field">
              <span>{{ t('Redeem: 1 point = … *') }}</span>
              <input type="number" min="0.01" step="0.01" v-model.number="loyaltyForm.point_value" />
            </label>
            <label class="field">
              <span>{{ t('Points expire after (days, 0 = never)') }}</span>
              <input type="number" min="0" v-model.number="loyaltyForm.expiry_days" />
            </label>
            <label class="field">
              <span>{{ t('Expense account (empty = auto-create)') }}</span>
              <LinkPicker doctype="Account" v-model="loyaltyForm.expense_account" :placeholder="t('Loyalty Points Expense…')" />
            </label>
          </div>
          <div class="editor-actions">
            <span style="flex: 1" />
            <button class="btn btn-outline" @click="creatingLoyalty = false">{{ t('Cancel') }}</button>
            <button class="btn btn-primary" :disabled="saving || !loyaltyForm.name" @click="saveLoyalty">
              {{ saving ? t('Creating…') : t('Create Program') }}
            </button>
          </div>
        </div>
      </div>

      <!-- Gift cards -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="gift" /> {{ t('Gift cards') }}</div>
        <p class="muted hint-row" style="padding: 0">
          {{ t('Sell cards from the gift-card button on the sell screen (money goes to the Gift Cards liability account — no tax until the card is spent). Redeem them as a payment method. Default expiry:') }}
          <b>{{ settingsInfo.gift_card_expiry_days ? t('{days} days', { days: settingsInfo.gift_card_expiry_days }) : t('never') }}</b>
          {{ t('(change it in the General tab).') }}
        </p>
        <div class="item-row">
          <input v-model="giftCardSearch" :placeholder="t('Search cards by number or customer…')" @input="debouncedLoadCards" style="max-width: 280px" />
        </div>
        <div v-if="!giftCardList.length" class="muted empty">{{ t('No gift cards yet') }}</div>
        <div v-for="card in giftCardList" :key="card.card_no" class="info-row gc-row">
          <div>
            <div class="row-title mono">{{ card.card_no }}</div>
            <div class="muted small">
              {{ t('{balance} of {initial} left', { balance: money(card.balance), initial: money(card.initial_amount) }) }}<span v-if="card.customer"> · {{ card.customer }}</span><span v-if="card.expiry_date"> · {{ t('expires {date}', { date: card.expiry_date }) }}</span>
            </div>
          </div>
          <div style="display: flex; gap: 8px; align-items: center">
            <span class="status-pill" :class="{ on: card.status === 'Active' }">{{ t(card.status) }}</span>
            <button v-if="card.status === 'Active' && perms.gift_cards" class="btn-ghost" :title="t('Disable card')" @click="disableCard(card)"><Icon name="ban" /></button>
          </div>
        </div>
      </div>
    </section>

    <!-- ============ CHANNELS & GENERAL ============ -->
    <section v-if="activeTab === 'General'" class="tab-body">
      <!-- Delivery apps -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="bike" /> {{ t('Delivery apps') }}</div>
        <p class="muted hint-row" style="padding: 0">
          {{ t('Sales can be tagged with the delivery app they came through. Each app can require an order ID and use its own price list — give an app its own list and tap') }} <b>{{ t('Edit prices') }}</b> {{ t('to set prices for that app only (e.g. Jahez prices). An app\'s price list overrides every price book.') }}
        </p>
        <div v-for="(app, i) in generalForm.delivery_apps" :key="i" class="app-block">
          <div class="item-row">
            <input v-model="app.app_name" :placeholder="t('App name (e.g. Jahez)')" />
            <LinkPicker doctype="Price List" v-model="app.price_list" :placeholder="t('Price list (optional)')" />
            <button class="btn-ghost new-pl" :title="t('Create a price list for this app')" @click="newAppPriceList(app)">{{ t('+ new') }}</button>
            <label class="inline-check">
              <input type="checkbox" v-model="app.require_order_id" :true-value="1" :false-value="0" />
              {{ t('Order ID required') }}
            </label>
            <button
              v-if="app.price_list"
              class="btn btn-outline"
              @click="expandedAppIdx = expandedAppIdx === i ? -1 : i"
            >
              {{ expandedAppIdx === i ? t('Hide prices') : t('Edit prices') }}
            </button>
            <button class="btn-ghost" @click="generalForm.delivery_apps.splice(i, 1)"><Icon name="close" /></button>
          </div>
          <PriceListEditor
            v-if="expandedAppIdx === i && app.price_list && !isProtected(app.price_list)"
            :key="app.price_list"
            :price-list="app.price_list"
            :compare-list="session.priceList"
            :can-manage="perms.edit_item_prices"
          />
          <div v-else-if="expandedAppIdx === i && isProtected(app.price_list)" class="dedicated-hint warn">
            <b>{{ t('“{list}” is a base selling list', { list: app.price_list }) }}</b> {{ t('— set a dedicated list for this app (＋ new) so its prices don\'t change your normal selling prices.') }}
          </div>
        </div>
        <button class="btn btn-outline add-row" @click="generalForm.delivery_apps.push({ app_name: '', price_list: '', require_order_id: 1 })">
          {{ t('+ Add delivery app') }}
        </button>
      </div>

      <!-- Register & Offline -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="store" /> {{ t('Register & Offline') }}</div>
        <div class="setting-list">
          <label class="setting-row">
            <input type="checkbox" class="setting-toggle" v-model="generalForm.allow_multiple_opening" :true-value="1" :false-value="0" />
            <span class="setting-text">
              <span class="setting-title">{{ t('Allow opening a new register while another shift is open') }}</span>
              <span class="setting-desc">{{ t('Testing only — keep OFF in production.') }}</span>
            </span>
          </label>
          <label class="setting-row">
            <input type="checkbox" class="setting-toggle" v-model="generalForm.offline_stock_only" :true-value="1" :false-value="0" />
            <span class="setting-text">
              <span class="setting-title">{{ t('Cache only in-stock items for offline use') }}</span>
              <span class="setting-desc">{{ t('Smaller, faster cache; refresh the catalog after changing.') }}</span>
            </span>
          </label>
          <label class="setting-row">
            <input type="checkbox" class="setting-toggle" v-model="generalForm.show_out_of_stock" :true-value="1" :false-value="0" />
            <span class="setting-text">
              <span class="setting-title">{{ t('Show out-of-stock items in the grid') }}</span>
              <span class="setting-desc">{{ t('Off = the sell grid shows only products with stock (services always show).') }}</span>
            </span>
          </label>
          <label class="setting-row">
            <input type="checkbox" class="setting-toggle" v-model="generalForm.serial_scan_only" :true-value="1" :false-value="0" />
            <span class="setting-text">
              <span class="setting-title">{{ t('Require scanning for serial numbers') }}</span>
              <span class="setting-desc">{{ t('Serial numbers must be scanned with a barcode scanner — manual typing is blocked. Turn off if no scanner is available.') }}</span>
            </span>
          </label>
          <label class="setting-row">
            <input type="checkbox" class="setting-toggle" v-model="generalForm.exchanges_enabled" :true-value="1" :false-value="0" />
            <span class="setting-text">
              <span class="setting-title">{{ t('Enable warranty exchanges') }}</span>
              <span class="setting-desc">{{ t('Shows the') }} <Icon name="exchange" /> {{ t('Exchange button. Warranty length comes from each item\'s warranty days.') }}</span>
            </span>
          </label>
        </div>
      </div>

      <!-- Gift cards mapping -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="gift" /> {{ t('Gift cards') }}</div>
        <p class="muted hint-row" style="padding: 0">
          {{ t('Map gift cards to your own accounting, or leave any field blank to auto-create the default. The') }} <b>{{ t('liability account') }}</b> {{ t('backs the cards (a sale increases it, redemption decreases it) and the') }} <b>{{ t('mode of payment') }}</b> {{ t('redeems them.') }}
        </p>
        <div class="field-grid">
          <label class="field">
            <span>{{ t('Mode of payment') }}</span>
            <LinkPicker doctype="Mode of Payment" v-model="generalForm.gift_card_mode_of_payment" :placeholder="t('Default: Gift Card')" />
          </label>
          <label class="field">
            <span>{{ t('Liability account') }}</span>
            <LinkPicker doctype="Account" v-model="generalForm.gift_card_account" :placeholder="t('Default: Gift Cards')" />
          </label>
          <label class="field">
            <span>{{ t('Gift card item') }}</span>
            <LinkPicker doctype="Item" v-model="generalForm.gift_card_item" :placeholder="t('Default: GIFT-CARD')" />
          </label>
          <label class="field">
            <span>{{ t('Expiry (days, 0 = never)') }}</span>
            <input type="number" min="0" v-model.number="generalForm.gift_card_expiry_days" />
          </label>
        </div>
      </div>

      <!-- Refunds -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="exchange" /> {{ t('Refunds') }}</div>
        <div class="setting-list">
          <label class="setting-row">
            <input type="checkbox" class="setting-toggle" v-model="generalForm.restrict_refund_to_paid_mode" :true-value="1" :false-value="0" />
            <span class="setting-text">
              <span class="setting-title">{{ t('Restrict refunds to the original payment method') }}</span>
              <span class="setting-desc">{{ t('A sale can only be refunded to a method the customer actually paid with (Store Credit is always allowed). Add exceptions below.') }}</span>
            </span>
          </label>
        </div>
        <template v-if="generalForm.restrict_refund_to_paid_mode">
          <p class="muted hint-row" style="padding: 10px 0 0">
            {{ t('Exceptions — “if paid with X, also allow refund as Y”. A method can always be refunded to itself, so only add the extras (e.g. paid') }} <b>{{ t('Mada') }}</b> → {{ t('also allow') }} <b>{{ t('Cash') }}</b>).
          </p>
          <div v-for="(rule, i) in generalForm.refund_rules" :key="i" class="rule-row">
            <span class="muted small">{{ t('If paid with') }}</span>
            <select v-model="rule.paid_mode" class="rule-select">
              <option value="">{{ t('— method —') }}</option>
              <option v-for="m in payModeOptions" :key="m" :value="m">{{ m }}</option>
            </select>
            <span class="muted small">{{ t('also allow refund as') }}</span>
            <select v-model="rule.refund_mode" class="rule-select">
              <option value="">{{ t('— method —') }}</option>
              <option v-for="m in payModeOptions" :key="m" :value="m">{{ m }}</option>
            </select>
            <button class="btn-ghost" @click="generalForm.refund_rules.splice(i, 1)"><Icon name="close" /></button>
          </div>
          <button
            class="btn btn-outline add-row"
            @click="generalForm.refund_rules.push({ paid_mode: '', refund_mode: '' })"
          >
            {{ t('+ Add refund rule') }}
          </button>
        </template>
      </div>

      <!-- Returns -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="refresh" /> {{ t('Returns') }}</div>
        <div class="setting-list">
          <label class="setting-row">
            <input type="checkbox" class="setting-toggle" v-model="generalForm.restrict_returns_to_window" :true-value="1" :false-value="0" />
            <span class="setting-text">
              <span class="setting-title">{{ t('Limit regular returns to a time window') }}</span>
              <span class="setting-desc">{{ t('Block returns after the window below. Past it, the cashier sends a return-approval request (approved by the Approver Role set under Discount approval).') }}</span>
            </span>
          </label>
        </div>
        <label v-if="generalForm.restrict_returns_to_window" class="field" style="max-width: 220px; margin-top: 10px">
          <span>{{ t('Return window (days, 0 = no limit)') }}</span>
          <input type="number" min="0" v-model.number="generalForm.return_window_days" />
        </label>
        <div class="sub-label" style="margin-top: 14px">{{ t('Return reasons') }}</div>
        <p class="muted hint-row" style="padding: 0 0 10px">
          {{ t('Shown at the till when a cashier refunds an item. The till always also offers') }}
          <b>{{ t('Other') }}</b> {{ t('for a free-text reason. Warranty exchanges default to') }}
          “{{ session.exchangeReturnReason }}”.
        </p>
        <div v-for="(r, i) in generalForm.return_reasons" :key="i" class="item-row">
          <input v-model="generalForm.return_reasons[i]" :placeholder="t('Reason (e.g. منتج تالف)')" />
          <button class="btn-ghost" @click="generalForm.return_reasons.splice(i, 1)"><Icon name="close" /></button>
        </div>
        <button
          class="btn btn-outline add-row"
          @click="generalForm.return_reasons.push('')"
        >
          {{ t('+ Add reason') }}
        </button>
      </div>

      <!-- Discount approval -->
      <div class="sec-card">
        <div class="sec-title"><Icon name="shield" /> {{ t('Discount approval') }}</div>
        <div class="field-grid">
          <label class="field">
            <span>{{ t('Discount limit % (0 = no limit)') }}</span>
            <input type="number" min="0" max="100" v-model.number="generalForm.discount_limit_percent" />
          </label>
          <label class="field">
            <span>{{ t('Over-limit approval method') }}</span>
            <select v-model="generalForm.discount_approval_mode">
              <option value="Passcode only">{{ t('Passcode only') }}</option>
              <option value="Request only">{{ t('Request only') }}</option>
              <option value="Passcode or request">{{ t('Passcode or request') }}</option>
            </select>
          </label>
        </div>
        <p class="muted hint-row">{{ modeHint }}</p>

        <!-- Passcode-based approval (a manager is at the till) -->
        <template v-if="generalForm.discount_approval_mode !== 'Request only'">
          <div class="field-grid">
            <label class="field">
              <span>{{ t('Master passcode') }} {{ settingsInfo.has_passcode ? t('(set — leave blank to keep)') : t('(optional)') }}</span>
              <input type="password" v-model="generalForm.discount_passcode" placeholder="••••" />
            </label>
          </div>
          <div class="sub-label">
            {{ t('Approvers — each manager has their own PIN; the name is recorded on the invoice') }}
          </div>
          <div v-for="(approver, i) in generalForm.approvers" :key="i" class="item-row">
            <input v-model="approver.approver_name" :placeholder="t('Approver name (e.g. Manager Khobar)')" />
            <input
              type="password"
              v-model="approver.passcode"
              :placeholder="approver.has_passcode ? t('PIN set — blank keeps it') : t('PIN')"
              style="max-width: 180px"
            />
            <button class="btn-ghost" @click="generalForm.approvers.splice(i, 1)"><Icon name="close" /></button>
          </div>
          <button
            class="btn btn-outline add-row"
            @click="generalForm.approvers.push({ approver_name: '', passcode: '' })"
          >
            {{ t('+ Add approver') }}
          </button>
        </template>

        <!-- Request-based approval (a role-holder approves remotely). The same
             role approves both discount AND return requests. -->
        <template v-if="generalForm.discount_approval_mode !== 'Passcode only' || generalForm.restrict_returns_to_window">
          <div class="sub-label">{{ t('Approver role for requests') }}</div>
          <div class="field-grid">
            <label class="field">
              <span>{{ t('Role that can approve requests (discount & return)') }}</span>
              <LinkPicker doctype="Role" v-model="generalForm.approver_role" :placeholder="t('e.g. LumenPOS Manager')" />
            </label>
          </div>
          <p class="muted hint-row">
            {{ t('Holders of this role (plus LumenPOS / System Managers) get an Approvals tray in the POS and can approve requests while the cashier\'s register is still open.') }}
          </p>
        </template>
      </div>

      <!-- Sticky footer -->
      <div class="editor-footer">
        <span style="flex: 1" />
        <button class="btn btn-primary" :disabled="saving || !canManage" @click="saveGeneral">
          {{ saving ? t('Saving…') : t('Save Settings') }}
        </button>
      </div>
      <p v-if="!canManage" class="muted hint-row">{{ t('You need write access to LumenPOS Settings to change these. Ask an administrator to grant the LumenPOS Manager role.') }}</p>
    </section>

    <!-- ============ STATUS ============ -->
    <section v-if="activeTab === 'Status'" class="tab-body">
      <div class="status-grid">
        <div class="stat sec-card"><div class="stat-label">{{ t('LumenPOS version') }}</div><div class="stat-value">{{ settingsInfo.version || '—' }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Outlet (POS Profile)') }}</div><div class="stat-value">{{ session.posProfile }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Default price list') }}</div><div class="stat-value">{{ session.priceList }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Connection') }}</div><div class="stat-value">{{ session.offline ? t('⚠ Offline') : t('✓ Online') }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Offline catalog cache') }}</div><div class="stat-value">{{ t('{n} items', { n: cachedItems }) }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Queued offline sales') }}</div><div class="stat-value">{{ session.queuedCount }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Receipt printer') }}</div><div class="stat-value">{{ session.printerConfigured ? t('✓ ESC/POS') : t('Browser print') }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Print format (POS Profile)') }}</div><div class="stat-value">{{ session.printFormat || t('Built-in receipt') }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('VAT / taxes') }}</div><div class="stat-value">{{ taxSummary }}</div></div>
        <div class="stat sec-card"><div class="stat-label">{{ t('Register') }}</div><div class="stat-value">{{ session.registerOpen ? t('Open') : t('Closed') }}</div></div>
      </div>
      <div class="editor-actions">
        <button class="btn btn-outline" @click="refreshCache"><Icon name="refresh" /> {{ t('Refresh offline catalog now') }}</button>
        <span style="flex: 1" />
      </div>
      <p class="muted hint-row">
        {{ t('Store-level settings (price list, warehouse, payment methods, taxes, printer) live on the') }} <b>{{ t('POS Profile') }}</b> {{ t('in ERPNext — that stays the single source of truth. This page covers what Vend kept in Setup: promotions, price books, channels and discount approval.') }}
      </p>
    </section>

  </div>
</template>

<script setup>
import Icon from '../components/Icon.vue'
import { ref, computed, onMounted } from 'vue'
import { call } from '../api'
import { money } from '../format'
import { useSessionStore } from '../stores/session'
import { useCatalogStore } from '../stores/catalog'
import { catalogCount } from '../offline'
import LinkPicker from '../components/LinkPicker.vue'
import PriceListEditor from '../components/PriceListEditor.vue'
import { t } from '../i18n'

const session = useSessionStore()
const catalog = useCatalogStore()

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
const ALL_TABS = ['Promotions', 'Bundles', 'Price Books', 'Loyalty & Gift Cards', 'General', 'Status']
const perms = computed(() => session.permissions || {})

function tabAllowed(tab) {
  const p = perms.value
  if (tab === 'Promotions') return p.promotions?.read
  if (tab === 'Bundles') return p.bundles?.read
  if (tab === 'Price Books') return p.price_books?.read
  if (tab === 'Loyalty & Gift Cards') return p.loyalty || p.gift_cards
  if (tab === 'General') return p.settings
  return true // Status is read-only info
}
const tabs = computed(() => ALL_TABS.filter(tabAllowed))
const activeTab = ref('Status')
// Settings-area manager (the General tab). Section-specific powers use perms.*
const canManage = computed(() => Boolean(perms.value.settings))
const saving = ref(false)
const settingsInfo = ref({})
const cachedItems = ref(0)
const groupPick = ref('')

const promotions = ref([])
const editingPromo = ref(false)
const promoForm = ref({})
const testBasket = ref([{ item_code: '', label: '', qty: 1 }])
const testResult = ref(null)
const testing = ref(false)

const priceBooks = ref([])
const editingBook = ref(false)
const bookForm = ref({})
const expandedAppIdx = ref(-1)

const bundles = ref([])
const editingBundle = ref(false)
const bundleForm = ref({})

const loyaltyPrograms = ref([])
const creatingLoyalty = ref(false)
const loyaltyForm = ref({ name: '', spend_per_point: 10, point_value: 0.1, expiry_days: 365, expense_account: '' })
const giftCardList = ref([])
const giftCardSearch = ref('')
let cardTimer = null

const generalForm = ref({
  delivery_apps: [],
  discount_limit_percent: 0,
  discount_passcode: '',
  discount_approval_mode: 'Passcode only',
  approver_role: '',
  restrict_returns_to_window: 0,
  return_window_days: 14,
  allow_multiple_opening: 0,
  offline_stock_only: 0,
  show_out_of_stock: 0,
  serial_scan_only: 0,
  gift_card_expiry_days: 0,
  gift_card_mode_of_payment: '',
  gift_card_account: '',
  gift_card_item: '',
  exchanges_enabled: 1,
  restrict_refund_to_paid_mode: 1,
  refund_rules: [],
  return_reasons: [],
  approvers: [],
})

// Payment methods offered in the refund-rule dropdowns.
const payModeOptions = computed(() => {
  const modes = (session.paymentModes || []).map((m) => m.mode_of_payment)
  if (session.storeCreditMode && !modes.includes(session.storeCreditMode)) {
    modes.push(session.storeCreditMode)
  }
  return modes
})

const hasInvalidRows = computed(() =>
  (promoForm.value.items || []).some((row) => !row.value)
)

const modeHint = computed(() => {
  const m = generalForm.value.discount_approval_mode
  if (m === 'Request only')
    return t('The cashier sends a request; a role-holder approves it while the register is open. No till passcode.')
  if (m === 'Passcode or request')
    return t('The cashier can either enter the manager passcode at the till or send a request for remote approval.')
  return t('A manager enters the passcode at the till to clear an over-limit discount.')
})

onMounted(() => {
  activeTab.value = tabs.value.includes('Promotions') ? 'Promotions' : tabs.value[0] || 'Status'
  load()
})

async function load() {
  cachedItems.value = await catalogCount().catch(() => 0)
  if (session.offline) return
  const info = await call('lumenpos.api.settings.get_settings')
  settingsInfo.value = info
  generalForm.value = {
    delivery_apps: JSON.parse(JSON.stringify(info.delivery_apps || [])),
    discount_limit_percent: info.discount_limit_percent || 0,
    discount_passcode: '',
    discount_approval_mode: info.discount_approval_mode || 'Passcode only',
    approver_role: info.approver_role || '',
    restrict_returns_to_window: info.restrict_returns_to_window || 0,
    return_window_days: info.return_window_days ?? 14,
    allow_multiple_opening: info.allow_multiple_opening || 0,
    offline_stock_only: info.offline_stock_only || 0,
    show_out_of_stock: info.show_out_of_stock || 0,
    serial_scan_only: info.serial_scan_only || 0,
    gift_card_expiry_days: info.gift_card_expiry_days || 0,
    gift_card_mode_of_payment: info.gift_card_mode_of_payment || '',
    gift_card_account: info.gift_card_account || '',
    gift_card_item: info.gift_card_item || '',
    exchanges_enabled: info.exchanges_enabled ?? 1,
    restrict_refund_to_paid_mode: info.restrict_refund_to_paid_mode ?? 1,
    refund_rules: JSON.parse(JSON.stringify(info.refund_rules || [])),
    return_reasons: [...(info.return_reasons || [])],
    approvers: (info.approvers || []).map((approver) => ({
      approver_name: approver.approver_name,
      has_passcode: approver.has_passcode,
      passcode: '',
    })),
  }
  promotions.value = await call('lumenpos.api.settings.list_promotions')
  priceBooks.value = await call('lumenpos.api.settings.list_price_books')
  bundles.value = await call('lumenpos.api.settings.list_bundles')
  loyaltyPrograms.value = await call('lumenpos.api.settings.list_loyalty_programs').catch(() => [])
  loadGiftCards()
}

// ---- loyalty & gift cards ----
async function saveLoyalty() {
  saving.value = true
  try {
    await call('lumenpos.api.settings.create_loyalty_program', {
      payload: { ...loyaltyForm.value, company: session.company },
    })
    session.notify(t('Loyalty program created — earning starts on the next sale'))
    creatingLoyalty.value = false
    loyaltyPrograms.value = await call('lumenpos.api.settings.list_loyalty_programs')
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

function debouncedLoadCards() {
  clearTimeout(cardTimer)
  cardTimer = setTimeout(loadGiftCards, 300)
}

async function loadGiftCards() {
  giftCardList.value = await call('lumenpos.api.settings.list_gift_cards', {
    search: giftCardSearch.value,
  }).catch(() => [])
}

async function disableCard(card) {
  if (!confirm(t('Disable gift card {card}? Its remaining balance becomes unusable.', { card: card.card_no }))) return
  try {
    await call('lumenpos.api.settings.disable_gift_card', { card_no: card.card_no })
    loadGiftCards()
  } catch (e) {
    session.notify(e.message, true)
  }
}

// ---- bundles ----
function newBundle() {
  bundleForm.value = {
    title: '', status: 'Active', bundle_price: 0,
    valid_from: null, valid_to: null,
    items: [{ item_code: '', label: '', qty: 1 }],
    pos_profiles: [],
  }
  editingBundle.value = true
}

function editBundle(bundle) {
  bundleForm.value = {
    name: bundle.name,
    title: bundle.title,
    status: bundle.status,
    bundle_price: bundle.bundle_price,
    valid_from: bundle.valid_from || null,
    valid_to: bundle.valid_to || null,
    items: bundle.items.map((row) => ({
      item_code: row.item_code,
      label: row.item_name || row.item_code,
      qty: row.qty,
      allocated_amount: row.allocated_amount || null,
    })),
    pos_profiles: [...(bundle.pos_profiles || [])],
  }
  editingBundle.value = true
}

const allocationTotal = computed(() =>
  (bundleForm.value.items || []).reduce(
    (sum, row) => sum + (Number(row.allocated_amount) || 0),
    0
  )
)

const taxSummary = computed(() => {
  const taxes = session.taxes || []
  if (!taxes.length) return t('No tax template')
  return taxes
    .map((tax) => {
      const label = tax.rate ? `${tax.description || t('Tax')} ${tax.rate}%` : tax.description || t('Tax')
      return tax.included
        ? t('{label} (included in price)', { label })
        : t('{label} (added on top)', { label })
    })
    .join(', ')
})

const allocationState = computed(() => {
  const rows = (bundleForm.value.items || []).filter((row) => row.item_code)
  if (!rows.length) return 'none'
  const filled = rows.filter((row) => Number(row.allocated_amount) > 0)
  if (!filled.length) return 'none'
  if (filled.length !== rows.length) return 'partial'
  return Math.abs(allocationTotal.value - (Number(bundleForm.value.bundle_price) || 0)) <= 0.01
    ? 'ok'
    : 'mismatch'
})

async function saveBundle() {
  saving.value = true
  try {
    const payload = JSON.parse(JSON.stringify(bundleForm.value))
    payload.items = payload.items.filter((row) => row.item_code)
    await call('lumenpos.api.settings.save_bundle', { payload })
    session.notify(t('Bundle saved'))
    editingBundle.value = false
    bundles.value = await call('lumenpos.api.settings.list_bundles')
    session.bundles = bundles.value.filter((bundle) => bundle.status === 'Active')
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

async function deleteBundle() {
  if (!confirm(t('Delete bundle "{title}"?', { title: bundleForm.value.title }))) return
  try {
    await call('lumenpos.api.settings.delete_bundle', { name: bundleForm.value.name })
    editingBundle.value = false
    bundles.value = await call('lumenpos.api.settings.list_bundles')
    session.bundles = bundles.value.filter((bundle) => bundle.status === 'Active')
  } catch (e) {
    session.notify(e.message, true)
  }
}

// ---- promotions ----
function newPromotion() {
  promoForm.value = {
    title: '', status: 'Active', promotion_type: 'Simple Discount',
    start_date: null, end_date: null, start_time: null, end_time: null,
    monday: 1, tuesday: 1, wednesday: 1, thursday: 1, friday: 1, saturday: 1, sunday: 1,
    stackable: 0, priority: 1, requires_coupon: 0, coupon_code: '',
    price_basis: 'Price Book Price',
    customer_eligibility: 'All Customers', apply_on_all: 0,
    discount_type: 'Percentage', discount_value: 0,
    buy_qty: 2, get_qty: 1, get_discount_type: 'Free', get_discount_value: 0, max_applications: 0,
    min_spend: 0, basket_discount_type: 'Percentage', basket_discount_value: 0,
    bundle_price: 0,
    pos_profiles: [], customer_groups: [], items: [],
  }
  couponStats.value = null
  couponMsg.value = ''
  editingPromo.value = true
}

// --- bulk coupon pool ---
const couponStats = ref(null)
const couponBusy = ref(false)
const couponMsg = ref('')
const couponFileInput = ref(null)
const couponGen = ref({ count: 50, prefix: '', usage_limit: 1, valid_until: '' })
const couponImp = ref({ usage_limit: 1, valid_until: '' })

async function loadCouponStats() {
  couponStats.value = null
  couponMsg.value = ''
  if (!promoForm.value.name) return
  try {
    couponStats.value = await call('lumenpos.api.settings.list_coupons', {
      promotion: promoForm.value.name,
    })
  } catch {
    /* ignore — coupon tools just won't show counts */
  }
}

async function generateCoupons() {
  if (!couponGen.value.count) return
  couponBusy.value = true
  couponMsg.value = ''
  try {
    const res = await call('lumenpos.api.settings.generate_coupons', {
      promotion: promoForm.value.name,
      count: couponGen.value.count,
      prefix: couponGen.value.prefix || '',
      usage_limit: couponGen.value.usage_limit ?? 1,
      valid_until: couponGen.value.valid_until || null,
    })
    couponStats.value = {
      total: res.total,
      used: res.used,
      available: res.available,
      redemptions: res.redemptions,
    }
    couponMsg.value = t('Generated {n} codes — click "Export codes" to download them', { n: res.created })
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    couponBusy.value = false
  }
}

function importCoupons(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const reader = new FileReader()
  reader.onload = async () => {
    couponBusy.value = true
    couponMsg.value = ''
    try {
      const res = await call('lumenpos.api.settings.import_coupons', {
        promotion: promoForm.value.name,
        filename: file.name,
        content: reader.result,
        usage_limit: couponImp.value.usage_limit ?? 1,
        valid_until: couponImp.value.valid_until || null,
      })
      couponStats.value = {
      total: res.total,
      used: res.used,
      available: res.available,
      redemptions: res.redemptions,
    }
      couponMsg.value = t('Imported {created} codes ({skipped} skipped)', {
        created: res.created,
        skipped: res.skipped,
      })
    } catch (e) {
      session.notify(e.message, true)
    } finally {
      couponBusy.value = false
    }
  }
  reader.readAsDataURL(file)
}

async function exportCoupons() {
  couponBusy.value = true
  try {
    const rows = await call('lumenpos.api.settings.export_coupons', { promotion: promoForm.value.name })
    const header = 'code,single_use,used,valid_until,batch\n'
    const body = rows
      .map((r) =>
        [r.code, r.single_use, r.used, r.valid_until || '', (r.batch || '').replace(/,/g, ' ')].join(',')
      )
      .join('\n')
    const blob = new Blob([header + body], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `coupons-${promoForm.value.name}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    couponBusy.value = false
  }
}

async function deleteUnusedCoupons() {
  if (!confirm(t('Delete all unused coupons for this promotion?'))) return
  couponBusy.value = true
  try {
    couponStats.value = await call('lumenpos.api.settings.delete_coupons', {
      promotion: promoForm.value.name,
      only_unused: 1,
    })
    couponMsg.value = ''
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    couponBusy.value = false
  }
}

async function editPromotion(name) {
  const data = await call('lumenpos.api.settings.get_promotion', { name })
  data.items = (data.items || []).map((row) => ({
    applies_to: row.applies_to || 'Item',
    value: row.item_code || row.item_group || row.brand || row.tag || '',
    label: row.item_code || row.item_group || row.brand || row.tag || '',
    role: row.role || 'Buy',
    qty: row.qty || 1,
    exclude: row.exclude || 0,
  }))
  promoForm.value = data
  editingPromo.value = true
  testResult.value = null
  testBasket.value = [{ item_code: '', label: '', qty: 1 }]
  loadCouponStats()
}

async function runTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await call('lumenpos.api.settings.test_promotion', {
      name: promoForm.value.name,
      pos_profile: session.posProfile,
      items: testBasket.value
        .filter((row) => row.item_code)
        .map((row) => ({ item_code: row.item_code, qty: row.qty || 1 })),
    })
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    testing.value = false
  }
}

function addGroup(form, option) {
  groupPick.value = ''
  if (option?.name && !form.customer_groups.includes(option.name)) {
    form.customer_groups.push(option.name)
  }
}

async function savePromotion() {
  if (hasInvalidRows.value) {
    session.notify(t('Pick every product row from the dropdown list first'), true)
    return
  }
  saving.value = true
  try {
    const payload = JSON.parse(JSON.stringify(promoForm.value))
    payload.customer_eligibility = payload.customer_groups.length
      ? 'Selected Customer Groups'
      : 'All Customers'
    payload.items = payload.items
      .filter((row) => row.value)
      .map((row) => ({
        applies_to: row.applies_to,
        item_code: row.applies_to === 'Item' ? row.value : null,
        item_group: row.applies_to === 'Item Group' ? row.value : null,
        brand: row.applies_to === 'Brand' ? row.value : null,
        tag: row.applies_to === 'Tag' ? row.value : null,
        role: row.role,
        qty: row.qty,
        exclude: row.exclude ? 1 : 0,
      }))
    await call('lumenpos.api.settings.save_promotion', { payload })
    session.notify(t('Promotion saved'))
    editingPromo.value = false
    promotions.value = await call('lumenpos.api.settings.list_promotions')
    session.refreshPromotions()
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

async function deletePromotion() {
  if (!confirm(t('Delete promotion "{title}"?', { title: promoForm.value.title }))) return
  try {
    await call('lumenpos.api.settings.delete_promotion', { name: promoForm.value.name })
    editingPromo.value = false
    promotions.value = await call('lumenpos.api.settings.list_promotions')
    session.refreshPromotions()
  } catch (e) {
    session.notify(e.message, true)
  }
}

// ---- price books ----
const bookItemPick = ref('')
const bookFileInput = ref(null)
const bookImporting = ref(false)
const bookImportReport = ref(null)
const bookFetch = ref({ by: 'Brand', value: '', label: '' })
const bookFetching = ref(false)
const bookBulk = ref({ percent: 10, round: '0' })

function roundTo(value, step) {
  step = Number(step) || 0
  if (step <= 0) return Math.round((value + Number.EPSILON) * 100) / 100
  return Math.round((value / step) + Number.EPSILON) * step
}

// Discount every item's book price by a % at once, with optional rounding to
// the nearest step. Applies to each row's CURRENT price.
function applyBulkDiscount() {
  const pct = Number(bookBulk.value.percent) || 0
  const items = bookForm.value.items || []
  if (!items.length) return
  if (!confirm(t('Apply a {pct}% discount to all {n} item prices?', { pct, n: items.length }))) return
  for (const row of items) {
    const base = Number(row.rate) || 0
    row.rate = roundTo(base * (1 - pct / 100), bookBulk.value.round)
  }
}

// Bulk-add every sellable item in a brand / item group / tag to the price book,
// each defaulted to its current selling price (the manager then discounts).
async function fetchBookItems() {
  if (!bookFetch.value.value) return
  bookFetching.value = true
  bookImportReport.value = null
  try {
    const args = {}
    if (bookFetch.value.by === 'Brand') args.brand = bookFetch.value.value
    else if (bookFetch.value.by === 'Item Group') args.item_group = bookFetch.value.value
    else args.tag = bookFetch.value.value
    const rows = await call('lumenpos.api.settings.resolve_items', args)
    let added = 0
    for (const r of rows) {
      if (!bookForm.value.items.some((x) => x.item_code === r.item_code)) {
        bookForm.value.items.push({ item_code: r.item_code, item_name: r.item_name, rate: r.rate || 0 })
        added++
      }
    }
    bookImportReport.value = { added, errors: [] }
    bookFetch.value = { by: bookFetch.value.by, value: '', label: '' }
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    bookFetching.value = false
  }
}

function newBook() {
  bookForm.value = {
    title: '', status: 'Active', priority: 1,
    valid_from: null, valid_to: null,
    pos_profiles: [], customer_groups: [], items: [],
  }
  bookImportReport.value = null
  editingBook.value = true
}

// Base selling lists must not be used as a DELIVERY-APP price list (apps still
// map to a real ERPNext Price List; editing a base list changes real prices).
const protectedPriceLists = computed(() => settingsInfo.value.protected_price_lists || [])
function isProtected(pl) {
  return !!pl && protectedPriceLists.value.includes(pl)
}

function editBook(book) {
  bookForm.value = {
    ...JSON.parse(JSON.stringify(book)),
    items: (book.items || []).map((r) => ({ ...r })),
  }
  bookImportReport.value = null
  editingBook.value = true
}

function addBookItem(option) {
  bookItemPick.value = ''
  if (!option?.name) return
  if (!bookForm.value.items) bookForm.value.items = []
  if (bookForm.value.items.some((r) => r.item_code === option.name)) {
    session.notify(t('{item} is already in this book', { item: option.item_name || option.name }), true)
    return
  }
  bookForm.value.items.unshift({
    item_code: option.name,
    item_name: option.item_name || option.name,
    rate: null,
  })
}

function importBookItems(event) {
  const file = event.target.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = async () => {
    bookImporting.value = true
    bookImportReport.value = null
    try {
      const res = await call('lumenpos.api.settings.parse_price_rows', {
        filename: file.name,
        content: reader.result,
      })
      if (!bookForm.value.items) bookForm.value.items = []
      let added = 0
      for (const row of res.items || []) {
        const existing = bookForm.value.items.find((r) => r.item_code === row.item_code)
        if (existing) existing.rate = row.rate
        else bookForm.value.items.push({ item_code: row.item_code, item_name: row.item_name, rate: row.rate })
        added += 1
      }
      bookImportReport.value = { added, errors: res.errors || [] }
      session.notify(t('Imported {n} item(s) — review and Save', { n: added }))
    } catch (e) {
      session.notify(e.message, true)
    } finally {
      bookImporting.value = false
      event.target.value = ''
    }
  }
  reader.readAsDataURL(file)
}

function exportBookItems() {
  const rows = [['Item Code', 'Item Name', 'Book Price']]
  for (const r of bookForm.value.items || []) rows.push([r.item_code, r.item_name || '', r.rate ?? ''])
  const csv = rows
    .map((cols) => cols.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${bookForm.value.title || 'price-book'} - items.csv`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

async function newAppPriceList(app) {
  const name = prompt(
    t('Name for this app price list (e.g. "Jahez Prices"):'),
    app.app_name ? t('{app} Prices', { app: app.app_name }) : ''
  )
  if (!name?.trim()) return
  try {
    app.price_list = await call('lumenpos.api.settings.create_price_list', {
      price_list_name: name.trim(),
    })
    session.notify(
      t('Price list "{list}" created — Save Settings to link it to {app}', { list: app.price_list, app: app.app_name || t('this app') })
    )
  } catch (e) {
    session.notify(e.message, true)
  }
}

async function saveBook() {
  if (!(bookForm.value.title || '').trim()) {
    session.notify(t('Give the price book a name'), true)
    return
  }
  saving.value = true
  try {
    const payload = {
      ...bookForm.value,
      items: (bookForm.value.items || [])
        .filter((r) => r.item_code)
        .map((r) => ({ item_code: r.item_code, rate: r.rate || 0 })),
    }
    await call('lumenpos.api.settings.save_price_book', { payload })
    session.notify(t('Price book saved'))
    editingBook.value = false
    priceBooks.value = await call('lumenpos.api.settings.list_price_books')
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

async function deleteBook() {
  if (!confirm(t('Delete price book "{title}"?', { title: bookForm.value.title }))) return
  try {
    await call('lumenpos.api.settings.delete_price_book', { name: bookForm.value.name })
    editingBook.value = false
    priceBooks.value = await call('lumenpos.api.settings.list_price_books')
  } catch (e) {
    session.notify(e.message, true)
  }
}

// ---- general ----
async function saveGeneral() {
  saving.value = true
  try {
    const info = await call('lumenpos.api.settings.save_settings', {
      payload: generalForm.value,
    })
    settingsInfo.value = info
    generalForm.value.discount_passcode = ''
    session.settings.delivery_apps = info.delivery_apps
    session.settings.discount_limit_percent = info.discount_limit_percent
    session.settings.discount_approval_mode = info.discount_approval_mode || 'Passcode only'
    session.settings.restrict_returns_to_window = info.restrict_returns_to_window || 0
    session.settings.return_window_days = info.return_window_days || 0
    session.settings.return_reasons = info.return_reasons || []
    session.settings.show_out_of_stock = info.show_out_of_stock || 0
    session.settings.serial_scan_only = info.serial_scan_only || 0
    session.notify(t('Settings saved'))
  } catch (e) {
    session.notify(e.message, true)
  } finally {
    saving.value = false
  }
}

async function refreshCache() {
  session.notify(t('Refreshing catalog cache…'))
  await catalog.cacheFullCatalog()
  cachedItems.value = await catalogCount().catch(() => 0)
  session.notify(t('Cached {n} items for offline use', { n: cachedItems.value }))
}

// ---- presentational helpers (UI re-layout only — no behaviour change) ----
const PROMO_TYPES = ['Simple Discount', 'Buy X Get Y', 'Spend and Save']
const showTest = ref(false)
const promoSearch = ref('')
const bundleSearch = ref('')
const bookSearch = ref('')

const filteredPromotions = computed(() => {
  const q = promoSearch.value.trim().toLowerCase()
  if (!q) return promotions.value
  return promotions.value.filter((p) => (p.title || '').toLowerCase().includes(q))
})
const filteredBundles = computed(() => {
  const q = bundleSearch.value.trim().toLowerCase()
  if (!q) return bundles.value
  return bundles.value.filter((b) => (b.title || '').toLowerCase().includes(q))
})
const filteredBooks = computed(() => {
  const q = bookSearch.value.trim().toLowerCase()
  if (!q) return priceBooks.value
  return priceBooks.value.filter((b) => (b.title || '').toLowerCase().includes(q))
})
</script>

<style scoped>
.settings {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  max-width: 920px;
  margin: 0 auto;
  width: 100%;
}

/* ---- Segmented pill tab bar ---- */
.tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 16px;
  flex-wrap: wrap;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 5px;
}
.tab {
  border: 1px solid transparent;
  background: transparent;
  border-radius: 999px;
  padding: 8px 18px;
  font-weight: 500;
  font-size: 13px;
  color: var(--text-muted);
  transition: background 0.12s ease, color 0.12s ease;
}
.tab:hover { color: var(--text); }
.tab.active { background: var(--brand-soft); color: #fff; }

.tab-body { display: flex; flex-direction: column; gap: 14px; }

/* ---- List (master) view ---- */
.list-view { display: flex; flex-direction: column; gap: 0; }
.list-head { display: flex; gap: 10px; align-items: center; margin-bottom: 6px; }
.list-search { flex: 1; min-width: 160px; }
.hint-row { font-size: 12.5px; margin: 0 0 10px; }
.empty {
  padding: 48px;
  text-align: center;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.card-list { display: flex; flex-direction: column; gap: 8px; }
.entity-card {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  text-align: left;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  transition: border-color 0.12s ease, background 0.12s ease;
}
.entity-card:hover { background: var(--surface-2); border-color: var(--brand-soft); }
.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 999px;
  background: var(--text-muted);
  flex: none;
  opacity: 0.5;
}
.status-dot.on { background: var(--brand); opacity: 1; }
.entity-main { flex: 1; min-width: 0; }
.entity-title { font-weight: 500; display: flex; align-items: center; gap: 6px; }
.entity-sub { margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.entity-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--brand-dark);
  white-space: nowrap;
}
.row-title { font-weight: 500; }
.small { font-size: 12px; }
.status-pill {
  font-size: 11px;
  font-weight: 500;
  border-radius: 999px;
  padding: 3px 11px;
  background: var(--surface-2);
  color: var(--text-muted);
  white-space: nowrap;
}
.status-pill.on { background: rgba(46, 91, 255, 0.1); color: var(--brand-dark); }
.status-pill.expired { background: rgba(226, 48, 48, 0.12); color: var(--red); }
html[data-theme='dark'] .status-pill.expired { background: rgba(255, 120, 120, 0.18); color: #ff9b9b; }

/* ---- Editor (detail) view ---- */
.editor { display: flex; flex-direction: column; gap: 14px; padding-bottom: 84px; }

/* Grouped section cards */
.sec-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
}
.sec-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text);
  margin-bottom: 14px;
}
.sec-title > span:first-child { display: inline-flex; align-items: center; gap: 8px; }
.sec-title .icon { color: var(--brand); }
button.sec-title.collapsible {
  width: 100%;
  text-align: left;
  margin-bottom: 0;
}
button.sec-title.collapsible + * { margin-top: 14px; }

.field-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}
.field { display: flex; flex-direction: column; gap: 5px; }
.field span { font-size: 11.5px; font-weight: 500; color: var(--text-muted); }
.span-2 { grid-column: span 2; }

.sub-label {
  font-size: 11.5px;
  font-weight: 500;
  color: var(--text-muted);
  margin: 16px 0 8px;
}

/* Segmented control (promotion type) */
.seg-field { margin-top: 14px; }
.seg-label { display: block; font-size: 11.5px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; }
.segmented {
  display: inline-flex;
  gap: 4px;
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 4px;
  flex-wrap: wrap;
}
.seg-btn {
  border-radius: calc(var(--radius) - 2px);
  padding: 7px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
}
.seg-btn:hover { color: var(--text); }
.seg-btn.on { background: var(--brand-soft); color: #fff; }

.toggle-row { display: flex; gap: 20px; align-items: center; flex-wrap: wrap; margin-top: 14px; }

.day-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.day-chip {
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  text-transform: capitalize;
}
.day-chip.on { background: var(--brand); border-color: var(--brand); color: #fff; }

.inline-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text);
  cursor: pointer;
  white-space: nowrap;
}

/* Products header row */
.prod-head {
  display: flex;
  gap: 8px;
  font-size: 10.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.prod-head .ph-mode { width: 96px; }
.prod-head .ph-type { width: 110px; }
.prod-head .ph-pick { flex: 1; }

/* Coupons */
.coupon-pool {
  margin: 0;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-2);
}
.coupon-stats { font-weight: 500; font-size: 12.5px; margin-bottom: 8px; }
.coupon-pool .item-row { margin-bottom: 8px; flex-wrap: wrap; }
.inline-num { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--text-muted); white-space: nowrap; }
.bulk-adjust { align-items: center; flex-wrap: wrap; gap: 8px; margin: 4px 0 10px; }

.item-row { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.mode-select { width: 96px; font-weight: 500; }
.mode-select.excluding { color: var(--red); border-color: rgba(226, 48, 48, 0.4); }
.new-pl { font-size: 11px; color: var(--brand); padding: 0 4px; }
.price-table { width: 100%; border-collapse: collapse; margin: 4px 0 8px; }
.price-table th {
  text-align: left;
  font-size: 10.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  padding: 6px 8px;
}
.price-table th.right, .price-table td.right { text-align: right; }
.price-table td { padding: 7px 8px; border-top: 1px solid var(--border); }
.price-item-name { font-weight: 500; font-size: 13px; }
.mono { font-family: ui-monospace, monospace; }
.price-input { width: 110px; text-align: right; padding: 6px 9px; }
.price-input.dirty { border-color: var(--amber); }
.item-row input { flex: 1; min-width: 160px; }
.add-row { margin-top: 2px; }

/* iOS-style settings list */
.setting-list { display: flex; flex-direction: column; }
.setting-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 13px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.setting-row:first-child { padding-top: 0; }
.setting-row:last-child { border-bottom: none; padding-bottom: 0; }
.setting-toggle { margin-top: 2px; width: 17px; height: 17px; flex-shrink: 0; cursor: pointer; }
.setting-text { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 0; }
.setting-title { font-weight: 500; font-size: 13.5px; color: var(--text); }
.setting-desc { font-size: 12px; color: var(--text-muted); line-height: 1.4; }

.rule-row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.rule-select { min-width: 150px; }
.dedicated-hint {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin: 8px 0;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}
.dedicated-hint.warn {
  background: rgba(245, 166, 35, 0.12);
  border-color: rgba(245, 166, 35, 0.4);
  color: var(--text);
}
.app-block {
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius);
  padding: 10px 12px;
  margin-bottom: 10px;
}
.app-block .item-row { margin-bottom: 0; }
.app-block .ple { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-subtle); }
.outlet-row { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 10px; }
.chip-sm {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  background: rgba(46, 91, 255, 0.08);
  color: var(--brand-dark);
  border-radius: 999px;
  padding: 4px 11px;
}

/* Loyalty / gift card inner blocks */
.loyalty-editor { margin-top: 14px; padding-top: 14px; border-top: 1px solid var(--border-subtle); }
.info-row {
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.info-row:last-child { border-bottom: none; }
.info-row.gc-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.editor-actions { display: flex; gap: 10px; margin-top: 14px; }
.danger { color: var(--red); }
.row-warning {
  color: var(--amber);
  font-weight: 500;
  font-size: 12.5px;
  margin: 8px 0 0;
}
.test-report {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  margin: 10px 0 4px;
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gate-ok { color: var(--brand-dark); font-weight: 500; }
.import-report {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
  margin: 4px 0 10px;
  font-size: 12.5px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.import-report .dismiss { align-self: flex-start; margin-top: 4px; color: var(--text-muted); }
.gate-bad { color: var(--red); font-weight: 500; }
.test-verdict {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
  font-size: 14px;
}

/* Sticky action footer */
.editor-footer {
  position: sticky;
  bottom: 0;
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 16px;
  margin: 0 -16px -16px;
  background: var(--card-bg);
  border-top: 1px solid var(--border);
  box-shadow: 0 -2px 8px rgba(20, 26, 40, 0.06);
  z-index: 5;
}

/* Status metric cards */
.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
}
.stat { padding: 14px 16px; }
.stat-label {
  font-size: 11.5px;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}
.stat-value { font-size: 16px; font-weight: 500; margin-top: 3px; }
</style>
