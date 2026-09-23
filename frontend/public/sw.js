/* Copyright (c) 2026 Lumen Solutions
   SPDX-License-Identifier: AGPL-3.0-only
   "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.

   The till's service worker: it keeps the SHELL of the POS (the page, its
   script, its stylesheet, its fonts) on the device, so the app opens with no
   connection at all. Before this, a shop that lost the network could keep
   selling only as long as nobody reloaded the tab, and a till that rebooted
   was a till that could not sell.

   It deliberately does NOT cache any data. Sales, the catalogue, customers and
   the queue live in IndexedDB, where the app can reason about them, and every
   API call is a POST which is passed straight through. A service worker that
   quietly answered an API call from a cache would be a shop selling against
   numbers nobody can see.

   Scope: it is served from the site root so it can control /pos, but it only
   ever answers requests for /pos and the POS assets. The desk is untouched.

   Versioning: the page registers it as /sw.js?v=<app version>, so a new
   release is a new worker and a new cache, and the old cache is dropped on
   activate. Nothing is version-stamped by hand.
*/

const VERSION = new URL(self.location.href).searchParams.get('v') || 'dev'
const CACHE = 'lumenpos-shell-' + VERSION
const PAGE = '/pos'
const ASSETS = '/assets/lumenpos/pos/'
const FONT_HOSTS = ['fonts.googleapis.com', 'fonts.gstatic.com']

const SHELL = [
  PAGE,
  ASSETS + 'pos.js?v=' + VERSION,
  ASSETS + 'pos.css?v=' + VERSION,
  ASSETS + 'manifest.json',
  ASSETS + 'icon-192.png',
  ASSETS + 'icon-512.png',
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) =>
      // One missing file must not leave the till with no shell at all, so each
      // is added on its own and a failure is tolerated.
      Promise.all(SHELL.map((url) => cache.add(url).catch(() => null)))
    )
  )
  self.skipWaiting()
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names
            .filter((name) => name.startsWith('lumenpos-shell-') && name !== CACHE)
            .map((name) => caches.delete(name))
        )
      )
      .then(() => self.clients.claim())
  )
})

async function cacheFirst(request) {
  const cache = await caches.open(CACHE)
  const hit = await cache.match(request, { ignoreSearch: false })
  if (hit) return hit
  const response = await fetch(request)
  if (response && (response.ok || response.type === 'opaque')) {
    cache.put(request, response.clone()).catch(() => {})
  }
  return response
}

// The page itself: always ask the server first, so a deploy is picked up the
// moment the till has a connection, and fall back to the copy on the device.
async function pageNetworkFirst(request) {
  const cache = await caches.open(CACHE)
  try {
    const response = await fetch(request)
    if (response && response.ok) cache.put(PAGE, response.clone()).catch(() => {})
    return response
  } catch (e) {
    const hit = (await cache.match(request, { ignoreSearch: true })) || (await cache.match(PAGE))
    if (hit) return hit
    throw e
  }
}

self.addEventListener('fetch', (event) => {
  const request = event.request
  if (request.method !== 'GET') return // every API call is a POST, never touched
  let url
  try {
    url = new URL(request.url)
  } catch (e) {
    return
  }
  const sameOrigin = url.origin === self.location.origin

  if (request.mode === 'navigate') {
    // Only the POS. A desk page must never be answered from this cache.
    if (sameOrigin && (url.pathname === PAGE || url.pathname.startsWith(PAGE + '/'))) {
      event.respondWith(pageNetworkFirst(request))
    }
    return
  }
  if (sameOrigin && url.pathname.startsWith(ASSETS)) {
    event.respondWith(cacheFirst(request))
    return
  }
  if (FONT_HOSTS.includes(url.hostname)) {
    event.respondWith(cacheFirst(request))
  }
})
