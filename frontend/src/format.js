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

// A browser reports an EMPTY value from <input type="number"> for anything it
// can't parse in the user's locale — "1,500", a stray space, Arabic-Indic
// digits — while the text the cashier typed stays visible on screen. That is
// how a register was opened with cash in the drawer and recorded 0.00.
// So money is read from the RAW text with this parser, never from .valueAsNumber.
// Returns null when the value is blank or unreadable — callers must stop rather
// than silently substitute zero.
const ARABIC_DIGITS = /[\u0660-\u0669\u06F0-\u06F9]/g

export function parseMoney(value) {
  if (value === null || value === undefined) return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  let s = String(value).trim()
  if (!s) return null
  // Arabic-Indic and Extended Arabic-Indic digits -> ASCII
  s = s.replace(ARABIC_DIGITS, (d) => {
    const c = d.charCodeAt(0)
    return String(c >= 0x06f0 ? c - 0x06f0 : c - 0x0660)
  })
  // Arabic decimal separator, spaces (incl. NBSP / thin space) and grouping
  s = s.replace(/\u066B/g, '.').replace(/\u066C/g, '').replace(/[\s\u00a0\u202f']/g, '')
  // If both separators appear, the LAST one is the decimal point.
  const lastComma = s.lastIndexOf(',')
  const lastDot = s.lastIndexOf('.')
  if (lastComma !== -1 && lastDot !== -1) {
    const decimal = lastComma > lastDot ? ',' : '.'
    const grouping = decimal === ',' ? '.' : ','
    s = s.split(grouping).join('')
    if (decimal === ',') s = s.replace(',', '.')
  } else if (lastComma !== -1) {
    // Only commas: a single one with 1-2 trailing digits is a decimal comma,
    // otherwise it's grouping ("1,500").
    const after = s.length - lastComma - 1
    s = s.split(',').length === 2 && after > 0 && after <= 2
      ? s.replace(',', '.')
      : s.split(',').join('')
  }
  if (!/^-?\d*\.?\d*$/.test(s) || s === '' || s === '.' || s === '-') return null
  const n = Number(s)
  return Number.isFinite(n) ? n : null
}
