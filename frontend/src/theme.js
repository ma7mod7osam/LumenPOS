// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
// Light/dark theme: persisted in localStorage, applied as data-theme on
// <html>. Defaults to the OS preference on first run.
import { ref } from 'vue'

const KEY = 'lumenpos-theme'

function initial() {
  const saved = localStorage.getItem(KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export const theme = ref(initial())

export function applyTheme() {
  document.documentElement.setAttribute('data-theme', theme.value)
}

export function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  localStorage.setItem(KEY, theme.value) // explicit LumenPOS choice, wins over ERPNext
  applyTheme()
}

// Follow the user's ERPNext desk theme (Light / Dark / Automatic) unless they
// have explicitly toggled the theme inside LumenPOS on this device.
export function syncFromErp(deskTheme) {
  if (localStorage.getItem(KEY)) return
  if (deskTheme === 'Dark') theme.value = 'dark'
  else if (deskTheme === 'Light') theme.value = 'light'
  else theme.value = window.matchMedia?.('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light'
  applyTheme()
}

// Apply immediately so there's no flash of the wrong theme.
applyTheme()
