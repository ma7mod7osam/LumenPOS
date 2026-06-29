let currency = 'USD'

export function setCurrency(code) {
  if (code) currency = code
}

export function money(amount) {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
    }).format(amount || 0)
  } catch {
    return `${currency} ${(amount || 0).toFixed(2)}`
  }
}

// Human-friendly warranty length from a number of days.
export function warrantyLabel(days) {
  days = Number(days) || 0
  if (days <= 0) return ''
  if (days % 365 === 0) {
    const y = days / 365
    return `${y} year${y > 1 ? 's' : ''} warranty`
  }
  if (days % 30 === 0) {
    const m = days / 30
    return `${m} month${m > 1 ? 's' : ''} warranty`
  }
  return `${days}-day warranty`
}

export function shortTime(value) {
  if (!value) return ''
  // Normalise Frappe timestamps that break Date parsing: space→T, drop the
  // microseconds (".252308"), and pad a single-digit hour ("T1:"→"T01:").
  let s = String(value).trim().replace(' ', 'T').replace(/\.\d+$/, '')
  s = s.replace(/T(\d):/, 'T0$1:')
  const d = new Date(s)
  if (isNaN(d)) return String(value).replace(/\.\d+.*$/, '') // last resort: at least no fractions
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}
