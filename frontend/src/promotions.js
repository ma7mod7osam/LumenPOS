// Mirror of lumenpos/promotions/engine.py — keep both in sync.
// Runs client-side so the cart updates instantly; the server re-evaluates
// authoritatively on submit.

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

function isActive(promo, now, cart) {
  const dateStr = localDate(now)
  if (promo.start_date && dateStr < promo.start_date) return false
  if (promo.end_date && dateStr > promo.end_date) return false

  const days = promo.days || {}
  if (Object.values(days).some(Boolean)) {
    const weekday = DAYS[(now.getDay() + 6) % 7] // JS Sunday=0 -> Python Monday=0
    if (!days[weekday]) return false
  }

  if (promo.start_time && promo.end_time) {
    const start = normTime(promo.start_time)
    const end = normTime(promo.end_time)
    // Equal times (e.g. both 00:00:00 from an empty form field) mean
    // "no daily window" — the promotion runs all day.
    if (start !== end) {
      const t = localTime(now)
      if (start <= end) {
        if (!(start <= t && t <= end)) return false
      } else if (!(t >= start || t <= end)) {
        return false
      }
    }
  }

  const profiles = promo.pos_profiles || []
  if (profiles.length && !profiles.includes(cart.pos_profile)) return false

  if (promo.requires_coupon) {
    const codes = (cart.coupon_codes || []).map((c) => String(c).toUpperCase())
    if (!codes.includes((promo.coupon_code || '').toUpperCase())) return false
  }

  if (promo.customer_eligibility === 'Selected Customer Groups') {
    const groups = promo.customer_groups || []
    if (!cart.customer_group || !groups.includes(cart.customer_group)) return false
  }
  return true
}

function localDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
function localTime(d) {
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}
function pad(n) {
  return String(n).padStart(2, '0')
}
function normTime(v) {
  v = String(v)
  return v.length > 5 ? v : v + ':00'
}

function lineMatches(line, rows, role = null) {
  for (const row of rows) {
    if (role && (row.role || 'Buy') !== role) continue
    const appliesTo = row.applies_to || 'Item'
    if (appliesTo === 'Item' && line.item_code === row.value) return true
    if (appliesTo === 'Item Group' && line.item_group === row.value) return true
    if (appliesTo === 'Brand' && line.brand === row.value) return true
    if (appliesTo === 'Tag' && (line.tags || []).includes(row.value)) return true
  }
  return false
}

function matchingIndexes(cart, promo, role = null) {
  // Include rows select lines; exclude rows then subtract from the result.
  const rows = promo.items || []
  const includeRows = rows.filter((r) => !r.exclude)
  const excludeRows = rows.filter((r) => r.exclude)

  let base
  if (promo.apply_on_all || (excludeRows.length && !includeRows.length)) {
    base = cart.items.map((_, i) => i)
  } else {
    if (role && !includeRows.some((r) => (r.role || 'Buy') === role)) return []
    base = cart.items
      .map((line, i) => (lineMatches(line, includeRows, role) ? i : -1))
      .filter((i) => i >= 0)
  }
  if (excludeRows.length) {
    base = base.filter((i) => !lineMatches(cart.items[i], excludeRows))
  }
  return base
}

function unitDiscount(price, dtype, value) {
  let d = 0
  if (dtype === 'Percentage') d = (price * (value || 0)) / 100
  else if (dtype === 'Amount') d = value || 0
  else if (dtype === 'Fixed Price') d = price - (value || 0)
  else if (dtype === 'Free') d = price
  return Math.max(0, Math.min(d, price))
}

// Mirror of engine._basis_unit_discount — "Standard Price" basis takes the
// lower of the price-book price and (standard - promo); default stacks on book.
function basisUnitDiscount(line, promo, dtype, value) {
  const book = line.price
  if ((promo.price_basis || 'Price Book Price') === 'Standard Price') {
    const std = line.standard_price == null ? book : line.standard_price
    const candidate = std - unitDiscount(std, dtype, value)
    return Math.max(0, book - candidate)
  }
  return unitDiscount(book, dtype, value)
}

function candidateSimple(cart, promo) {
  const lineDiscounts = {}
  for (const i of matchingIndexes(cart, promo)) {
    const line = cart.items[i]
    const perUnit = basisUnitDiscount(line, promo, promo.discount_type, promo.discount_value)
    if (perUnit > 0) lineDiscounts[i] = perUnit * line.qty
  }
  return [lineDiscounts, 0]
}

function expandUnits(cart, indexes) {
  const units = []
  for (const i of indexes) {
    const line = cart.items[i]
    const std = line.standard_price == null ? line.price : line.standard_price
    for (let n = 0; n < Math.floor(line.qty); n++) units.push([line.price, std, i])
  }
  return units
}

function candidateBxgy(cart, promo) {
  const buyQty = Math.floor(promo.buy_qty || 0)
  const getQty = Math.floor(promo.get_qty || 0)
  if (buyQty < 1 || getQty < 1) return [{}, 0]

  const hasGetRows = (promo.items || []).some((r) => (r.role || 'Buy') === 'Get')
  let buyIdx = promo.apply_on_all
    ? matchingIndexes(cart, promo)
    : matchingIndexes(cart, promo, 'Buy')
  const getIdx = hasGetRows ? matchingIndexes(cart, promo, 'Get') : buyIdx

  const buyUnits = expandUnits(cart, buyIdx)
  const getUnits = expandUnits(cart, getIdx)
  if (!buyUnits.length || !getUnits.length) return [{}, 0]

  const shared = buyIdx.some((i) => getIdx.includes(i))
  let apps = Math.min(
    Math.floor(buyUnits.length / buyQty),
    Math.floor(getUnits.length / getQty)
  )
  if (shared) {
    const union = expandUnits(cart, [...new Set([...buyIdx, ...getIdx])].sort((a, b) => a - b))
    apps = Math.min(apps, Math.floor(union.length / (buyQty + getQty)))
  }
  const maxApps = Math.floor(promo.max_applications || 0)
  if (maxApps > 0) apps = Math.min(apps, maxApps)
  if (apps < 1) return [{}, 0]

  const rewardCount = apps * getQty
  const rewards = [...getUnits].sort((a, b) => a[0] - b[0]).slice(0, rewardCount)
  const lineDiscounts = {}
  for (const [price, std, idx] of rewards) {
    const d = basisUnitDiscount(
      { price, standard_price: std },
      promo,
      promo.get_discount_type || 'Free',
      promo.get_discount_value
    )
    if (d > 0) lineDiscounts[idx] = (lineDiscounts[idx] || 0) + d
  }
  return [lineDiscounts, 0]
}

function candidateSpendSave(cart, promo) {
  let indexes
  if (promo.apply_on_all || (promo.items || []).length) {
    indexes = matchingIndexes(cart, promo)
  } else {
    // no product rows at all: the whole basket counts toward the spend
    indexes = cart.items.map((_, i) => i)
  }
  const eligibleTotal = indexes.reduce(
    (sum, i) => sum + cart.items[i].price * cart.items[i].qty,
    0
  )
  const minSpend = promo.min_spend || 0
  if (eligibleTotal <= 0 || eligibleTotal < minSpend) return [{}, 0]

  const dtype = promo.basket_discount_type || 'Percentage'
  const value = promo.basket_discount_value || 0
  const discount = dtype === 'Percentage' ? (eligibleTotal * value) / 100 : value
  return [{}, Math.max(0, Math.min(discount, eligibleTotal))]
}

function candidateBundle(cart, promo) {
  const rows = (promo.items || []).filter((r) => !r.exclude)
  const bundlePrice = promo.bundle_price || 0
  if (!rows.length || bundlePrice <= 0) return [{}, 0]

  const pool = []
  cart.items.forEach((line, i) => {
    for (let n = 0; n < Math.floor(line.qty); n++) pool.push({ price: line.price, idx: i, used: false })
  })

  const maxApps = Math.floor(promo.max_applications || 0)
  const consumed = []
  let apps = 0
  for (;;) {
    const roundSelected = []
    let filled = true
    for (const row of rows) {
      const need = Math.floor(row.qty || 1)
      const candidates = pool
        .filter((u) => !u.used && lineMatches(cart.items[u.idx], [row]))
        .sort((a, b) => a.price - b.price)
      if (candidates.length < need) {
        filled = false
        break
      }
      for (const unit of candidates.slice(0, need)) {
        unit.used = true
        roundSelected.push(unit)
      }
    }
    if (!filled) {
      for (const unit of roundSelected) unit.used = false
      break
    }
    consumed.push(...roundSelected)
    apps++
    if (maxApps && apps >= maxApps) break
  }

  if (!apps) return [{}, 0]
  const natural = consumed.reduce((sum, u) => sum + u.price, 0)
  const discount = natural - bundlePrice * apps
  if (discount <= 0 || natural <= 0) return [{}, 0]

  const lineDiscounts = {}
  for (const unit of consumed) {
    const share = discount * (unit.price / natural)
    lineDiscounts[unit.idx] = (lineDiscounts[unit.idx] || 0) + share
  }
  // Cent-correct the proportional split (mirror of engine.py)
  const rounded = {}
  for (const [idx, value] of Object.entries(lineDiscounts)) rounded[idx] = round2(value)
  const delta = round2(round2(discount) - Object.values(rounded).reduce((a, b) => a + b, 0))
  if (delta) {
    const biggest = Object.keys(rounded).reduce((a, b) => (rounded[a] >= rounded[b] ? a : b))
    rounded[biggest] = round2(rounded[biggest] + delta)
  }
  return [rounded, 0]
}

const CANDIDATES = {
  'Simple Discount': candidateSimple,
  'Buy X Get Y': candidateBxgy,
  'Spend and Save': candidateSpendSave,
  'Bundle Price': candidateBundle,
}

export function evaluatePromotions(cart, promotions, now = null) {
  now = now || new Date()
  const items = cart.items || []
  const result = {
    line_discounts: items.map(() => 0),
    line_promotions: items.map(() => []),
    basket_discount: 0,
    applied: [],
    total_savings: 0,
  }
  if (!items.length) return result

  const candidates = []
  for (const promo of promotions || []) {
    if ((promo.status || 'Active') !== 'Active') continue
    if (!isActive(promo, now, cart)) continue
    const fn = CANDIDATES[promo.promotion_type]
    if (!fn) continue
    const [lineDiscounts, basketDiscount] = fn(cart, promo)
    const savings =
      Object.values(lineDiscounts).reduce((a, b) => a + b, 0) + basketDiscount
    if (savings > 0) candidates.push({ promo, lineDiscounts, basketDiscount, savings })
  }
  if (!candidates.length) return result

  const stackable = candidates.filter((c) => c.promo.stackable)
  const exclusive = candidates
    .filter((c) => !c.promo.stackable)
    .sort((a, b) => b.savings - a.savings || (b.promo.priority || 0) - (a.promo.priority || 0))

  const stackTotal = stackable.reduce((a, c) => a + c.savings, 0)
  const chosen =
    exclusive.length && exclusive[0].savings > stackTotal ? [exclusive[0]] : stackable

  for (const c of chosen) {
    for (const [idx, amount] of Object.entries(c.lineDiscounts)) {
      result.line_discounts[idx] += amount
      result.line_promotions[idx].push(c.promo.title)
    }
    result.basket_discount += c.basketDiscount
    result.applied.push({
      name: c.promo.name,
      title: c.promo.title,
      promotion_type: c.promo.promotion_type,
      savings: round2(c.savings),
    })
  }

  let basketTotal = 0
  items.forEach((line, i) => {
    const lineTotal = line.price * line.qty
    result.line_discounts[i] = round2(Math.min(result.line_discounts[i], lineTotal))
    basketTotal += lineTotal - result.line_discounts[i]
  })
  result.basket_discount = round2(Math.min(result.basket_discount, basketTotal))
  result.total_savings = round2(
    result.line_discounts.reduce((a, b) => a + b, 0) + result.basket_discount
  )
  return result
}

function round2(n) {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

// ---------------------------------------------------------------------------
// Offer suggestions — "the cart almost qualifies, nudge the cashier".
// UX-only (no Python mirror needed); pricing stays with evaluatePromotions.
// ---------------------------------------------------------------------------

function rewardText(promo) {
  const qty = Math.floor(promo.get_qty || 1)
  const unit = qty > 1 ? `${qty} ` : ''
  switch (promo.get_discount_type || 'Free') {
    case 'Free':
      return `get ${unit}free`
    case 'Percentage':
      return `get ${unit}at ${promo.get_discount_value}% off`
    case 'Amount':
      return `get ${promo.get_discount_value} off ${unit}`.trim()
    case 'Fixed Price':
      return `get ${unit}for ${promo.get_discount_value}`
    default:
      return 'get a discount'
  }
}

function rowLabel(row) {
  return row.value || 'eligible items'
}

export function suggestOffers(cart, promotions, now = null) {
  now = now || new Date()
  const items = cart.items || []
  if (!items.length) return []

  const suggestions = []
  for (const promo of promotions || []) {
    if (suggestions.length >= 3) break
    if ((promo.status || 'Active') !== 'Active') continue
    if (!isActive(promo, now, cart)) continue
    const fn = CANDIDATES[promo.promotion_type]
    if (!fn) continue
    const [lineDiscounts, basketDiscount] = fn(cart, promo)
    const savings = Object.values(lineDiscounts).reduce((a, b) => a + b, 0) + basketDiscount
    if (savings > 0) continue // already applying; nothing to suggest

    if (promo.promotion_type === 'Buy X Get Y') {
      const buyQty = Math.floor(promo.buy_qty || 0)
      const getQty = Math.floor(promo.get_qty || 0)
      if (buyQty < 1 || getQty < 1) continue
      const hasGetRows = (promo.items || []).some((r) => (r.role || 'Buy') === 'Get')
      const buyIdx = promo.apply_on_all
        ? matchingIndexes(cart, promo)
        : matchingIndexes(cart, promo, 'Buy')
      const buyCount = expandUnits(cart, buyIdx).length
      if (!buyCount) continue
      if (hasGetRows) {
        const getIdx = matchingIndexes(cart, promo, 'Get')
        const getCount = expandUnits(cart, getIdx).length
        const shared = buyIdx.some((i) => getIdx.includes(i))
        if (shared) {
          // Same item (or overlapping pool) on both sides: a unit can't be
          // trigger AND reward, so suggest topping up to buyQty + getQty.
          const unionIdx = [...new Set([...buyIdx, ...getIdx])].sort((a, b) => a - b)
          const union = expandUnits(cart, unionIdx).length
          if (union >= buyQty && union < buyQty + getQty) {
            const need = buyQty + getQty - union
            const target = (promo.items || [])[0]
            suggestions.push({
              title: promo.title,
              message: `Add ${need} more — ${rewardText(promo)}`,
              target: target?.applies_to === 'Item' ? target.value : null,
              for_lines: unionIdx,
            })
          }
        } else if (buyCount >= buyQty && getCount < getQty) {
          const target = (promo.items || []).find((r) => (r.role || 'Buy') === 'Get')
          suggestions.push({
            title: promo.title,
            message: `Add ${rowLabel(target)} — ${rewardText(promo)}`,
            target: target?.applies_to === 'Item' ? target.value : null,
            for_lines: buyIdx,
          })
        }
      } else if (buyCount >= buyQty && buyCount < buyQty + getQty) {
        const need = buyQty + getQty - buyCount
        const target = (promo.items || [])[0]
        suggestions.push({
          title: promo.title,
          message: `Add ${need} more — ${rewardText(promo)}`,
          target: target?.applies_to === 'Item' ? target.value : null,
          for_lines: buyIdx,
        })
      }
    } else if (promo.promotion_type === 'Bundle Price') {
      const rows = promo.items || []
      if (!rows.length || !(promo.bundle_price > 0)) continue
      const missing = []
      let haveSomething = false
      for (const row of rows) {
        const need = Math.floor(row.qty || 1)
        const have = expandUnits(cart, matchingIndexes({ items, pos_profile: cart.pos_profile }, { apply_on_all: 0, items: [row] })).length
        if (have > 0) haveSomething = true
        if (have < need) missing.push(`${need - have} × ${rowLabel(row)}`)
      }
      if (haveSomething && missing.length) {
        const firstMissing = rows.find((row) => {
          const need = Math.floor(row.qty || 1)
          const have = expandUnits(cart, matchingIndexes({ items, pos_profile: cart.pos_profile }, { apply_on_all: 0, items: [row] })).length
          return have < need && row.applies_to === 'Item'
        })
        const presentIdx = matchingIndexes(cart, { apply_on_all: 0, items: rows })
        suggestions.push({
          title: promo.title,
          message: `Complete the bundle for ${promo.bundle_price}: add ${missing.join(', ')}`,
          target: firstMissing?.value || null,
          for_lines: presentIdx,
        })
      }
    } else if (promo.promotion_type === 'Spend and Save') {
      const minSpend = promo.min_spend || 0
      if (minSpend <= 0) continue
      let indexes
      if (promo.apply_on_all || !(promo.items || []).length) {
        indexes = items.map((_, i) => i)
      } else {
        indexes = matchingIndexes(cart, promo)
      }
      const eligible = indexes.reduce((sum, i) => sum + items[i].price * items[i].qty, 0)
      if (eligible > 0 && eligible < minSpend && eligible >= minSpend * 0.6) {
        const saveText =
          (promo.basket_discount_type || 'Percentage') === 'Percentage'
            ? `save ${promo.basket_discount_value}%`
            : `save ${promo.basket_discount_value}`
        suggestions.push({
          title: promo.title,
          message: `Spend ${round2(minSpend - eligible)} more to ${saveText}`,
          target: null,
          for_lines: [], // basket-level: shown in the totals area, not on a line
        })
      }
    }
  }
  return suggestions
}
