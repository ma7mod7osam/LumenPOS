// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
//
// Help for staff (0.58.0): the "?" panel, the tour on screen, and the card
// that welcomes someone new or says what is new after an update. What each
// person has seen is kept by the server (lumenpos.api.help) and, in case the
// server could not be told, on this device too.
import { defineStore } from 'pinia'
import { call } from '../api'
import { TOPICS, TOURS, WHATS_NEW } from '../help/content'
import { useSessionStore } from './session'

const LOCAL = 'lumenpos-help-seen:'
const MAX_NEWS = 8

// "0.58.0" and a test bench's "0.58.0-r42" are the same release.
export function compareVersions(a, b) {
  const parts = (v) => String(v || '').split('-')[0].split('.').map((n) => parseInt(n, 10) || 0)
  const x = parts(a)
  const y = parts(b)
  for (let i = 0; i < Math.max(x.length, y.length); i++) {
    const d = (x[i] || 0) - (y[i] || 0)
    if (d) return d > 0 ? 1 : -1
  }
  return 0
}

function localSeen(user) {
  try {
    return localStorage.getItem(LOCAL + user) || ''
  } catch {
    return ''
  }
}

function keepLocal(user, version) {
  try {
    localStorage.setItem(LOCAL + user, version)
  } catch {
    /* private window: the server's copy is the one that counts */
  }
}

const applies = (entry, session) => !entry.when || entry.when(session)

export const useHelpStore = defineStore('help', {
  state: () => ({
    panelOpen: false,
    tourId: null,
    stepIndex: 0,
    // 1 going forward, -1 going back: a step whose element is missing is
    // skipped in the same direction.
    direction: 1,
    // 'welcome' (someone who has not seen the help), 'news' (after an
    // update) or 'all-news' (opened from the panel), else null.
    card: null,
    seenVersion: '',
    toursDone: [],
  }),

  getters: {
    switches: () => useSessionStore().help || {},
    inTill() {
      return Boolean(this.switches.in_till)
    },
    version: () => useSessionStore().settings?.version || '',
    // This person's news: newer than what they saw (everything when they have
    // seen nothing yet), up to this release, for what they may use.
    news() {
      const session = useSessionStore()
      return WHATS_NEW.filter(
        (entry) =>
          (!this.seenVersion || compareVersions(entry.version, this.seenVersion) > 0) &&
          compareVersions(entry.version, this.version) <= 0 &&
          applies(entry, session)
      ).slice(0, MAX_NEWS)
    },
    // The panel's "What is new" lists the latest news whatever was seen.
    allNews() {
      const session = useSessionStore()
      return WHATS_NEW.filter(
        (entry) => compareVersions(entry.version, this.version) <= 0 && applies(entry, session)
      ).slice(0, MAX_NEWS)
    },
    topicsFor: () => (path) => {
      const session = useSessionStore()
      return TOPICS.filter((topic) => topic.route === path && applies(topic, session))
    },
    availableTours() {
      const session = useSessionStore()
      return Object.entries(TOURS)
        .filter(([, tour]) => applies(tour, session))
        .map(([id, tour]) => ({ id, title: tour.title, done: this.toursDone.includes(id) }))
    },
    tour() {
      return this.tourId ? TOURS[this.tourId] : null
    },
    tourSteps() {
      const session = useSessionStore()
      return this.tour ? this.tour.steps.filter((step) => applies(step, session)) : []
    },
  },

  actions: {
    // After the bootstrap: what this person has seen, and which card (if
    // any) greets them.
    init() {
      const session = useSessionStore()
      const sw = this.switches
      const fromServer = sw.seen_version || ''
      const fromDevice = localSeen(session.user)
      this.seenVersion = compareVersions(fromDevice, fromServer) > 0 ? fromDevice : fromServer
      this.toursDone = [...(sw.tours_done || [])]
      this.card = null
      if (!this.version) return
      if (!this.seenVersion) {
        if (sw.in_till && sw.offer_tour) this.card = 'welcome'
        else if (sw.whats_new && this.news.length) this.card = 'news'
      } else if (sw.whats_new && compareVersions(this.version, this.seenVersion) > 0) {
        // Nothing new for this person: remember it quietly.
        if (this.news.length) this.card = 'news'
        else this.markSeen()
      }
    },

    markSeen() {
      const session = useSessionStore()
      const version = this.version
      if (!version) return
      this.seenVersion = version
      keepLocal(session.user, version)
      call('lumenpos.api.help.mark', { seen_version: version }).catch(() => {})
    },

    dismissCard() {
      // Only the cards that greet someone count as seen; the panel's own list
      // changes nothing.
      if (this.card === 'welcome' || this.card === 'news') this.markSeen()
      this.card = null
    },

    openPanel() {
      this.panelOpen = true
    },
    closePanel() {
      this.panelOpen = false
    },
    togglePanel() {
      this.panelOpen = !this.panelOpen
    },
    showAllNews() {
      this.panelOpen = false
      this.card = 'all-news'
    },

    startTour(id) {
      if (!TOURS[id] || !this.inTill) return
      if (this.card) this.dismissCard()
      this.panelOpen = false
      this.direction = 1
      this.stepIndex = 0
      this.tourId = id
    },
    next() {
      this.direction = 1
      if (this.stepIndex < this.tourSteps.length - 1) this.stepIndex += 1
      else this.endTour(true)
    },
    back() {
      this.direction = -1
      if (this.stepIndex > 0) this.stepIndex -= 1
    },
    // A step whose element is not on screen: on in the same direction, and at
    // the very start, forward.
    skip() {
      if (this.direction < 0 && this.stepIndex > 0) this.back()
      else this.next()
    },
    endTour(finished) {
      const id = this.tourId
      this.tourId = null
      this.stepIndex = 0
      if (!finished || !id) return
      if (!this.toursDone.includes(id)) this.toursDone.push(id)
      call('lumenpos.api.help.mark', { tour_done: id }).catch(() => {})
    },

    // "Show me" on a piece of news: its tour, or its screen.
    showMe(entry, router) {
      if (entry.tour && this.inTill && TOURS[entry.tour]) {
        this.startTour(entry.tour)
        return
      }
      this.dismissCard()
      if (entry.route && router) router.push(entry.route)
    },
  },
})
