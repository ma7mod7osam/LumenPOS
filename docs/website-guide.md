# LumenPOS Documentation

A fast, single-screen point of sale for ERPNext / Frappe v15. This guide covers everything from installing the app to running a busy shift — written for shop owners, managers and the ERPNext admin setting it up.

> **In a hurry?** Install the app → open a POS Profile and add your cashier → go to `https://your-site/pos` → enter an opening float → start selling.

---

## Contents

1. [What LumenPOS is](#what-lumenpos-is)
2. [Requirements](#requirements)
3. [Installing](#installing)
4. [First-time setup](#first-time-setup)
5. [Making a sale](#making-a-sale)
6. [Customers](#customers)
7. [Discounts and promotions](#discounts-and-promotions)
8. [Taking payment](#taking-payment)
9. [The register (opening and closing the till)](#the-register)
10. [Returns and refunds](#returns-and-refunds)
11. [Gift cards, store credit and loyalty](#gift-cards-store-credit-and-loyalty)
12. [Receipts and printing](#receipts-and-printing)
13. [Working offline](#working-offline)
14. [Serial numbers](#serial-numbers)
15. [Multi-company and invoice modes](#multi-company-and-invoice-modes)
16. [Permissions and the audit log](#permissions-and-the-audit-log)
17. [Language](#language)
18. [Troubleshooting and FAQ](#troubleshooting-and-faq)
19. [Support](#support)

---

## What LumenPOS is

LumenPOS is a retail till that runs on top of ERPNext. It gives your cashiers a quick, modern selling screen — search or scan, tap to add, take payment, print — while every sale posts as a normal ERPNext invoice with the right stock and accounting behind it. Nothing is kept in a side system: your inventory, customers, and books stay in ERPNext.

It's designed for real counters, so it also handles the things a shop needs day to day: its own promotions, gift cards, store credit, loyalty points, returns, cash-drawer reconciliation, and selling while the internet is down.

---

## Requirements

- **Frappe / ERPNext v15**
- A configured **POS Profile** — company, selling price list, warehouse, and payment methods
- Your cashier's user added to that POS Profile (under *Applicable for Users*)

That's it. The front end is pre-built and shipped with the app, so you don't need Node.js or a build step to install it.

---

## Installing

### On Frappe Cloud (marketplace)

Install LumenPOS onto your site from the Frappe Marketplace, then let the site finish updating. When it's done, open `https://your-site/pos`.

### On a self-hosted bench

```bash
cd frappe-bench
bench get-app https://github.com/ma7mod7osam/LumenPOS
bench --site your-site install-app lumenpos
bench --site your-site clear-cache
```

Then open `https://your-site/pos`.

> **Developers:** if you change anything under `frontend/src`, rebuild and commit the assets:
> ```bash
> cd frontend && npm install && npm run build
> ```

---

## First-time setup

**1. Create (or open) a POS Profile.** In ERPNext, go to *POS Profile* and make sure it has:

- a **Company**
- a **Selling Price List**
- a **Warehouse** that belongs to that company
- the **payment methods** you accept (Cash, Mada, Credit Card, etc.)
- your cashier under **Applicable for Users**

**2. Set a default customer** on the POS Profile (for example, "Walk-in Customer"). This is what a sale is billed to when no specific customer is chosen — and in Sales-Invoice mode a customer is required, so don't skip it.

**3. Open the POS.** Go to `https://your-site/pos`. The first time you open it online, LumenPOS quietly caches your catalogue so search is instant and offline selling works later.

**4. Adjust settings (optional).** Open **Settings** inside the POS to configure promotions, price books, receipt design, gift cards, permissions and more. Store-level things like price list, warehouse, taxes and payment methods stay on the POS Profile in ERPNext — that remains the single source of truth.

---

## Making a sale

The sell screen is one page:

- **Find products** by typing in the search box or scanning a barcode. Scanning a barcode adds the item straight to the cart.
- **The cart** shows each line, quantity and price, with a badge when a promotion is applied.
- **Change quantities** or remove lines directly in the cart.
- **Park a sale** to set it aside (a customer forgot their wallet, say) and **Retrieve** it later from the top bar.
- **Discard** clears the cart.

When you're ready, press **Pay** to go to the payment screen.

Prices and promotions are always worked out on the server when the sale is submitted, so the amount you charge is exactly what the posted invoice shows — no rounding surprises.

---

## Customers

- **Add a customer** with the "+ Add a customer" button — search existing customers by name, mobile or tax ID, or create a new one on the spot.
- Create either an **individual** or a **company** customer; company records can carry a tax ID and address for the receipt.
- Picking a customer can activate a **customer-group price book**, so their pricing updates automatically.

If you create a customer while offline, LumenPOS saves them locally and reconciles on reconnect — matching an existing record by mobile number if one already exists, so you don't end up with duplicates.

---

## Discounts and promotions

LumenPOS has its own promotions engine, so you don't have to wrangle ERPNext Pricing Rules at the till. Create promotions in the desk under **POS Promotion → New**.

> **LumenPOS pricing vs ERPNext Pricing Rules.** LumenPOS owns pricing at the point of sale. Its **price books, promotions and bundles** are always the source of truth, and it **automatically ignores ERPNext Pricing Rules on every POS sale** — so the price the till shows always matches the posted invoice, and there's nothing to enable or disable. (You may see an *Ignore Pricing Rule* option in ERPNext; LumenPOS already applies it for you at the POS.) Your existing Pricing Rules keep working on non-POS documents such as Sales Orders and regular Sales Invoices.

| Type | What it does | Key fields |
|---|---|---|
| **Simple Discount** | A percentage or fixed amount off matching products | Discount type, value |
| **Buy X Get Y** | Multi-buy offers (e.g. buy 2 get 1 free); the cheapest qualifying unit is the one discounted | Buy qty, get qty, reward, max applications |
| **Spend & Save** | A basket-level discount once the cart passes a threshold | Minimum spend, basket discount |
| **Bundle Price** | Sells listed products together for one fixed price; the bundle's items appear as separate lines on the invoice | Products, quantities, bundle price |

**Targeting.** A promotion can match by **item**, **item group** or **brand**, or apply to everything. Limit it to certain **outlets** (POS Profiles) and **customer groups**.

**Scheduling.** Run a promotion within a date range, on specific days of the week, and even within a daily time window (happy hour).

**Coupon codes.** Turn on *Requires Coupon Code* to gate a promotion behind a code the cashier enters at the till. Codes are unique across active promotions.

**Stacking.** Promotions marked *Can combine* stack with each other. Non-stackable ones compete, and the customer automatically gets whichever is worth more. A discount never exceeds the line or basket total.

**Nudges.** When a cart is one item short of a Buy X Get Y, or just under a Spend & Save threshold, the screen suggests the customer add a little more to unlock the deal.

---

## Taking payment

On the payment screen:

- Choose a tender — **Cash**, card (Mada, Credit Card), **Gift Card**, or **Store Credit**.
- **Split payments** across several methods; quick-cash buttons speed up cash entry.
- **Change due** is shown for cash over-tender.
- Redeem **loyalty points** or **store credit** if the customer has a balance.

Press **Complete Sale** to post the invoice. If the sale can't post for any reason, nothing is half-saved — your cart and entered payments stay on screen so you can fix the issue and try again.

---

## The register

LumenPOS treats each shift as a register session so the cash drawer always balances.

- **Open the register** at the start of a shift and enter the **opening float** (the cash you start with).
- **Cash in / cash out** records money added to or taken from the drawer during the shift.
- **X-report** — a mid-shift read of sales and expected takings, available any time from the top bar. It does **not** close the drawer or post anything.
- **Close the register** at the end of the shift: count the drawer (a blind count, so the expected figure doesn't bias it), and LumenPOS compares counted vs expected per payment method and produces a **Z-report**.

In the standard POS-Invoice mode, closing consolidates the shift's sales the way ERPNext expects.

---

## Returns and refunds

- Open **History**, find the sale, and choose **Refund**.
- Refund the whole sale or selected lines.
- Send the refund back to any **payment method** or to **store credit**.
- The refund posts as a proper credit-note invoice, linked to the register session, so the drawer count stays correct.

Who is allowed to process a return — and who can approve one past the return window — is controlled in Permissions (below).

---

## Gift cards, store credit and loyalty

**Gift cards.** Sell a gift card as a normal sale (it posts to a gift-card liability account, with no tax until the card is spent), then redeem it later as a payment method. Balances and history are tracked per card.

**Store credit.** Each customer can hold a store-credit balance, backed by a liability account. It appears as a "Store Credit" payment method and can be topped up by refunds.

**Loyalty.** LumenPOS uses ERPNext's native Loyalty Program. Assign a program to your customers (directly or via customer group); points are earned automatically on sales, and the customer can redeem them at the payment screen.

> **Setup tip:** to switch loyalty on, create a Loyalty Program in ERPNext and assign it to customers. To use store credit, just take it as payment — the account and payment method are created on first use.

---

## Receipts and printing

You have three ways to print, and LumenPOS picks the best available automatically:

1. **Thermal printer (ESC/POS).** Configure a printer IP and port on the POS Profile. The Frappe server prints to it directly and can kick the cash drawer. (On cloud-hosted sites the printer needs to be reachable from the server; otherwise LumenPOS falls back to browser printing.)
2. **Your own ERPNext Print Format.** Set a Print Format on the POS Profile and it takes over — full control over layout, bilingual receipts, QR blocks, anything a Print Format can do.
3. **The built-in receipt designer.** In **Settings → Receipt**, choose a template (Compact, Standard, Detailed), pick what to show (item code, barcode, serial number, unit price, payment methods, note, tax ID, address, terms), and add a logo, header and footer. A live preview shows your changes as you make them.

---

## Working offline

LumenPOS is built to keep selling through a network outage.

- **Products, prices and promotions** are cached on the device the first time you open the POS online, and refreshed in the background.
- If the connection drops, the till keeps working. **Sales are queued locally** and upload automatically when you're back online. Queued writes carry a safety key so a lost confirmation can never post a sale twice.
- **The offline sales log** (open it from the Offline / Syncing pill in the top bar, or Settings → Status) shows every offline sale and its status: **Pending** (queued), **Uploaded** (posted, with the real invoice number), or **Needs attention** (the server rejected it, with the reason). Nothing is removed until the server confirms it.

**Good to know:**

- **Keep the tab open during an outage.** The app is served by your ERPNext site, so refreshing or navigating away while fully offline can't reload it. Any queued sales are still safe. (Full offline reload is on the roadmap.)
- A few things need a connection and can't be queued: serialised items, delivery-app sales, gift-card and loyalty redemption, and store-credit payments.
- Named customers with a customer-group price book keep their shelf price offline; the correct price is re-resolved when the sale syncs.

---

## Serial numbers

For serialised products, LumenPOS enforces scanning so the right unit is sold:

- A serialised item **won't enter the cart** until you scan or type a serial number.
- The serial must **exist**, be **Active**, and belong to **this register's warehouse**.
- Quantity is locked to the number of serials scanned — there's no automatic FIFO pick.
- Serialised items can't be sold offline (the serial has to be validated live).

---

## Multi-company and invoice modes

**Multi-company.** If your site runs several companies, LumenPOS scopes accounts per company, so a sale never posts to another company's ledger. Set per-company accounts under **Settings → Company Accounts**.

**Invoice mode.** Choose per POS Profile how sales post:

- **POS Invoice** (default) — sales post as POS Invoices and consolidate the ERPNext way at register close.
- **Sales Invoice** — sales post directly as Sales Invoices. Useful when your accounting prefers Sales Invoices; you can still run opening/closing entries for cash control.

Both modes move stock, post to the ledger, and appear in reports exactly as ERPNext expects. The promotions applied to each sale are stored on the invoice for auditing.

---

## Permissions and the audit log

Under **Settings → Permissions**, decide which roles can:

- **edit a price / apply a discount** at the till,
- **process a return**, and
- **approve a return beyond the return window** (with a manager passcode).

Sensitive actions — over-limit discounts, returns, register open/close, settings changes, receipt emails — are written to a **LumenPOS Audit Log** you can review in the desk.

There's also an optional **till lock**: a PIN lock screen that can lock the register manually or after a period of inactivity, so an unattended till is protected.

---

## Language

LumenPOS is bilingual — **English and Arabic**, with full right-to-left layout. Switch language from the top bar. New installs follow your ERPNext desk theme (light/dark) until you override it.

---

## Troubleshooting and FAQ

**A sale showed an error and didn't complete — did I lose it?**
No. If a sale can't post, the whole thing is rolled back — there's no half-made invoice to clean up (any invoice number you saw in the error is just a skipped number, which is normal). Your cart and payments stay on screen; fix the cause and press Complete Sale again. If the fix needs an app update, park the sale and complete it afterwards.

**How do I correct a sale that already posted?**
Submitted invoices can't be edited (that's an accounting rule). Refund/return the sale to reverse it, then ring the correct one — or, in the desk, cancel and amend the invoice. During a shift, the refund route keeps your drawer count consistent.

**The receipt isn't using my custom layout.**
Set your Print Format on the **POS Profile**. When one is set, it takes over printing and the built-in designer only styles the on-screen receipt. (A configured thermal printer uses its own fixed layout.)

**Selling a gift card or paying with one fails on a multi-company site.**
Make sure the company has its own warehouse and gift-card/liability accounts. LumenPOS auto-creates sensible defaults, but a valid warehouse for the company must exist. Keep the app up to date — multi-company handling improves with releases.

**Nothing loads / search is empty.**
Open the POS online at least once so the catalogue can cache. Then use **Settings → Status → Refresh offline catalog** to rebuild the cache.

**Do I need to turn off ERPNext Pricing Rules to use promotions, bundles or price books?**
No. LumenPOS ignores ERPNext Pricing Rules automatically on every POS sale, so its price books, promotions and bundles always take precedence at the till — there's nothing to switch on or off. Your Pricing Rules keep working on non-POS documents.

**Where do I change the price list, taxes or payment methods?**
On the **POS Profile** in ERPNext — that's the source of truth. The in-POS Settings page covers promotions, price books, receipts, permissions and the like.

---

## Support

- **Email:** support@lumen-solutions.co
- **Website:** https://lumen-solutions.co

Please include your ERPNext version and, if you hit an error, the message shown at the till — it makes fixing things much faster.

---

*LumenPOS is built by Lumen Solutions and improves regularly. This document reflects the current release.*
