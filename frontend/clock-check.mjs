// The shift clock in the top bar (0.61.1): format.siteMs, skewFrom,
// siteNowFrom and shiftClock, the arithmetic App.vue and the session store
// use. A shift's opening time is the site's wall clock, so the clock must
// count on the site's clock, never the device's zone.
// Usage: node clock-check.mjs (the quality gate runs it)
import { shiftClock, siteMs, siteNowFrom, skewFrom } from './src/format.js'

let failures = 0
function check(label, actual, expected) {
  const ok = Object.is(actual, expected) || actual === expected
  if (!ok) failures++
  console.log(`${ok ? 'PASS' : 'FAIL'} ${label}: got ${JSON.stringify(actual)}, want ${JSON.stringify(expected)}`)
}

// Frappe's datetimes, read as the site's wall clock.
check('a Frappe datetime with microseconds', siteMs('2026-10-03 17:03:07.827194'), Date.UTC(2026, 9, 3, 17, 3, 7))
check('an unpadded time (Frappe 14 and later)', siteMs('2026-10-03 7:3:7.5'), Date.UTC(2026, 9, 3, 7, 3, 7))
check('nothing to read', Number.isNaN(siteMs('')), true)

// The clock itself.
check('two minutes in', shiftClock('2026-10-03 17:03:07', siteMs('2026-10-03 17:05:09')), '00:02:02')
check('the hours count on past a day', shiftClock('2026-10-01 10:00:00', siteMs('2026-10-05 11:30:05')), '97:30:05')
check('never below zero', shiftClock('2026-10-03 17:03:07', siteMs('2026-10-03 17:00:00')), '00:00:00')
check('a time it cannot read shows nothing', shiftClock('not a time', Date.now()), '')

// A site on New York time (UTC-4 in October), a device on Riyadh time (UTC+3):
// the shift opened at 17:00:00 site time, 21:00:00 UTC. The bootstrap answered
// at 21:00:30 UTC saying 17:00:30, and it is now 21:01:30 UTC.
const skew = skewFrom('2026-10-03 17:00:30.000000', Date.UTC(2026, 9, 3, 21, 0, 30))
check('the skew between the two clocks', skew, -4 * 3600 * 1000)
check('a device in another zone: 90 seconds, not 7 hours',
  shiftClock('2026-10-03 17:00:00', siteNowFrom(Date.UTC(2026, 9, 3, 21, 1, 30), skew)), '00:01:30')
// A device whose clock is 5 minutes fast reads the same.
const fast = skewFrom('2026-10-03 17:00:30', Date.UTC(2026, 9, 3, 21, 5, 30))
check('a device 5 minutes fast reads the same',
  shiftClock('2026-10-03 17:00:00', siteNowFrom(Date.UTC(2026, 9, 3, 21, 6, 30), fast)), '00:01:30')
check('a server older than 0.61.1 sends no time: no skew', skewFrom(undefined, Date.now()), null)

// No skew measured yet: the device's own wall clock, as before 0.61.1.
const now = new Date()
const opened = new Date(now.getTime() - 90 * 1000)
const two = (n) => String(n).padStart(2, '0')
const wall = (d) => `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}:${two(d.getSeconds())}`
check('no skew yet: the device wall clock, as before', shiftClock(wall(opened), siteNowFrom(now.getTime(), null)), '00:01:30')

console.log(failures ? `${failures} FAILED` : 'ALL PASS')
process.exit(failures ? 1 : 0)
