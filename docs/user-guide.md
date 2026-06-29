# LumenPOS — Complete User Guide

*Applies to LumenPOS v0.3.0. This document is updated with every feature change.*

**Dark mode:** the nav rail has a **Dark / Light** toggle at the bottom. On
first run LumenPOS follows your **ERPNext desk theme** (My Settings → Theme:
Light / Dark / Automatic); Automatic falls back to the operating system's
appearance. The moment you use the in-POS toggle, that choice is remembered
per device and overrides the ERPNext theme from then on. Printed receipts
always come out black-on-white regardless of the screen theme.

**Language (Arabic / English):** the top bar has a one-tap language switch
(shows **العربية** when you're in English, **English** when you're in Arabic).
Arabic flips the whole interface to **right-to-left** and translates every
label, button, message and tooltip. **Master data is never translated** — item
names, customer names, codes and barcodes always show exactly as entered in
ERPNext, in whatever language they were typed. On first run LumenPOS follows the
browser language (Arabic on a typically-Arabic device); your choice is then
remembered per device. Return reasons and other configurable lists show the
text you saved in Settings.

LumenPOS is a Vend (Lightspeed X-Series) style Point of Sale for ERPNext v15.
Sales post as **POS Invoices** with native **POS Opening/Closing Entries**, so
ERPNext consolidates them into Sales Invoices automatically at register close —
stock, GL and reports behave exactly as standard ERPNext.

---

## 1. Installation & first-time setup

### Install (Frappe Cloud)
1. Dashboard → your **Bench Group** → **Apps** → **Add App** → From GitHub →
   `https://github.com/ma7mod7osam/lumenpos`, branch `main` → **Deploy**.
2. Site → **Apps** → **Install** next to LumenPOS.
3. Updates later: the bench shows **Update Available** → Deploy. The site
   migrates automatically and browsers fetch the new build on next load
   (asset URLs are version-stamped — no manual cache clearing needed).

### Install (bench with shell access)
```bash
cd frappe-bench
bench get-app https://github.com/ma7mod7osam/lumenpos
bench --site yoursite install-app lumenpos
bench --site yoursite clear-cache
```
The frontend ships pre-built — **no Node/npm needed on the bench**.

### Prerequisites in ERPNext
Create a **POS Profile** per register/branch with:
- **Company**, **Selling Price List**, **Warehouse**
- **Payment methods** (at least one; mark one as Default; have one of type Cash)
- Your cashiers under **Applicable for Users**
- Optional: **Taxes and Charges** template, default **Customer** (walk-in),
  **Print Format** (used for browser printing), **Item Groups** (limits the grid)
- Optional (printer): `Printer IP` / `Printer Port` fields (LumenPOS section)
  for a network ESC/POS thermal printer

Items need an **Item Price** on the profile's selling price list. Items
without a price ring up at 0.

### Open the POS
Log in to ERPNext, then open **`https://yoursite/pos`**.
The **LumenPOS workspace** in the desk has shortcuts to everything.

---

## 2. The Sell screen

| Area | What it does |
|---|---|
| **Search bar** | Type to search name/code/barcode (instant — served from a local cache). Press **Enter** with a scanned barcode or serial number to add the item directly. |
| **Category chips** | One scrollable row. **All** shows everything; **🎁 Bundles** appears when bundles exist. |
| **Product grid** | Tap a tile to add to cart. Tiles show price, stock count and an **S/N** badge for serialized items. |
| **Cart (right panel)** | Customer, channel, salesperson, lines, coupons, totals, Pay. |

### Cart line controls
Tap a line to expand it: quantity stepper, **Discount %** (manual), Remove.
Lines show `item code · ▮ barcode` under the name.

- **Promotion badges (★ purple)** appear on lines a promotion is discounting.
- **💡 Suggestions** appear *under the specific line* they relate to
  ("Add 1 more — get at 50% off"). Click one to find the suggested product.
  Basket-level suggestions (Spend & Save) show above the totals.
- **🎁 Bundle lines** are locked (no qty edit / manual discount); expanding
  offers *Remove bundle*, which removes the whole bundle instance.
- **Serialized lines** show serial chips; qty always equals scanned serials.

### Customer
Tap **Add a customer** → search by name / mobile / tax ID → select, or create:
- **Individual**: name + mobile mandatory.
- **Company**: name, mobile, **Tax ID** and **national address** (building,
  street, district, city, postal code) mandatory — creates a linked Address.

When a customer is attached, the cart shows their **loyalty points** and
**store credit**, and prices reprice if a price book applies to their group.

### Channel (delivery apps) & Exchange
The channel picker defaults to **Walk-in**. Selecting a delivery app
(configured in Settings → General):
- forces an **Order ID** if the app requires one (Pay is blocked without it),
- switches prices to the app's price list if it has one,
- records the channel on the invoice using your site's existing fields:
  `pick_customer` (checkbox, ticked), `custom_app_type` (the app — must be
  an option of that Select field), `pick_order_no` (the order ID), and
  `is_exchange` for exchanges. LumenPOS writes these only if they exist.

The **Exchange** toggle flags the sale as a damaged-product exchange
(`is_exchange` field).

### Salesperson
Type a name **or the salesperson number** (`sales_person_no`) and pick.
Persists across sales (shift-based); recorded on the invoice's sales team
(100%), so ERPNext commission reports work.

### Coupons
Type the code → **Apply**. Coupon-locked promotions never reach the browser
until a valid code is entered (codes can't leak). Multiple coupons allowed.

### Park / Retrieve / Discard
**Park** saves the cart with a note; **Retrieve Sale** (top right) brings it
back. Parked sales survive across devices.

---

## 3. Payments

Tap **Pay**. The payment screen shows the amount, a tender input with
quick-cash buttons, and a tile per payment method.

- **Scheme logos**: each tile shows the card scheme / wallet logo detected from
  the Mode of Payment name — **Visa, Mastercard, mada, American Express,
  Tamara, Tabby, STC Pay, Apple Pay** — on a white chip (legible in light and
  dark). Other methods (Cash, Bank Transfer…) keep a clean line icon.
- **Split payments**: add any combination; each shows in the list with ✕.
- **Cash** may over-tender → change due is shown and recorded.
- **Store Credit** tile appears when the customer has balance.
- **🎁 Gift Card**: scan/type the card → **Check** shows the live balance →
  **Apply**. Multiple cards per sale supported.
- **Loyalty points**: when the customer has points, a redeem box shows their
  value; capped server-side at the customer's real balance.
- **Discount approval**: if any manual discount exceeds the limit
  (Settings → General → *Discount approval*), Pay is blocked until the discount
  is approved. How it's cleared depends on the **over-limit approval method**:
  - **Passcode only** (default) — a manager enters the **passcode / approver
    PIN** at the till. The approver's name is recorded on the invoice.
  - **Request only** — the cashier taps **Send approval request**; the till
    waits while a role-holder approves it (see below). No PIN on the device.
  - **Passcode or request** — the cashier can do either.
  A **request** is single-use, tied to the open register session, and **expires
  if the register closes** before it's approved. Approvals are re-checked
  server-side, so the limit can't be bypassed from the client.

  **Approving requests:** users holding the configured **Approver Role** (plus
  LumenPOS / System Managers) get an **Approvals** tab in the left rail with a live
  count badge. Open it to **Approve** or **Reject** each pending request — only
  while the cashier's register is still **open**. On approval the cashier's till
  proceeds automatically; on rejection they must lower the discount.

**Taxes:** the cart computes taxes from the POS Profile's tax template the
same way ERPNext does — exclusive rows appear as `+ VAT 15%` lines and are
part of the Pay amount; inclusive rows show as "(included)" for information.
The displayed total always equals the invoice grand total.

> **VAT-inclusive pricing (shelf prices already include VAT):** the VAT row
> in your Sales Taxes and Charges template **must** have *"Is this Tax
> included in Basic Rate?"* ticked. Then the price the customer sees is what
> they pay, with VAT shown as "(included)". If that flag is **off**, ERPNext
> (and the cart) will add 15% on top of the shelf price — overcharging.
> Verify the current setting at a glance in **Settings → Status → VAT / taxes**
> ("included in price" vs "added on top").

Everything the client computed is **re-validated server-side** at submit:
prices, promotions, serials, balances, passcodes. The client math is
display-only.

### After the sale
The receipt modal shows totals, taxes, payments, change, applied promotions
(★) and bundles (🎁), loyalty earned/redeemed, gift card info.
**Print receipt** uses, in order:
1. the **ESC/POS network printer** (if configured on the profile, incl. cash-drawer kick),
2. the profile's **Print Format** via ERPNext print view,
3. the built-in receipt via the browser dialog.

---

## 4. Promotions (replaces ERPNext Pricing Rules at the POS)

Managed in **POS Settings → Promotions** (or the desk DocType). LumenPOS sets
`ignore_pricing_rule` on its invoices, so ERPNext Pricing Rules never
double-apply. **Promotions only affect sales made through /pos** — desk-made
invoices are untouched.

### Types
| Type | Behaviour | Key fields |
|---|---|---|
| **Simple Discount** | % off, amount off, or a fixed price on matching products | Discount type + value |
| **Buy X Get Y** | Multi-buy. **Buy rows trigger** (any of them, mix & match), **Get rows are rewarded** (cheapest eligible units first). No Get rows = the buy list rewards itself (classic buy-2-get-1). Same item on both sides works: a unit is never trigger *and* reward (buy-1-get-1-50% needs 2 units). | Buy qty, Get qty, Reward, Max uses/sale |
| **Spend and Save** | Basket discount once eligible spend crosses a threshold | Min spend, basket discount |

### Calculate discount on (price-book basis)
For Simple Discount and Buy X Get Y, choose what the discount is measured from
when a promoted item also has an active **price book**:
- **Price book price** (default): the discount stacks on the price-book price.
  Standard 99, book 49, 20% off → **39.20**.
- **Standard price**: the discount is measured from the regular price and the
  customer gets the **lower** of the price-book price or (standard − promo) —
  it never stacks with the book and never raises the price. Standard 99, book
  49, 20% off → the book's 49 wins → **49.00**; the promo only kicks in if it
  beats the book. Uses the **highest-priority** active book as the comparison.

(Spend and Save and Bundle promotions always use the cart's current price.)

### Products: include & exclude
Each row is **Include** or **Exclude** and targets an Item, Item Group,
Brand, or **Tag** (an ERPNext item tag — tag items in the desk, then group them
here without listing every group/brand). All picked from a validating dropdown
(free text is rejected):
- *All products except brand X*: tick **Apply on all products** + Exclude row.
- *Group except items*: Include the group + Exclude the items.
- Exclude-only rows = "everything else".

### Scheduling & eligibility — all optional
- No dates and no times = runs **all the time**.
- Date range, days of week, and a daily time window (wraps midnight for
  happy hours). Equal start/end times mean "all day".
- Outlets (none ticked = all) and customer groups (empty = everyone).
- **Requires Coupon Code** gates the promo behind a code at the till. Use the
  single code field for one shared code, or open a saved coupon promo and
  **Generate** / **Import (Excel/CSV)** a whole batch of unique codes. Each batch
  has a **use limit** — how many times each code may be redeemed (**1** = single
  use, **0** = unlimited) — plus an optional expiry. Redemptions are counted and
  a code is marked Fully Used once it hits its limit. **Export codes** downloads
  the batch to print/hand out.

### Stacking
Promotions marked **Can combine** stack with each other; non-stackable ones
compete and the single best applies. The customer automatically gets
whichever is worth more. Discounts never exceed line/basket totals.
Promotions **never touch bundle lines**.

### Testing a promotion
Open a saved promotion → **Test this promotion** → pick real items + qty →
**▶ Run test**. The server dry-runs it and shows every gate pass/fail
(status, dates, weekday, time, outlet, customer group), what each product row
matches in the basket, items missing a price, and the final savings.
**Use this first whenever a promotion "doesn't work".**

---

## 5. Bundles

**Settings → Bundles** (separate from promotions). A bundle = a name, a
**fixed bundle price**, component items with quantities, outlets, and an
optional **Valid From / Valid To** window. Past **Valid To** the bundle is
**expired** — it stops being offered at the till and shows an *Expired* badge in
the Settings list. Serialized items can't be bundled.

On the sell screen the **🎁 Bundles** chip shows bundle cards; **Add** puts
every component in the cart as **separate lines** (each individually
returnable — the point of the design), highlighted with a 🎁 chip and priced
together. Removing any line removes the whole instance.

**Price split:** by default the bundle saving is split across the lines
**proportionally to their regular prices** (cent-correct, so line totals sum
exactly to the bundle price). To control the split yourself — e.g. protect
margin on one item — fill the optional **Allocated Price** per component:
all rows must be filled and must sum exactly to the bundle price (validated
live in the editor and again on save).

---

## 6. Price Books (Vend-style)

**Settings → Price Books.** A price book is simply **a list of items with a
special price** that applies for a period — a discount off your normal selling
price. **No ERPNext Price List is created or touched**; the prices live on the
book itself, so your Standard Selling master is never changed.
- **Set it up**: give it a name, **priority** (highest wins when several books
  cover the same item), optional **validity dates**, and the **outlets** /
  **customer groups** it applies to (empty = everyone / all outlets).
- **Add the items** under **Item prices**: pick items (search by name, code or
  barcode) and type each one's price, or **↥ Import Excel/CSV** (matched by
  code, name or barcode; the Book Price / Price column — or the last column if
  the file has no header — sets the price). **↧ Export** downloads the book's
  items. Or **Add all by** brand / item group / tag to pull every matching
  sellable item in one click (each added at its current selling price, so
  nothing accidentally sells at 0 — then lower the ones you want to discount).
  To reprice the whole book at once, use **Discount all prices by X%** with an
  optional rounding step (nearest 0.05 / 0.25 / 0.50 / 1 / 5). Reopen the book
  any time and the items are right there.
- **How it applies at the till**: while the book is active (date window +
  outlet + customer group match), its items sell at the book price; everything
  else keeps the normal selling price. When several active books list the same
  item, the **highest-priority** book wins for that item.

Order at the till: **delivery-app price list → active price book(s) →
normal selling price.** (Delivery-app prices still use a real ERPNext Price
List and override price books.)

**Per-app prices (e.g. Jahez):** give a delivery app its own price list in
**Settings → General → Delivery apps** (use **+ new** to create one named after
the app), then tap **Edit prices** to open the same editor — including
Excel/CSV import/export — for that app only. An app's price list overrides
every price book, so it's the place to keep channel-specific prices.

**Fallback pricing:** a price book only changes the items it lists — every
other item keeps its normal selling price. A partial book can never make the
rest of the catalog ring up at 0.

---

## 7. Gift cards

Correct retail accounting throughout: selling a card moves money into a
**Gift Cards liability account** with **no revenue and no tax** — tax applies
when the card is spent.

**Accounting mapping (Settings → General → Gift cards):** point gift cards at
your own **mode of payment**, **liability account** and **item**, or leave any
field blank to auto-provision the defaults (Gift Card / Gift Cards / GIFT-CARD).

- **Sell**: 🎁 button in the cart actions → amount, card number (scan a
  physical card or auto-generate), payment method. The receipt shows the card
  number + balance. Default expiry: Settings → General.
- **Redeem**: Gift Card tile in payments → scan → balance check → apply.
  Multiple cards per sale; server re-validates balance/expiry/status.
- **Manage**: Settings → Loyalty & Gift Cards → search cards, see balances
  and history, disable a card.
- Gift cards require a connection (no offline redemption), and a gift card
  can't pay for a gift card.

---

## 8. Loyalty

Uses ERPNext's native **Loyalty Program** — LumenPOS adds the setup and till UX:
- **Create** in Settings → Loyalty & Gift Cards: earn rate (1 point per X
  spent), point value, expiry days, expense account (auto-created if empty).
  Auto opt-in enrolls **all customers**.
- **Earning** is automatic on every POS sale once a program exists.
- **Redeeming** appears in the payment screen when the customer has points;
  capped at their real balance, validated server-side.
- The receipt shows points earned and redeemed.

**Store credit** (related but separate): refunds can go to store credit
(per-customer balance on a liability account); it appears next to the
customer in the cart and as a payment tile.

---

## 9. Returns & refunds

**History** → open a sale → **Refund…**:
- Pick lines and quantities — partial returns tracked, you can never return
  more than remains returnable.
- **Serialized items**: **scan or type each serial** coming back — it's checked
  against the serials sold on this invoice (and still returnable). This forces
  the cashier to read the actual unit rather than blind‑pick from a list.
- **Return reason (required)** — pick why the item is coming back from the list
  configured in **Settings → General → Return reasons**, or choose **Other** to
  type a free-text reason. The reason is stored on the credit-note invoice
  (field *Return Reason*) for reporting. Manage the list (add/remove) in
  Settings; the till always offers **Other** on top of it.
- **Return window (optional).** When *Limit regular returns to a time window* is
  on (**Settings → General → Returns**), a sale can be returned normally only
  within **N days** (default **14**, configurable; 0 = no limit). Past the
  window the Refund button is blocked and the cashier taps **Send return
  approval request** — a holder of the **Approver Role** approves it from the
  **Approvals** tray (while the register is open), then the refund proceeds.
  The approval is single-use and tied to that invoice; the server re-checks the
  window and the approval, so it can't be bypassed from the client. Off by
  default (existing behaviour: no time limit).
- **Refund method is restricted to how the sale was paid** (when *Restrict
  refunds to the original payment method* is on in Settings → Refunds, the
  default). The dropdown shows only the tenders the customer actually used
  (plus **Store Credit**, always allowed). Add exceptions per method in
  Settings → Refunds — e.g. *paid Visa → refund Visa only*, *paid Mada →
  refund Mada or Cash*. The server enforces this even if the UI is bypassed.
- Posts a credit-note POS Invoice tied to the open register session, so the
  drawer count stays right.
- **Consolidated sales are still refundable at the till.** Once a shift closes,
  its sales are merged into Sales Invoices — but you can still refund them from
  the POS exactly the same way. LumenPOS posts the credit note against the original
  POS sale, tied to your **current** open shift, so the refund comes out of the
  current drawer; ERPNext merges it into a consolidated credit note at the next
  close. (You no longer need the ERPNext desk for everyday post-close returns.)
  Refund a given sale through **one** channel only (the till *or* the desk), not
  both, so the returnable quantity stays accurate.
- **Sets return together.** Items sold as a **bundle** or a **Buy X Get Y**
  offer are linked — on a **regular return** you must return the **whole set**
  (every member, full quantity) or none; the screen badges them *Set — return
  together* and steps the whole set at once, and the server enforces it. Need to
  give back just one item of a set? Use **Exchange** instead (exchanges are
  exempt). Each line stores its set in `lumenpos_return_group` at sale time.

### Warranty exchanges (damage replacement)

Exchanges are an optional feature — turn them on with **Settings → General →
Enable warranty exchanges** (the Exchange button only shows when enabled).

For warranty/damage swaps, open the original sale in **History → click the
invoice → Exchange** (next to Refund) instead of doing a return and a sale by
hand. The exchange opens pre‑loaded with that invoice. One guided screen:

1. **Damaged item(s)** coming back — each item is checked against
   **its own warranty period** (the item's *warranty days*, counted from the
   sale date); items out of warranty (or with no warranty set) can't be
   selected. Credited at exactly what the customer paid on that invoice. For
   serialized items, **scan each serial** coming back (validated against the
   original). The warranty also shows on every cart line during normal sales.
   The replacement's warranty is **counted from the original purchase date**,
   not the exchange date — so the customer keeps only the **remaining** term
   (e.g. buy with a 24‑month warranty, exchange at month 22 → the replacement
   has 2 months left). This chains correctly across repeat exchanges.
2. **Add the replacement item(s)** going out (optional — leave empty for a
   pure refund). Ticking a damaged item **auto-fills a replacement of the same
   item at the original price** (a net-zero warranty swap) — change the item,
   quantity or price, or delete the row if the customer just wants a refund.
3. LumenPOS shows the **net difference** and you settle it: collect the extra,
   refund the difference (cash or store credit), or confirm an even swap.
   - **Override the replacement price**: each replacement line has an editable
     **unit price** — type a new price to, say, give a pricier item at the same
     price. When the replacement is dearer, a **"Give as even swap"** button
     waives the difference in one tap (prices the replacement at the damaged
     credit, net 0). Overridden lines are flagged and noted on the invoice.

A **return reason** sits next to the settlement, pre-filled with the default
warranty reason **"استبدال ضمان"** — change it to any other configured reason
or **Other** (free text) if needed. It's recorded on the damaged-return credit
note just like a normal refund.

On confirm LumenPOS creates the same two documents you made manually — a
**return** POS Invoice for the damaged item (`is_return` + `is_exchange`,
which your hourly script moves to the damage warehouse) and a **sale** POS
Invoice for the replacement (`is_exchange`) — atomically. Only the net
difference touches the drawer; the matched value is settled through an
internal **Exchange Credit** clearing account that nets to zero.

Both documents are stamped with the original sale in **`exchange_against_invoice`**
(the site's existing POS Invoice field), so an exchange's two legs are always
traceable back to the invoice they came from.

---

## 10. Serial numbers (strict)

A serialized item can never be sold without its exact serials:
- Adding one opens a scan prompt; the serial must exist, belong to that item,
  be **Active** stock in this register's warehouse, and not repeat in the sale.
- Quantity is locked to the scanned serial count.
- Scanning a serial in the search bar adds its item with the serial attached.
- Returns require selecting exactly which sold serials come back.
- Everything is re-validated at submit; serialized items can't be sold
  offline or inside bundles.
- **Scan-only (optional).** Turn on *Require scanning for serial numbers*
  (Settings → General) to **block manual typing** when **selling** and on
  **returns** — serials must be read with a barcode scanner. **Exchanges are
  exempt**: there the damaged item's serial only has to **match one sold on the
  original invoice**, so the cashier may type it. Leave off if a register has no
  scanner.

---

## 11. Register & cash management

- The **"Register open"** pill in the top bar is a shortcut — click it to
  jump to the Register page (where closing happens).
- When the register is closed, the open-register prompt only blocks the
  **Sell** screen — the nav rail and the History/Register/Settings tabs stay
  usable. You can also open the register directly from the **Register** tab.
- **Open register** (mandatory before selling): enter the opening float →
  creates a **POS Opening Entry**. One live shift per register — if you
  already have one, you're offered **Continue that shift** or (only when the
  testing toggle in Settings → General is ON) **Open a new one anyway**.
- **Cash in / out** during the day from the Register page (reason logged). Each
  movement is **netted into the expected cash** at close (expected = opening +
  cash sales + cash in − cash out) **and declared on the POS Closing Entry**
  itself: a **Cash In / Cash Out** total plus a **Cash Movements** table (under
  the payment reconciliation), so the Z-report shows exactly what was added to or
  taken from the drawer.
- **Fix a wrong payment method before closing.** If you rang a sale up on the
  wrong tender (e.g. Visa instead of Mada), do the **return + corrected sale
  while the shift is still open** — they're picked up automatically. Once you
  close, the shift can't be sold on again, so always correct first.

**How closing works (and why it's now reliable).** Closing is a strict
three-step state so a slow or failed consolidation can never strand a shift:

  1. **Open** → you confirm the cash counts and hit *Close Register*.
  2. **Closing** → the shift flips to *Closing* and is saved **immediately**.
     From this instant it's **not sellable and not resumable**, whatever
     happens next. ERPNext then consolidates the shift's POS Invoices into
     Sales Invoices in a **background job**, run **one shift at a time** (a
     cluster-wide lock) so two registers closing together can never deadlock.
  3. **Closed** → once consolidation succeeds, the shift is *Closed*, the
     **POS Opening Entry** is closed and the **POS Closing Entry** is linked.

  If consolidation fails (heavy load, a data issue), the shift stays in
  *Closing* with a **Failed** badge and an error — it does **not** silently
  reopen. A **↻ Retry closing** button (on the close panel, on the Sell
  screen's prompt, and in Previous sessions) re-runs it; ERPNext rolls a
  failed attempt back fully, so retrying never double-posts. A background
  **self-healer also retries stuck shifts every ~10 minutes**, so most resolve
  themselves. The next cashier can't open a new shift on that register until
  the previous close completes — no more "I accidentally kept selling on
  yesterday's shift."

  **Stuck overnight? Start a new shift anyway.** Blocking new sales until a
  close finishes is the safe default, but a close that keeps **Failing** into
  the next day shouldn't keep the store shut. On a *Failed* close, a manager
  (anyone who can close registers) sees a **"Start a new shift anyway"** option
  — with an opening-float box — on both the Sell-screen prompt and the Register
  page. It opens a fresh shift immediately and **leaves the failed shift in the
  background**, where the self-healer (and the **↻ Retry closing** button) keep
  retrying its consolidation until it succeeds. Nothing is lost: the old shift's
  invoices still consolidate on their own; you've just unblocked the till. Only
  offered when the previous close actually **failed** — a close that's merely
  still *finalising* must finish (or be retried) first.
- **Previous sessions**: the Register page lists closed (and still-finalising)
  sessions — takings, discounts, count differences, status, and direct links
  to each session's **POS Opening Entry** and **POS Closing Entry**.

---

## 12. Sales history

Search bar matches invoice no, customer name/ID, **mobile**, and **order ID**.
Filters: date range, status, document status, **channel** (walk-in / app),
**online order** (online only / in-store only), **payment method**, outlet,
**item**, **serial number**, amount range. The online-order filter reads the
site's `online_order` field (falls back to `custom_online_order` /
`is_online_order`); if no such field exists the filter simply matches nothing.
Each row shows the **cashier who made the sale**, a clean date/time, the
**payment method(s)** next to the total, the mobile/order info, and badges:
channel/ONLINE, DRAFT/CANCELLED, **REFUND**, and **EXCHANGE** (so warranty swaps
are obvious at a glance). Click → receipt → reprint or refund.

---

## 13. Offline mode

After the first online load the catalog (incl. barcodes) is cached locally —
this also makes everyday search instant. If the connection drops:
- an amber **Offline — N queued** pill appears,
- search and selling continue; finished sales are **queued** and sync
  automatically when the network returns (errors keep the sale queued and
  tell you why),
- needs a connection: history, customers, loyalty, store credit, gift cards,
  serialized items, delivery-app sales, register opening.
- **Keep the tab open while offline** — the page itself can't reload during
  an outage.
- Settings → Status shows cache size and queued count; **Refresh offline
  catalog** re-pulls it. The General toggle *Cache only in-stock items*
  keeps the cache to your warehouse's stock.

---

## 14. Settings reference (gear icon → /settings)

| Tab | Contents |
|---|---|
| **Promotions** | List + Vend-style editor for all types, include/exclude rows, coupons, the dry-run **Test** panel. |
| **Bundles** | Fixed-price bundles: components, price, outlets. |
| **Price Books** | Items with special prices for a period (validity + priority + outlets/customer groups); add items or **Excel/CSV import**. No ERPNext price list created — the master is never changed. |
| **Loyalty & Gift Cards** | Create/view loyalty programs; search/disable gift cards. |
| **General** | Delivery apps (name, price list — **+ new** to create, **Edit prices** to set per-app prices with import/export, order-ID required); register & offline toggles; gift card expiry; **Refunds** (*restrict refunds to the original payment method* + per-method exception rules); **Returns** (*limit returns to a time window* + **return window days**); **Discount approval** — limit %, **over-limit method** (passcode only / request only / passcode or request), master passcode + per-manager **approver PINs**, and the shared **Approver Role** for discount & return requests. |
| **Status** | Version, outlet, price list, connection, cache size, queue, printer, register state. |
| **Approvals** | (Approvers only) Live tray of pending **discount and return** requests to Approve / Reject — shown in the left rail when discount requests are enabled or returns are window-limited. |

Each tab is shown only to users with permission for it (see **Roles** below),
and each action (create / edit / delete) is gated separately. Store-level
config (price list, warehouse, payments, taxes, printer, print format) stays
on the **POS Profile** — the single source of truth.

---

## 15. Roles & permissions

LumenPOS access is governed entirely by **standard ERPNext DocType permissions** —
manage them in **Role Permissions Manager** (Frappe Cloud → desk → search
"Role Permissions Manager"), no LumenPOS-specific switches. The POS reads your
permissions on start and **shows/hides each tab, button and the Pay button
accordingly**, and every server action re-checks them.

LumenPOS ships two ready-made roles (assign them in the user's **Roles**):

| Role | Can |
|---|---|
| **LumenPOS Cashier** | Open the POS, sell, park, return, open/close & retry the register; read promotions/bundles/price books |
| **LumenPOS Manager** | Everything a cashier can, **plus** manage promotions, bundles, price books, delivery-app prices, settings, gift cards and loyalty |
| **Sales User / Sales Manager / System Manager** | The native ERPNext roles still work exactly as before (Sales User ≈ cashier, Sales Manager ≈ manager) |

What each capability maps to (so you can build your own custom roles):

| Capability | Controlled by permission on |
|---|---|
| See the POS at all | **POS Invoice → read** (no read = "you don't have access to the POS") |
| Make sales / returns | **POS Invoice → create** (the Pay button disables without it) |
| Open / close the register | **POS Opening Entry / POS Closing Entry → create** |
| See & edit Promotions | **POS Promotion → read / write / create / delete** |
| See & edit Bundles | **POS Bundle → …** |
| See & edit Price Books and item prices | **POS Price Book → …** and **Item Price → write** |
| Change the General settings tab | **LumenPOS Settings → write** |
| Loyalty / gift-card management | **Loyalty Program → create** / **POS Gift Card → write** |

> The **LumenPOS Cashier** role is granted the needed rights on POS Invoice, the
> opening/closing entries and Sales-Invoice consolidation automatically on
> install/update, so assigning it is enough to run a till. Tighten or widen any
> of it afterwards in Role Permissions Manager.

Discounts above the limit still need approval regardless of role — a manager
**passcode/PIN** at the till and/or an approved **discount request** (Settings →
General → *Discount approval* → over-limit method). Request approval is allowed
for holders of the configured **Approver Role** plus LumenPOS / System Managers.

---

## 16. Troubleshooting

| Symptom | Check |
|---|---|
| Paid in full but "must be paid in full" error | Fixed in v0.8: tiny rounding gaps from promotion discounts/taxes are absorbed via the POS Profile **Write Off Account** (set one for clean books) or by a 1-cent payment adjustment. |
| Print format ignored | Set **Print Format** on the POS Profile (Print Settings section; format must target POS Invoice). Verify what loaded in Settings → Status. An ESC/POS printer IP takes priority when configured. |
| Promotion not applying | Open it → **Run test** with the real items: the report shows the failing gate, rows that match nothing, or items priced 0. |
| "Already has an open entry" when opening register | You have an open POS Opening Entry — continue that shift, or cancel the entry in the desk. The choice dialog handles it. |
| "Previous shift not finished / Retry closing" when opening | The last shift's closing hasn't finished consolidating (or failed). Click **↻ Retry closing** — it's safe to retry repeatedly. It also self-heals every ~10 min. You can't open a fresh shift until it completes (this is what prevents selling on a stale shift). |
| Closing shows **Failed** with an error | Read the error (usually a stuck invoice or a transient lock). Hit **↻ Retry closing**; nothing is double-posted. If it keeps failing, open the linked POS Closing Entry in the desk and retry there. |
| A close **keeps failing** and you need to keep selling | On a *Failed* close, a manager can click **"Start a new shift anyway"** (Sell prompt or Register page) to open a fresh shift now. The failed shift stays in the background and keeps retrying — its invoices still consolidate on their own. |
| "You do not have access to the POS" | The user lacks **POS Invoice → read**. Grant the **LumenPOS Cashier** role (or POS Invoice access) in Role Permissions Manager. |
| A tab or the Pay button is missing for a user | That's the new permission gating — grant the matching permission (see **Roles & permissions**). |
| Item rings up at 0 | No Item Price on the **active** price list (book/app list overrides the default). |
| Can't add an item | Out of stock with negative stock disallowed, or it's serialized (scan required). |
| New features not visible after update | One hard refresh (Ctrl+Shift+R); from v0.5 asset URLs are version-stamped so this self-heals. |
| Old version shown in Status tab | The deploy didn't run — check the bench dashboard. |

---

## 17. Customers (client lookup)

The **Customers** tab (left rail) is a fast way to find a client and see their
POS activity in one place.

- **Search** by name, phone/mobile, customer code, email or tax ID, and filter
  by **customer group**. The list is server-paginated (**Load more**).
- Open a customer for their **profile** (phone, email, tax ID, type, member
  since, last purchase), **balances** (loyalty points, store credit) and
  **lifetime stats** (sales count, net spent, returns count).
- Their **transactions** list shows every till sale / return / exchange (POS
  Invoices, including consolidated ones), filterable by **type** and **date
  range**, paginated. Click a row to view / print the receipt.

**Performance:** every query is server-paginated and scoped to indexed columns,
and per-customer totals are computed only when you open a customer — never for
the whole list. The screen runs queries only while it's open, so it has no
effect on the Sell flow. The tab needs **Customer → read** (hidden otherwise).

---

## 18. Changelog

> **LumenPOS 0.1.0** is a standalone fork of this POS for the Frappe Marketplace,
> rebranded to the **Lumen** identity (primary blue `#1463FF`, Plus Jakarta Sans
> typography). The version history below is the shared lineage carried over from
> the original app.

### LumenPOS releases
| Version | Highlights |
|---|---|
| 0.3.0 | **Granular permissions** (Settings → General → *Permissions*). Three role gates, each enforced server-side and mirrored in the UI; managers always pass, blank role = anyone: **Edit price / discount** (who may apply a manual discount — the field is disabled otherwise), **Make returns** (who may refund — the Refund button hides otherwise), and **Exceed return window** (this role returns past the window *directly*; everyone else still uses the approval-request flow). |
| 0.2.0 | **Removed warranty Exchange.** Added: a per-POS-Profile **"Ignore ERPNext Pricing Rules"** toggle (on by default — LumenPOS uses its own promotion engine; off lets Pricing Rules apply); **add-item-on-scan** — a scanned barcode now adds the item instantly without pressing Enter (typed searches still use Enter). |
| 0.1.0 | Standalone fork of the POS + Lumen brand identity (logomark, blue glow, Plus Jakarta Sans). |

### Inherited lineage (from the original POS)
| Version | Highlights |
|---|---|
| 0.1 | Sell screen, payments, promotions engine (dual py/js), register sessions, parked sales |
| 0.2 | Offline mode, returns/refunds, loyalty redemption, store credit, ESC/POS printing |
| 0.3 | Bundle promo type, smart suggestions, salesmen, coupons, stock guard, strict serials |
| 0.4 | **POS Invoice migration** + native opening/closing entries, #2E5BFF rebrand, price books, delivery apps + exchange, settings page, discount passcode, customer types, history filters, local-first catalog, workspace, shift-choice dialog |
| 0.5 | Validating item picker, barcodes everywhere, approver PINs, 50k offline cache, cache-busting, promotion dry-run tester |
| 0.6 | **Standalone bundles** chosen from the sell screen, optional schedule fields (midnight-window bug fixed), include/exclude product rows, price editor inside price books |
| 0.7 | Per-line offer suggestions, **gift cards** (sell/redeem/manage, liability accounting), loyalty program setup, POS Profile print-format printing |
| 0.8 | Bundle **allocated prices** (manager-controlled split, validated to the bundle price), price-book **fallback pricing** (no more all-zero catalogs), register **session history** with POS Opening/Closing Entry links, closing-result panel, **rounding-gap absorber** (fixes "must be paid in full" on promotion sales), print format shown in Status |
| 0.8.1 | **Cart computes taxes from the profile's tax template** (exclusive VAT added to the Pay amount, inclusive shown as info) so the displayed total equals the invoice grand total; "Register open" pill links to the Register page; the close panel shows errors + Retry instead of hiding |
| 0.8.2 | Status tab shows the active **VAT / tax** config (included-in-price vs added-on-top) so VAT-inclusive setups can be verified at a glance |
| 0.8.3 | **Fixed promotion/discount sales failing with "Partial Payment not allowed"**: discounts are now applied *after* `set_missing_values` (which was resetting them to zero), basket discounts are folded into the lines (correct under VAT-inclusive), and payment reconciliation guarantees the invoice settles or shows a clear total-mismatch message |
| 0.8.4 | **Real discount fix**: with Pricing Rules off ERPNext honours only `discount_percentage` (not `discount_amount`), so all LumenPOS discounts are now posted as a percentage and survive onto the invoice — promotion/bundle sales complete. Register close panel hardened: never strands the cashier (shows a warning + lets you count and close even if the expected-takings summary fails to load) |
| 0.8.5 | Delivery-app sales write to the site's **existing** fields (`pick_customer`, `custom_app_type`, `pick_order_no`, `is_exchange`) instead of creating new `lumenpos_*` fields; history search/receipt read them too |
| 0.8.6 | **Register close no longer times out (504)**: the session is closed and saved immediately, and the POS Closing Entry consolidation runs in a background job; the POS polls for the entry and shows a "Generate closing entry" retry on any closed session missing one |
| 0.9.0 | **Dark mode** — theme toggle in the nav rail, persisted per device, defaults to the OS preference; full dark palette across every screen with #2E5BFF kept as the accent; receipts still print black-on-white |
| 0.9.1 | The open-register prompt no longer blocks the whole app — it covers only the Sell screen, so the nav rail and other tabs stay usable; the register can also be opened from the Register tab |
| 0.10.0 | **Warranty exchanges** — one guided ⇄ Exchange screen: find the original sale, pick the damaged item (credited at its original price) and the replacement, see the net difference, and confirm. Creates the damaged return (is_return+is_exchange) and replacement sale (is_exchange) atomically; only the net hits the drawer via an internal Exchange Credit clearing account |
| 0.10.1 | Exchange warranty now comes from each **item's warranty days** (per-line check, not a global setting); the warranty shows on every cart line during sales; exchanges are a toggleable feature (Settings → General → Enable warranty exchanges) — the ⇄ button hides when off |
| 0.10.2 | **Dark mode now follows your ERPNext desk theme** (Light/Dark/Automatic) on first load, so LumenPOS matches the look you already set in ERPNext; the in-POS Dark/Light toggle still overrides it per device |
| 0.10.3 | Item pickers in **promotions, bundles and price books** now search by **name, item code or barcode** (barcode shown in the dropdown); price-book editor gains **Excel/CSV import & export**; **delivery apps can have their own editable price list** (per-app prices, e.g. Jahez) with the same editor + import/export; new price books default to **Standard Selling** (changeable) |
| 0.28.2 | **Scan-only scope.** *Require scanning for serial numbers* now applies only to **selling** and **returns**, not exchanges — in an exchange the cashier may type the damaged item's serial, which must still **match one sold on the original invoice** (enforced client- and server-side). |
| 0.28.1 | **Clearer offer suggestions.** The "Add X — get free" promotion suggestion chips (cart line + basket) now have a proper tinted background and border, and a **lighter purple on a stronger tint in dark mode**, so they're legible instead of faint purple-on-dark. |
| 0.28.0 | **Return sets together · serial scan-only.** Items sold together — a **bundle** or a **Buy X Get Y** offer — must now be **returned as a whole on a regular return** (all members, full quantity, or none); the refund screen marks them with a *Set — return together* badge and steps the whole set at once, and the server enforces it. **Exchanges are exempt** (you can still swap one item of a set). Each line carries a `lumenpos_return_group` stamped at sale time. New setting **Require scanning for serial numbers** (Settings → General, default off): when on, serials must be **scanned** with a barcode scanner when **selling** and on **returns** — manual typing is blocked. **Exchanges are exempt** (the damaged serial just has to match one on the original invoice). |
| 0.27.0 | **Bundle expiry · expired badges · exchange warranty from original · sale note.** Bundles now have **Valid From / Valid To** dates — past Valid To a bundle stops being offered at the till (like a promotion's end date). Promotions, bundles and price books show an **Expired** badge in their Settings list when past their end/valid-to date. Warranty **exchanges now count the replacement's warranty from the ORIGINAL purchase date** (chained across repeat exchanges via a new `lumenpos_warranty_start_date`), so a replacement carries only the remaining term, not a fresh one. The cart has a **note field** (flows to the invoice `remarks`). |
| 0.26.2 | **Approval requests fix.** Pending requests weren't reaching the Approvals tray because the list was **scoped to the approver's own POS profile** — now an approver sees **every open-shift request** regardless of which till/profile raised it. A **manager** may now approve their **own** request (manager override; also lets a single owner test the flow) — role-only approvers still can't (separation of duties). The over-limit prompt now commits the typed discount immediately (`@input`), so it triggers reliably instead of intermittently. Approvals badge polls every 10s (was 20s). |
| 0.26.1 | `exchange_against_invoice` already exists on POS Invoice (a site field), so LumenPOS no longer creates it — it just writes the original invoice to the existing field on both exchange legs. |
| 0.26.0 | **Exchange traceability + cash movements on the Z-report.** Both legs of a warranty exchange (the credit note and the replacement sale) are now stamped with **`exchange_against_invoice`** = the original invoice, so an exchange always traces back to its source (written to the site's existing `exchange_against_invoice` field). And drawer **cash in / out** is now **declared on the POS Closing Entry** — a Cash In / Cash Out total plus a Cash Movements table beside the payment reconciliation — in addition to being netted into the expected cash (the netting already existed; this makes the movements visible/auditable on the official close). |
| 0.25.0 | **Customers screen (client lookup).** New **Customers** tab: search clients by name / phone / code / email / tax ID, filter by customer group, and open any client to see their profile, balances (loyalty + store credit), lifetime stats and full **POS transactions** (filter by type + date range, click to view/print). Built performance-first — server-paginated, indexed lookups, per-customer totals computed only on open, and no background work — so it doesn't touch the till. Hidden unless the user has **Customer → read**. |
| 0.24.0 | **Return window + generalised approval requests.** Regular returns can be limited to a **time window** (Settings → General → Returns → *Limit regular returns to a time window* + **Return window (days)**, default 14, 0 = no limit). Past the window the till blocks the refund and the cashier sends a **return approval request** that an **Approver Role** holder clears from the **Approvals** tray while the register is open — single-use, tied to the invoice, server-enforced. The approval request system from 0.23.0 was generalised: one **POS Approval Request** doctype with a **request type** (Discount or Return), and the approver role setting is now shared by both (renamed *Approver Role*). |
| 0.23.0 | **Discount approval as a role-based request (not just a passcode).** Settings → General → *Discount approval* now has an **over-limit approval method**: *Passcode only* (today's behaviour), *Request only*, or *Passcode or request*. With requests on, a cashier hitting the limit taps **Send approval request** and the till waits; a holder of the configured **Approver Role** (plus LumenPOS/System Managers) sees a live **Approvals** tray in the left rail (with a count badge) and **Approves/Rejects** it. Requests are tied to the **open register session**, are **single-use**, and **expire when the register closes** — and approvals are re-checked server-side, so the limit can't be bypassed from the client. (The audit doctype shipped as **POS Approval Request** — see 0.24.0.) |
| 0.22.0 | **Out-of-stock hiding · serial re-scan on returns · exchange from the invoice.** The sell grid now **hides out-of-stock items** by default (toggle *Show out-of-stock items* in Settings → General; non-stock items always show). On returns **and** exchanges, serialized items must be **scanned/typed** (validated against the sold serials) instead of tapped from a list — so the cashier verifies the actual unit. The **Exchange** action moved off the cart to **History → open the invoice → Exchange** (beside Refund), launching the exchange pre-loaded with that sale. |
| 0.21.1 | **Real payment method in history + clearer tags.** Sales/returns/exchanges now store only the **tenders actually used** — ERPNext pre-fills a zero row for every payment method on the profile, which made the invoice (and history) list all eleven; LumenPOS now drops the unused zero rows on save, and history only shows/filters non-zero tenders (fixes existing invoices too). The REFUND / EXCHANGE / channel tags are now legible in **dark mode** (brighter text on stronger tints). |
| 0.21.0 | **Settings redesign (same features, calmer layout).** The whole settings page was reorganised: a segmented tab bar; Promotions / Bundles / Price books are now **list → editor** (searchable cards that open a focused editor); each editor is split into clean **section cards** (Basics · Offer · Products · When & where · Coupons) with a **type-aware Offer** (only the fields for the chosen promo type show), compact day/outlet pickers, and a sticky Save/Cancel/Delete footer. General / Loyalty / Channels became tidy two-column cards; Status shows metric cards. No behaviour change — every field, toggle and tool is the same, just easier to scan. The Offer also now exposes the engine's **Amount** discount type. |
| 0.20.0 | **Payment method in history + coupon polish.** Sales history rows now show the **payment method(s)** next to the total, and a **Payment method filter** lets you list invoices by tender. Coupons: fixed the stats line showing a literal `{redemptions}`, and clarified that the single **shared code is optional** (no limit — always works) while generated/imported codes are unique and limited; when the pool runs out only the shared code keeps working (or none, if left empty). |
| 0.19.0 | **Coupon use limit + bulk price-book discount.** Coupons now have a **use limit** — how many times each code may be redeemed (1 = single use, 0 = unlimited), set per batch and counted as they're spent (replaces the single-use checkbox; the desk shows Times Used / Fully Used). Price books get **"Discount all prices by X%"** with a rounding choice (none / 0.05 / 0.25 / 0.50 / 1 / 5) to reprice every item in the book at once. |
| 0.18.0 | **Bulk coupons.** A coupon-locked promotion can now have a whole **pool of codes**, not just one: **Generate** N unique random codes (optional prefix) or **Import** an Excel/CSV list, choosing **single-use** (spent after one redemption) or **reusable** (until an optional expiry) per batch. Codes unlock the promotion at the till exactly like the single code; single-use ones are marked spent on the sale. **Export codes** downloads the batch as CSV (to print/distribute), and **Delete unused** clears a batch. New `POS Coupon` doctype. |
| 0.17.0 | **Tags in promotions + bulk price-book add.** Promotions can now target a product **Tag** (ERPNext item tags) alongside Item / Item Group / Brand — handy when items span many groups/brands; the tag flows through both the live cart and the server engine (parity-tested). Price books gain **"Add all by" brand / item group / tag** — one click pulls every matching sellable item (each defaulted to its current selling price, so nothing accidentally sells at 0) ready for you to discount. |
| 0.16.0 | **Sales history clarity + default exchange item.** History rows now show the **cashier who made the sale**, a clean timestamp (no microseconds), and an **EXCHANGE** badge so warranty swaps are obvious at a glance (alongside REFUND). On the Exchange screen, ticking a damaged item now **auto-adds a replacement of the same item at the original price** (a net-zero warranty swap) — the cashier can change the item, qty or price, or delete it. (Also removed the temporary refund diagnostic now that refunds post correctly.) |
| 0.15.7 | **Exchange invoice search is fast again** — the lookup was doing a full document load (plus per-serial queries) for every candidate sale, i.e. dozens of round-trips. Rewritten to a handful of batched queries (items, prior returns, warranty, serials fetched once for all candidates) — no per-invoice `get_doc`. The exchange still re-validates returnable quantities authoritatively when you confirm, so the faster preview is safe |
| 0.15.6 | **Refund rejection — actually fixed (root cause).** Diagnostics revealed the credit note's `paid_amount` field held the *original sale's full paid amount* (e.g. −274.50), because `make_return_doc` copies it and `calculate_taxes_and_totals` doesn't recompute it for returns — so it never matched the refund's payment rows (−137.24), tripping "Paid amount … greater than Grand Total". LumenPOS now forces `paid_amount`/`base_paid_amount` to equal the actual refund rows on returns and exchange credit notes. (0.15.1/0.15.3 had targeted the wrong variable.) |
| 0.15.5 | **Refund diagnostic** — if a refund still fails, the error now reports the running version and the exact `paid / grand_total / rounded_total / write_off / payments` figures (also written to Error Log) so the cause can be read, not guessed. Temporary instrumentation, removed once the refund is confirmed working |
| 0.15.4 | **No more phantom "change" on the till** — the payment screen now pulls the exact payable from the server (new `quote_sale`, the same pricing path as the real sale) before you collect, so a card payment equals the posted invoice to the cent. Previously a VAT-inclusive promo line could round a couple of halalas differently on the till vs the invoice, leaving a stray SAR 0.02 "change". Cash can still over-tender for real change. `submit_sale` and the quote now share one builder so they can never drift |
| 0.15.3 | **Rounding fix, done right** — the v0.15.1 attempt relied on `disable_rounded_total`, which POS Invoice doesn't have, so refunds of tax-inclusive items still failed with *"Paid amount … greater than Grand Total"*. ERPNext validates a return's payment against `rounded_total or grand_total`; LumenPOS now refunds **exactly** that figure (and forces `write_off_amount = 0`) on returns and both exchange documents, so the difference is always zero regardless of how rounding is configured |
| 0.15.2 | **Refund consolidated sales from the till** — a sale whose shift already closed (merged into a Sales Invoice) is no longer blocked from the POS refund/exchange screen. LumenPOS posts the credit note against the original POS sale tied to the **current** open shift (refund from the current drawer); ERPNext merges it into a consolidated credit note at the next close — no ERPNext-desk trip for everyday post-close returns. Refund each sale through one channel only |
| 0.15.1 | **Refund & exchange fixes** — (1) returns/exchanges no longer fail with *"Paid amount … greater than Grand Total"*: the credit note now disables the rounded-total adjustment and pays the grand total to the cent, so a tax-inclusive half-cent can't break it. (2) Warranty exchanges no longer fail with *"Is Exchange … should be one of Yes, No"*: LumenPOS now writes boolean flags (is_exchange, pick_customer) in the form the site's field expects — `1` for a Check, `Yes`/`No` for a Yes/No Select — and reads them back either way (EXCHANGE receipt stamp still shows) |
| 0.15.0 | **Arabic / full RTL** — a one-tap language switch in the top bar flips the entire interface between English and Arabic, including right-to-left layout, and translates every label, button, toast and tooltip across the till, register, history and settings. **Master data is never translated** (item/customer names, codes, barcodes stay as entered). Language is remembered per device and defaults to the browser language. Built on a lightweight in-app i18n layer (no desk-language dependency) |
| 0.14.0 | **Return reasons** — refunds now require a reason picked from a configurable list (**Settings → General → Return reasons**, add/remove freely) or a free-text **Other**; it's stored on the credit note (*Return Reason* field). Warranty **exchanges default to "استبدال ضمان"** (changeable). **Start a new shift after a failed close** — if a close keeps *Failing* (e.g. overnight), a manager can open a fresh shift anyway while the failed one keeps retrying in the background, so the till is never stuck shut. Also fixes a latent bug where a retry/closing control response could momentarily flip the register to "open" |
| 0.13.0 | **Price books reworked to plain item overrides** — a price book is now just a list of items with a special price (added manually or by Excel/CSV) that applies for a period by priority/outlet/customer group. It **no longer creates or uses an ERPNext Price List** and never touches Standard Selling; reopening a book shows its items. Existing dedicated-list books are migrated automatically |
| 0.12.0 | **Promotions can be calculated on the standard price or the price-book price** — a new per-promotion "Calculate discount on" option. "Standard Price" gives the customer the lower of the price-book price or (standard − promo), never stacking with the book and using the highest-priority active book; "Price Book Price" (default) keeps stacking. Plumbed through both the live cart and the server engine (parity-tested) |
| 0.11.9 | **Price books can no longer touch base selling lists** — Standard Selling and outlet selling lists are blocked from price-book/app editing (server + UI) so setting a "book price" can never overwrite real master prices; the book editor now **shows the book's own items on open** (loads the dedicated list, not the whole catalogue), and base lists are hidden from the price-list picker |
| 0.11.8 | **Gift card accounting is mappable** (Settings → General → Gift cards): choose the mode of payment, liability account and item, or leave blank to auto-create defaults. **Exchange price override** — replacement lines have an editable unit price and a one-tap "Give as even swap" that waives the difference (give a pricier item at the same price) |
| 0.11.7 | **Exchange fixes** — auto-provisioned clearing modes of payment (Exchange Credit, Store Credit, Gift Card) now fill any **mandatory custom fields a site adds to Mode of Payment / Item** (e.g. an Arabic name), so completing an exchange/sale no longer fails with "Value missing for Mode of Payment"; the exchange **invoice search is much faster** (single combined query, mobile lookup via the customer table, no double doc-load, and the UI waits for 3+ characters) |
| 0.11.6 | A new **price book now gets its own dedicated price list** (auto-created on save, named after the book) instead of defaulting to Standard Selling — so overrides never touch the master list, and the editor genuinely starts empty (only items you add/import belong to the book) |
| 0.11.5 | Sales history gains an **Online order** filter (online only / in-store only) reading the site's `online_order` field; rows show an ONLINE badge |
| 0.11.4 | Fixed the price-book **Import/Export buttons** rendering their icon markup as literal text (the v0.11.2 icon swap had injected it inside a text expression); the price editor now **starts empty** instead of auto-loading the whole price list — search / add / import to populate it |
| 0.11.3 | **Payment tiles show real scheme logos** — Visa, Mastercard, mada, American Express, Tamara, Tabby, STC Pay and Apple Pay are detected from the Mode of Payment name and rendered as their brand mark on a white chip (via the new `PaymentBrand` component); other methods keep a generic line icon |
| 0.11.2 | **Emojis replaced with professional line icons** — a new `Icon` component (same SVG line style as the nav rail, themed to the brand colour) replaces every emoji/pictograph across the till (gift, delivery, warranty shield, coupon, walk-in, customer type, payment-method, exchange, refresh, import/export, barcode, loyalty star, etc.). Standard status marks (✓ ✗ ⚠) and prose arrows are kept as typography |
| 0.11.1 | **No green anywhere** — the legacy `--green`/`--teal` CSS tokens and `btn-green` class are renamed to brand tokens (`--brand` `#2E5BFF`, `--brand-dark`, `--brand-soft`, `.btn-primary`) across the whole frontend, so every primary action (Open Register, Retry closing, Continue shift, Pay, Save, etc.) is brand blue with no green identifier left to regress |
| 0.11.0 | **Role-based permissions** — every tab, action and the Pay button is governed by standard ERPNext DocType permissions (Role Permissions Manager); ships **LumenPOS Cashier / LumenPOS Manager** roles and a POS-access gate (no POS Invoice read = no entry). **Robust register closing** — a strict Open→Closing→Closed state machine: a closed shift can never be sold-on or resumed even if consolidation is slow or fails; consolidation is serialized cluster-wide (no concurrent-close deadlocks), runs synchronously under our control, is fully retryable, and a scheduled **self-healer** re-drives any stuck shift. A sell-time row lock stops a sale landing on a shift mid-close, so no invoice is ever left un-consolidated; cashiers can only close/alter **their own** till. **Refund method rules** — refunds are restricted to the tender the customer paid with (configurable per method, e.g. paid Mada → refund Mada or Cash). Cleaner **General settings** layout |
