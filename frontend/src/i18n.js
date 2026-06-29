// Lightweight i18n for the POS UI (no extra dependency).
//
// Translations are keyed by the ENGLISH source string, so a missing key simply
// falls back to English — partial translation degrades gracefully and never
// shows a raw key. Only the chrome/labels are translated; MASTER DATA (item
// names, customer names, item codes, barcodes, money, dates) is never passed
// through t() and stays exactly as entered in ERPNext.
import { ref } from 'vue'

import { messages } from './messages'

const KEY = 'lumenpos-locale'

function initial() {
  const saved = localStorage.getItem(KEY)
  if (saved === 'ar' || saved === 'en') return saved
  // First run: follow the browser. KSA machines are typically Arabic.
  return (navigator.language || '').toLowerCase().startsWith('ar') ? 'ar' : 'en'
}

export const locale = ref(initial())

// Reactive translate. Reads locale.value so any template using t() re-renders
// when the language is switched. params fill {placeholders}.
export function t(key, params) {
  const dict = messages[locale.value]
  let out = (dict && dict[key]) || key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      out = out.replaceAll(`{${k}}`, v)
    }
  }
  return out
}

export const isRTL = () => locale.value === 'ar'

export function applyDir() {
  const ar = locale.value === 'ar'
  document.documentElement.lang = ar ? 'ar' : 'en'
  document.documentElement.dir = ar ? 'rtl' : 'ltr'
}

export function setLocale(loc) {
  if (loc !== 'ar' && loc !== 'en') return
  locale.value = loc
  localStorage.setItem(KEY, loc)
  applyDir()
}

export function toggleLocale() {
  setLocale(locale.value === 'ar' ? 'en' : 'ar')
}

// Apply direction immediately so the first paint is already RTL/LTR.
applyDir()
