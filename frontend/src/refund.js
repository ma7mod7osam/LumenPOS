// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
//
// Taking a sale back WITHOUT a connection (0.56.0).
//
// The till pays the money out before the server sees the return, so it must
// know the figure the books will show. This repeats ERPNext's own arithmetic
// for the credit note (erpnext/controllers/taxes_and_totals.py, with Frappe's
// rounding) on what the server told the till with the sale (sales._sale_answer)
// or, for a sale still waiting to upload, on what the till itself charged. The
// server still posts ERPNext's figure (sales.create_return) and records any
// difference, so this only has to be right, it is never trusted.
//
// Pure functions, no store and no Vue: the bench suite runs this file in node
// against real credit notes on every supported ERPNext version.

const LEGACY = "Banker's Rounding (legacy)"
// The charges this file can work out. Anything else (a service charge is an
// "Actual" row) makes the return wait for the connection.
const SUPPORTED = ['On Net Total', 'On Previous Row Total']

const F64 = new Float64Array(1)
const BITS = new BigUint64Array(F64.buffer)

// Python's round(x, digits) (float.__round__), exactly: the float's exact
// binary value rounded to `digits` decimals, an exact tie to the even digit,
// and the decimal read back as the nearest float. Multiplying by 10 ** digits
// first would round twice: 0.705 plus its last-place nudge times 100 lands on
// 70.5 exactly, and Frappe's Commercial Rounding would then go the wrong way.
function pyRound(x, digits = 0) {
  if (!Number.isFinite(x) || x === 0) return x
  F64[0] = x
  const bits = BITS[0]
  const exponent = Number((bits >> 52n) & 0x7ffn)
  let mantissa = bits & 0xfffffffffffffn
  if (exponent) mantissa |= 0x10000000000000n
  const power = (exponent || 1) - 1075 // |x| = mantissa * 2 ** power
  if (power >= 0) return x // a whole number already
  const scaled = mantissa * 10n ** BigInt(digits)
  const unit = 1n << BigInt(-power)
  let q = scaled / unit
  const twice = (scaled % unit) * 2n
  if (twice > unit || (twice === unit && q % 2n === 1n)) q += 1n
  let text = q.toString()
  if (digits > 0) {
    text = text.padStart(digits + 1, '0')
    text = text.slice(0, -digits) + '.' + text.slice(-digits)
  }
  return x < 0 ? -Number(text) : Number(text)
}

// Python's math.ulp(x): the gap to the next float up.
function ulp(x) {
  F64[0] = Math.abs(x)
  const exponent = Number((BITS[0] >> 52n) & 0x7ffn)
  return 2 ** ((exponent || 1) - 1075)
}

// Frappe's rounded() / flt(x, precision) (frappe/utils/data.py), each of the
// three methods a site can choose (System Settings, v14 and later; v13 has
// the legacy one only), on the signed value as ERPNext computes a credit
// note: under the legacy method -1.515 rounds to -1.51 where 1.515 gives 1.52.
// `commercial`: how the site's Frappe nudges a tie away from zero, by the
// value's last place ('ulp', v16) or by 2 ** (log2 x - 52) ('log', v14, v15),
// as sales.rounding_rule reports it.
export function frappeRound(num, precision = 2, method = LEGACY, commercial = 'ulp') {
  if (!Number.isFinite(num) || num === 0) return 0
  const multiplier = 10 ** precision
  const sign = num < 0 ? -1 : 1
  if (method === "Banker's Rounding") {
    const n = pyRound(Math.abs(num) * multiplier, 12)
    if (n === 0) return 0
    const floor = Math.floor(n)
    const epsilon = 2 ** (Math.log2(n) - 52)
    const tie = epsilon < 0.5 && Math.abs(n - floor - 0.5) < epsilon
    const out = tie ? (floor % 2 === 0 ? floor : floor + 1) : pyRound(n)
    return (sign * out) / multiplier
  }
  if (method === 'Commercial Rounding') {
    // A tie goes away from zero: the value is nudged outwards first.
    const nudge = commercial === 'log' ? 2 ** (Math.log(Math.abs(num)) / Math.log(2) - 52) : ulp(num)
    return pyRound(num + sign * nudge, precision)
  }
  // Banker's Rounding (legacy): Frappe's default before v16, the only one on v13.
  let n = pyRound(precision ? num * multiplier : num, 8)
  const floor = Math.floor(n)
  const decimal = n - floor
  if (!precision && decimal === 0.5) n = floor % 2 === 0 ? floor : floor + 1
  else if (decimal === 0.5) n = floor + 1
  else n = pyRound(n)
  return precision ? n / multiplier : n
}

// Frappe's remainder(), with Python's float modulo (the divisor's sign).
function remainder(num, den, precision, method, commercial) {
  const m = 10 ** precision
  const a = precision ? num * m : num
  const b = precision ? den * m : den
  let r = a % b
  if (r !== 0 && b < 0 !== r < 0) r += b
  return frappeRound(precision ? r / m : r, precision, method, commercial)
}

// round_based_on_smallest_currency_fraction (frappe/utils/data.py).
export function roundTotal(value, rule = {}) {
  const precision = rule.precision ?? 2
  const method = rule.method || LEGACY
  const commercial = rule.commercial || 'ulp'
  if (rule.disabled) return frappeRound(value, precision, method, commercial)
  const fraction = Number(rule.fraction) || 0
  let v = value
  if (fraction) {
    const rem = remainder(v, fraction, precision, method, commercial)
    if (rem > fraction / 2) v += fraction - rem
    else v -= rem
  } else {
    v = frappeRound(v, 0, method, commercial)
  }
  return frappeRound(v, precision, method, commercial)
}

// One row per item code, as sales._build_return_doc keeps it: the FIRST line
// of that item on the sale, carrying the whole quantity.
export function saleItems(record) {
  const out = []
  const byCode = {}
  for (const line of record?.lines || []) {
    const row = byCode[line.item_code]
    if (row) {
      row.qty += Number(line.qty) || 0
      continue
    }
    byCode[line.item_code] = {
      item_code: line.item_code,
      item_name: line.item_name || line.item_code,
      qty: Number(line.qty) || 0,
      rate: Number(line.rate) || 0,
      item_tax_rate: line.item_tax_rate || {},
      serial: Boolean(line.serial),
      group: line.group || null,
    }
    out.push(byCode[line.item_code])
  }
  const returned = record?.returned || {}
  for (const row of out) {
    row.returned = Number(returned[row.item_code]) || 0
    row.returnable = Math.max(0, pyRound(row.qty - row.returned, 8))
  }
  return out
}

/**
 * What ERPNext will refund for taking back `picks` ({item_code: qty}, positive
 * quantities) of this sale: {total, grand, net, tax}, positive, in the sale's
 * currency. `total` is what the customer gets (the rounded total when the
 * site rounds totals). null when the sale carries a charge this file cannot
 * work out, so the return has to wait for the connection.
 */
export function estimateRefund(record, picks) {
  const rule = record?.rounding || {}
  const precision = rule.precision ?? 2
  const method = rule.method || LEGACY
  const f = (x) => frappeRound(x, precision, method, rule.commercial || 'ulp')
  const taxes = record?.taxes || []
  if (taxes.some((t) => !SUPPORTED.includes(t.charge_type))) return null
  const rateFor = (tax, item) =>
    item.item_tax_rate && Object.prototype.hasOwnProperty.call(item.item_tax_rate, tax.account_head)
      ? Number(item.item_tax_rate[tax.account_head]) || 0
      : Number(tax.rate) || 0

  // calculate_item_values: a credit note line is the sale's rate times a
  // negative quantity.
  const items = saleItems(record)
    .filter((row) => Number(picks?.[row.item_code]) > 0)
    .map((row) => {
      const qty = -Number(picks[row.item_code])
      const amount = f(row.rate * qty)
      return { ...row, qty, amount, net: amount }
    })
  if (!items.length) return { total: 0, grand: 0, net: 0, tax: 0 }

  // determine_exclusive_rate: prices that include tax are brought back to net.
  const inclusive = taxes.some((t) => Number(t.included))
  if (inclusive) {
    for (const item of items) {
      let slope = 0
      const fractions = []
      taxes.forEach((tax, i) => {
        let s = 0
        if (Number(tax.included)) {
          const rate = rateFor(tax, item) / 100
          if (tax.charge_type === 'On Net Total') s = rate
          else s = rate * (fractions[(Number(tax.row_id) || i) - 1] ?? 1)
        }
        fractions[i] = (i === 0 ? 1 : fractions[i - 1]) + s
        slope += s
      })
      if (slope) item.net = f(item.amount / (1 + slope))
    }
  }

  // calculate_net_total, then calculate_taxes row by row, rounded at the end
  // of each row (or per line, where Accounts Settings says so).
  const total = f(items.reduce((sum, item) => sum + item.amount, 0))
  const net = f(items.reduce((sum, item) => sum + item.net, 0))
  const rows = taxes.map(() => ({ tax: 0, total: 0 }))
  for (const item of items) {
    const running = []
    taxes.forEach((tax, i) => {
      const rate = rateFor(tax, item) / 100
      let current =
        tax.charge_type === 'On Net Total'
          ? rate * item.net
          : rate * (running[(Number(tax.row_id) || i) - 1] ?? item.net)
      if (rule.row_wise) current = f(current)
      rows[i].tax += current
      running[i] = (i === 0 ? item.net : running[i - 1]) + current
    })
  }
  rows.forEach((row, i) => {
    row.tax = f(row.tax)
    row.total = f((i === 0 ? net : rows[i - 1].total) + row.tax)
  })
  let grand = rows.length ? rows[rows.length - 1].total : net
  // adjust_grand_total_for_inclusive_tax: the total of tax-inclusive prices
  // wins over the sum of the rounded parts when the two are at most 0.05 apart
  // (at two decimals: 5 / 10 ** precision).
  if (inclusive && rows.length) {
    const other = rows.reduce((sum, row, i) => sum + (Number(taxes[i].included) ? 0 : row.tax), 0)
    const diff = f(total + other - rows[rows.length - 1].total)
    if (diff && Math.abs(diff) <= 5 / 10 ** precision) grand += diff
  }
  grand = f(grand)
  const payable = roundTotal(grand, rule)
  return { total: -payable, grand: -grand, net: -net, tax: -f(grand - net) }
}

// The shift-sale record's fields from a posted sale's receipt (the server's
// figures replace what the till worked out while it was offline).
export function fromReceipt(receipt) {
  const facts = receipt?.offline_return || null
  return {
    name: receipt?.name || null,
    queued: false,
    currency: receipt?.currency || null,
    company_currency: receipt?.company_currency || null,
    conversion_rate: Number(receipt?.conversion_rate) || 1,
    customer: receipt?.customer || null,
    customer_name: receipt?.customer_name || null,
    lines: (receipt?.items || []).map((row) => ({
      item_code: row.item_code,
      item_name: row.item_name,
      qty: Number(row.qty) || 0,
      rate: Number(row.rate) || 0,
      item_tax_rate: row.item_tax_rate || {},
      serial: Boolean(row.serial_no),
      group: row.return_group || null,
    })),
    taxes: (receipt?.taxes || []).map((row) => ({
      charge_type: row.charge_type,
      rate: Number(row.rate) || 0,
      included: Number(row.included) || 0,
      account_head: row.account_head,
      row_id: row.row_id || null,
    })),
    rounding: facts?.rounding || null,
    total: Number(receipt?.rounded_total || receipt?.grand_total) || 0,
    paid_modes: (receipt?.payments || []).filter((p) => Number(p.amount) > 0).map((p) => p.mode_of_payment),
    refund_modes: facts ? facts.refund_modes ?? null : null,
    blocked: facts ? facts.blocked || {} : null,
    facts: Boolean(facts),
    loyalty: Number(receipt?.loyalty_points_redeemed) > 0,
    // A sale on account (0.60.0): its debt lives on the server.
    on_account: Boolean(receipt?.on_account || facts?.on_account),
  }
}

// The refund tenders a till may use for this sale WITHOUT a connection: the
// shop's allowed ones (the server's answer for a posted sale, else the
// policy, as sales._allowed_refund_modes), never a wallet (store credit, a
// gift card, cashback: their balances live on the server) and never the
// exchange clearing tender, and only tenders this till has.
export function offlineRefundModes(record, ctx) {
  const wallets = [ctx.storeCreditMode, ctx.giftCardMode, ctx.cashbackMode, ctx.creditMode, 'Exchange'].filter(Boolean)
  const own = (ctx.paymentModes || []).map((m) => m.mode_of_payment)
  let modes
  if (Array.isArray(record?.refund_modes)) {
    modes = [...record.refund_modes]
  } else if (ctx.policy?.restrict) {
    const paid = new Set(record?.paid_modes || [])
    const allowed = new Set([...paid].filter((m) => !wallets.includes(m)))
    for (const rule of ctx.policy.rules || []) {
      if (paid.has(rule.paid_mode) && rule.refund_mode && !wallets.includes(rule.refund_mode)) {
        allowed.add(rule.refund_mode)
      }
    }
    modes = [...allowed]
  } else {
    modes = own
  }
  return modes.filter((mode) => !wallets.includes(mode) && own.includes(mode))
}

// Why this sale cannot be taken back here without a connection, or '' when
// it can. English, the caller translates. `ctx`: {session, settings,
// permissions}.
export function offlineBlocker(record, ctx) {
  if (!ctx.settings?.offline_returns) return 'Returns without a connection are switched off'
  if (ctx.permissions?.can_return === false) return "You're not allowed to make returns."
  if (!record || record.session !== ctx.session) return 'Only a sale of this shift can be taken back without a connection'
  if (record.loyalty) return 'A sale paid with loyalty points needs a connection to refund'
  if (record.on_account) return 'A sale on account needs a connection to refund.'
  if (!record.rounding) return 'This sale needs a connection to refund'
  if (!record.queued && !record.facts) return 'This sale needs a connection to refund'
  if (record.queued && ctx.settings?.return_restricted) {
    return 'This shop limits returns of some products, so a sale not sent yet needs a connection to refund'
  }
  if (estimateRefund(record, {}) === null) return "This sale's charges need a connection to refund"
  return ''
}

// Mirror of sales._compute_return_groups for a sale queued offline: bundle
// lines come back together, and so do the lines an applied Buy X Get Y offer
// bound. `matching(cart, promo, role)` is promotions.js matchingIndexes.
export function returnGroups(lines, applied, promotions, promoCart, promoIdx, matching) {
  const groups = lines.map((line) => (line.bundle_key ? 'BUNDLE:' + line.bundle_key : null))
  const names = new Set((applied || []).filter((a) => a.promotion_type === 'Buy X Get Y').map((a) => a.name))
  for (const name of names) {
    const promo = (promotions || []).find((p) => p.name === name)
    if (!promo) continue
    const involved = new Set([...matching(promoCart, promo, 'Buy'), ...matching(promoCart, promo, 'Get')])
    for (const pos of involved) {
      const orig = promoIdx[pos]
      if (orig !== undefined && groups[orig] == null) groups[orig] = 'PROMO:' + name
    }
  }
  return groups
}
