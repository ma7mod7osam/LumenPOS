# LumenPOS — a professional Point of Sale for ERPNext / Frappe

> 📘 **[Full user guide & documentation → docs/user-guide.md](docs/user-guide.md)**
> (setup, every feature in detail, settings reference, troubleshooting, changelog —
> kept up to date with every release)

A Frappe app that gives ERPNext a point of sale modeled on **Vend (Lightspeed
X-Series)**: the same sell-screen experience and a Vend-style **promotions
schema** that replaces ERPNext Pricing Rules at the POS.

Since v0.4 sales post as **POS Invoices** with native **POS Opening/Closing
Entries**, so ERPNext consolidates them into Sales Invoices at register close
exactly like the standard POS. v0.4 also adds: **price books** (Vend-style
customer-group/outlet price lists), **delivery-app channels**
(`custom_app_type` + mandatory order ID + per-app price list), an exchange
flag, an **in-POS Settings page** (promotions, price books, channels,
discount approval — Vend Setup style), **manager-passcode discount approval**,
Individual/Company customer creation (tax ID + national address for
companies), salesperson search by name or number, a **local-first catalog**
(IndexedDB-served search, near-instant), and a **LumenPOS workspace** in the
ERPNext desk. Brand accent color: `#2E5BFF`.

- Sell screen at **`/pos`**: product grid + search/barcode, cart with live
  promotion badges, customer lookup/create, park & retrieve sales, split
  payments with quick-cash buttons, change due, printable receipt,
  salesperson attribution (posted to the invoice Sales Team for commission
  reports), and an out-of-stock guard.
- **Promotions engine**: Simple Discount, Buy X Get Y (multi-buy, cheapest
  unit rewarded), Spend & Save, and **Bundle Price** (these N products
  together for a fixed total — items stay separate invoice lines, the saving
  is split cent-correctly across them) — scheduled by date range, days of
  week and daily time windows (happy hour, wraps midnight), scoped by outlet
  and customer group, with stacking control and optional **coupon codes**
  (coupon-locked promotions never reach the browser until the right code is
  entered). Evaluated instantly client-side, re-evaluated **authoritatively
  server-side** on submit (`ignore_pricing_rule` is set, so ERPNext Pricing
  Rules never interfere).
- **Smart offer nudges**: when the cart almost qualifies — has the "buy"
  items of a Buy X Get Y, misses one bundle component, or sits near a
  spend-and-save threshold — the cart shows a suggestion the cashier can
  tap to pull up the missing product.
- **Register sessions**: opening float, cash in/out, blind-countable closing
  counts per payment mode with expected vs counted differences (Z-report data
  stored on the `POS Register Session` doc).
- **Returns & refunds**: open any sale from History → Refund, pick lines and
  quantities (partial returns tracked), refund to any payment mode or to
  store credit. Posts a proper credit-note Sales Invoice linked to the
  register session, so the drawer count stays right.
- **Loyalty & store credit**: earn/redeem via ERPNext's native Loyalty
  Program; store credit is a per-customer ledger backed by an auto-created
  liability account and a "Store Credit" mode of payment. Balances show in
  the cart and the payment screen.
- **Offline mode**: the catalog, promotions and bootstrap are cached in
  IndexedDB. If the connection drops, search keeps working and sales are
  queued locally, then synced automatically when the network returns.
- **ESC/POS printing**: receipts print to network thermal printers (RAW TCP
  9100, Epson-compatible) configured per POS Profile, with cash-drawer kick;
  falls back to browser printing when no printer is configured.
- **Strict serial numbers**: a serialized item cannot enter the cart without
  scanning/typing its serial — validated live (exists, Active, in this
  register's warehouse) and re-validated on submit; no FIFO auto-pick.
  Quantity is locked to the scanned serial count, scanning a serial in the
  search bar adds its item directly, and refunds require selecting exactly
  which sold serials are coming back. Serialized items can't be sold offline.
- Sales post as standard **Sales Invoices** (`is_pos = 1`) so stock, GL and
  reports work exactly as ERPNext expects. Applied promotions are stored on
  the invoice (`lumenpos_promotions`) for auditing.

## Requirements

- Frappe / ERPNext **v15**
- A configured **POS Profile** (company, selling price list, warehouse,
  payment methods; add your cashier under *Applicable for Users*)

## Install

The frontend ships pre-built (`lumenpos/public/pos`), so the bench does **not**
need Node or npm:

```bash
cd frappe-bench
bench get-app https://github.com/ma7mod7osam/lumenpos
bench --site yoursite install-app lumenpos
bench --site yoursite clear-cache
```

If you change anything under `frontend/src`, rebuild and commit the assets:
`cd frontend && npm install && npm run build`.

Open **`https://yoursite/pos`**, enter an opening float, and sell.

## Creating promotions

Desk → **POS Promotion** → New.

| Type | What it does | Key fields |
|---|---|---|
| Simple Discount | % / amount off, or a fixed price, on matching products | Discount Type, Discount Value |
| Buy X Get Y | Multi-buy. "Buy" rows trigger, "Get" rows are rewarded (cheapest units first). No "Get" rows = classic *buy 2 get 1 free* on the same pool | Buy Qty, Get Qty, Reward, Max Applications |
| Spend and Save | Basket-level discount once eligible spend crosses a threshold | Minimum Spend, Basket Discount |
| Bundle Price | The listed products bought together (Qty column per row) for a fixed total; items stay separate lines on the invoice | Products + Qty, Bundle Price |

Tick **Requires Coupon Code** on any promotion to gate it behind a code the
cashier enters at the till. Codes are unique across active promotions and
are never shipped to the browser.

Products match by **Item, Item Group, or Brand** (or *Apply on all products*).
Eligibility: outlets (POS Profiles) and customer groups. Scheduling: date
range, days of week, and an optional daily time window.

**Stacking rule:** promotions marked *Can combine* stack with each other;
non-stackable promotions compete and the customer automatically gets whichever
is worth more — the combined stack or the single best exclusive promotion.
Discounts never exceed the line/basket total.

## Architecture

```
lumenpos/
├── lumenpos/
│   ├── promotions/
│   │   ├── engine.py        # pure evaluation engine (no Frappe imports)
│   │   ├── loader.py        # POS Promotion -> engine dicts
│   │   └── test_engine.py   # standalone unit tests
│   ├── api/                 # whitelisted endpoints (session, catalog, sales, register)
│   ├── lumenpos/doctype/        # POS Promotion (+children), POS Register Session, POS Parked Sale
│   └── www/pos.html         # serves the built SPA at /pos
└── frontend/                # Vue 3 + Vite + Pinia
    └── src/promotions.js    # JS mirror of engine.py (instant cart feedback)
```

The promotion engine exists twice **by design**: the JS copy gives the cart
instant feedback; the Python copy recomputes everything on submit and is the
only one that is trusted. `frontend/parity-check.mjs` runs the same scenarios
through the JS engine that `test_engine.py` covers in Python:

```bash
python -m unittest lumenpos.promotions.test_engine   # from the app root
node parity-check.mjs                            # from frontend/
```

## Development

```bash
cd frontend
npm run dev    # Vite dev server on :8080, proxies /api to a bench on :8000
```

## Feature setup notes

- **Loyalty**: create a Loyalty Program in ERPNext and assign it to customers
  (or via customer group); earning happens automatically on POS sales,
  redemption appears in the payment screen when the customer has points.
- **Store credit**: nothing to configure — the "Store Credit" mode of payment
  and its liability account are created on first use.
- **Printer**: on the POS Profile set *Printer IP* (and port, default 9100).
  The Frappe server opens the socket, so the printer must be reachable from
  the server — on cloud-hosted sites use the browser-print fallback.
- **Offline**: the catalog caches automatically after the first online load.
  The register must be opened while online; loyalty/store credit and history
  need a connection. Queued sales sync as soon as the network returns.
  **Keep the tab open while offline** — the page itself is served by the
  server, so a refresh or navigation during an outage cannot reload the app
  (a service worker for full offline boot is on the roadmap).

## Not yet included (roadmap)

- Quick Keys (customizable tile layouts)
- Sale-level manual discount and per-line price override
- Promo codes (coupon-gated promotions)
- Gift cards, customer-facing display, email receipts
