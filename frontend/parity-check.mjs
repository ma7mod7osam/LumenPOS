// Quick parity check: run the same scenarios through the JS engine and
// compare against expected values from the Python unit tests.
// Usage: node parity-check.mjs
import { evaluatePromotions } from './src/promotions.js'

const NOW = new Date(2026, 5, 10, 14, 0, 0) // Wed 2026-06-10 14:00

const base = {
  name: 'PROMO-TEST', title: 'Test', promotion_type: 'Simple Discount',
  priority: 1, stackable: 0, days: {}, pos_profiles: [],
  customer_eligibility: 'All Customers', customer_groups: [],
  apply_on_all: 0, items: [], max_applications: 0,
}
const cart = (items, extra = {}) => ({ customer_group: null, pos_profile: 'Main Store', items, ...extra })
const line = (item_code, price, qty = 1, item_group = 'Products') => ({ item_code, item_group, brand: null, qty, price })

let failures = 0
function check(label, actual, expected) {
  const ok = Math.abs(actual - expected) < 0.001
  if (!ok) failures++
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}: got ${actual}, want ${expected}`)
}

// 10% off COLA x3 @ 2.00 -> 0.60
let r = evaluatePromotions(
  cart([line('COLA', 2, 3), line('CHIPS', 1.5)]),
  [{ ...base, items: [{ applies_to: 'Item', value: 'COLA', role: 'Buy' }], discount_type: 'Percentage', discount_value: 10 }],
  NOW
)
check('simple percentage', r.total_savings, 0.6)

// Buy 2 get 1 free shared pool: 2x COLA@2 + 1x JUICE@3 -> cheapest (2.0) free
r = evaluatePromotions(
  cart([line('COLA', 2, 2, 'Drinks'), line('JUICE', 3, 1, 'Drinks')]),
  [{ ...base, promotion_type: 'Buy X Get Y', items: [{ applies_to: 'Item Group', value: 'Drinks', role: 'Buy' }], buy_qty: 2, get_qty: 1, get_discount_type: 'Free' }],
  NOW
)
check('bxgy shared pool', r.total_savings, 2.0)

// 6x COLA, buy2get1 -> 2 applications -> 4.0
r = evaluatePromotions(
  cart([line('COLA', 2, 6)]),
  [{ ...base, promotion_type: 'Buy X Get Y', items: [{ applies_to: 'Item', value: 'COLA', role: 'Buy' }], buy_qty: 2, get_qty: 1, get_discount_type: 'Free' }],
  NOW
)
check('bxgy repeats', r.total_savings, 4.0)

// Buy SHIRT get TIE 50% off
r = evaluatePromotions(
  cart([line('SHIRT', 40), line('TIE', 10)]),
  [{ ...base, promotion_type: 'Buy X Get Y', items: [
    { applies_to: 'Item', value: 'SHIRT', role: 'Buy' },
    { applies_to: 'Item', value: 'TIE', role: 'Get' },
  ], buy_qty: 1, get_qty: 1, get_discount_type: 'Percentage', get_discount_value: 50 }],
  NOW
)
check('bxgy separate get pool', r.total_savings, 5.0)

// Spend 100 save 10%
r = evaluatePromotions(
  cart([line('TV', 120)]),
  [{ ...base, promotion_type: 'Spend and Save', apply_on_all: 1, min_spend: 100, basket_discount_type: 'Percentage', basket_discount_value: 10 }],
  NOW
)
check('spend and save', r.basket_discount, 12.0)

// Stacking: exclusive 20% beats exclusive 10%
r = evaluatePromotions(
  cart([line('A', 10)]),
  [
    { ...base, title: '10 off', apply_on_all: 1, discount_type: 'Percentage', discount_value: 10 },
    { ...base, title: '20 off', apply_on_all: 1, discount_type: 'Percentage', discount_value: 20 },
  ],
  NOW
)
check('best exclusive wins', r.total_savings, 2.0)

// Weekday gate: Saturday-only promo on a Wednesday
const days = Object.fromEntries(['monday','tuesday','wednesday','thursday','friday','saturday','sunday'].map(d => [d, 0]))
days.saturday = 1
r = evaluatePromotions(
  cart([line('A', 10)]),
  [{ ...base, apply_on_all: 1, discount_type: 'Percentage', discount_value: 10, days }],
  NOW
)
check('weekday gate', r.total_savings, 0)

// Midnight-wrapping happy hour
const hh = { ...base, apply_on_all: 1, discount_type: 'Percentage', discount_value: 10, start_time: '22:00:00', end_time: '02:00:00' }
r = evaluatePromotions(cart([line('A', 10)]), [hh], new Date(2026, 5, 10, 23, 30))
check('late-night window active', r.total_savings, 1.0)
r = evaluatePromotions(cart([line('A', 10)]), [hh], new Date(2026, 5, 10, 12, 0))
check('late-night window inactive at noon', r.total_savings, 0)

// Bundle: A(120) + B(120) + C(100) for 300 -> 40 off across separate lines
const bundle = {
  ...base, promotion_type: 'Bundle Price', bundle_price: 300,
  items: [
    { applies_to: 'Item', value: 'A', role: 'Buy', qty: 1 },
    { applies_to: 'Item', value: 'B', role: 'Buy', qty: 1 },
    { applies_to: 'Item', value: 'C', role: 'Buy', qty: 1 },
  ],
}
r = evaluatePromotions(cart([line('A', 120), line('B', 120), line('C', 100)]), [bundle], NOW)
check('bundle three for 300', r.total_savings, 40)
r = evaluatePromotions(cart([line('A', 120), line('B', 120)]), [bundle], NOW)
check('bundle missing component', r.total_savings, 0)
r = evaluatePromotions(
  cart([line('A', 120, 2), line('B', 120, 2), line('C', 100, 2)]), [bundle], NOW
)
check('bundle repeats (cent-correct)', r.total_savings, 80)

// Coupon gate
const couponPromo = {
  ...base, apply_on_all: 1, discount_type: 'Percentage', discount_value: 10,
  requires_coupon: 1, coupon_code: 'SAVE10',
}
r = evaluatePromotions(cart([line('A', 10)]), [couponPromo], NOW)
check('coupon required (no code)', r.total_savings, 0)
r = evaluatePromotions(
  { ...cart([line('A', 10)]), coupon_codes: ['save10'] }, [couponPromo], NOW
)
check('coupon applied', r.total_savings, 1)

// Exclusions: all products except brand Apple
const exclPromo = {
  ...base, apply_on_all: 1, discount_type: 'Percentage', discount_value: 10,
  items: [{ applies_to: 'Brand', value: 'Apple', role: 'Buy', exclude: 1 }],
}
r = evaluatePromotions(
  cart([
    { item_code: 'CABLE', item_group: 'G', brand: 'Apple', qty: 1, price: 100 },
    { item_code: 'CHIPS', item_group: 'G', brand: 'Lays', qty: 1, price: 50 },
  ]),
  [exclPromo], NOW
)
check('exclude brand from all', r.total_savings, 5)

// Tag scope: 10% off items tagged "vip" (only the tagged line discounts)
const tagPromo = {
  ...base, discount_type: 'Percentage', discount_value: 10,
  items: [{ applies_to: 'Tag', value: 'vip', role: 'Buy' }],
}
r = evaluatePromotions(
  cart([
    { item_code: 'A', item_group: 'G', brand: 'B', tags: ['vip', 'new'], qty: 1, price: 100 },
    { item_code: 'C', item_group: 'G', brand: 'B', tags: ['clearance'], qty: 1, price: 50 },
  ]),
  [tagPromo], NOW
)
check('tag scope matches tagged item', r.total_savings, 10)

// Equal times = all day (empty-field guard)
const equalTimes = {
  ...base, apply_on_all: 1, discount_type: 'Percentage', discount_value: 10,
  start_time: '00:00:00', end_time: '00:00:00',
}
r = evaluatePromotions(cart([line('A', 10)]), [equalTimes], NOW)
check('equal times treated as all day', r.total_savings, 1)

// Promotion price basis (price book 49 / standard 99)
const bookLine = [{ item_code: 'A', item_group: 'G', brand: 'B', qty: 1, price: 49, standard_price: 99 }]
const basisBook = { ...base, apply_on_all: 1, discount_type: 'Percentage', discount_value: 20, price_basis: 'Price Book Price' }
r = evaluatePromotions(cart(bookLine), [basisBook], NOW)
check('basis: price book price stacks (20% of 49)', r.total_savings, 9.8)
const basisStd = { ...base, apply_on_all: 1, discount_type: 'Percentage', discount_value: 20, price_basis: 'Standard Price' }
r = evaluatePromotions(cart(bookLine), [basisStd], NOW)
check('basis: standard price, book lower wins', r.total_savings, 0)
r = evaluatePromotions(
  cart([{ item_code: 'A', item_group: 'G', brand: 'B', qty: 1, price: 90, standard_price: 99 }]),
  [{ ...basisStd, discount_value: 50 }], NOW
)
check('basis: standard price, promo beats book', r.total_savings, 40.5)

process.exit(failures ? 1 : 0)
