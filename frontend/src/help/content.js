// Copyright (c) 2026 Lumen Solutions
// SPDX-License-Identifier: AGPL-3.0-only
// "LumenPOS" is a trademark of Lumen Solutions. See TRADEMARKS.md.
//
// Help for staff (0.58.0): each screen's help, the tours and what is new.
//
// Every text is an English key for t(), so it shows in the till's language.
// A step written as [text, { name: 'Label' }] fills {name} with the button's
// own label in that language, so the help always says what the screen says.
// `when(session)` keeps a topic, a tour step or a piece of news to the people
// and shops it applies to (permissions and switches are re-checked by the
// server whatever the help says).
//
// A tour step points at an element marked data-tour="<target>" in the
// screens (quality/gate.mjs checks every target exists). `route` opens a
// screen first, `click` opens something first (a receipt), and `optional`
// skips a step whose element is not on screen (no sales yet, a switch off).

const salespeople = (s) => s.salesPersons.length > 0 && s.settings.salesperson_mode !== 'Off'
const manager = (s) => Boolean(s.permissions.is_manager)

export const SCREENS = {
  '/': 'Sell',
  '/history': 'Sales History',
  '/customers': 'Customers',
  '/holds': 'Holds',
  '/register': 'Register',
  '/insights': 'Insights',
  '/settings': 'Settings',
}

export const TOPICS = [
  // Sell
  {
    route: '/',
    title: 'Add products',
    tour: 'sell',
    steps: [
      'Type part of a product\'s name or code in the search box, or scan its barcode.',
      'Tap a group above the products to see that group only.',
      'Tap a product to add it to the cart. Tap it again to add one more.',
      'A product with serial numbers asks for its serial number first.',
      ['{check} shows a product\'s price and stock without selling it.', { check: 'Price check' }],
    ],
  },
  {
    route: '/',
    title: 'The customer',
    steps: [
      ['Tap {add} at the top of the cart to find a customer by name, mobile or tax ID.', { add: 'Add a customer' }],
      ['Not there yet? Tap {new} in the same window, fill in the form and save.', { new: 'New customer' }],
      'Without a customer, the sale goes to the outlet\'s walk-in customer.',
      'The customer\'s points, store credit and cashback show under their name.',
    ],
  },
  {
    route: '/',
    title: 'The salesperson',
    when: salespeople,
    steps: [
      'Type the salesperson\'s name or number under the customer and pick it from the list.',
      'If your shop made it required, Pay waits until one is picked.',
      'Their sales and commission show on the Register page and in Insights.',
    ],
  },
  {
    route: '/',
    title: 'Change a line in the cart',
    steps: [
      'Tap a line to open it.',
      'Change the quantity with the minus and plus buttons, or remove the line.',
      'Give the line a discount, or type a new price, if you are allowed to.',
      'Offers apply by themselves and show their name under the line.',
    ],
  },
  {
    route: '/',
    title: 'Coupons, discounts and notes',
    steps: [
      ['{coupon}: type the code and tap Apply. Its offer applies at once.', { coupon: 'Coupon' }],
      ['{discount}: a percentage off the whole sale, where your shop allows it.', { discount: 'Discount' }],
      ['{note}: a short note kept with the sale.', { note: 'Note' }],
    ],
  },
  {
    route: '/',
    title: 'How the total is made',
    steps: [
      ['Tap {details} above the total to see how it is made.', { details: 'Details' }],
      'Offers, bundles and discounts come off the subtotal.',
      'Tax is added on top, or shown as included when your prices already include it.',
      'When your shop chose it, the total also shows in other currencies under it.',
    ],
  },
  {
    route: '/',
    title: 'Park a sale and come back to it',
    steps: [
      ['{park} keeps the basket aside so you can serve the next customer.', { park: 'Park' }],
      ['{retrieve} brings a parked basket back to the cart.', { retrieve: 'Retrieve Sale' }],
    ],
  },
  {
    route: '/',
    title: 'Take the payment',
    tour: 'sell',
    steps: [
      ['{pay} opens the payment screen with the total.', { pay: 'Pay' }],
      'Tap how the customer pays. To split it, take part with one method and the rest with another.',
      'For cash, type what the customer hands over and the change shows before you finish.',
      'Gift cards, store credit and cashback are ways to pay too, when the customer has them.',
      'Complete the sale to post it and show or print the receipt.',
    ],
  },
  {
    route: '/',
    title: 'Hold goods for a customer',
    when: (s) => Boolean(s.settings.enable_layaway) && s.permissions.can_hold_goods !== false,
    steps: [
      ['{hold} keeps the goods for a customer who pays over time, with a first payment now.', { hold: 'Hold' }],
      ['On the Holds page, {take} adds a payment, and the goods are handed over once paid.', { take: 'Take payment' }],
      'The price agreed on the day of the hold stays, whatever happens to prices later.',
    ],
  },
  {
    route: '/',
    title: 'Sell a gift card',
    steps: [
      'The gift button under the cart sells a gift card.',
      'Type the amount and how it is paid. Scan a physical card, or leave the number empty for a new one.',
      'The customer pays with it later as a way to pay.',
    ],
  },
  {
    route: '/',
    title: 'Sell in another currency',
    tour: 'currency',
    when: (s) => s.saleCurrencies.length > 0,
    steps: [
      'Pick the currency at the top of the cart to sell to a walk-in in it.',
      'A customer billed in another currency in ERPNext buys in it by themselves.',
      'Prices are converted at the rate fixed for the shift.',
      'Take the payment in that currency, or part of it in yours.',
    ],
  },
  {
    route: '/',
    title: 'When the connection drops',
    steps: [
      'Keep selling: sales wait on this device and go out by themselves once the connection is back.',
      'The amber Offline button at the top counts the sales still waiting. Tap it to see them.',
      'Do not clear the browser\'s data while sales are waiting.',
    ],
  },

  // Sales History
  {
    route: '/history',
    title: 'Find a sale',
    tour: 'returns',
    steps: [
      'Search by invoice number, customer, mobile or order ID.',
      ['{filters} narrows it by date, item, serial number or amount.', { filters: 'Filters' }],
      'Tap a sale to open its receipt.',
    ],
  },
  {
    route: '/history',
    title: 'Refund a sale',
    tour: 'returns',
    when: (s) => s.permissions.can_return !== false,
    steps: [
      ['Open the sale and tap {refund}.', { refund: 'Refund…' }],
      'Pick what comes back and the reason.',
      'Choose how the money goes back. Your shop may limit it to how the sale was paid.',
      'A return outside the shop\'s rules waits for a manager to approve it.',
    ],
  },
  {
    route: '/history',
    title: 'Exchange goods',
    tour: 'returns',
    when: (s) => s.permissions.can_exchange !== false,
    steps: [
      ['Open the sale and tap {exchange}.', { exchange: 'Exchange…' }],
      'Pick what comes back, then add what the customer takes instead.',
      'Only the difference is paid or given back.',
    ],
  },
  {
    route: '/history',
    title: 'Print a receipt again',
    steps: [['Open the sale and tap {print}.', { print: 'Print receipt' }]],
  },
  {
    route: '/history',
    title: 'Refunds without a connection',
    when: (s) => Boolean(s.settings.offline_returns),
    steps: [
      'Offline, this list shows the sales of this shift made on this device.',
      'They can be refunded at once. The refund posts when the connection is back.',
    ],
  },

  // Customers
  {
    route: '/customers',
    title: 'Look up a customer',
    steps: [
      'Search by name, phone, code or email.',
      'Tap a customer to see their purchases, returns, points and store credit.',
      'New customers are added from the cart while selling.',
    ],
  },

  // Holds
  {
    route: '/holds',
    title: 'Holds and deposits',
    steps: [
      'Each hold shows what is paid so far and what is still to pay.',
      ['{take} adds a payment to the hold.', { take: 'Take payment' }],
      'Once paid in full, hand the goods over. What is already paid comes off the bill.',
      'Cancelling a hold refunds what was paid.',
    ],
  },

  // Register
  {
    route: '/register',
    title: 'Open the shift',
    tour: 'shift',
    steps: [
      'Count the cash in the drawer before selling.',
      ['Type it as the opening float and tap {open}.', { open: 'Open Register' }],
      'A drawer in another currency has its own float.',
    ],
  },
  {
    route: '/register',
    title: 'Cash in and out',
    tour: 'shift',
    when: (s) => s.permissions.can_move_cash !== false,
    steps: [
      'Record cash put into or taken out of the drawer, with the amount and a reason.',
      'It counts in the cash expected at the close.',
    ],
  },
  {
    route: '/register',
    title: 'X-report',
    when: (s) => Boolean(s.settings.enable_xreport),
    steps: [['{xreport} at the top reads the shift at any time without closing it.', { xreport: 'X-report' }]],
  },
  {
    route: '/register',
    title: 'Close the shift',
    tour: 'shift',
    steps: [
      'Count each way of paying and type what you counted. The difference shows straight away.',
      'Wrong payment method on a sale? Return it and ring it again before you close.',
      ['Tap {close}. ERPNext posts the shift in the background, and this page says if it needs a retry.', { close: 'Close Register' }],
    ],
  },
  {
    route: '/register',
    title: 'A shift someone left open',
    when: manager,
    steps: [
      'Other shifts still open at this outlet are listed on this page.',
      'A manager counts and closes them here, the same way as their own.',
    ],
  },

  // Insights
  {
    route: '/insights',
    title: 'Sales dashboard',
    when: (s) => Boolean(s.permissions.insights),
    steps: [
      'Net sales, invoices, average basket and returns, then sales by day, outlet and cashier.',
      'Filter it by dates, outlet, customer, payment method or item.',
    ],
  },
  {
    route: '/insights',
    title: 'Salespeople',
    when: (s) => Boolean(s.permissions.sales_by_person) && s.settings.salesperson_mode !== 'Off',
    steps: [
      'Each salesperson\'s sales, returns, net and commission for the period you pick.',
      'For this outlet or every outlet of the company, with a CSV download.',
    ],
  },

  // Settings
  {
    route: '/settings',
    title: 'Where things are',
    steps: [
      'Offers, cashback, bundles and price books each have their own tab.',
      'General holds the switches for the whole shop, in groups.',
      'Who may do what is under General, Approvals and access.',
    ],
  },
  {
    route: '/settings',
    title: 'System check',
    when: (s) => Boolean(s.permissions.system_check),
    steps: [
      'The System check tab says what may stop the till on this site and what to do about it.',
      'Copy it for support and send it with any question.',
    ],
  },
]

export const TOURS = {
  basics: {
    title: 'Getting around',
    steps: [
      { target: 'nav-rail', title: 'Your screens', text: 'Sell, history, customers, the register and more. Each person sees the screens they may use.' },
      { target: 'register-pill', title: 'Your shift', text: 'Open or closed at a glance. Tap it to open or close the shift on the Register page.' },
      { target: 'language', title: 'Your language', text: 'Pick the language of the till. The next person can pick theirs.', optional: true },
      { target: 'help-button', title: 'Help on every screen', text: 'Tap here on any screen for its help and short tours like this one.' },
    ],
  },
  sell: {
    title: 'Your first sale',
    route: '/',
    steps: [
      { target: 'register-pill', title: 'Open the shift first', text: 'No shift is open yet. Tap here, count the cash in the drawer and open it.', when: (s) => !s.registerOpen },
      { target: 'sell-search', title: 'Find a product', text: 'Type part of its name or code, or scan its barcode.' },
      { target: 'sell-groups', title: 'Groups', text: 'Show one group of products at a time.' },
      { target: 'sell-products', title: 'Add it', text: 'Tap a product to add it to the cart. Tap again for one more.', optional: true },
      { target: 'cart-customer', title: 'The customer', text: 'Find or add the customer. Without one, the sale goes to the walk-in customer.' },
      { target: 'cart-salesperson', title: 'Who sold it', text: 'Pick the salesperson. Your shop may make it required.', optional: true },
      { target: 'cart-lines', title: 'The cart', text: 'Tap a line to change its quantity, give a discount or remove it.' },
      { target: 'cart-tools', title: 'Coupon, discount and note', text: 'For the whole sale. A button that holds something stays lit.' },
      { target: 'cart-totals', title: 'The total', text: 'Details shows how it is made: offers, discounts and tax.' },
      { target: 'cart-park', title: 'Park', text: 'Keeps this basket aside so you can serve the next customer.' },
      { target: 'cart-pay', title: 'Pay', text: 'Opens the payment screen. Pick how the customer pays, split it if needed, and the change is worked out for you.' },
    ],
  },
  returns: {
    title: 'Refunds and exchanges',
    route: '/history',
    steps: [
      { target: 'history-search', title: 'Find the sale', text: 'By invoice number, customer, mobile or order ID. Filters narrows it further.' },
      { target: 'history-row', title: 'Open it', text: 'Tap a sale to open its receipt.', optional: true },
      { target: 'receipt-refund', click: 'history-row', title: 'Refund', text: 'Pick what comes back and how the money goes back.', optional: true, when: (s) => s.permissions.can_return !== false },
      { target: 'receipt-exchange', title: 'Exchange', text: 'Swap for other goods. Only the difference is paid or given back.', optional: true, when: (s) => s.permissions.can_exchange !== false },
      { target: 'receipt-print', title: 'Print it again', text: 'The receipt prints again from here.', optional: true },
    ],
  },
  shift: {
    title: 'Open and close the shift',
    route: '/register',
    steps: [
      { target: 'register-open', title: 'Open the shift', text: 'Count the cash in the drawer, type it as the opening float and open.', optional: true },
      { target: 'register-summary', title: 'This shift', text: 'Sales so far, by way of paying and by salesperson.', optional: true },
      { target: 'register-cash', title: 'Cash in and out', text: 'A float top-up or a payout, with a reason. It counts in the cash expected at the close.', optional: true },
      { target: 'xreport', title: 'X-report', text: 'Reads the shift at any time without closing it.', optional: true },
      { target: 'register-count', title: 'Count', text: 'At the end, type what you counted for each way of paying. The difference shows before you close.', optional: true },
      { target: 'register-close', title: 'Close the shift', text: 'ERPNext posts it in the background. If it needs a retry, this page says so.', optional: true },
    ],
  },
  currency: {
    title: 'Selling in another currency',
    route: '/',
    when: (s) => s.saleCurrencies.length > 0,
    steps: [
      { target: 'cart-currency', title: 'The currency', text: 'Switch a walk-in to the currency they pay in. A customer billed in another currency buys in it by themselves.' },
      { target: 'cart-totals', title: 'The total', text: 'Prices are converted at the rate fixed for the shift.' },
      { target: 'cart-pay', title: 'Pay', text: 'Take the payment in that currency, or part of it in yours.' },
    ],
  },
}

// What is new, newest first. Shown once per person after an update, only the
// entries newer than what they last saw and that apply to them.
export const WHATS_NEW = [
  { version: '0.58.0', title: 'Refunds to store credit', text: 'Before 0.58.0, saving the General settings switched off Allow refunding to Store Credit. If your shop refunds to store credit, switch it on again in Settings, General, Returns and refunds.', route: '/settings', when: (s) => Boolean(s.permissions.settings) },
  { version: '0.58.0', title: 'Help on every screen', text: 'Tap ? at the top of any screen for its help and short tours over the real buttons.', tour: 'basics', when: (s) => Boolean(s.help.in_till) },
  { version: '0.57.0', title: 'Thirteen languages', text: 'Portuguese (Brazil), Persian, Russian and Turkish join the list. Pick yours from the language button at the top.' },
  { version: '0.57.0', title: 'The salesperson on every sale', text: 'Pick who made the sale under the customer. Your shop may make it required.', tour: 'sell', when: salespeople },
  { version: '0.57.0', title: 'Sales by salesperson', text: 'Insights has a Salespeople tab: each person\'s sales, returns and commission for any period.', route: '/insights', when: (s) => Boolean(s.permissions.sales_by_person) && s.settings.salesperson_mode !== 'Off' },
  { version: '0.57.0', title: 'System check', text: 'Settings, System check says what may stop the till on this site and what to do. Copy it for support.', route: '/settings', when: (s) => Boolean(s.permissions.system_check) },
  { version: '0.56.1', title: 'Returned goods sell again at once', text: 'An item a customer brings back can be sold to the next customer straight away, serial numbers included.' },
  { version: '0.56.0', title: 'Refunds without a connection', text: 'This shift\'s sales made on this device can be refunded even offline. The refund posts once the connection is back.', route: '/history', when: (s) => Boolean(s.settings.offline_returns) },
  { version: '0.55.0', title: 'A new price at the till', text: 'Open a line in the cart and type the new price, where your shop allows it.', when: (s) => Boolean(s.permissions.can_change_price) },
  { version: '0.54.0', title: 'Close a shift someone left open', text: 'The Register page lists the other shifts open at this outlet, and a manager counts and closes them there.', route: '/register', when: manager },
]
