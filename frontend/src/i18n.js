// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
// Lightweight i18n for the POS UI (no extra dependency).
//
// Translations are keyed by the ENGLISH source string, so a missing key simply
// falls back to English, partial translation degrades gracefully and never
// shows a raw key. Only the chrome/labels are translated; MASTER DATA (item
// names, customer names, item codes, barcodes, money, dates) is never passed
// through t() and stays exactly as entered in ERPNext.
//
// English and Arabic ship inside the main bundle. Every other language is a
// file of its own (locales/<code>.js) fetched the first time it is chosen, so
// a shop downloads only the language it uses, and the service worker keeps it
// on the device like the rest of the shell. A language's code is its ERPNext
// Language code: api.js sends it with every request, so the server's own
// messages come back in the same language as the screen.
import { computed, ref } from 'vue'

import { messages } from './messages'

const KEY = 'lumenpos-locale'

// Every language the till speaks, named in itself, in the order ERPNext is used
// in them (a study of public ERPNext sites and Frappe Cloud installs,
// 2026-09). `dir` drives the layout. Adding one: scripts/i18n/README.md.
export const LANGUAGES = [
  { code: 'en', name: 'English', dir: 'ltr' },
  { code: 'ar', name: 'العربية', dir: 'rtl' },
  { code: 'es', name: 'Español', dir: 'ltr' },
  { code: 'de', name: 'Deutsch', dir: 'ltr' },
  { code: 'zh', name: '简体中文', dir: 'ltr' },
  { code: 'fr', name: 'Français', dir: 'ltr' },
  { code: 'th', name: 'ไทย', dir: 'ltr' },
  { code: 'id', name: 'Bahasa Indonesia', dir: 'ltr' },
  { code: 'vi', name: 'Tiếng Việt', dir: 'ltr' },
  { code: 'pt-BR', name: 'Português (Brasil)', dir: 'ltr' },
  { code: 'fa', name: 'فارسی', dir: 'rtl' },
  { code: 'ru', name: 'Русский', dir: 'ltr' },
  { code: 'tr', name: 'Türkçe', dir: 'ltr' },
]

const packs = import.meta.glob('./locales/*.js')
const dicts = { en: messages.en, ar: messages.ar }

const byCode = (code) => LANGUAGES.find((l) => l.code === code)

// The languages this shop offers (Settings, General, Languages). null means
// all of them; English is always there, it is what every missing key falls
// back to.
const offeredCodes = ref(null)
const isOffered = (code) =>
  code === 'en' || !offeredCodes.value || offeredCodes.value.includes(code)
export const offeredLanguages = computed(() => LANGUAGES.filter((l) => isOffered(l.code)))

function remembered() {
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null
  }
}

function remember(code) {
  try {
    localStorage.setItem(KEY, code)
  } catch {
    /* private window: the choice lasts until the tab closes */
  }
}

// The browser's preferred language that the till speaks, e.g. "pt-BR" for a
// Brazilian machine or "ar" for a Saudi one (ar-SA falls back to ar).
function fromBrowser() {
  const tags = (navigator.languages && navigator.languages.length
    ? navigator.languages
    : [navigator.language || '']
  ).map((tag) => String(tag).toLowerCase())
  for (const tag of tags) {
    const exact = LANGUAGES.find((l) => l.code.toLowerCase() === tag)
    if (exact) return exact.code
    // zh is Simplified Chinese: a Traditional Chinese browser (Taiwan, Hong
    // Kong, Macau) is not handed it unasked.
    if (/^zh-(tw|hk|mo|hant)/.test(tag)) continue
    const base = LANGUAGES.find((l) => l.code.toLowerCase() === tag.split('-')[0])
    if (base) return base.code
  }
  return 'en'
}

function initial() {
  const saved = remembered()
  if (saved && byCode(saved)) return saved
  return fromBrowser()
}

export const locale = ref('en')

// Reactive translate. Reads locale.value so any template using t() re-renders
// when the language is switched. params fill {placeholders}.
export function t(key, params) {
  const dict = dicts[locale.value]
  let out = (dict && dict[key]) || dicts.en[key] || key
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      out = out.replaceAll(`{${k}}`, v)
    }
  }
  return out
}

export const isRTL = () => (byCode(locale.value) || LANGUAGES[0]).dir === 'rtl'

export function applyDir() {
  const lang = byCode(locale.value) || LANGUAGES[0]
  document.documentElement.lang = lang.code
  document.documentElement.dir = lang.dir
}

async function load(code) {
  if (dicts[code]) return true
  const loader = packs[`./locales/${code}.js`]
  if (!loader) return false
  try {
    dicts[code] = (await loader()).default
    return true
  } catch {
    // Offline, and this language was never opened on this device: the screen
    // stays in the language it has, the choice is kept for the next start.
    return false
  }
}

export async function setLocale(code, { keep = true } = {}) {
  if (!byCode(code) || !isOffered(code)) return false
  if (!(await load(code))) return false
  locale.value = code
  if (keep) remember(code)
  applyDir()
  return true
}

// Settings narrows the list: a till left on a language the shop no longer
// offers goes back to English.
export function setOffered(codes) {
  offeredCodes.value = Array.isArray(codes) && codes.length ? codes : null
  if (!isOffered(locale.value)) setLocale('en')
}

// The customer display is another window of the same till: it follows the
// language the cashier picks.
window.addEventListener('storage', (event) => {
  if (event.key === KEY && event.newValue && event.newValue !== locale.value) {
    setLocale(event.newValue, { keep: false })
  }
})

// Apply the language before the first paint. English and Arabic are already
// here; any other language resolves `ready` once its file is in (main.js
// mounts the app after that, so the first screen is never in the wrong
// language).
const first = initial()
if (dicts[first]) locale.value = first
applyDir()
export const ready = dicts[first] ? Promise.resolve(true) : setLocale(first, { keep: false })
