# LumenPOS — Frappe Marketplace listing copy

Paste-ready text for the marketplace **App Profile** form, plus notes for each field.

---

## Title

```
LumenPOS
```

## Summary (short description)

```
A fast, single-screen point of sale for ERPNext — with its own promotions engine, offline selling, gift cards, store credit and loyalty built in.
```

## Description (long)

> Paste everything between the lines into the **Description** box. It's plain Markdown.

---

# LumenPOS

A point of sale for ERPNext that feels like it was built for the counter, not the back office.

If you run ERPNext and you've ever watched a cashier fight with the stock POS during a queue, this is the fix. LumenPOS is one fast screen: search or scan, tap to add, take the payment, print, next customer. No page reloads, no digging through menus, no waiting on the network between keystrokes.

And it's not a separate silo. Every sale posts straight into ERPNext — real invoices, real stock movements, real ledger entries — so your accounts stay exactly where they belong. LumenPOS just makes the selling part quick and pleasant.

## Built for the way shops actually sell

**Promotions that make sense.** LumenPOS brings its own promotions engine, so you're not bending ERPNext Pricing Rules to fit a shop counter. Set up a straight discount, a Buy X Get Y offer, a "spend 200, take 20 off" basket deal, or a fixed-price bundle — and the cart works out the price the instant items go in. Offers can stack or stay exclusive, run on a schedule, and hide behind a coupon code when you want them gated. The cart even nudges the customer: *add one more to get the deal*.

Because LumenPOS handles pricing itself, it automatically ignores ERPNext Pricing Rules at the till — so your price books, promotions and bundles are always exactly what the customer is charged, with nothing to switch on or off. Your existing ERPNext Pricing Rules keep working everywhere else.

**It keeps selling when the internet doesn't.** Products, prices and promotions are cached on the device. If the connection drops mid-shift, the till carries on — sales queue locally and upload themselves the moment you're back online. A plain-English log shows the cashier exactly what's synced and what's still waiting, so nothing quietly disappears.

**The money side is handled.** Open a register with a float, ring the shift, and close with a blind count that's checked against what the system expected, Z-report included. Take cash, card, split tenders, gift cards or store credit, and give change. Do returns and refunds back to the original payment method or to store credit. Pull a mid-shift X-report any time you want a read without closing the drawer.

**Gift cards, store credit and loyalty** are all in the box — sell and redeem gift cards, keep per-customer store-credit balances, and award loyalty points customers can spend at the till.

## Receipts your way

Design the on-screen and browser receipt right in Settings: pick a layout, choose what shows (barcode, serial number, tax ID, notes, and the rest), drop in your logo and footer. Want full control? Point the POS Profile at any ERPNext Print Format and it takes over. Running a thermal printer? LumenPOS talks to network ESC/POS printers directly and kicks the cash drawer.

## Fits your setup, not the other way round

- **One company or many.** Accounts are scoped per company, so a multi-company site never posts to the wrong ledger.
- **POS Invoice or Sales Invoice.** Choose per outlet how sales post — the consolidated POS flow, or direct Sales Invoices when that suits your accounting.
- **Your team, your rules.** Decide who can change a price, who can run a return, and who can approve one past the return window. Every override lands in an audit log.
- **Serial numbers done properly.** A serialised item won't enter the cart until a real, active serial from this register's warehouse is scanned — no silent auto-pick.
- **English and Arabic**, right-to-left included.

## What you need

- Frappe / ERPNext **v15**
- A configured **POS Profile** (company, price list, warehouse, payment methods) with your cashier added to it

The front end ships pre-built, so there's no Node or build step — it installs like any other Frappe app.

## Still on the roadmap

LumenPOS is under active development and ships improvements most weeks. A few things are honestly still in progress: layaway and deposits, and reloading the app itself while fully offline (today, keep the tab open during an outage — queued sales are safe either way). Everything described above works now.

Built by **Lumen Solutions** · support@lumen-solutions.co

---

## The other profile fields

| Field | What to put | Notes |
|---|---|---|
| **Title** | `LumenPOS` | Done. |
| **Documentation** | e.g. `https://lumen-solutions.co/lumenpos/docs` | Publish `website-guide.md` (in this folder) on your site and link it here. |
| **Website** | `https://lumen-solutions.co/` | Use **https**. A dedicated `/lumenpos` product page converts better than the homepage. |
| **Support** | `support@lumen-solutions.co` | Done. Consider adding a support form or Help Desk link too. |
| **Terms of Service** | `https://lumen-solutions.co/terms` | You'll need a page. Keep it simple; a short SaaS/app ToS is fine. |
| **Privacy Policy** | `https://lumen-solutions.co/privacy` | Required by most marketplaces. Note what the app stores locally (offline cache in the browser) and that it posts to the customer's own ERPNext site. |
| **Summary** | See above | Keep it to one sentence. |
| **Description** | See above | Markdown. |

## Screenshots & video (upload 5–7)

Show the product doing real work. Suggested order:

1. **The sell screen** with a full cart and a promotion badge showing.
2. **The payment screen** — split payment or a gift card being applied.
3. **Creating a promotion** (Buy X Get Y or Bundle) in the desk.
4. **The receipt designer** with the live preview.
5. **Register close** — expected vs counted / Z-report.
6. **Offline sales log** — Pending / Uploaded / Needs attention.
7. *(optional)* a short screen recording of ringing a sale end to end.

Tips: capture at a clean resolution (around 1280×800 or 1440×900), use the light theme so the **Lumen blue (#1463FF)** reads well, and blur any real customer data.
