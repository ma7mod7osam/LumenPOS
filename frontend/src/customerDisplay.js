// Customer-facing display sync. The till (main window) publishes a fully
// pre-formatted cart snapshot over a BroadcastChannel; the display window
// (route #/display, opened on a second monitor) listens and renders it.
//
// A BroadcastChannel never receives its OWN posts, so the same channel object
// can both publish 'cart' and listen for the display's 'request' handshake
// (sent when a display opens so it gets the current cart immediately, without
// waiting for the next change).

const NAME = 'lumenpos-customer-display'
let channel = null

function chan() {
  if (channel === null && typeof BroadcastChannel !== 'undefined') {
    channel = new BroadcastChannel(NAME)
  }
  return channel
}

export function publishCart(snapshot) {
  try {
    chan()?.postMessage({ kind: 'cart', snapshot })
  } catch {
    /* channel unavailable — ignore */
  }
}

// Main window: answer a display's request for the current state.
export function onDisplayRequest(handler) {
  const c = chan()
  if (!c) return () => {}
  const fn = (e) => {
    if (e.data?.kind === 'request') handler()
  }
  c.addEventListener('message', fn)
  return () => c.removeEventListener('message', fn)
}

// Display window: receive cart snapshots, and ask for the current one now.
export function onCart(handler) {
  const c = chan()
  if (!c) return () => {}
  const fn = (e) => {
    if (e.data?.kind === 'cart') handler(e.data.snapshot)
  }
  c.addEventListener('message', fn)
  try {
    c.postMessage({ kind: 'request' })
  } catch {
    /* ignore */
  }
  return () => c.removeEventListener('message', fn)
}
