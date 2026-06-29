// Distinguish a barcode-scanner burst from manual typing, so serial entry can
// be locked to "scan only" (Settings → Require scanning for serial numbers).
//
// A hand scanner in keyboard-wedge mode emits all characters within a few ms of
// each other and ends with Enter; a human types far slower. We record the
// timestamp of each character keydown and, on confirm, accept only if the whole
// code arrived as a fast burst. Deliberately lenient — real scanners (even slow
// ones, ~30–40ms/char) pass; only human-speed typing is rejected.

const MAX_AVG_GAP_MS = 70 // average ms between characters that still counts as a scan

export function createScanGuard() {
  let stamps = []
  return {
    onKeydown(event) {
      // Only count printable single characters (ignore Enter, Tab, arrows, etc.)
      if (event.key && event.key.length === 1) stamps.push(performance.now())
    },
    reset() {
      stamps = []
    },
    // True when `value` looks like it was scanned rather than typed.
    isScan(value) {
      const len = (value || '').length
      if (len === 0) return false
      // Fewer keydowns than characters → pasted/programmatic, not a scan.
      // More keydowns than characters → edited by hand, not a clean scan.
      if (stamps.length !== len) return false
      if (len === 1) return true // a single scanned character has no gap to measure
      const span = stamps[stamps.length - 1] - stamps[0]
      return span / (len - 1) <= MAX_AVG_GAP_MS
    },
  }
}
