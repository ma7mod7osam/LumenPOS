# LumenPOS: Complete User Guide

*Applies to LumenPOS v0.61.1. This document is updated with every feature change.*

> **Note on this document.** Sections 1 to 17 below were written up to v0.17 and are
> being brought forward release by release; the **changelog in section 18 is
> authoritative and current**. For a complete, up-to-date description of every
> feature, multi-outlet shifts, shift ownership, per-user PINs, shift schedules,
> payment restrictions, split refunds, per-outlet and dynamic receipts, the
> offline sales log and the performance-index page. See
> **[the full product guide](website-guide.md)**, which is current as of v0.39.1.

**Dark mode:** the nav rail has a **Dark / Light** toggle at the bottom. On
first run LumenPOS follows your **ERPNext desk theme** (My Settings → Theme:
Light / Dark / Automatic); Automatic falls back to the operating system's
appearance. The moment you use the in-POS toggle, that choice is remembered
per device and overrides the ERPNext theme from then on. Printed receipts
always come out black-on-white regardless of the screen theme.

**Languages:** the till speaks **English, Arabic, Spanish, German, Chinese (Simplified), French, Thai, Indonesian, Vietnamese, Portuguese (Brazil), Persian, Russian and Turkish**, the
languages ERPNext is used in most after English, in that order (a study of
public ERPNext sites and Frappe Cloud installs, September 2026). The last four
came in 0.57.0. The language control sits in the top bar: with two languages it
is a single tap (it shows the other one's name), with more it opens a short
list, each language named in itself. Arabic and Persian flip the whole interface to
**right-to-left**. Every label, button, message and tooltip is translated, and
so are the **server's own messages**: the till sends its language with every
request, so a refusal or a warning comes back in the language on the screen,
ERPNext's own messages included, whatever the user's language in the desk.
**Master data is never translated**: item names, customer names, codes and
barcodes always show exactly as entered in ERPNext. On first run LumenPOS
follows the browser's language (Arabic on a typically Arabic device, Spanish on
a Mexican one). The choice is then remembered per device, and a customer
display on the same device follows it. **Settings → General → Languages**
chooses which languages cashiers may pick (English always stays: a text not
translated yet shows in it). While every language is ticked, a language added by
a later update is offered by itself. Return reasons and other configurable lists
show the text you saved in Settings. The Insights dashboard stays in English or
Arabic, the two languages Lumen Reports builds it in.

LumenPOS is a professional Point of Sale for ERPNext / Frappe. Each **POS
Profile** chooses how sales post (POS Profile → *LumenPOS Options* → **Sale posts
as**):
- **POS Invoice** (default), sales are POS Invoices with native **POS
  Opening/Closing Entries**, consolidated into Sales Invoices at register close.
- **Sales Invoice**, each sale posts a **Sales Invoice directly** (GL posts
  immediately, no consolidation). The register is a **lightweight LumenPOS cash
  shift** by default (no POS Opening/Closing Entry; works on v14/v15 too), or,
  if you tick **Use POS Opening/Closing Entries** on the POS Profile, it opens a
  **POS Opening Entry** and closes with a **POS Closing Entry** for cash
  supervision and the standard ERPNext POS reports (still no consolidation,
  since the sales are already Sales Invoices).

Either way, stock, GL and reports behave as standard ERPNext.

---

## 1. Installation & first-time setup

### Install (Frappe Cloud)
1. Dashboard → your **Bench Group** → **Apps** → **Add App** → From GitHub →
   `https://github.com/ma7mod7osam/lumenpos`, branch `main` → **Deploy**.
2. Site → **Apps** → **Install** next to LumenPOS.
3. Updates later: the bench shows **Update Available** → Deploy. The site
   migrates automatically and browsers fetch the new build on next load
   (asset URLs are version-stamped, no manual cache clearing needed).

### Install (bench with shell access)
```bash
cd frappe-bench
bench get-app https://github.com/ma7mod7osam/lumenpos
bench --site yoursite install-app lumenpos
bench --site yoursite clear-cache
```
The frontend ships pre-built, **no Node/npm needed on the bench**.

### Prerequisites in ERPNext
Create a **POS Profile** per register/branch with:
- **Company**, **Selling Price List**, **Warehouse**
- **Payment methods** (at least one; mark one as Default; have one of type Cash)
- Your cashiers under **Applicable for Users**
- Optional: **Taxes and Charges** template, default **Customer** (walk-in),
  **Print Format** (used for browser printing), **Item Groups** (limits the grid
  to those groups and every group beneath them, as ERPNext's own POS does, so
  listing a parent group such as *Food* covers its sub-groups, and listing
  *All Item Groups* is the same as listing none)
- Optional (printer): `Printer IP` / `Printer Port` fields (LumenPOS section)
  for a network ESC/POS thermal printer

Items need an **Item Price** on the profile's selling price list. Items
without a price ring up at 0. Stock items with no stock in the profile's
warehouse stay off the grid unless **Show out-of-stock items in the grid** is
on (Settings, General, Register and shifts), and the grid says so when that is
why it is empty.

### Open the POS
Log in to ERPNext, then open **`https://yoursite/pos`**.
The **LumenPOS workspace** in the desk has shortcuts to everything.

### Help on every screen (0.58.0)
The **?** button at the top of every screen opens that screen's help: what it is
for, the everyday tasks in short numbered steps, and a **Show me** beside the
tasks that have a tour. A tour lights up the real buttons one at a time, with a
card that says what each is for (Next, Back, or Esc to leave). It only shows and
explains: nothing is sold or changed, and the screen under it cannot be tapped
while it runs. The tours: *Getting around*, *Your first sale*, *Refunds and
exchanges*, *Open and close the shift* and, where the shop sells in other
currencies, *Selling in another currency*. The help and the tours speak the
language each person picks, and each one shows only what that person may use.

Someone who has not seen the help yet is offered a one-minute tour the first time
they open the till, with a short list of what was added lately. After an update,
each person sees once what is new for them (a manager also sees the manager-only
news), with a **Show me** where a tour exists. What each person has seen is kept
per user in ERPNext (user defaults), so a cashier who took the tour on one till is
not asked again on another. The three parts are switched in **Settings, General,
Help for staff**, all on by default.

---

## 2. The Sell screen

| Area | What it does |
|---|---|
| **Search bar** | Type to search name/code/barcode (instant, served from a local cache). Press **Enter** with a scanned barcode or serial number to add the item directly. |
| **Category chips** | One scrollable row. **All** shows everything; **🎁 Bundles** appears when bundles exist. |
| **Product grid** | Tap a tile to add to cart. Tiles show price, stock count and an **S/N** badge for serialized items. The stock number is what you can still sell here, so anything already sold on a shift that has not been consolidated is taken off it, anything returned is put back on it (from 0.56.1, on every ERPNext version), and it moves the moment a sale or a return posts. A line running low is visible long before the till refuses it. |
| **Cart (right panel)** | Customer, channel, salesperson, the lines (always at least three lines high), then **Coupon**, **Discount** and **Note** as three small buttons that open their field on demand and stay lit while they hold something, the total with **Details** folding the subtotal, discounts, tax and service charge away (and what the customer saved beside it), other currencies on one line, and Pay. |

### Cart line controls
Tap a line to expand it: quantity stepper, **Discount %** (manual), Remove.
Lines show `item code · ▮ barcode` under the name.

- **Promotion badges (★ purple)** appear on lines a promotion is discounting.
- **💡 Suggestions** appear *under the specific line* they relate to
  ("Add 1 more, get at 50% off"). Click one to find the suggested product.
  Basket-level suggestions (Spend & Save) show above the totals.
- **🎁 Bundle lines** are locked (no qty edit / manual discount); expanding
  offers *Remove bundle*, which removes the whole bundle instance.
- **Serialized lines** show serial chips; qty always equals scanned serials.

### Customer
Tap **Add a customer** → search by name / mobile / tax ID → select, or create.
What the new-customer form asks is the shop's choice, under **Settings →
General → Customers**: every field is **Hidden**, **Optional** or **Required**,
for individuals and for companies apart, and any other field of Customer (your
own custom fields too, such as a national ID or a commercial registration
number) can be added the same way. The server applies the same rules as the
screen. Out of the box the form is the Saudi one it always was:
- **Individual**: name + mobile mandatory, email optional.
- **Company**: name, mobile, **Tax ID** and **national address** (building,
  street, district, city, postal code) mandatory, additional number optional;
  it creates a linked Address.

A shop outside Saudi Arabia keeps only the address parts it needs (the block is
then called *Address*). The mobile is how the till recognises a customer it
already has, so a shop that makes it optional may see the same person added
twice.

When a customer is attached, the cart shows their **loyalty points** and
**store credit**, and prices reprice if a price book applies to their group.

### Channel (delivery apps)
The channel picker defaults to **Walk-in**. Selecting a delivery app
(configured in Settings → General):
- forces an **Order ID** if the app requires one (Pay is blocked without it),
- switches prices to the app's price list if it has one,
- records the channel on the invoice using your site's existing fields:
  `pick_customer` (checkbox, ticked), `custom_app_type` (the app, must be
  an option of that Select field) and `pick_order_no` (the order ID).
  LumenPOS writes these only if they exist.

### Salesperson
Type a name **or the salesperson number** (`sales_person_no`) and pick.
It stays for the next sales (the person on shift) and is recorded on the
invoice's Sales Team at 100%, with the commission ERPNext works out at that
person's rate (Sales Person, Commission Rate), and printed on the receipt.
Salespeople are ERPNext's Sales Persons.

**Settings, General, Features, Salesperson at the till** (from 0.57.0):

- **Optional** (the default, as before): the cashier may pick who sold.
- **Required**: Pay stays on the sale until a salesperson is picked, and the
  server refuses a sale, a gift card sale or an exchange's new sale without
  one. A sale the till queued offline before the switch still posts.
- **Off**: the till asks for nobody and records nobody.

**Sales by salesperson** (the **Salespeople** tab of **Insights**): per
person over a period (today, yesterday, the last 7 days, this month, or any
dates), for this outlet or every outlet of its company: sales and returns
(how many, and the net amount before tax), the net, and the commission. A
return counts against the salesperson of the sale it takes back, and the sales
nobody was named on come as their own row, so the page adds up to the
outlet's net sales. **Download CSV** gives the same as a spreadsheet. The
Register page and the X-report list the shift by salesperson.

Who sees it: managers, and anyone named for **See sales by salesperson**
(Settings, Approvals and permissions). Only they see the commission on the
shift report.

ERPNext's own Sales Person reports show this only for a Sales Invoice outlet:
at a POS Invoice outlet (the default) the close merges the shift's sales into
a Sales Invoice without the Sales Team, and those reports read no POS Invoice
(ERPNext 13 to 16). The Salespeople page reads the till's own invoices.

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
  the Mode of Payment name, **Visa, Mastercard, mada, American Express,
  Tamara, Tabby, STC Pay, Apple Pay**, on a white chip (legible in light and
  dark). Other methods (Cash, Bank Transfer…) keep a clean line icon.
- **Split payments**: add any combination; each shows in the list with ✕.
- **Cash** may over-tender → change due is shown and recorded.
- **Store Credit** tile appears when the customer has balance.
- **Cashback**: when a named customer has a cashback balance, a **Cashback
  available** row shows it with a **Use cashback** button (it spends the cashback
  closest to expiring first). On a qualifying sale the screen also shows **This sale
  earns … cashback** before you take payment. Cashback belongs to a customer, so pick
  the customer to earn or spend it. Set the rules in **Settings → Cashback**, choose
  its accounts in **Settings → General → Company accounts**, and switch the feature on
  or off in **Settings → General**.
- **🎁 Gift Card**: scan/type the card → **Check** shows the live balance →
  **Apply**. Multiple cards per sale supported.
- **Loyalty points**: when the customer has points, a redeem box shows their
  value; capped server-side at the customer's real balance.
- **Discount approval**: if any manual discount exceeds the limit
  (Settings → General → *Discount approval*), Pay is blocked until the discount
  is approved. How it's cleared depends on the **over-limit approval method**:
  - **Passcode only** (default), a manager enters the **passcode / approver
    PIN** at the till. The approver's name is recorded on the invoice.
  - **Request only**, the cashier taps **Send approval request**; the till
    waits while a role-holder approves it (see below). No PIN on the device.
  - **Passcode or request**, the cashier can do either.
  A **request** is single-use, tied to the open register session, and **expires
  if the register closes** before it's approved. Approvals are re-checked
  server-side, so the limit can't be bypassed from the client.

  **Approving requests:** users holding the configured **Approver Role** (plus
  LumenPOS / System Managers) get an **Approvals** tab in the left rail with a live
  count badge. Open it to **Approve** or **Reject** each pending request, only
  while the cashier's register is still **open**. On approval the cashier's till
  proceeds automatically; on rejection they must lower the discount.

**Taxes:** the cart computes taxes from the POS Profile's tax template the
same way ERPNext does, exclusive rows appear as `+ VAT 15%` lines and are
part of the Pay amount; inclusive rows show as "(included)" for information.
The displayed total always equals the invoice grand total.

> **VAT-inclusive pricing (shelf prices already include VAT):** the VAT row
> in your Sales Taxes and Charges template **must** have *"Is this Tax
> included in Basic Rate?"* ticked. Then the price the customer sees is what
> they pay, with VAT shown as "(included)". If that flag is **off**, ERPNext
> (and the cart) will add 15% on top of the shelf price, overcharging.
> Verify the current setting at a glance in **Settings → Status → VAT / taxes**
> ("included in price" vs "added on top").

Everything the client computed is **re-validated server-side** at submit:
prices, promotions, serials, balances, passcodes. The client math is
display-only.

### Selling on account (0.60.0)

A customer takes the goods now and pays later: all of it, or the rest after paying
part. The sale is a POS invoice like any other.

**Turn it on** in **Settings, General, Sales on account**:

- **Sell on account**: off by default. Off, the till shows nothing about it.
- **Who can buy on account**: *Only customers allowed on their card* (the default:
  a manager ticks **Allowed to buy on account** on the customer, in Customers), or
  *Any named customer*. Never the walk-in customer.
- **Default credit limit**: for a customer with no credit limit of their own in
  ERPNext (on the customer, its group or the company), in the company's currency.
  0 = no limit.
- Who may sell on account, take customer payments and set a customer's credit is set
  in **Approvals and access, Permissions** (see section 16). Until someone is named
  there, only managers can.

LumenPOS makes what it needs itself, in each company with an outlet: a payment method
**Credit Sale** and a clearing account **POS Credit Sale Clearing**. The Settings card
says what it set up. A payment method of that name that the shop made itself, on
another account, is never taken over: the card says so, and the shop renames it.

**At the till:** choose the customer, tap **Pay**, take what the customer pays now, then
**Put … on account** for the rest. The card shows what the customer already owes and
what their limit leaves. The receipt shows what is still owed on the sale and in all,
with a line for the customer to sign.

**Owes, and holds apart (0.61.1):** *Owes* is the customer's balance in the books, the
sales on account and invoices they have not paid, which is what the list of their sales
adds up to. Their open holds (and any Sales Order or Delivery Note not invoiced yet) are
not owed, so they show on their own line, **Holds and orders not invoiced**, on the
customer's page and on the payment screen's card. They still count against the credit
limit, because ERPNext counts them when it checks the limit: *Left to use* is the limit
less both.

**What happens in ERPNext:** the part on account is paid on the invoice by the *Credit
Sale* tender, and in the same moment LumenPOS books the debt on the customer with its own
**Journal Entry** (the customer debited, the clearing account credited). So the debt
shows on the customer's account and in Accounts Receivable at once, one entry per sale.
When the shift closes, the merged invoice's *Credit Sale* payment clears the clearing
account back to zero.

**The limit:** ERPNext's own credit limit (the customer's, then its group's, then the
company's), else LumenPOS's default. The till refuses a sale that would take the
customer past it and says what is left. ERPNext refuses a limit below what is already
owed.

**Not allowed:** a walk-in customer, a customer not allowed on their card, more on
account than the other tenders leave (no change comes out of a debt), a sale in a
currency other than the company's, a sale made without a connection, a gift card or a
hold on account, and the difference of an exchange.

Why a tender and an entry, and not ERPNext 15/16's *Allow Partial Payment*: ERPNext 16
refuses a POS invoice with nothing paid, ERPNext 13 and 14 refuse a POS return that does
not refund in full, and ERPNext checks the credit limit only when a shift's invoices are
merged, so a sale over the limit failed the whole close. This way every version takes a
sale with nothing paid, a return comes off the debt, and the limit is checked at the sale.

**Returns:** what comes back goes off what the customer still owes on that sale first,
and only the rest goes back as money (out of the drawer), never onto the customer's account. A sale already paid off comes
back as money in full. A sale still owing is not exchanged: take it back, then sell the
new goods.

### Selling in other currencies

For a shop whose customers pay in more than one currency: a UAE shop with
customers billed in dollars, a tourist paying in dollars at a riyal till.
Switch it on under **Settings → General → Other currencies** (*Sell in other
currencies*), add the currencies, **Save**, then set each rate.

**What saving sets up.** For each currency, for every company that has an
outlet, LumenPOS creates ordinary ERPNext records: a receivable account
(*Debtors USD*), a cash account (*Cash USD*) and a payment method *Cash USD*
added to every outlet, and a customer *Walk-in USD* billed in that currency.

**Which currency a sale is in.** The customer's **Billing Currency** in ERPNext
(Customer → Currency and Price List). Pick a customer billed in dollars and the
whole sale is in dollars, as the customer expects. A walk-in can be switched to
another currency with the currency picker beside the channel on the cart, or
with **Sell in** at the top of the payment screen; a named customer always buys
in their own currency. The customer search shows the currency next to such a
customer.

**Prices.** One price list, in the outlet's currency, is all a shop needs:
price books, bundles, offers and discounts stay in that currency and are
converted at the shift's rate, so nothing has to be priced twice. To fix prices
in another currency instead (round ZWG prices, say), make a selling price list
in that currency and set it as the *Default Price List* of that currency's
walk-in customer (*Walk-in ZWG*), of a customer, or of their customer group.
Every item that list prices sells at its own figure; an item it does not list
keeps the outlet's price, converted at the shift's rate. The cart shows the sale
in its currency with its local value underneath; a local sale can also show its
value in the currencies ticked *Show the equivalent at the till*.

**Rates.** Kept in ERPNext (*Currency Exchange*, selling). Set them in the same
Settings card. A shift fixes the rate of every currency as it opens and keeps
it until it closes, because ERPNext merges each customer's shift into one
invoice at one rate, and a new rate applies from the next shift. (A currency
that has no rate yet when the shift opens gets it at its first sale in it.
Until 0.55.0 every rate was fixed at the first sale, which a till without a
connection could not know.)

**Automatic rates (optional).** Tick *Update exchange rates automatically* and
choose, for each currency, a **Fixed rate** (the one you set, as before) or an
**Automatic rate**. Once a day, at a quarter past midnight, LumenPOS reads the
published rates from ExchangeRate-API (free, about 160 currencies) and saves
today's rate of every Automatic currency in ERPNext, exactly as if someone had
typed it. **Update now** does it at once. An Automatic currency can carry a
**margin**: the till values it that much below the published rate, the way a
shop taking a volatile currency at the market rate does (a published 26.6 to
the dollar with a 24% margin is 35 to the dollar). A rate typed for today in the
same card always wins, for that day. If the rates service cannot be reached, the
last rate stays in force and the reason shows under the currency.

**Paying.** Each payment is typed in the money actually handed over: the
payment screen asks **Amount in** dollars or riyals, converts at the shift's
rate and shows what is left in both. Local cash and cards are always offered,
the *Cash USD* drawer only on a sale in dollars (ERPNext refuses a dollar
account on a riyal invoice at the close). **Change comes back in local money,
from the main drawer**, the way ERPNext's own POS gives it, unless the currency
is set to **Give change in USD** (same card): then the change of every sale in
dollars comes back in dollars, from the *Cash USD* drawer, and the payment
screen, the receipt and the close say so. The choice holds for the whole shift,
like the rate, because the close books all of a customer's change from one
account. An outlet whose POS Profile names its own *Account for Change Amount*
keeps it (ERPNext uses it on every sale), the till shows the change in that
account's money, and a sale whose change that account cannot take (one in a
third currency) is refused at the till rather than failing the shift close.
Selling in other currencies also turns on ERPNext's *Create Ledger Entries for
Change Amount* (POS Settings on ERPNext 16, Accounts Settings before): change
given from one drawer for money paid into another needs its own ledger entry.

**The shift.** Each drawer in another currency keeps its own opening float,
cash in and out, expected amount and count, in its own money. The takings,
discounts and variance alerts are in the company currency. The X-report lists
the rates. At the close ERPNext consolidates each customer's sales in their
currency, and the books balance: a test sale in dollars paid with 20 dollars
and 70 riyals, refunded in part, closed with both drawers at a zero difference.

**Receipts** show the sale in its currency, its local value and the rate, each
payment in the money it was made in, and the change in local money.
**Refunds** go back in the sale's currency at its original rate, through local
cash and cards or its own drawer.

**What stays in the outlet's currency.** Gift cards, store credit, cashback,
loyalty redemption, holds and exchanges keep one currency in their ledgers, so
they are refused for a sale in another currency with a plain message (refund
it and ring up a new sale instead of an exchange).

**Without a connection.** A sale in another currency can be made offline, to
that currency's walk-in customer (**Sell in ZWG**): the till prices it at the
rate the shift fixed as it opened, and from the walk-in's own price list when
it has one (the till keeps it with the catalogue), and the sale is queued like
any other. The server posts it only at the shift's rate. A till that was out
of date sees the sale refused with both rates, never posted at a price nobody
paid (and a refused sale never holds the close). A named customer billed in
another currency still needs a connection, since their own prices are not kept
on the device.

**Off.** With the switch off, a customer billed in another currency is refused
at the till, with the reason, instead of being posted wrong. Rates and the
currency list need permission to change LumenPOS Settings.

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
double-apply. **Promotions only affect sales made through /pos**, desk-made
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
  customer gets the **lower** of the price-book price or (standard − promo),
  it never stacks with the book and never raises the price. Standard 99, book
  49, 20% off → the book's 49 wins → **49.00**; the promo only kicks in if it
  beats the book. Uses the **highest-priority** active book as the comparison.

(Spend and Save and Bundle promotions always use the cart's current price.)

### Products: include & exclude
Each row is **Include** or **Exclude** and targets an Item, Item Group,
Brand, or **Tag** (an ERPNext item tag, tag items in the desk, then group them
here without listing every group/brand). An Item Group covers every group
beneath it, as an ERPNext pricing rule does: a row on *Food* also takes the
items filed under *Food > Burgers*. The same goes for cashback rules. All picked
from a validating dropdown (free text is rejected):
- *All products except brand X*: tick **Apply on all products** + Exclude row.
- *Group except items*: Include the group + Exclude the items.
- Exclude-only rows = "everything else".

### Scheduling & eligibility: all optional
- No dates and no times = runs **all the time**.
- Date range, days of week, and a daily time window (wraps midnight for
  happy hours). Equal start/end times mean "all day".
- Outlets (none ticked = all) and customer groups (empty = everyone). On a
  site with several companies the outlets become **Whole group / One company /
  Chosen outlets**: one company means every outlet it has, including outlets
  opened later (see *Several companies on one site* in section 15).
- **Requires Coupon Code** gates the promo behind a code at the till. Use the
  single code field for one shared code, or open a saved coupon promo and
  **Generate** / **Import (Excel/CSV)** a whole batch of unique codes. Each batch
  has a **use limit**, how many times each code may be redeemed (**1** = single
  use, **0** = unlimited), plus an optional expiry. Redemptions are counted and
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
**expired**, it stops being offered at the till and shows an *Expired* badge in
the Settings list. Serialized items can't be bundled. On a site with several
companies a bundle is offered to the whole group, one company or chosen
outlets, like a promotion. The server checks the dates and the outlet again at
the sale, so a cart kept past the end date, a queued sale or another company's
till cannot ring it up.

On the sell screen the **🎁 Bundles** chip shows bundle cards; **Add** puts
every component in the cart as **separate lines** (each individually
returnable, the point of the design), highlighted with a 🎁 chip and priced
together. Removing any line removes the whole instance.

**Price split:** by default the bundle saving is split across the lines
**proportionally to their regular prices** (cent-correct, so line totals sum
exactly to the bundle price). To control the split yourself, e.g. protect
margin on one item, fill the optional **Allocated Price** per component:
all rows must be filled and must sum exactly to the bundle price (validated
live in the editor and again on save).

---

## 6. Price Books (Vend-style)

**Settings → Price Books.** A price book is simply **a list of items with a
special price** that applies for a period, a discount off your normal selling
price. **No ERPNext Price List is created or touched**; the prices live on the
book itself, so your Standard Selling master is never changed.
- **Set it up**: give it a name, **priority** (highest wins when several books
  cover the same item), optional **validity dates**, and the **outlets** /
  **customer groups** it applies to (empty = everyone / all outlets).
- **Add the items** under **Item prices**: pick items (search by name, code or
  barcode) and type each one's price, or **↥ Import Excel/CSV** (matched by
  code, name or barcode; the Book Price / Price column, or the last column if
  the file has no header, sets the price). **↧ Export** downloads the book's
  items. Or **Add all by** brand / item group / tag to pull every matching
  sellable item in one click (each added at its current selling price, so
  nothing accidentally sells at 0, then lower the ones you want to discount).
  To reprice the whole book at once, use **Discount all prices by X%** with an
  optional rounding step (nearest 0.05 / 0.25 / 0.50 / 1 / 5). Reopen the book
  any time and the items are right there.
- **How it applies at the till**: while the book is active (date window +
  outlet + customer group match; on a site with several companies the outlet
  side is the whole group, one company or chosen outlets), its items sell at
  the book price; everything
  else keeps the normal selling price. When several active books list the same
  item, the **highest-priority** book wins for that item.

Order at the till: **delivery-app price list → active price book(s) →
normal selling price.** (Delivery-app prices still use a real ERPNext Price
List and override price books.)

**Per-app prices (e.g. Jahez):** give a delivery app its own price list in
**Settings → General → Delivery apps** (use **+ new** to create one named after
the app), then tap **Edit prices** to open the same editor, including
Excel/CSV import/export, for that app only. An app's price list overrides
every price book, so it's the place to keep channel-specific prices.

**Fallback pricing:** a price book only changes the items it lists, every
other item keeps its normal selling price. A partial book can never make the
rest of the catalog ring up at 0.

---

## 7. Gift cards

Correct retail accounting throughout: selling a card moves money into a
**Gift Cards liability account** with **no revenue and no tax**, tax applies
when the card is spent. That holds at an outlet that adds VAT too: the card's
line carries a zero tax template (`LumenPOS Zero Tax - <company abbreviation>`),
because ERPNext puts the outlet's tax back on any sale whose tax table is
empty. Before 0.56.2 a card of 100 came to 115 at such an outlet.

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
- **Several companies**: a card belongs to the company that sold it. Whether
  the outlets of the other companies take it is set in **Settings, General,
  Companies** (see *Several companies on one site* in section 15). Scanning a
  card shows the company that issued it.

---

## 8. Loyalty

Uses ERPNext's native **Loyalty Program**. LumenPOS adds the setup and till UX:
- **Create** in Settings → Loyalty & Gift Cards: earn rate (1 point per X
  spent), point value, expiry days, expense account (auto-created if empty).
  Auto opt-in enrolls **all customers**.
- **Earning** is automatic on every POS sale once a program exists.
- **Redeeming** appears in the payment screen when the customer has points;
  capped at their real balance, validated server-side.
- The receipt shows points earned and redeemed.

**Several companies:** ERPNext ties a loyalty program to one company. Points
are earned at any outlet but redeemed only at the outlets of the program's
company, and only points earned there, so the till offers points to spend only
there. Choose the company when you create the program. For a reward that every
company of the group honours, use cashback, which follows the Companies setting.

**Store credit** (related but separate): refunds can go to store credit
(per-customer balance on a liability account); it appears next to the
customer in the cart and as a payment tile.

---

## 9. Returns & refunds

**History** → open a sale → **Refund…**:
- Pick lines and quantities, partial returns tracked, you can never return
  more than remains returnable.
- **Serialized items**: **scan or type each serial** coming back, it's checked
  against the serials sold on this invoice (and still returnable). This forces
  the cashier to read the actual unit rather than blind‑pick from a list.
- **Return reason (required)**. Pick why the item is coming back from the list
  configured in **Settings → General → Return reasons**, or choose **Other** to
  type a free-text reason. The reason is stored on the credit-note invoice
  (field *Return Reason*) for reporting. Manage the list (add/remove) in
  Settings; the till always offers **Other** on top of it.
- **Return window (optional).** When *Limit regular returns to a time window* is
  on (**Settings → General → Returns**), a sale can be returned normally only
  within **N days** (default **14**, configurable; 0 = no limit). Past the
  window the Refund button is blocked and the cashier taps **Send return
  approval request**, a holder of the **Approver Role** approves it from the
  **Approvals** tray (while the register is open), then the refund proceeds.
  The approval is single-use and tied to that invoice; the server re-checks the
  window and the approval, so it can't be bypassed from the client. Off by
  default (existing behaviour: no time limit).
- **Refund method is restricted to how the sale was paid** (when *Restrict
  refunds to the original payment method* is on in Settings → Refunds, the
  default). The dropdown shows only the tenders the customer actually used
  (plus **Store Credit**, always allowed). Add exceptions per method in
  Settings → Refunds, e.g. *paid Visa → refund Visa only*, *paid Mada →
  refund Mada or Cash*. The server enforces this even if the UI is bypassed.
- Posts a credit-note POS Invoice tied to the open register session, so the
  drawer count stays right. The credit note gives back the tax the sale
  charged and no more: a sale made with no tax comes back with no tax, even
  after the outlet has been given a tax template (before 0.56.2 it came back
  taxed at the outlet's new rate, so a sale of 90 refunded 108).
- **The goods are back on sale at once** (from 0.56.1, on ERPNext 13 to 16).
  The moment the return posts, the item's tile counts it again and the next
  customer can buy it, in the same shift, without waiting for the close. This
  holds for a return of an earlier shift's sale, for an exchange, and for a
  bundle's components. The close still posts every sale and return in the
  right order, so the books and the stock come out exactly as they would have.
  - On **ERPNext 15 and 16** ERPNext counts a return itself as soon as it is
    made, all but a returned **serial number**, which it holds until the
    return is posted to the books. So LumenPOS posts a return that brings a
    serial back right away (as below), and the serial sells again at once.
  - On **ERPNext 13 and 14** ERPNext counts a returned item only once the
    return is posted to the books, so LumenPOS posts it right away, together
    with the sale it takes back, the way the shift close would (ERPNext's own
    consolidation). The shift close then leaves those two out of its merge and
    still counts them in its totals.
  - If that posting cannot happen at that moment (another shift is being
    closed), the return still stands, the item comes back when the shift
    closes, and the tile (or, for a serial, the scan) says so.
- **Consolidated sales are still refundable at the till.** Once a shift closes,
  its sales are merged into Sales Invoices, but you can still refund them from
  the POS exactly the same way. LumenPOS posts the credit note against the original
  POS sale, tied to your **current** open shift, so the refund comes out of the
  current drawer; ERPNext merges it into a consolidated credit note at the next
  close. (You no longer need the ERPNext desk for everyday post-close returns.)
  Refund a given sale through **one** channel only (the till *or* the desk), not
  both, so the returnable quantity stays accurate.
- **Sets return together.** Items sold as a **bundle** or a **Buy X Get Y**
  offer are linked, on a **regular return** you must return the **whole set**
  (every member, full quantity) or none; the screen badges them *Set, return
  together* and steps the whole set at once, and the server enforces it. Each
  line stores its set in `lumenpos_return_group` at sale time.
- **Without a connection**, a sale this device made in the same shift can still
  be taken back from Sales History (section 14, *Returns without a connection*).
- **A refund never posts twice.** Every refund carries its own key from its
  first attempt, so one whose answer was lost on the way back, and was then
  tried again, is answered with the credit note that already posted.

---

### Exchange in one step

A customer swapping one thing for another is not two errands. **History** to the
sale, then **Exchange…** instead of **Refund…**:

1. Pick what is coming back, exactly as you would for a refund. Everything a
   return checks still applies here: return restrictions, the return window and
   its approval request, serial numbers, sets that must come back together.
2. Press **Pick the new items**. The till returns to **Sell** with a banner
   showing which sale is being exchanged and what the returned goods are worth.
   Ring up what the customer is taking instead, the usual way.
3. **Pay** shows the arithmetic: the new items, the credit for what came back,
   and one line for what is actually owed. Dearer, and you collect the
   difference with any tender. Cheaper, and you give the difference back, by the
   same refund rules a normal refund follows. Equal, and nothing moves in the
   drawer at all.

Both documents post together, in one request: a credit note for the goods
returned and a POS sale for the replacement. If anything fails, neither exists.
There is no moment where the shop has taken goods back without handing over the
replacement.

**How it settles.** The matched part of the two documents goes through a
clearing tender called **Exchange**, backed by a liability account LumenPOS
creates on first use. So the drawer, the card totals and the Z-report only ever
see the difference, and the clearing account is back to zero the moment the
exchange finishes. The replacement sale is tagged **EXCHANGE** in History.

**Who may do it.** Anyone who may make returns, unless a shop names a role in
**Settings → General → Approvals and permissions → Exchange role**. An exchange
always needs return permission as well.

**Needs a connection.** An exchange is not queued offline, because it posts two
linked documents against an existing sale.

---
## 10. Holds and deposits (layaway)

A customer who wants the goods kept while they pay for them over time. Ring
the items up as usual, pick the customer, then **Hold** instead of Pay.

**Switched off until you want it.** A shop that never puts goods aside sees
nothing of this: no button on the cart, no screen in the rail. Turn it on under
Settings, General, Holds and deposits. Turning it off again strands nothing: a
hold that is still open keeps its screen until it is handed over or cancelled,
because that money and those goods belong to a customer.

1. The modal shows what is being held and asks for the deposit and how it was
   paid, plus a date to hold until and a note. The shop can insist on a
   minimum first payment (Settings).
2. The goods are **reserved**: LumenPOS raises a Sales Order, so ERPNext shows
   the quantity as committed and another till cannot sell the last one. A shop
   that does not want that can switch it off.
3. The **Holds** screen lists what is on hold, for whom, paid and still to pay,
   and flags anything past its date. From there you take another instalment,
   hand the goods over, or cancel.
4. **Hand over** sells the goods at the price agreed on the day of the hold,
   takes the balance, releases the reservation and closes the hold.
5. **Cancel** refunds every instalment through the ordinary return, so the
   refund method rules a shop set apply here too, and the goods go back.

### Where the money sits

A deposit is **not a sale**. Each instalment posts a real POS sale of one line,
a *Customer Deposit*, whose income account is a **liability** (LumenPOS creates
*Customer Deposits* on first use, or use your own in Settings). So the drawer
and the Z-report see the money the moment it is taken, but nothing is counted
as revenue while the goods are still in the shop.

At hand-over, what was already paid comes off the bill and only the balance is
collected, so the drawer is right both times.

The figure a hold quotes is **what the customer will pay in the end, tax and
all**, worked out on the day the hold is made and frozen there. At an outlet
whose price list is net of VAT that is more than the shelf prices add up to,
and it has to be: a customer who pays a hold off in full has paid the tax too,
and hands over nothing on the day they collect.

### Tax on a deposit

Off by default: **the deposit carries no tax and the goods are taxed in full**
when they are handed over. Turn on *Deposits are taxable when taken* (Settings →
General → Holds and deposits) where an advance against a known supply is
taxable on receipt, as it is in Saudi Arabia. Then the deposit is invoiced with
the tax **inside** the amount the customer handed over, and at hand-over that
advance is deducted from the taxable amount, so the same money is never taxed
twice. Both settings work with tax-inclusive and tax-exclusive price lists.

**Who may do it:** anyone, unless a shop names a role or a person for *Hold
goods for a customer* under Settings → General → Approvals and access.

**Needs a connection.** A hold reserves stock and posts documents, so it is not
available offline.

---
## 11. Serial numbers (strict)

A serialized item can never be sold without its exact serials:
- Adding one opens a scan prompt; the serial must exist, belong to that item,
  be **Active** stock in this register's warehouse, and not repeat in the sale.
- Quantity is locked to the scanned serial count.
- Scanning a serial in the search bar adds its item with the serial attached.
- Returns require selecting exactly which sold serials come back.
- A serial already sold on a sale the shift close has not booked yet is
  refused, with that sale's number. ERPNext moves no stock until the close, so
  such a serial still reads *Active* in the warehouse, and the till used to
  offer it again only for ERPNext to refuse the sale. The till now asks
  ERPNext's own question for the version. A return of that sale gives the
  serial back at once, on every version (from 0.56.1: ERPNext 15 and 16 hold a
  returned serial until the return is posted, so LumenPOS posts it right away).
  If that posting cannot happen at that moment, the serial comes back when the
  shift closes, and the till says so when it is scanned.
- Everything is re-validated at submit; serialized items can't be sold
  offline or inside bundles.
- **Scan-only (optional).** Turn on *Require scanning for serial numbers*
  (Settings → General) to **block manual typing** when **selling** and on
  **returns**, serials must be read with a barcode scanner. Leave off if a
  register has no scanner.

---

## 12. Register & cash management

- The **"Register open"** pill in the top bar is a shortcut, click it to
  jump to the Register page (where closing happens).
- When the register is closed, the open-register prompt only blocks the
  **Sell** screen, the nav rail and the History/Register/Settings tabs stay
  usable. You can also open the register directly from the **Register** tab.
- **Open register** (mandatory before selling): enter the opening float →
  creates a **POS Opening Entry**. One live shift per register, if you
  already have one, you're offered **Continue that shift** or (only when the
  testing toggle in Settings → General is ON) **Open a new one anyway**.
- **Whose shift it is** (Settings, General, Register and shifts, *A shift belongs to*). *The
  cashier* (the default since 0.60.1): each cashier opens their own shift on the register and sells
  only on it, with their own drawer and Z-report. *The outlet*: one shift per register, and any
  assigned cashier sells on it. A site that already had shifts before 0.60.1 keeps the way it worked
  (where nothing was chosen, that was *The outlet*). On ERPNext 16 an outlet sells on one open shift
  at a time, so with *The cashier* each cashier there needs their own POS Profile.
- **Shifts at other outlets.** One person may hold open shifts at several
  outlets at once (a manager covering branches), and the Open Register screen
  lists them as a reminder, each with a button to its Register page. A shop that
  wants each person on one shift at a time ticks **One open shift per person**
  (Settings, General, Register and shifts, off by default): a new shift is then
  refused, by the server as well as on screen, until the open one is closed. On
  ERPNext 16 this also keeps an outlet free for its own cashier, since ERPNext 16
  sells on one open shift per outlet at a time.

  Nobody is ever locked out by it. A shift whose close was started no longer
  counts, even when that close failed (it keeps retrying on its own, see
  below). A shift at an outlet the person can no longer reach (the outlet
  disabled, or their access to it removed) does not hold them back either: the
  screen lists it with "ask a manager to close it". And a person who cannot
  close their shift themselves asks a manager, who closes it for them.
- **Closing a shift for someone else.** A manager's Register page lists every
  other shift still open at that outlet, with who opened it and when; **Close
  this shift** loads its figures, the manager counts its drawers and closes it
  like their own. For a cashier who went home, who may not close a register, or
  whose shift will not close. In *Per cashier* scope, where each cashier holds
  their own shift, this is the only way a manager reaches one from the till.
- **A close always goes through.** If the expected takings cannot be worked out
  when a shift is closed (with 0.52.0 on ERPNext 16 this failed on every shift,
  so none could close and each one kept its outlet shut), the counts are kept
  and the shift closes anyway. The close panel and Previous sessions say the
  figures are pending; they are filled in from the shift's **POS Closing
  Entry** when it consolidates (a Sales Invoice outlet's cash shift, which has
  none, gets them once they can be worked out again), and the variance alert
  goes out then.
- **A reason for a short or over.** When a counted drawer differs from what it
  should hold, the close panel asks why: the cashier writes the reason in their
  own words, or taps one of the shop's reasons, and can say what was done about
  it (for example recounted, reported to the manager). Both stay with the shift, show under its difference in **Previous
  sessions** and go in the variance email. Settings, General, Register and
  shifts: **Reason for a short or over** is *Optional* (the default, offered and
  never forced), *Required* (the register does not close without one, checked
  on the server too) or *Off*. With *Required*, **Ask only when the difference is more than** spares
  small differences (in the company currency, a drawer in another currency at
  its shift rate). The quick reasons start with six common ones the shop can change.
  A manager closing someone else's shift answers the same question.
- **An ERPNext accounting period that locks sales.** In ERPNext an *Accounting
  Period* locks the month it covers: ERPNext ticks every document in it as
  Closed when it is made, Sales Invoice among them. A POS Invoice is never
  locked, so the till sells all day, but the close posts the shift's sales as a
  Sales Invoice and ERPNext refuses it ("You cannot create a Sales Invoice
  within the closed Accounting Period ..."). With **Warn about locked
  accounting periods** on (Settings, General, Register and shifts, on by
  default), the Open Register screen says so before the shift starts, and a
  close it stopped names the period and what to do: a period made ahead of time
  is deleted in ERPNext (ERPNext 15 and 16 do not let anyone edit a period that
  has not ended), a period over a month that is really over has Sales Invoice
  unticked while the shift is retried. Then **Retry closing**. The system check
  lists every such period whatever the switch says. There is no need to "open"
  a month in ERPNext: posting is allowed whenever the Fiscal Year covers the
  date.
- **A shift past midnight (ERPNext 16).** ERPNext 16 takes sales only on a shift
  opened the same day. With **Keep a shift open past midnight** on (Settings,
  General, Register and shifts, on by default and shown on ERPNext 16 only), the
  first sale after midnight (or return, or sale made offline and uploaded then)
  closes the day in ERPNext and opens the next one by itself, the way ERPNext
  does it: a **POS Closing Entry** for the day's sales, closed at what the drawer
  should hold rather than counted, and a new **POS Opening Entry** that opens at
  that amount for each payment method. The shift carries on, and the cashier
  counts the drawer once, at the end, against the whole shift. The day's sales
  are posted in the background (the self-healer retries), and the Register page
  lists each closed day with its entry and whether it is posted, with **Try
  again** when posting failed. The shift's own close waits for those days, since
  a return in a later day may be of a sale in an earlier one. With the switch
  off, a shift from an earlier day refuses every sale until it is closed and a
  new one is opened. Before ERPNext 16 a shift simply runs past midnight.
- **A shift several cashiers sold on closes.** In *Per outlet* scope any cashier
  sells on the outlet's shift. ERPNext's own check on a POS Closing Entry wants
  every sale made by the cashier who opened it, so until 0.55.0 such a shift
  failed its close for good ("POS Invoice isn't created by user"). LumenPOS now
  makes that entry itself, with the checks that matter.
- **Cash in / out** during the day from the Register page (reason logged). Since
  0.61.0 putting money in and taking it out are two permissions (*Cash in*, *Cash
  out*), an amount must be above zero, and Settings, General, Approvals and access,
  **Cash out** sets two things: **A reason for every cash out** (on by default) and
  **Manager approval for cash out**: *Off* (the default), *Above an amount* (in the
  company's currency, a drawer in another currency valued at the shift's rate) or
  *Always*. When a cash out needs it, the till asks for a manager's passcode (the
  approvers and their PINs in Discount approval, or the master passcode), or the
  cashier sends a request that a manager approves from the **Approvals** tray. A
  request is for that shift, that drawer and at most that amount, and is used once.
  A manager (LumenPOS or System Manager) needs nobody's approval. Who approved shows
  under the movement on the Register page and in the audit log. Each
  movement is **netted into the expected cash** at close (expected = opening +
  cash sales + cash in − cash out) **and declared on the POS Closing Entry**
  itself: a **Cash In / Cash Out** total plus a **Cash Movements** table (under
  the payment reconciliation), so the Z-report shows exactly what was added to or
  taken from the drawer.
- **Fix a wrong payment method before closing.** If you rang a sale up on the
  wrong tender (e.g. Visa instead of Mada), do the **return + corrected sale
  while the shift is still open**, they're picked up automatically. Once you
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
  *Closing* with a **Failed** badge and an error, it does **not** silently
  reopen. A **↻ Retry closing** button (on the close panel, on the Sell
  screen's prompt, and in Previous sessions) re-runs it; ERPNext rolls a
  failed attempt back fully, so retrying never double-posts. A background
  **self-healer also retries stuck shifts every ~10 minutes**, so most resolve
  themselves. The next cashier can't open a new shift on that register until
  the previous close completes, no more "I accidentally kept selling on
  yesterday's shift."

  **Stuck overnight? Start a new shift anyway.** Blocking new sales until a
  close finishes is the safe default, but a close that keeps **Failing** into
  the next day shouldn't keep the store shut. On a *Failed* close, a manager
  (anyone who can close registers) sees a **"Start a new shift anyway"** option
with an opening-float box, on both the Sell-screen prompt and the Register
  page. It opens a fresh shift immediately and **leaves the failed shift in the
  background**, where the self-healer (and the **↻ Retry closing** button) keep
  retrying its consolidation until it succeeds. Nothing is lost: the old shift's
  invoices still consolidate on their own; you've just unblocked the till. Only
  offered when the previous close actually **failed**, a close that's merely
  still *finalising* must finish (or be retried) first.
- **Sales Invoice outlets list their invoices on the Z-report.** ERPNext's own
  table on a POS Closing Entry links POS Invoices, so an outlet that posts
  **Sales Invoices** directly left it empty and an accountant had nothing but
  the totals. LumenPOS adds a **Sales Invoices in this shift** table to the
  closing entry: every invoice the shift posted, with customer, date, total
  and whether it was a return.
- **Previous sessions**: the Register page lists closed (and still-finalising)
  sessions, takings, discounts, count differences, status, and direct links
  to each session's **POS Opening Entry** and **POS Closing Entry**.

---

## 13. Sales history

Search bar matches invoice no, customer name/ID, **mobile**, and **order ID**.
Filters: date range, status, document status, **channel** (walk-in / app),
**online order** (online only / in-store only), **payment method**, outlet,
**item**, **serial number**, amount range. The online-order filter reads the
site's `online_order` field (falls back to `custom_online_order` /
`is_online_order`); if no such field exists the filter simply matches nothing.
Each row shows the **cashier who made the sale**, a clean date/time, the
**payment method(s)** next to the total, the mobile/order info, and badges:
channel/ONLINE, DRAFT/CANCELLED, and **REFUND**. Click → receipt → reprint or
refund. On a site with several companies the list can be narrowed to one
company, a list that spans outlets names each row's outlet and company, and a user held to some
companies (ERPNext User Permissions) sees only theirs.

---

## 14. Offline mode

After the first online load the catalog (incl. barcodes) is cached locally,
this also makes everyday search instant. If the connection drops:
- an amber **Offline, N queued** pill appears,
- search and selling continue; finished sales are **queued** and sync
  automatically when the network returns (errors keep the sale queued and
  tell you why),
- needs a connection: the full sales history, customers, loyalty, store credit,
  gift cards, serialized items, delivery-app sales, register opening. (A sale this
  device made in the shift can be taken back without one, see below.)
- **The till survives a reload and a reboot.** The app itself (page, script,
  styles, fonts) is kept on the device by a service worker, so /pos opens with
  no connection at all and the shift carries on: cached catalogue, queued
  sales, the lot. It needs one online visit first, Settings → Status says
  **Opens without a connection: ✓ Ready** once it is in place.
- **Install it like an app.** From Chrome or Edge on the till, *Install* (or
  Add to home screen) puts LumenPOS in its own window with its own icon, no
  address bar, and it starts straight at /pos.
- The switch happens in seconds, both ways. Every request carries a deadline,
  so a connection that dies mid-call flips the till to offline instead of
  hanging on it, and while the connection is down the till asks the server
  every five seconds and comes back on its own the moment it answers. No
  page reload.
- **Every till refreshes its stock after an outage.** The moment a till is
  back online it uploads its queued sales and pulls a fresh copy of the whole
  catalogue, so its tiles include what the other tills sold while the
  connection was down, and it does so once more a minute later, for a till that
  was still uploading its own sales. The server never sells more than it has,
  whatever a tile showed.
- **A sale the server refuses never keeps the shift open.** A queued sale the
  server refused (the offline sales log says why) shows apart on the Register
  page. The close waits for sales not sent yet, never for refused ones: close
  the shift, taking the refused sales' cash out of the drawer before you count,
  and put it back once the next shift is open. A refused sale is sent again as
  soon as a shift opens, and on every upload after that.
- **Returns without a connection** (from 0.56.0, Settings, General, Register
  and Offline, on by default). Sales History lists this device's own sales of
  the open shift, those it sent and those still waiting (the search box finds
  them by invoice, customer or item), and any of them can be taken back there:
  pick the items and the reason, and refund in cash or the
  way the customer paid (never onto store credit, a gift card or cashback, whose
  balances live on the server). The till works the refund out the way ERPNext
  will (taxes, a line's own tax template, rounded totals and the site's rounding
  method, all as ERPNext does them), so the figure it shows is the one to pay
  out. The return waits in the queue behind the sale it takes back and is sent
  after it. The server checks everything again: ERPNext's figure is what posts,
  a difference within the outlet's payment tolerance is written on the credit
  note and in the audit log, a bigger one is refused with both figures, and the
  shop's switch and the right to make returns are enforced there too. Not
  offline: serial numbers, a sale paid with loyalty points, products the shop
  takes back only with an approval, a sale with a service charge, and a sale
  not sent yet at a shop that restricts returns of some products. The screen
  says which, and why.
- **Sent in the background** (from 0.56.0, Settings, General, Register and
  Offline, on by default). Sales and returns made without a connection are sent
  by the browser the moment the network is back, even with the till closed, in
  Chrome, Edge and on Android (the browser's Background Sync). The till still
  sends them itself whenever it is open, and the two take turns, so nothing is
  sent twice. Frappe v13 cannot serve the part of the till this runs in, so
  there the till sends them when it is open, as before.
- **Nothing posts twice.** Every sale and refund carries its own key from its
  first attempt. A sale whose answer was lost on the way back (the connection
  dropped after the server posted it) is queued under the same key, and the
  server answers it with the invoice it already made. Two uploads of one sale
  that reach the server together get the same answer. (Before 0.56.0 a sale
  made online got its key only when it was queued, so a lost answer could post
  it twice.)
- **The browser keeps the offline data for good, or says it will not.** A
  browser that has not agreed to keep the till's storage may clear it when the
  device runs short of space, with the sales waiting to be sent. The till asks
  as it opens, and when the browser did not agree, a banner says so, with
  **Protect** to ask again (Firefox asks you, Chrome and Edge agree once the
  till is installed as an app or bookmarked) and **Later** for a day. Settings,
  General, Register and Offline, *Warn when offline sales are not protected*
  (on by default).
- Settings → Status shows cache size and queued count; **Refresh offline
  catalog** re-pulls it. The General toggle *Cache only in-stock items*
  keeps the cache to your warehouse's stock.


### What is NOT available offline

Anything that has to reach ERPNext to be true: the full sales history (this
device's own sales of the shift are listed, and can be taken back), the customer
directory beyond the cached recent list, loyalty and store credit balances,
gift cards, serialized items, delivery-app sales, exchanges, and **opening or
closing a shift**. Open the shift while you have a connection, and the till can
sell through an outage on its own.

The service worker keeps only the app itself. It never answers an API call from
a cache, because a shop selling against numbers nobody can see is worse than a
shop that knows it is offline. Sales made offline are queued in the browser
database and posted when the connection returns.

(Frappe v13 does not support the hook this needs, so a v13 site keeps the old
behaviour: it sells offline as long as the tab stays open.)
---

## 15. Settings reference (gear icon → /settings)

| Tab | Contents |
|---|---|
| **Promotions** | List + Vend-style editor for all types, include/exclude rows, coupons, the dry-run **Test** panel. |
| **Cashback** | List + editor for cashback rules: percentage or fixed give-back, cap, minimum spend, expiry and activation-delay days, include/exclude products, schedule (dates/times/days), outlets, customer group, optional coupon, stackable. An **Accounting** card shows, per company, the cashback liability and expense accounts in use, what is waiting to be booked, what customers hold and the liability account's balance, with **Book to accounts now** for settings managers. The two accounts are chosen per company in **General → Company accounts** and are created automatically when left empty. |
| **Bundles** | Fixed-price bundles: components, price, outlets. |
| **Price Books** | Items with special prices for a period (validity + priority + outlets/customer groups); add items or **Excel/CSV import**. No ERPNext price list created, the master is never changed. |
| **Loyalty & Gift Cards** | Create/view loyalty programs; search/disable gift cards. |
| **General** | Split into groups, one at a time, each saying what it is for: **Features** (what the till offers, plus the one-tap favourites), **Register and shifts** (shift ownership, one shift per person, a shift past midnight on ERPNext 16, locked accounting periods, the reason for a short or over and its list, variance and overdue alerts, offline cache, returns without a connection, sending in the background, the storage warning), **Payments and delivery** (delivery apps with their price lists and per-method rules), **Other currencies** (the switch, the currencies the till sells in, their rates), **Customers** (what the new-customer form asks, field by field), **Companies** (whether gift cards, cashback and store credit are shared by the group or kept per company, what waits to be booked between companies and **Book now**), **Returns and refunds** (return window, return reasons, **what cannot be returned**, and the refund method rules), **Receipt**, **Languages** (which languages cashiers may pick), **Help for staff** (the ? help and its tours, the tour offered to new staff, what is new after an update, and a button to take the tour), **Accounts and gift cards** (per-company accounts, including the two that carry balances spent across the group, gift card expiry), **Approvals and access** (discount limit and over-limit method, master passcode, approver PINs, the shared Approver Role, permissions, audit log). One Save button covers them all. |
| **System check** | (Managers, and anyone named for *See the system check*.) What may stop LumenPOS working on this site and what to do, on one screen to read or photograph: the versions (and whether ERPNext is newer than the release LumenPOS was last tested on), ERPNext 16 set to refuse POS Invoices, change in another currency the books cannot take, each outlet's setup and how its prices carry tax (included or added on top), shifts stuck in Closing or open for more than a day, accounting periods that lock sales today or will, opening entries from an earlier day blocking an outlet on ERPNext 16, sales older than 3 days not in the books, currencies not set up, automatic rates not updating, missing performance indexes, LumenPOS errors and failed background jobs of the last 7 days, background jobs not running. **Copy for support** copies it as text. |
| **Status** | Version, outlet, price list, connection, cache size, queue, printer, register state. |
| **Approvals** | (Approvers only) Live tray of pending **discount and return** requests to Approve / Reject, shown in the left rail when discount requests are enabled or returns are window-limited. |

Each tab is shown only to users with permission for it (see **Roles** below),
and each action (create / edit / delete) is gated separately. Store-level
config (price list, warehouse, payments, taxes, printer, print format) stays
on the **POS Profile**, the single source of truth.

### Several companies on one site

One ERPNext site can hold several companies, a group. LumenPOS keeps each
company's sales, shifts and books apart, and lets the group decide what they
share.

**Customer balances (Settings, General, Companies).** Gift cards, cashback and
store credit are either:
- **Shared by the group** (the default, and how LumenPOS always behaved): a
  customer spends their balance at any outlet of any company that keeps its
  books in the same currency. The till spends the balance its own company
  issued first.
- **Separate per company**: a balance is spent only at the company that issued
  it. Another company's card is refused when it is scanned, with the name of
  the company that issued it.

Companies in different currencies never share a balance, whatever the setting.

**The books stay right.** When a balance issued by company A is spent at
company B, B's sale is paid from B's own liability account as always, and the
amount is recorded to be settled. Once a day, and whenever a manager presses
**Book now** on the Companies card, LumenPOS books ERPNext's own **Inter
Company Journal Entry**, one pair per day, pair of companies and kind of
balance:
- at B: debit *Due from Group Companies*, credit B's balance account;
- at A: debit A's balance account, credit *Due to Group Companies*.

B's liability is back to what its own customers hold, A's goes down by what its
customer spent, and A owes B for the goods B handed over. The two accounts are
created beside each company's receivable and payable accounts the first time
they are needed, or choose your own per company under **Accounts and gift
cards** (an asset and a liability that take no party). The Companies card shows
what is waiting, with the reason when an entry could not be booked, and links
to the latest entry pairs.

**Where rules apply.** Promotions, cashback rules, bundles and price books
apply to the **whole group**, **one company** (every outlet it has, including
outlets opened later) or **chosen outlets**.

**Who sees what.** LumenPOS follows ERPNext's **User Permissions**: a user
allowed only some companies (a User Permission on Company) sees and opens only
their outlets, their sales in History, their customers' figures, their gift
cards and holds, and the entries between their companies, and receives the cash
difference and overdue shift emails of those companies only. With several
companies the till names the company beside the outlet, and a manager switches
outlets from the top bar.

**Holds and returns.** A hold takes instalments and refunds at any outlet of
its own company, and hands the goods over at the outlet that keeps them. A
return is taken by a till of the sale's own company.

**Loyalty.** ERPNext ties a loyalty program to one company: see section 8.

---

## 16. Roles & permissions

LumenPOS access is governed entirely by **standard ERPNext DocType permissions**,
manage them in **Role Permissions Manager** (Frappe Cloud → desk → search
"Role Permissions Manager"), no LumenPOS-specific switches. The POS reads your
permissions on start and **shows/hides each tab, button and the Pay button
accordingly**, and every server action re-checks them.

LumenPOS ships two ready-made roles (assign them in the user's **Roles**):

| Role | Can |
|---|---|
| **LumenPOS Cashier** | Open the POS, sell, park, return, open/close & retry the register; read promotions/bundles/price books; find and add customers and open the Customers screen |
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
> install/update, and read and create on **Customer**, **Contact** and **Address**
> (ERPNext keeps a new customer's mobile as a Contact and its address as an
> Address) plus read on **Customer Group** and **Territory** (ERPNext reads them
> to enrol a new customer in a loyalty program), and what ERPNext 15 and 16 check
> as the user while a sale is made: **select** on **Account** (the customer's
> receivable account, by name only, never the account's record), and read on
> **Item** and **POS Profile**. So assigning it is enough to run a till on every
> version, adding customers included.
> Editing or deleting customers stays with the roles ERPNext gives it to. Tighten
> or widen any of it afterwards in Role Permissions Manager.

Discounts above the limit still need approval regardless of role, a manager
**passcode/PIN** at the till and/or an approved **discount request** (Settings →
General → *Discount approval* → over-limit method). Request approval is allowed
for holders of the configured **Approver Role** plus LumenPOS / System Managers.

---

### Changing a price at the till

Where an outlet allows it, the way ERPNext's own POS does (POS Profile, **Allow
User to Edit Rate**), a person who may **Edit price / discount** taps a line in
the cart and types its **Price**, in the money of the sale. It replaces the
list's price for that line, offers apply on top of it as on any price, the line
says "Price changed at the till", and the audit log records the item, the old
price and the new one. Clearing the field goes back to the list's price. The
server checks the outlet's switch and the rule again on every sale, and a hold
takes a price other than the list's only from someone who may give it. An item
with no price at all (US$0.00) can be sold this way.

### Who can do what (Settings → General → Approvals and permissions)

ERPNext roles decide what a person may reach. This table decides what they may
do at the till, and it can name **a role or one person**, so "the shift leads,
plus Fatima" is two rows rather than a role invented for one person.

| Action | What it covers |
|---|---|
| **Edit price / discount** | A manual discount on a sale line, and typing a new price on it where the outlet allows that (POS Profile, **Allow User to Edit Rate**) |
| **Make returns** | Creating a credit note from the till |
| **Return past the window** | Returning a sale older than the return window WITHOUT an approval request |
| **Exchange goods** | The one-step exchange (needs *Make returns* as well) |
| **Cash in** | Putting money in the drawer mid-shift (0.61.0: apart from cash out) |
| **Cash out** | Taking money out of the drawer mid-shift, and Settings can also ask for a reason and a manager's approval (0.61.0) |
| **Reprint a receipt** | Printing a receipt again: from History or Customers, or a second time from the sale's own screen (and with it, kicking the drawer). The first print of the sale just made always goes through. From 0.60.0 the till asks the server before every copy, in the browser too, and each one is in the audit log |
| **Open the register** | Starting a shift |
| **Close the register** | Counting the drawer and closing |
| **Hold goods for a customer** | Starting a hold, taking an instalment, handing over and cancelling |
| **See sales by salesperson** | The Salespeople page, and the commission on the shift report |
| **See the system check** | Settings, System check |
| **Sell on account** | Putting part or all of a sale on the customer's account (0.60.0) |
| **Take customer payments** | Taking a customer's payment of what they owe into the drawer (0.60.0) |
| **Set a customer's credit** | Allowing a customer on account and setting their credit limit, from Customers (0.60.0) |

Rules for the same action are an OR: any row that matches lets the person
through. **An action with no row is open to everyone**, so nothing locks up the
day you update. Six stay shut until somebody is named: *Return past the
window* (everyone else sends an approval request), *See sales by salesperson*,
*See the system check*, and the three of sales on account.
System and LumenPOS Managers always pass.

The till hides what a person may not do (the cash in/out panel, the reprint
button, the open and close buttons), and every one of those actions is checked
again on the server, so a stale browser tab or a direct API call cannot get
round it.

Upgrading from the four single-role fields (Edit price role, Make returns role,
Exceed return window role, Exchange role) needs nothing: each role that was set
becomes one row automatically on update, and a site that restricted nothing
stays open.

---
## 17. Troubleshooting

| Symptom | Check |
|---|---|
| Paid in full but "must be paid in full" error | Fixed in v0.8: tiny rounding gaps from promotion discounts/taxes are absorbed via the POS Profile **Write Off Account** (set one for clean books) or by a 1-cent payment adjustment. |
| Print format ignored | Set **Print Format** on the POS Profile (Print Settings section; format must target POS Invoice). Verify what loaded in Settings → Status. An ESC/POS printer IP takes priority when configured. |
| Promotion not applying | Open it → **Run test** with the real items: the report shows the failing gate, rows that match nothing, or items priced 0. |
| "Already has an open entry" when opening register | You have an open POS Opening Entry, continue that shift, or cancel the entry in the desk. The choice dialog handles it. |
| "Previous shift not finished / Retry closing" when opening | The last shift's closing hasn't finished consolidating (or failed). Click **↻ Retry closing**, it's safe to retry repeatedly. It also self-heals every ~10 min. You can't open a fresh shift until it completes (this is what prevents selling on a stale shift). |
| After midnight: "This shift was opened on ... ERPNext 16 accepts sales only on a shift opened today" | ERPNext 16's own rule. From 0.55.0 the first sale after midnight closes the day in ERPNext and opens the next by itself, unless **Keep a shift open past midnight** is off (Settings, General, Register and shifts). With it off, close the shift on the Register page and open a new one. |
| Closing fails with "POS Invoice isn't created by user" | A shift more than one cashier sold on, before 0.55.0. Update, then press **Retry closing** (or let the self-healer do it). |
| The price cannot be changed in the cart, though the POS Profile allows it | Before 0.55.0 LumenPOS had no price field. From 0.55.0 a line's price is typed in the cart, at an outlet whose POS Profile has **Allow User to Edit Rate** ticked, by whoever may **Edit price / discount** (Settings, General, Approvals and permissions). |
| A refund made without a connection shows "Rejected" in the offline sales log | The server refused it (the log says why: the sale was taken back elsewhere, a product needs an approval, or ERPNext's figure differs from what the till paid out by more than the outlet's payment tolerance). The money has left the drawer, so make the return again from Sales History with the connection on, and the close counts it. |
| The till says "Offline sales are not protected on this device" | The browser has not agreed to keep the till's storage for good. Install the till as an app (Chrome or Edge, the install button in the address bar) or bookmark it, then press **Protect**. The banner can be switched off in Settings, General, Register and Offline. |
| An offline sale was refused and the shift will not close | From 0.55.0 a refused sale no longer holds the close: the Register page shows it apart with its reason. Take its cash out of the drawer before you count, close, and put the cash back once the next shift is open: the sale is sent again then. |
| "Customer Deposit" shows on the sell screen, with a price | It is LumenPOS's own item for deposits on holds, and ERPNext's *Auto Insert Item Price If Missing* (Stock Settings) saved the first deposit's amount as its price. From 0.55.0 it is kept off the sell screen and a sale refuses it. Take deposits from the Holds screen. |
| Closing fails with "Cannot link cancelled document: POS Opening Entry" | The shift's POS Opening Entry was cancelled in ERPNext (ERPNext 13 to 15 allow that even with sales on it), and ERPNext refuses to close a shift against a cancelled entry. From 0.54.1 LumenPOS closes it against the entry's **amendment**, ERPNext's own way back: it uses one made by hand, or makes one (for example *POS-OPE-2026-00014-1*), and leaves a note on the shift. Press **Retry closing**, or let the self-healer do it. |
| **Close Register** stays greyed out after counting | The shop asks for a reason when a drawer is short or over (Settings, General, Register and shifts, *Required*). Write the reason under the count, or tap one of the quick reasons. Recount first if the difference is a mistake. |
| Closing fails with "You cannot create a Sales Invoice within the closed Accounting Period ..." (or, on ERPNext 13, "... any accounting entries with in the closed Accounting Period ...") | An ERPNext **Accounting Period** locks Sales Invoices on these dates, often one made ahead of time "to open" a month: it locks the month instead. The Register page names it (0.58.1). If the period has not ended, delete it in ERPNext (ERPNext 15 and 16 refuse to save any change to it until it ends, "Accounting Period cannot be created for a future date"); if it covers a month that is really over, untick Sales Invoice in it, press **Retry closing**, then tick it again. Delete any period made ahead for later months too. |
| Closing shows **Failed** with an error | Read the error (usually a stuck invoice or a transient lock). Hit **↻ Retry closing**; nothing is double-posted. If it keeps failing, open the linked POS Closing Entry in the desk and retry there. |
| "Close your open shift first" when opening a register | The shop has **One open shift per person** on and you still have a shift open at another outlet. Tap **Go to its Register page**, count and close it, then open this one. If you may not close registers, or the shift is at an outlet you can no longer open, a manager closes it from that outlet's Register page (**Other open shifts here**). An administrator can also turn the setting off. |
| "difference pending" on a closed shift | The shift closed, but its expected takings could not be worked out at the time. They are filled in from its POS Closing Entry when it consolidates; nothing to do unless the close itself shows **Failed**. |
| A close **keeps failing** and you need to keep selling | On a *Failed* close, a manager can click **"Start a new shift anyway"** (Sell prompt or Register page) to open a fresh shift now. The failed shift stays in the background and keeps retrying, its invoices still consolidate on their own. |
| A refund to store credit is refused: "This sale was paid by Cash, so it can only be refunded to..." | Before 0.58.0, every Save of Settings, General switched off **Allow refunding to Store Credit** (Settings, General, Returns and refunds). Switch it on again if your shop refunds to store credit. With *Restrict refunds to the original payment method* on, a sale can only be refunded the way it was paid, or to store credit when that switch is on. |
| The **?** button is missing, or the welcome or *What is new* card never shows | Settings, General, **Help for staff**: the three switches. *What is new* shows once per person after an update, and only news that applies to them. |
| The **On account** card or the *Put … on account* button is missing | Sales on account are off (Settings, General, Sales on account), the person is not named for *Sell on account* in Permissions, the sale has no named customer (the walk-in never buys on account), the customer is not allowed on their card, the sale is in another currency, or the till is offline. With a named customer the card says which. |
| "… owes … of a limit of …, so at most … can go on account" | The customer's credit limit (ERPNext's own, or the shop's default). Take more now, or a manager raises the limit on the customer's card. |
| "… owes … and has … in holds and orders not invoiced, of a limit of …" | The customer's open holds count against the limit too (ERPNext counts them). Take more now, hand over or cancel a hold, or a manager raises the limit. |
| Settings, Sales on account says a payment method named Credit Sale already exists | The shop made a payment method of that name on its own account. Rename it in ERPNext (Mode of Payment, Rename), then save Settings again: LumenPOS makes its own. |
| A cashier can still reprint a receipt | Before 0.60.0 the reprint rule was checked only on a network receipt printer. Update: the till now asks the server before every copy. |
| "You do not have access to the POS" | The user lacks **POS Invoice → read**. Grant the **LumenPOS Cashier** role (or POS Invoice access) in Role Permissions Manager. |
| A tab or the Pay button is missing for a user | That's the new permission gating, grant the matching permission (see **Roles & permissions**). |
| Item rings up at 0 | No Item Price on the **active** price list (book/app list overrides the default). |
| Can't add an item | Out of stock with negative stock disallowed, or it's serialized (scan required). |
| An item returned in this shift still shows 0, or "only 0 in stock" | Before 0.56.1 the till took sales off the stock number but put returns back only at the close. Update: from 0.56.1 a return puts the goods back at once, on every ERPNext version. On ERPNext 13 and 14, and for a serial number on 15 and 16, that happens by posting the return right away: if another shift was being closed at that moment, the item comes back when this shift closes (the Error Log says "return not posted at once"). |
| New features not visible after update | One hard refresh (Ctrl+Shift+R); from v0.5 asset URLs are version-stamped so this self-heals. |
| Old version shown in Status tab | The deploy didn't run. Check the bench dashboard. |

---

## 18. Customers (client lookup)

The **Customers** tab (left rail) is a fast way to find a client and see their
POS activity in one place.

- **Search** by name, phone/mobile, customer code, email or tax ID, and filter
  by **customer group**. The list is server-paginated (**Load more**).
- Open a customer for their **profile** (phone, email, tax ID, type, member
  since, last purchase), **balances** (loyalty points, store credit) and
  **lifetime stats** (sales count, net spent, returns count). On a site with
  several companies the balances and stats are those of one company, the
  till's own by default, with a picker to see another.
- Their **transactions** list shows every till sale and return (POS Invoices,
  including consolidated ones, or Sales Invoices in direct mode), filterable by
  **type** and **date range**, paginated. Click a row to view / print the receipt.

### A customer's account (0.60.0)

While the shop sells on account, a customer's page has an **On account** card: what they
owe, their credit limit and what it leaves, and each sale still owing, oldest first.

- **Take a payment** (Permissions: *Take customer payments*) takes the customer's
  money into this till's drawer, so the register must be open. It settles the oldest
  sales first, or the sales ticked. Never more than is owed, and a retry after a lost
  answer never takes it twice. It is ERPNext's own receipt voucher, a **Cash Entry** (a
  **Bank Entry** for a card or a transfer), allocated to each sale's entry, and the
  shift's close expects the money in that drawer. Print the payment receipt from the
  same card.
- **Allowed to buy on account** and **Credit limit of their own** (Permissions: *Set a
  customer's credit*): the limit is ERPNext's own, on the customer's card for this
  company. 0 removes it, so the group's, the company's or the shop's default applies.

The customer can also pay in ERPNext as usual (a Payment Entry or a Journal Entry
against the sale's entry).

**Performance:** every query is server-paginated and scoped to indexed columns,
and per-customer totals are computed only when you open a customer, never for
the whole list. The screen runs queries only while it's open, so it has no
effect on the Sell flow. The tab needs **Customer → read** (hidden otherwise),
which both LumenPOS roles are given.

---

## 19. Changelog

> **LumenPOS 0.1.0** is a standalone fork of this POS for the Frappe Marketplace,
> rebranded to the **Lumen** identity (primary blue `#1463FF`, Plus Jakarta Sans
> typography). The version history below is the shared lineage carried over from
> the original app.

### LumenPOS releases
| Version | Highlights |
|---|---|
| 0.61.1 | **What a customer owes, without their holds** (the owner agreed on 2026-10-04). *Owes*, on the payment screen's On account card and on the customer's page, was ERPNext's credit figure, which counts a hold that is not invoiced yet: a customer with a hold of 1,000 and no debt read "Owes 1,000" above a list that said nothing was owed. Now *Owes* is their balance in the books, and **Holds and orders not invoiced** shows apart. The limit is unchanged: holds still count against it, as ERPNext counts them, and when a sale is refused for the limit the message names the holds. **The shift clock** in the top bar reads like a clock, 07:01:20, and counts on the site's own time: a device set to another time zone (or a wrong time) used to show a new shift as hours old, and the Arabic read "7 ساعة". |
| 0.61.0 | **Cash out under control** (the owner: so nobody takes money out of the drawer as they please). **Putting money in and taking it out are two permissions** now, *Cash in* and *Cash out*: a rule a shop wrote on the old *Cash in / out* becomes one of each on update, so nobody gains or loses anything. **A reason for every cash out**, on by default. **A manager's approval for a cash out**, off by default, above an amount or always (Settings, General, Approvals and access, Cash out): the manager types their passcode at the till, or approves the cashier's request from the Approvals tray, the same way an over-limit discount is approved. A request covers that shift, that drawer and at most that amount, once. Managers need nobody's approval. Who approved shows under the movement and in the audit log, where every cash in and out is now recorded. Also: an amount at or below zero is refused (a negative cash in was really a cash out that nobody checked). In all thirteen languages. |
| 0.60.1 | **"The cashier" is the default for *A shift belongs to*** (Settings, General, Register and shifts): on a new site each cashier opens their own shift and sells only on it, with their own drawer and Z-report. A site that already has shifts keeps the way it worked: where nothing was chosen it stays on *The outlet*, written down once by the update, and a choice made in Settings is never changed. On ERPNext 16 an outlet sells on one open shift at a time, so with *The cashier* each cashier there needs their own POS Profile. In all thirteen languages. |
| 0.60.0 | **Sales on account** (asked by a shop in Zimbabwe). A customer takes the goods now and pays later, all of it or the rest after paying part, and the sale is a POS invoice like any other: the part on account is paid by LumenPOS's *Credit Sale* tender, and the same moment books the debt on the customer with its own Journal Entry, so it shows on their account and in Accounts Receivable at once (works on ERPNext 13 to 16 alike, nothing paid included). ERPNext's credit limit, or the shop's default, is checked at the sale. Settings, General, Sales on account: the switch, who may buy (customers allowed on their card, or any named customer, never the walk-in) and the default limit, with how it works. The customer's page shows what they owe sale by sale; **Take a payment** takes their money into the drawer as a Cash or Bank Entry, oldest sales first or the ones ticked, and the close expects it there. A return comes off the debt first and gives back only the rest. The receipt shows what is still owed, with a line to sign. Three permissions, closed until someone is named: *Sell on account*, *Take customer payments*, *Set a customer's credit*. Also: **a receipt printed again is really kept to whoever may reprint** (asked by a shop in Nigeria): until now the rule was checked only on a network receipt printer, and a refused copy fell back to the browser. The till now asks the server before every copy, a second print of the same sale counts, and each reprint is in the audit log. Fixed on the way: on ERPNext 14 and later a sale made in the first ten seconds of a minute showed in History as a raw timestamp ("2026-10-03 12:47:9"), and in Customers every time looked like that; both now read as the other sales do. The X-report shows when the shift opened without fractions of a second. In all thirteen languages. |
| 0.59.0 | **A reason for a short or over at the close** (asked by a shop in Zimbabwe). When a counted drawer differs from what it should hold, the cashier writes the reason in their own words, or taps one of the shop's quick reasons, and can say what was done about it. Both are kept with the shift, shown under its difference in Previous sessions and on the close panel, and sent with the variance email. A manager closing someone else's shift is asked the same. Settings, General, Register and shifts: *Reason for a short or over*, Optional (the default), Required (the register does not close without one, checked on the server too, optionally only past an amount) or Off, and the quick reasons, six to start with. In all thirteen languages, with its own help on the Register page and in What is new. Also: on a phone the Register page no longer runs off the screen (the cash in and out form stacks, and each payment in the count shows as its own block with Expected, Counted and Difference), and Settings shows the ready-made return reasons and reasons for a short or over in the screen's language (a reason left as it was is still saved in English, so every till keeps showing it in its own language). |
| 0.58.1 | **A locked accounting period is explained, and seen before it bites.** A shop in Zimbabwe had made ERPNext's *Accounting Period* for October ahead of time to "open" the month: ERPNext locks a month with it instead, ticking Sales Invoice and every other document Closed, so the till sold all day and the shift's close was refused ("You cannot create a Sales Invoice within the closed Accounting Period OCTOBER - ..."), and ERPNext 16 would not even let them edit the period, since it had not ended. Now the Open Register screen says when an accounting period locks Sales Invoices today (a Sales Invoice outlet is told that no sale can be posted), a close it stopped names the period and what to do (delete one made ahead of time, or untick Sales Invoice in one over a month that is really over, then **Retry closing**), and the system check lists every period that locks sales today or will. Settings, General, Register and shifts: *Warn about locked accounting periods* (on). In all thirteen languages. **Errors read as text:** the Register page and the Open Register screen showed ERPNext's message with its HTML (`<strong>OCTOBER - ...</strong>`). A failed close is now kept as plain text, and one kept before is shown without the tags. |
| 0.58.0 | **Help on every screen.** A **?** button at the top of the till opens the help of the screen in use: the everyday tasks in short steps, with **Show me** for the ones that have a tour. Five tours light up the real buttons one by one (getting around, a first sale, refunds and exchanges, opening and closing the shift, selling in another currency): they only show and explain, nothing is sold or changed. Someone new is offered the tour the first time they open the till, and after an update each person sees once what is new for them, filtered by what they may use. Settings, General, **Help for staff** has the three switches (all on). In all thirteen languages. Also: the Arabic **Retrieve Sale** read "استرجاع بيع", the word the till uses for a refund, and now reads "المبيعات المعلقة" (the parked sales), the cart's **Discard** reads "مسح" instead of "تجاهل", and the top bar now names the Insights and Holds pages (it said Sell there). **Fixed: saving the General settings switched off *Allow refunding to Store Credit*** (since 0.29.0 the screen never read that switch back, so every Save stored it off, and a refund to store credit was then refused unless the sale had been paid from a wallet). The screen now reads every switch it saves, a test saves the screen unchanged and checks that nothing moved, and managers are told once, through *What is new*, to check the switch. |
| 0.57.0 | **Salespeople.** Settings, General, Features, *Salesperson at the till*: Optional (as before), Required (a sale, a gift card sale and an exchange's new sale are refused without one, by the server too, except a sale the till already queued offline), or Off (the till asks for nobody and records nobody). **Sales by salesperson**, a **Salespeople** tab on the Insights page: per person over a period, for this outlet or every outlet of its company, the sales and returns (how many and the net amount before tax), the net, and the commission ERPNext works out at each person's rate, with the sales nobody was named on as their own row and a CSV download. ERPNext's own Sales Person reports cannot show this for a POS Invoice outlet (the close merges the shift into a Sales Invoice without the salesperson). The Register page and the X-report list the shift by salesperson. For managers until someone is named for *See sales by salesperson*. **System check** (Settings, a new tab): what may stop LumenPOS working on the site and what to do, on one screen to read or send, from ERPNext 16 refusing POS Invoices and shifts stuck in Closing to each outlet's tax setup, sales not in the books, failed background jobs and the LumenPOS errors of the last week. **Copy for support** copies it as text. For managers until someone is named for *See the system check*. **A phone:** the top bar keeps to the screen (the clock and shift timer give way, the buttons scroll inside the bar), so History, Register, Settings, Insights and the new pages fit a phone. **Frappe Marketplace audit:** every argument of every LumenPOS endpoint now carries a type hint, written so that Frappe does not enforce it (nothing a till sends can be refused because of it), and the service worker file is read without `open()`: the audit's last warnings are gone. **Four more languages:** Portuguese (Brazil), Persian (right to left, in the Vazirmatn type), Russian and Turkish, the next four ERPNext is used in, screens and server messages alike, so the till now speaks thirteen. Also: *Hold goods for a customer* is now offered in the permissions table (the server has had it since 0.50.0), and the dark theme's scrollbars are dark too. |
| 0.56.2 | **Holds work again.** From 0.55.0 the till's **Hold** button was refused on every site ("not whitelisted"): the price check added to holds in 0.55.0 had been placed where it took the web access of the function that starts a hold, and the tests call that function directly, so they never saw it. A hold starts again as before, with the 0.55.0 price check kept. **A gift card is sold without tax where the outlet adds VAT.** ERPNext puts the outlet's tax template back on any sale whose tax table is empty, so at an outlet whose POS Profile carries a tax template a gift card of 100 was invoiced at 115, 15 of it tax (ERPNext 13 to 16). The card's line now carries a zero tax template, as a hold's deposit already did, and the tax is charged when the card is spent. That template also takes in a tax account added to the outlet's template later, for deposits too. **A return gives back only the tax its sale charged.** ERPNext refills an empty tax table from the outlet's current template, so a sale made with no tax (before the outlet had a template, or at an outlet without one) came back taxed: a sale of 90 refunded 108. Such a return's lines now carry the zero template too, in a refund, an exchange and a return made without a connection. |
| 0.56.1 | **A returned item is back on sale at once, on every version.** A shop on ERPNext 16 could not sell an item to the next customer after taking it back in the same shift: the till counted the sale but not the return until the shift closed, so the item read 0, left the grid and was refused ("only 0 in stock"), although ERPNext 16 already had it back. Now the till counts returns as ERPNext 15 and 16 do (a bundle's components too), on the tiles, in the price checker's other branches, in the answer to every sale, return and exchange, and on the favourites. ERPNext 13 and 14 count a returned item only once the return is posted to the books, so there LumenPOS posts a return made at the till (or in an exchange) right away, with the sale it takes back, through ERPNext's own consolidation, as the shift close would. If that cannot happen at that moment, the return stands and the item comes back at the close, and the tile says so. (Frappe's Marketplace does not allow an app to replace or patch ERPNext's own stock check, so this is done with ERPNext's own posting.) **The close posts such a shift.** ERPNext merges a shift's sales and its returns separately, and on 15 and 16 it posts the sales at the time of the last sale but the returns at the close, so a resale of a returned item failed the close ("1.0 units of Item ... needed"). The close now merges the shift in parts wherever a sale relied on an earlier return, each posted before the next, as ERPNext already does for serial numbers. A shift without that closes exactly as before. Also: offline, a sale or a return moves the stock of an item even when it is not on screen, and the favourites follow every sale and return. A returned serial number sells again at once too: ERPNext 15 and 16 hold one until its return is posted, so LumenPOS posts that return right away there as well. |
| 0.56.0 | **Returns without a connection.** Sales History now lists, while the connection is down, the sales this device made in the open shift, and any of them can be taken back there, even one still waiting to be sent: refunded in cash or the way the customer paid, at the figure ERPNext will post, which the till works out as ERPNext does (taxes added or included, a line's own tax template, a tax on the previous row, rounded totals to a fraction or to whole units, and each of Frappe's rounding methods, checked against real credit notes on ERPNext 13 to 16). The return is queued behind its sale and posted after it, and the server checks it all again: ERPNext's figure posts, a small difference is recorded on the credit note and in the audit log, a bigger one is refused with both figures. Settings, General, Register and Offline: *Returns without a connection* (on). **Sales sent in the background.** A sale or return made offline is sent by the browser as soon as the network is back, even with the till closed (Chrome, Edge, Android), and the till and the browser take turns so nothing is sent twice. *Send queued sales in the background* (on). **A warning when the browser may clear the offline data**, with a button that asks it again. *Warn when offline sales are not protected* (on). **A sale never posts twice**: a sale made online now carries its key from its first attempt, so one whose answer was lost and that the till then queued (or the cashier tried again) is answered with the invoice already made, where before it could post a second time. Refunds carry their own key the same way, and two uploads of one sale or refund that meet at the server get one answer. |
| 0.55.0 | **A shift can run past midnight on ERPNext 16.** ERPNext 16 takes sales only on a shift opened the same day, so a shop open until one in the morning could not sell after midnight, a sale made offline could not upload, and the Register page would not close while that sale waited: the till was stuck both ways (a shop in Zimbabwe). Now the first sale after midnight closes the day in ERPNext and opens the next one by itself, the way ERPNext does it (a POS Closing Entry for the day, a new POS Opening Entry), while the shift carries on. The cashier counts the drawer once, at the end of the shift, against the whole shift: what each payment method should hold is carried into the next day's entry. The day's sales are posted in the background, and the Register page lists each closed day with its entry and whether it is posted, with a retry if posting failed. Settings, General, Register and shifts: *Keep a shift open past midnight* (on by default, shown on ERPNext 16 only). **An offline sale the server refuses no longer keeps the shift open.** The Register page still waits for sales not sent yet, but a sale the server refused now shows apart with its reason, and the shift can be closed: its cash is taken out before the count and put back once the next shift is open, and the sale is sent again at once. **A shift several cashiers sold on closes.** In *Per outlet* scope (the default) any cashier sells on the outlet's shift, but ERPNext's own check on a closing entry wants every sale made by the cashier who opened it, so such a shift failed its close for good with "POS Invoice isn't created by user", on every version. LumenPOS now makes that entry itself, with the checks that matter, as it already did for opening entries. **Selling in another currency without a connection** (asked by the same shop, whose customers pay in ZWG): a shift now fixes its exchange rates as it opens, so every till knows them, and a sale to a currency's walk-in is queued offline at that rate, priced from the walk-in's own list when it has one. The server posts it only at the shift's rate, and refuses it with both rates otherwise. **A price typed at the till**, where the outlet allows it the way ERPNext's POS does (POS Profile, *Allow User to Edit Rate*), for whoever may *Edit price / discount*: tap a line, type its price in the sale's money, offers apply on top, the audit log keeps the old and the new price, and the server checks it all again. A hold no longer takes a price the person may not give. **The receipt of a sale in another currency** showed an offer's saving in the outlet's number (saved €13.20 for a saving of €3.30 at 4 dollars to the euro), since 0.51.0. It now shows it in the sale's money. **The Customer Deposit item is no longer sold as a product.** LumenPOS's own item for deposits on holds could show on the sell screen, and where ERPNext's *Auto Insert Item Price If Missing* had saved the first deposit's amount as its price, it sold like goods, with offers and VAT on it and no hold behind it. It is now kept off the grid, search, price check and the offline copy, like the gift-card item, and a sale refuses both as a product line. |
| 0.54.1 | **An outlet listing "All Item Groups" shows its products again.** The sell grid matched an outlet's item groups, and the group chip a cashier taps, by name only, so an outlet whose POS Profile listed *All Item Groups* (or any parent group) showed "No products found": every item sits in a group beneath it. It now reads them the way ERPNext's own POS does, each group with every group beneath it, on the server and in the catalog kept on the device for instant search and offline selling. *All Item Groups* listed is the same as nothing listed, so the chips show the item groups as usual. Reported by a shop whose till showed no products at all. **The grid says why it is empty:** when products were found but none has stock at the outlet (and out-of-stock items are hidden), it says so and names the setting, instead of "No products found". **Offers and cashback rules on an item group cover its sub-groups too**, as ERPNext's pricing rules do: an offer on *Food* missed every item filed under *Food > Burgers*, and excluding a group let its sub-groups through. The till and the server work it out the same way, from the offer's own list of groups. **A shift whose POS Opening Entry was cancelled in ERPNext closes again.** Its close failed for good with "Cannot link cancelled document: POS Opening Entry" (a shop's report), so its sales never reached the books. It now closes against the entry's amendment, ERPNext's own way back from a cancelled document: one made by hand is used (a draft one is finished), otherwise LumenPOS makes it, and the shift carries a note naming both entries. |
| 0.54.0 | **One open shift per person, when a shop wants it.** Settings, General, Register and shifts: *One open shift per person* (off by default). On, nobody opens a new shift while they still have one open at another outlet: the server refuses it, naming the open shift, and the Open Register screen says so, with a button that goes straight to that outlet's Register page to close it. Off, a person may still hold shifts at several outlets (a manager covering branches), and the reminder now says how many are open (it said "another register" above a list of five). Asked by a shop in Zimbabwe whose one login held five shifts at five outlets: on ERPNext 16 each of those also kept that outlet's own cashier from opening a shift, since ERPNext 16 sells on one open shift per outlet at a time. **Nobody is locked out by it:** a shift whose close was started, even a failed one, does not count, nor does one at an outlet the person can no longer reach (listed with "ask a manager"). **A manager closes anyone's open shift** from the outlet's Register page (*Other open shifts here*), which in *Per cashier* scope was out of a manager's reach until now. **A close always goes through:** when the expected takings cannot be worked out (the 0.52.0 failure on ERPNext 16 that kept every shift of that shop open), the counts are kept, the shift closes, and its figures come from its POS Closing Entry at consolidation, with the variance alert sent then. **A user holding only the LumenPOS Cashier (or Manager) role can sell on ERPNext 15 and 16:** ERPNext checks, as the person selling, that they may select the customer's receivable account and read the Item (and, on 16, the POS Profile), so such a user was refused with "User don't have permissions to select/read this account" (then Item, then POS Profile). Both roles now get select on Account (the name only, not read) and read on Item and POS Profile on update; on ERPNext 13 and 14 nothing was missing. Found by this release's strict shift tests, which now open, sell, close and consolidate as a cashier holding nothing else. |
| 0.53.0 | **The till in more languages, starting with the ones ERPNext is used in most.** A study of public ERPNext sites (their default language), Frappe Cloud installs of each country's app and traffic to Frappe's sites ranks the languages after English: Arabic, Spanish, German, Chinese, French, Thai, Indonesian, Vietnamese. **Spanish, German, Chinese (Simplified), French, Thai, Indonesian and Vietnamese** join English and Arabic, every screen and every message. Thai uses IBM Plex Sans Thai, the family of the Arabic font, and Chinese the system's own Chinese font. The top bar's language control becomes a short list when a shop offers more than two, and **Settings → General → Languages** chooses which ones cashiers may pick (all by default, English always). **The server now answers in the till's language.** Until now a refusal from the server (a PIN that is too short, a serial that cannot be sold, a shift that cannot close) came up in English even on an Arabic till, because LumenPOS carried no translations for its server messages. It now carries them for every language it speaks, and the till sends its language with each request, so ERPNext's own messages follow too, whatever the user's language in the desk. LumenPOS never renames a text that Frappe or ERPNext already translate, so the desk keeps its own wording. **A serial number cannot be offered twice.** A serial already sold on a sale the shift close has not booked yet still reads Active in ERPNext, because the stock moves only at the close, and the till used to offer it again, only for ERPNext to refuse the sale with a message about the warehouse. The serial check, the scanner and the sale now ask ERPNext's own question for the version and refuse it first, naming that sale. After a return of the sale, ERPNext 13 and 14 give the serial back at once, while ERPNext 15 and 16 hold it until the close books the sale, and the till says so. **The cart keeps its room for the goods** (asked by the owner: with coupons, a bundle, VAT and two other currencies on screen, only one line of the sale was left visible). Coupon, order discount and note are now three small buttons that open their field when tapped, the breakdown under the total folds away under *Details* (each device remembers whether it is open) with the saving shown beside it, and the other currencies share one line. On a 1554 by 874 window the lines went from about 100 to about 430 pixels, and they never shrink below three lines: what sits under them scrolls first. **Also:** the top bar no longer breaks onto two lines in a long language (below 1400 pixels the user's name makes room for the outlet), the title of every settings card sits beside its icon (it was pushed to the far end of the card), and a long label in the left rail (Configuración, Einstellungen) is set smaller instead of running under the page. |
| 0.52.1 | **Tested on a real Frappe and ERPNext 16, and fixed where it differs.** LumenPOS has been offered for v16 since 0.37.0 but had only ever run on v13 to v15. A v16 installation (Frappe 16.35, ERPNext 16.36, Python 3.14) now runs every test, and this is what it found. **The X-report** stopped with "SQL functions are not allowed as strings in SELECT" (reported by a shop in Zimbabwe), because v16 no longer accepts a count or a sum written as text in a list query. That query and four more of the same kind (store credit balances, the customers kept for offline use, the quantities already returned on an invoice, and the order cashback is spent in) now use a form every version runs. **Closing a shift** failed, because v16 renamed the closing entry's table of invoices. **A sale paid partly with loyalty points** showed "Partly Paid" with the points still owing, though the books were right. It now shows paid, as on v13 to v15. **ERPNext 16's rules for every POS sale are said plainly before a sale fails.** An outlet sells with one open shift at a time: a previous shift still closing is finished first, and anything else still open (another cashier's shift, or one from ERPNext's own POS) is named with what to do, so on v16 cashiers who each keep their own shift need a POS Profile each. A shift sells only on the day it opened, so after midnight it is closed and a new one opened. A site set to make Sales Invoices from the POS (POS Settings, which is how a new v16 site starts) cannot take the POS Invoices an outlet makes, and the till says where to change it. **Change on a new v16 site.** A new v16 site does not record change as its own ledger entry, so it cannot take change from one drawer for money paid into another. Selling in other currencies now turns that on, and on every version a sale whose change the books could not take is refused with the reason. |
| 0.52.0 | **Automatic exchange rates, when you want them.** In Settings, General, Other currencies, tick *Update exchange rates automatically*, then set each currency to a **fixed rate** (yours) or an **automatic** one: once a day LumenPOS reads the published rate from ExchangeRate-API (free, about 160 currencies, the Saudi riyal, UAE dirham and Zimbabwe gold included) and saves it in ERPNext as that day's rate, less the currency's **margin** when a shop sells a volatile currency at a market rate. A rate typed for the day always wins, **Update now** fetches at once, and when the service cannot be reached the last rate stays and the reason shows under the currency. Shifts keep the rate they started with, as before. **Change in the sale's currency, when you want it.** Tick *Give change in ZWG* on a currency and the change of a sale in it comes back in it, from its own drawer, instead of in local money from the main drawer. The payment screen, the receipt and the shift close follow, and the choice holds for the whole shift, like the rate (asked by a shop in Zimbabwe). The till now also shows change in the money of the account ERPNext really books it from, so an outlet whose POS Profile names its own change account no longer shows it in the wrong currency, and a change account in a third currency is refused at the sale instead of failing the close. **Also:** switching the outlet from the top bar refreshes the screen that is open. Register, History, Customers, Holds and Settings load their figures when they open, so after a switch they kept showing the previous outlet's until they were opened again. The open screen is now rebuilt for the new outlet at once (the same fix as in Lumen Restaurants). And the product grid no longer sticks on "Loading…" the first time a till opens on a new device. And with *Sell in other currencies* switched off, opening a shift no longer asks for a float in another currency's drawer (the drawers stay on the outlet for when it is switched back on). |
| 0.51.1 | **An item missing from a customer's own price list is converted.** A customer billed in another currency with their own price list in it (on the customer, their group, or the currency's walk-in customer) paid the outlet's price as a number in their currency for every item that list did not price: a US$5 item was charged ZWG 5 instead of ZWG 175 (reported by a shop in Zimbabwe), and in the other direction a dearer currency was overcharged. Such an item now keeps the outlet's price and is converted at the shift's rate, and the cart shows the prices of the customer's own list, so the cart and the payment screen always show the same total. **Setting up another currency works on Frappe v15.** On a v15 site whose outlets' default customer sits in a group customer group ("All Customer Groups"), saving Other currencies set nothing up: v15 refused the currency's walk-in customer, so each currency stayed "Set up when you save" while its cash drawer was created on its own. The walk-in customer now goes into a group ERPNext accepts, a currency is set up whole or not at all, and when it cannot be, the reason shows under it. The exchange rates show to anyone who may see the settings (they hid behind "Save the currencies first" for anyone who may not change them), without ERPNext's "Unable to find exchange rate" message box. A payment method the shop already had under the drawer's name ("CASH ZAR") whose account is in another currency is no longer taken as that currency's drawer, which counted rand in dollars: the setup says so and asks for a rand account or another name. And the setup runs on every save of the settings, not only the first, so an outlet or a company added later gets its drawer in each currency (ERPNext gives a new company's cash account to the first cash method it finds, which could be a currency drawer: the drawer gets its own account back). |
| 0.51.0 | **Sell in other currencies.** A customer billed in dollars (ERPNext, Customer, Billing Currency) now buys in dollars: the sale, its receipt and its books are in dollars at the rate of the shift, and ERPNext's shift close merges it in that currency and balances. A walk-in paying in dollars is switched to dollars in one tap, on the cart or on the payment screen. Prices, offers and discounts stay in the outlet's currency and convert; a customer's own list in their currency is used as is. Each payment is typed in the money handed over, so a tourist can pay part in dollars and part in riyals, and change always comes back in local money from the main drawer. Every drawer in another currency keeps its own float, cash in and out and count, and the X-report lists the rates. Switched on and set up (accounts, a *Cash USD* drawer on every outlet, a *Walk-in USD* customer, the rates) in Settings, General, Other currencies. Gift cards, store credit, cashback, loyalty redemption, holds and exchanges stay in the outlet's currency. **After an outage every till refreshes its stock**, once on reconnecting and once a minute later, so the tiles include what the other tills sold meanwhile. **Refunds:** the refund screen fills in its refund line by itself again (since 0.36.0 it stayed empty until the cashier pressed Split), one refund line takes the whole refund ERPNext computes, tax included, instead of the screen's estimate, and the internal *Exchange* tender is no longer offered as a refund method. **The new-customer form is the shop's own:** every field hidden, optional or required, for individuals and companies apart, and any Customer field can be added, so a shop outside Saudi Arabia is no longer held to the national address (Settings, General, Customers; out of the box it is the form it always was). On Frappe v15 a new customer no longer fails with "Cannot select a Group type Customer Group" on a site whose default customer group is a group, and the company address no longer spills out of the window in Arabic. **New fields can be added to Sales Invoice again.** Since 0.49.0 LumenPOS marked the customer name on Sales Invoice as an indexed field, to keep History's search fast. Frappe does not allow that marking on that kind of field, so from then on adding any field to Sales Invoice failed, from Customize Form or from another app, with "Fieldtype Small Text for Customer Name cannot be indexed". The marking is removed on update and is never set on such a field again. Nothing gets slower: the index itself stays, because Frappe never removes an index on that kind of column. LumenPOS's own fields were never affected. **Several companies on one site.** Gift cards, cashback and store credit are shared by the group or kept per company, chosen in Settings, General, Companies (shared is the default and how LumenPOS always behaved). A balance spent at another company is settled with ERPNext's own Inter Company Journal Entry, once a day or on demand, so each company's books stay right, and companies in different currencies never share. Promotions, cashback rules, bundles and price books apply to the whole group, one company or chosen outlets, and a bundle is checked again at the sale. ERPNext User Permissions on Company now hold a user to their companies' outlets, history, customer figures, gift cards, holds, entries and alert emails. A hold is served at any outlet of its company. A loyalty program is created for the company you choose. **The LumenPOS Cashier role is enough on its own for customers:** a cashier holding only that role was refused a new customer at the till and never saw the Customers screen; the role (and LumenPOS Manager) now gets read and create on Customer, Contact and Address, and read on Customer Group and Territory, on update, like its POS Invoice rights, still adjustable in Role Permissions Manager (editing and deleting customers is not included). **Fixes found on the way:** saving the settings no longer erases the PIN of every named discount approver (any save did, even one that changed nothing, so approval by PIN stopped working until the PINs were typed again), nor a per-company deposit account set in Desk; the receipt printed right after a sale no longer counts as a reprint (and a copy printed later from History does); a Sales Invoice outlet prints to its receipt printer; and a sale paid by gift card or cashback is no longer refunded back onto that tender, which credited the account without restoring the balance: that part is refunded as store credit. |
| 0.50.1 | **A hold now quotes the price with tax on it.** At an outlet that adds VAT at the till, a hold used to total the shelf prices and nothing else, so a customer who had paid it "in full" was short by exactly the tax and handing the goods over failed with a mismatch. The tax is worked out on the day of the hold and frozen on it, so the balance on the screen is the money the till will actually take. Open holds are re-costed on update. **Holds are also switched off by default now** (Settings, General, Holds and deposits): a shop that never puts goods aside sees no button and no screen. And the Holds and deposits settings card, which rendered as a wall of run-on text, is laid out like the rest of them. |
| 0.50.0 | **Holds and deposits.** A customer can leave a deposit and have the goods kept for them. Ring the items up, press **Hold**, take what they are paying today: the goods are reserved with a Sales Order so no other till sells the last one, and the money goes to a **liability** account, not revenue, because the shop is holding it. The new **Holds** screen shows what is held, for whom, paid and still to pay, flags anything past its date, and takes the next instalment, hands the goods over, or cancels and refunds. Handing over sells at the price agreed the day of the hold and collects only the balance. Tax follows the shop: by default the deposit is untaxed and the goods are taxed in full at hand-over, or switch on taxable deposits (as Saudi Arabia requires for an advance against a known supply) and the tax declared on the deposit is deducted at hand-over instead of charged twice. |
| 0.49.0 | **The till opens with no connection at all, and installs like an app.** Until now an outage was survivable only as long as nobody reloaded the tab: the page itself came from the server, so a reload or a reboot meant a till that could not sell. The app now keeps itself on the device (a service worker holds the page, its script, styles and fonts), so /pos opens offline and the shift carries on with the cached catalogue and the offline queue. Settings → Status shows **Opens without a connection**. It can also be installed from Chrome or Edge, own window, own icon, starting at the till. Nothing about the data changed: no API answer is ever served from a cache, and opening or closing a shift still needs the server. |
| 0.48.0 | **Who can do what, by role or by person.** The four separate role fields (edit price, make returns, exceed the return window, exchange) are now one table in Settings, with four more actions a shop can hold back: **cash in / out**, **reprint a receipt**, **open the register** and **close the register**. A rule names a role or a single person, and several rules for the same action mean any of them passes, so "the shift leads plus Fatima" no longer needs a role invented for one person. An action with no rule is open to everyone, so updating locks nothing, and the roles a shop already set move across on their own. The till hides what a person may not do and the server refuses it again, so a stale tab cannot get round it. |
| 0.47.0 | **Exchange in one step.** A customer swapping one item for another used to be two errands, a refund and then a fresh sale, with the cashier holding the arithmetic in their head. Now: History, **Exchange…**, pick what comes back, ring up what they are taking instead, and the payment screen shows one figure, the difference. Dearer and you collect it with any tender, cheaper and you give it back by the normal refund rules, equal and the drawer never opens. The credit note and the replacement sale post together in one request, so there is no moment where the goods are back but the replacement is not, and the matched part settles through a clearing tender (**Exchange**, a liability account created on first use) so cash and card totals only ever see the difference. Everything a return enforces still applies: restrictions, the return window and its approval, serials, sets. A shop can name its own **Exchange role** in Settings. |
| 0.46.4 | **The stock on a tile is live and honest, and the till notices the network in seconds.** The quantity on a product tile is now what you can actually still sell (ERPNext holds back anything sold on a shift that has not been consolidated yet, and that hold is now visible instead of turning up as a refusal), and it moves the moment a sale or a return posts instead of waiting for the next catalogue refresh. Offline: every request now has a deadline, so a connection that dies mid-call flips the till to offline in seconds instead of hanging, and while it is down the till asks the server every five seconds and comes back by itself, no page reload. The POS Closing Entry of an outlet that sells as **Sales Invoice** now lists those invoices, because ERPNext's own table only links POS Invoices and an accountant was left with totals and no documents. The payment screen also asks the server once instead of twice, and asks while the cashier is still scanning. |
| 0.46.3 | **The text reads like a person wrote it, and the Arabic is complete.** Every em dash is gone from the app and from this guide (852 of them), replaced by the punctuation a person would actually type. Where a dash was the only thing separating two parts of a sentence, the sentence itself was rewritten: the register screen used to run the shift name straight into the next word ("Session POS-SES-0001closed."), and now reads "Session POS-SES-0001 closed. POS Closing Entry ACC-PCE-0001 consolidated its invoices." Separately, 58 labels still came up in English inside the Arabic till: the PIN lock and reset screens, the offline upload prompts, the payment method rules, the shift ownership and alert settings, and the store credit refund switch. They are translated, so every string on screen now has Arabic. |
| 0.46.2 | **The Arabic in the till is written the way people write it.** The interface text carried 386 vowel marks (tashkeel) left over from earlier translation work, which reads like machine output and is not how a shop writes Arabic. They are gone, in every screen, with no other wording change: same keys, same 1071 strings, only the marks removed. |
| 0.46.1 | Fixes two cards that the new General grouping put in the wrong place: the gift card settings on the **Loyalty and gift cards** tab, and the **Audit log** tab, both of which could come up empty. The gift card accounts card inside General now sits with the other accounts, where it belongs. |
| 0.46.0 | **Say what the shop will not take back, and find every setting faster.** A new **return restriction** refuses a return by item, item group (and everything under it), brand or tag, at every outlet or only at some. Each rule is one of two strengths: the item comes back only when an approver allows it (the cashier sends the same return approval request the till already uses for a late return), or it never comes back at all. The refund screen marks the line, says why in your own words, and switches the button to the approval request, and the server checks again before a credit note posts, so a stale tab or a direct call cannot slip past. Set them up in **Settings, General, Returns and refunds**. **The General tab is now split into groups** the way the tabs on the left split the rest of Settings: Features, Register and shifts, Payments and delivery, Returns and refunds, Receipt, Accounts and gift cards, Approvals and access. Each group says in one line what it is for, one group shows at a time, and the Save button still saves them all together. Returns and refunds now holds the return window, the return reasons, the new restrictions and the refund method rules in one place. |
| 0.45.3 | **A promotion with no dates and no times works again, wherever it was created.** Frappe fills an empty time field with the moment of the save, so a promotion or a cashback rule created outside the POS settings screen (in the ERPNext desk, by an import, or by a script) came back with a start and an end a fraction of a second apart. Read literally that is a daily window open for a blink, which switched the offer off for the rest of the day, at random, depending on which side of a second the save landed. LumenPOS now treats any window shorter than a minute as no window at all, in the till and on the server, and clears those two times in the database right after such a save, so older records heal themselves. Outlets were checked at the same time and were always correct: a promotion, a cashback rule or a price book with no outlet ticked applies to every outlet, proven on real Frappe 13, 14 and 15. **The return reasons LumenPOS ships are now English with an Arabic translation**, so an Arabic till shows Arabic while the credit note keeps one wording whatever language the cashier works in. A list an admin has edited is left untouched, and a reason typed by hand is shown exactly as typed. |
| 0.45.2 | **The performance indexes are now kept by Frappe instead of being rebuilt on every update.** Version 0.45.1 made the rebuild work. This release removes the need for it: Frappe drops an index when it does not know the column is indexed, so LumenPOS now registers those columns with Frappe, the same way Frappe's own index helper does. On a shop with millions of invoices an update no longer spends minutes rebuilding indexes that were dropped moments earlier. One index also turned out to be a duplicate: the key that stops the same sale posting twice is already unique, and a unique column is indexed, so LumenPOS no longer builds a second index on it. LumenPOS still checks on every update and builds anything genuinely missing, and **Settings, Status, Performance indexes** still lists them. Tested on real Frappe 13, 14 and 15: refreshing the invoice tables now leaves every index in place. |
| 0.45.1 | **The performance indexes are now rebuilt reliably when LumenPOS is updated.** LumenPOS adds up to eight database indexes that keep a large shop fast: the check that stops a sale posting twice, shift reports, customer search, loyalty lookups and the stock check ERPNext runs on every sale. Frappe removes some of them whenever an update refreshes the invoice tables, so LumenPOS rebuilds them at the end of every update. That rebuild failed quietly into the Error Log whenever the update had saved a setting just before it, because Frappe refuses to change a table in the middle of unsaved work. On the three test benches (Frappe 13, 14 and 15) none of the eight existed. The update now saves its work before building each index, the way Frappe's own index helper does, and on all three benches an update now leaves all eight in place. **The demo builder now runs as Administrator only.** It used to switch itself to Administrator when a System Manager started it, which the Frappe Cloud Marketplace security audit flags. It now asks you to sign in as Administrator instead (on Frappe Cloud, use Login as Administrator on the site's dashboard). |
| 0.45.0 | **Cashback: a customizable wallet customers earn on sales and spend later, booked properly to the accounts.** You set the rules in Settings, Cashback: give back a percentage of the sale or a fixed amount, cap it, require a minimum spend, choose which products count (include or exclude by item, group, brand or tag), pick outlets and a customer group, run it on set dates, times and weekdays, and optionally behind a coupon. Earned cashback carries its own validity (expires after N days, with an optional delay before it can be used), and rules can stack or compete like promotions. At the till the payment screen shows what a sale will earn, the customer's available cashback appears as its own **Use cashback** tender, and paying with cashback never earns fresh cashback on the part it paid for. A return gives back the unspent part, and a nightly job writes off what expires. **Accounting (full accrual):** each company chooses a cashback liability account and a cashback expense account in Settings, General, Company accounts, and both are created automatically if left empty. Earned cashback is booked as an expense against the liability, spent cashback leaves the liability through the sale's own payment, and expired or returned cashback is reversed. These are booked as one summary Journal Entry per company, day and outlet cost center, never one per sale: every night for the days that have ended, or at once with **Book to accounts now** in the Cashback tab. Once everything is booked and the shifts are closed, the liability account equals what customers hold. The feature is on by default, can be switched off in Settings, General, and earns nothing while it is off. |
| 0.44.3 | **The Insights dashboard now uses the full width of the screen.** The page was squeezed into a narrow column of about 350 pixels with the rest of the screen empty, so the dashboard switched to its phone layout and stacked every chart in one column. It now fills the content area, and on a normal screen the charts sit side by side as designed. Checked on lumenv14: the dashboard frame went from 310 to 1,138 pixels wide and the four summary cards now share one row. |
| 0.44.2 | **Insights never sits on "Loading…" when something is wrong.** If Lumen Reports could not report its status, or reported a state this page does not recognise, the Insights page used to show "Loading…" with a Refresh button indefinitely. It now says plainly that Lumen Reports cannot show the dashboard right now, and shows Lumen Reports' own explanation or error underneath when there is one. |
| 0.44.1 | **Insights now works on Frappe v14.** Lumen Reports 1.2.0 added support for Frappe v14, but the Insights page still turned away anything older than v15 with its own message, so a v14 site with Lumen Reports installed never reached the dashboard. The page now trusts Lumen Reports whenever it is installed, and only a site without it is told the minimum Frappe version, which is now v14. On v13 the page still explains that the dashboard needs a newer Frappe. The number in that message now comes from the server, so it cannot fall out of date again. And if Lumen Reports itself fails while creating the dashboard, the manager now sees a plain message saying so, with nothing half-created left behind, instead of a server error. Tested on a real Frappe 14.101.1 and ERPNext 14.92.14 site with Lumen Reports 1.2.0: the dashboard, all ten charts, the filters, and a manager's access with and without a Lumen role. |
| 0.44.0 | **A new Insights page: full sales statistics inside the till.** LumenPOS does not draw its own charts. Instead the Insights page shows a ready-made sales dashboard from the separate **Lumen Reports** app, embedded right inside the POS: takings by day and by outlet, the payment mix, top items, busy hours and more, all with filters. If Lumen Reports is not installed, the page explains how to get it. If it is installed, one tap builds the dashboard and it appears in place, in the same language and theme as the till. The page is for managers, and there is a switch to turn it off in Settings. It needs **Lumen Reports 1.1.0 or newer** on **Frappe v15 or v16**: on v13 and v14 the page says so plainly rather than showing a broken screen, and a cashier who needs access is told exactly which role an administrator grants. The two apps stay at arm's length and neither depends on the other, so each still works installed on its own. |
| 0.43.1 | **Public contact unified to hello@lumen-solutions.co.** `app_email`, the `pyproject.toml` author, the compatibility error message and the website guide now use **hello@lumen-solutions.co**, matching LumenPDF Studio and Lumen Reports. No functional change. |
| 0.43.0 | **Relicensed to the GNU Affero General Public License v3.0, and a trademark policy added.** LumenPOS moved from GPL-3.0-or-later (since 0.39.0) to AGPL-3.0-only. The GPL only requires publishing source when the software is distributed. Since LumenPOS is the kind of software people run as a service for others, a modified copy could be offered to shops without its changes ever being shared, because running a service is not distribution. The AGPL closes that: anyone who runs a modified LumenPOS for other people over a network must offer them its complete source. Earlier releases keep their own terms: everything up to 0.38.0 stays MIT, and 0.39.0 to 0.42.1 stay GPL-3.0-or-later, permanently, for anyone who already has a copy under those terms. See NOTICE for the full history. A new TRADEMARKS.md sets out that the LumenPOS name and logo are trademarks separate from the code licence, so a fork must use a different name, and every source file now carries a short header stating the licence and the trademark. AGPL-3.0 is on the Frappe Cloud Marketplace's accepted licence list, and it combines cleanly with ERPNext's GPLv3 (both licences say so, in their own section 13). **Two issues an automated code review found in the demo builder are fixed.** It used to change how every document on the site saves, for the length of a run, then change it back afterwards, so it could backdate a demo's invoices to the days they belong to. That technique is risky in a way that has nothing to do with what it was used for: if the run ever crashed before the "change it back" step, every save on the site would stay altered until the next restart. It now uses Frappe's own, much narrower mechanism for the same job, which only ever touches the handful of document types a demo run creates, and cannot leak into a crash. Separately, several places in the demo builder and in the v13/v14 store-credit fix (0.41.0) saved to the database more often than they needed to, because the functions they called already save that state on their own. Those extra saves are removed. The ones that genuinely protect a multi-hour run against a late failure are kept and explained in place. No visible change for anyone running the app. |
| 0.42.1 | Demo builder: customers are now enrolled on the loyalty programme, so the demo actually shows points being earned. A till receipt only earns points when the sale carries a programme, and it takes that from the customer record, so without enrolling anyone nobody in the demo ever earned a point. |
| 0.42.0 | **A one-call demo builder, for showing the app to somebody.** On an empty site it fills in everything a shop needs and then trades for a month: a VAT template, three branches with their own warehouses, 48 products with barcodes (some with serial numbers), 150 customers, every payment method, the till settings, a loyalty programme, price books, bundles, a coupon, gift cards, and **over a thousand invoices spread across thirty days**, with a realistic mix of baskets, payment types, discounts and refunds. Every shift is opened, closed and consolidated the normal way, and today's shift is left open so the till opens onto live trade. Nothing is faked: every sale goes through the same code a cashier's tap goes through, so the promotions, receipts, loyalty points and stock are all real. It is available to a System Manager only, it is not attached to any button, and it refuses to run on a site that already has more than fifty posted sales, so it cannot be pointed at a working shop by accident. |
| 0.41.0 | **v13 and v14 are now tested on real installations, not just declared supported.** Three benches were built from scratch (v13, v14 and v15) and a full shift was run on each: open the register, sell, sell a serial numbered item, refund both, close the register and let ERPNext consolidate into Sales Invoices. That found three faults, all fixed here. **Closing the register failed on v13**, because older Frappe does not prepare a document's sub tables the way newer Frappe does, so building the Z report tripped over the payments table before anything had been added to it. **A promotion saved without a happy hour never applied, on every version.** Frappe stamps the current time into a time field left empty, so those promotions ended up with a daily window a fraction of a second wide and were skipped all day. Promotions already saved start working again with nothing to do, and new ones no longer store a window nobody set. **Store credit could not be refunded or spent** on a till that posts POS Invoices, which is the normal setting: the record kept the sale in a field that only accepted Sales Invoices, so the refund failed outright. That field now accepts either kind, and existing records are labelled automatically on upgrade. **Loyalty points never showed at the till, on every version.** ERPNext was collecting the points correctly, but the call that reads them back needs the customer's programme named explicitly, and LumenPOS was leaving that out, so every customer looked like they had no programme and no points. A customer who is not enrolled is now reported as such instead of failing silently. **Paying part cash and part points is refused by ERPNext v15 and v16 unless one box is ticked.** The sale itself is correct on every version: ERPNext deducts the points and the invoice posts with nothing outstanding. But v15 added a check that looks only at the cash and card taken, sees less than the total, and refuses the sale with "Partial Payment in POS Invoice is not allowed". The fix is to tick **Allow Partial Payment** on the POS Profile. That is safe here, because LumenPOS already refuses any sale whose payments do not add up to the posted total. Until it is ticked, LumenPOS now says exactly that at the start of the sale instead of letting ERPNext fail at the end. |
| 0.40.0 | **Installs on v13 as well, so all four versions are covered.** The requirement is now **v13, v14, v15 or v16** from one branch. The only thing that had been blocking v13 was our own package declaring it needed Python 3.10, while Frappe v13 runs on Python 3.7 to 3.9. Every line of the app was checked and none of it needs anything newer than 3.7, so that floor was lowered. Serial numbers already adapt to the version (older sites use the classic serial field instead of v15's bundle), and the places where LumenPOS calls ERPNext's own code report a clear message if a release ever moves one. |
| 0.39.1 | **Cleared the marketplace security audit.** The index checks asked the database "does this index exist?" in a way that built the table name into the SQL text, harmless in practice (the names are fixed constants in our own code, never user input), but it's the same shape as a SQL-injection flaw and the audit flagged it. Rewritten to ask `information_schema` instead, where the table name is passed as a **bound value**, so there is nothing interpolated and nothing to justify. No behaviour change. |
| 0.39.0 | **Licence changed to GPL-3.0-or-later.** From this release LumenPOS is published under the **GNU GPL v3 (or later)** instead of MIT. Two reasons: it keeps LumenPOS consistent with **ERPNext, which is GPLv3** and whose code LumenPOS calls directly; and it means anyone distributing a modified version must publish their changes, so the work can't be taken and closed. Nothing changes for you as a **user**, you can still run, modify and even sell it; a shop running LumenPOS has no obligations at all. **Earlier releases up to 0.38.0 remain MIT**, that grant cannot be revoked and isn't. |
| 0.38.0 | **Also installs on v14, and serial handling adapts to the version.** The requirement is now **v14, v15 or v16** from one branch. Serial numbers moved into a *Serial and Batch Bundle* in v15; LumenPOS now detects whether a site has that and reads serials the right way for each, on an older site it uses the classic serial field instead of querying tables that don't exist there. That removes two places (opening a refund, searching history by serial) that would have failed outright on v14. **v13 is not offered**: it runs on Python 3.7 to 3.9 while this app needs 3.10, so a v13 bench cannot install it at all. |
| 0.37.0 | **Runs on Frappe/ERPNext v16 as well as v15.** The app declared `frappe <16` / `erpnext <16`, so bench and the Frappe Cloud marketplace treated it as v15-only and wouldn't offer it to a v16 site, the reason the marketplace listing couldn't add a Version 16 build. The requirement is now **v15 or v16 from the same branch**. The four places LumenPOS calls ERPNext's own code (loyalty points, POS-invoice consolidation, the credit-note builder) now go through a single compatibility layer: if a future ERPNext release moves one of them, the till shows one clear message naming what broke and the ERPNext version, instead of an internal error mid-sale. |
| 0.36.0 | **Split a refund across payment methods.** A customer who paid partly by card and partly in cash can now be refunded the same way: add as many refund lines as you need, each with its own amount and (where the method requires it) its transaction reference. A running **"x left to allocate"** turns green when the split matches to the cent, and the Refund button stays disabled until it does. **Direction is respected**: collecting money may use any tender, but refunding is still limited to the methods your refund rules allow, and now *every* line is checked, not just the first. Store credit is issued from the split rows, so a part-credit refund credits exactly the part you allocated. |
| 0.35.0 | **Shift schedules and a forgotten-shift alert.** Build a reusable **POS Shift Schedule** (a timetable of shifts, one schedule can serve many outlets, and a shift whose end time is earlier than its start is understood to cross midnight), then attach it to an outlet on its POS Profile. LumenPOS checks hourly and emails a chosen role when a register is **still open well past when its shift should have ended**, with a configurable grace period, and a simple "hours after opening" fallback for outlets with no schedule. Each shift is reported **once**. Deliberately **no auto-close**: a till closed without a real cash count produces figures nobody can trust, so this alerts a human instead. |
| 0.34.0 | **Every cashier gets their own till PIN.** The lock screen used to take a **shared** manager passcode, so once it circulated, "who unlocked this till?" had no answer and changing it meant telling everyone. Each person now sets their **own** 4 to 8 digit PIN the first time they meet the lock screen, and unlocking checks *theirs* (the unlock is written to the audit log with their name). **Forgot your PIN?** emails a 6-digit code, valid 15 minutes, that lets them set a new one. There's deliberately **no manager override**, the lock screen guards an unattended till, it doesn't authorise anything. PINs are stored only as a salted hash, never in readable form. *(The separate approvals passcode for over-limit discounts is unchanged.)* |
| 0.33.0 | **Jump from a customer's purchase straight to History.** Opening one of a customer's past sales now offers **Open in History**, which takes you there with that sale already open, so a refund is one step away without duplicating the refund flow into the Customers screen. History understands a linked sale (`/history?invoice=…`), searches across all outlets for it and opens it automatically, since the sale may belong to another branch. |
| 0.32.0 | **Approvals you can actually judge, and no dangling shift paperwork.** (1) **An approval request now shows what it's for**, the cart lines being discounted, or the items being returned, instead of asking a manager to approve a bare percentage. (2) **Nothing unconfirmed survives a shift**: pending (and approved-but-unused) requests are voided when the register closes, so an approval can't be spent on the next shift's drawer. (3) **Cancelling or deleting a shift now cancels its ERPNext opening entry**, so no orphan "Open" entry is left behind, that orphan was the thing that used to make the next cashier resume a dead shift. A shift that recorded cash movements refuses deletion outright and must be cancelled instead. |
| 0.31.0 | **Control how a basket may be paid.** (1) **Payment restrictions**, a new **POS Payment Restriction** record blocks a payment method when the cart contains a matching product, by **item, item group (including everything under it), brand or tag**, optionally only at chosen outlets. Classic use: *no gift cards on a buy-now-pay-later method*. The till greys the method out and says why; the server re-checks before posting, so a stale tab, a queued offline sale or a direct API call can't slip past. (2) **Required transaction references**, under **Settings → General → Payment Methods** you can mark a method as needing a terminal or transfer reference (with your own label, e.g. *Approval code*). The payment screen shows an input per split, highlights a missing one and won't let the sale complete until it's filled, so a disputed card payment can always be traced back. |
| 0.30.0 | **Counter answers, manager access, and correct Arabic numbers.** (1) **"Do you have it at the other branch?"**, the price checker's all-stores figure now expands into a per-warehouse list (available, reserved, this-store-first), so the question is answered at the counter instead of by phoning around. (2) **A manager is never stranded**: managers now see every outlet in the outlet picker, and the POS opens on the outlet where you already have a live shift rather than an arbitrary assignment. (3) **Search results can't be overwritten by a stale response**, typing fires several searches, and a slow early one arriving last used to wipe the correct results. (4) **Arabic/RTL amounts read correctly**: every formatted amount is now bidi-isolated, so a refund's minus sign stays attached to its number instead of migrating to the wrong end. |
| 0.29.0 | **Serialized returns work again, and refunding to credit is a choice.** (1) On ERPNext v15 a sold serial is no longer reliably marked "Delivered", and LumenPOS was using exactly that flag to decide what could come back, so a serialized item offered **nothing to pick** and couldn't be returned at all. Returnable serials are now worked out from LumenPOS's own record of what was sold and what has already come back on a previous credit note. The same check runs at return time, so a serial still can't be returned twice. (2) That also removed a per-serial database lookup, so a serialized invoice opens quickly instead of crawling. (3) New setting **Allow refunding to Store Credit**, previously a refund could always be parked on the customer's account, which some shops don't permit. Turning it off leaves money-back only, with one sensible exception: credit the customer actually *spent* on that sale can always go back to credit, otherwise a credit-paid sale would have no refund method at all. |
| 0.28.0 | **Who owns a shift, and an alert when the drawer doesn't balance.** New setting **A shift belongs to**: *The outlet* (default, unchanged, one shift per register and any assigned cashier sells on it) or *The cashier*, each person opens their **own** shift on that register and can only sell on their own. That lets several people share one counter while each stays accountable for their own drawer and gets their own Z-report; the sell screen says whose shift it is and the Pay button is disabled on someone else's. There is deliberately **no manager override** for selling, a handover is close + reopen, which is instant. Separately, **Email an alert on a large closing variance** notifies a chosen role when a counted amount differs from expected by more than a threshold, it records and notifies, and never blocks the close. |
| 0.27.0 | **A return belongs to the outlet handling it.** ERPNext builds a credit note by copying the original sale, including its outlet, warehouse and cost centre. So when one branch took back an item sold by another (an online order, say), the refund left *that branch's* drawer but was recorded under the **selling** outlet: the branch's own closing didn't see it, and returned stock went back to the wrong warehouse. Returns are now re-stamped onto the till actually processing them, outlet, warehouse, cost centre and price list, on the header and every line, so the money and the stock land where they really moved. Returns across **different companies** are refused outright rather than posting into the wrong company's books. |
| 0.26.0 | **The drawer count can't be wrong any more.** Three guards, each from a real incident. (1) **Typed money is never trusted to a number input.** A browser silently reports an *empty* value for anything it can't read in its own locale, `1,500`, a stray space, Arabic-Indic digits, while the text stays visible on screen. That is how a register was opened with cash in the drawer and recorded **0.00**. Every money box (opening float, cash in/out, drawer counts) now reads what was actually typed, handles both `1,500.50` and `1.500,50` and Arabic digits, refuses to continue on something unreadable, and asks you to confirm a genuine zero float. (2) **Stale closing screen.** If a sale lands from another till or tab after the closing screen was opened, the figures the cashier counted against are out of date, the close is now refused with a note to refresh and re-check. (3) **Queued offline sales block the close**, since they belong to *this* shift's drawer; the close screen shows how many are waiting with an **Upload now** button. |
| 0.25.0 | **A shift can never be resumed, opening is always a fresh shift.** The register session's own status is now the only thing that decides whether a shift is live. Previously a failed or slow end-of-day close left ERPNext's opening entry marked "Open", so the next cashier was offered *"continue the previous shift"*, reviving a dead shift onto a new day's drawer. That prompt is gone, along with the resume path, the orphan-shift chooser and the "allow a second open shift" setting (which no longer means anything). Opening now does one thing: check this register for a live session, if one is genuinely open you're told so, if the last one is still finalising you get a new shift immediately and it keeps consolidating in the background, otherwise a clean new shift. A stale opening entry left by a failed close or by the stock POS can no longer block a store from opening. |
| 0.24.0 | **Built for a big shop, not just a demo.** (1) **Sales search rebuilt.** One wide search across invoice number, customer, mobile and order id, every part a "contains" match, one of them across a join, let the database choose between using an index and reading the whole table, which is why the same search could be instant one minute and time out the next. Search now runs several precise, individually-indexed lookups and merges them, then fetches the row detail by key, with a bounded fallback for mid-word matches. (2) **More indexes**, including the one ERPNext itself needs on every submit (it checks reserved quantity per cart line against the biggest table on the site) plus customer-name and loyalty lookups. (3) **Settings → Status now lists every performance index** as Built / Missing / Not-on-this-site, with a **Rebuild missing indexes** button that runs in the background, index builds can fail quietly on a busy table, and previously that was invisible. (4) **Slow sales now explain themselves:** a sale over 2.5s writes one log entry breaking the time into pricing, insert, ERPNext submit and receipt, so "the POS is slow" becomes a measurement instead of a guess. |
| 0.23.0 | **Fits the site it lands on (host-site adaptation).** LumenPOS installs on sites it has never seen, and the same field name can mean different things on each. (1) **Fields are now detected by type, not just by name.** A site whose `online_order` field holds the marketplace order *number* used to break the Yes/No online filter (it compared an order number to 1 and matched nothing), now a flag is only used as a flag, a text field only as text, and that order number is picked up as the order id instead of being invisible to search. (2) **A customer is identified by mobile, not by name.** Creating a customer whose mobile the site already knows now **reuses** that record instead of adding a duplicate, names repeat endlessly, mobiles don't, and the check also looks in the site's *own* mobile field. (3) **The host's automation gets what it needs:** when the site defines its own mobile field, LumenPOS fills it too, so site rules that build a customer's name from it still fire (otherwise POS-created customers came out bare-named and collided). Offline customer sync uses the same identity rule. |
| 0.22.0 | **Four money-and-access fixes proven on a live pilot.** (1) **An item could ring up at 0.00**, a blank cell in a price-book import, or a draft Item Price, became a real 0.00 price that shadowed the correct one. Prices now only count when they are **actually in effect**: the date window is respected (a future-dated row no longer applies early, an expired one no longer lingers), and a 0.00 rate is treated as the unfilled cell it is. (2) **The opening float is the drawer's, not every "Cash" method's**, sites that type delivery apps or "On Account" as Cash had the float written to all of them, counted once per method on the X-report and close, and change coming off whichever sorted first. Everything drawer-related now resolves **one** drawer mode, and closing self-heals shifts opened before the fix. (3) **X-report works for any cashier on the till**, reading a shift's figures no longer requires having opened it (closing and cash in/out still do). (4) **Index on the sale idempotency + session keys**, every sale was full-scanning the invoice table to check for a replay; invisible on a small site, seconds per sale on a large one. Also adds `scripts/check_endpoints.py`, a pre-release guard that catches dead endpoints, accidentally-public helpers, stolen decorators and bad keyword args. |
| 0.21.0 | **Dynamic receipt fields, pull any field from the POS Profile or the sale onto the receipt (incl. ZATCA QR).** The receipt designer gains a **Custom fields** section: add a row, pick the **source** (POS Profile or the sale invoice), pick the **field** from a dropdown (custom fields included), give it a **label**, choose **Text** or **Image / QR**, and place it in the **Header** or **Footer**. At print each value is pulled from that outlet's POS Profile or the posted invoice, so a **ZATCA QR** stored as an image field shows as the QR, and country-specific or profile fields (CR number, branch info) print automatically. Fields are **global by default, with per-outlet extras** (via the "Editing receipt for" selector), and show in the live preview. *(Deploy runs a migration to add the two JSON stores; nothing shows until you add fields.)* |
| 0.20.0 | **A slow or failed close never blocks the next shift.** The **Register Session** is now the single gate for opening: the moment a cashier closes a shift, the register is free, you can **open a new shift right away, no matter the closing status** (Pending / Queued / **Failed**). The POS Closing Entry consolidation keeps finalising (and self-healing) in the background, so no invoice is lost. Previously an in-progress or failed consolidation forced a "retry the closing" gate and could keep the outlet shut. The Open Register dialog now always offers **Open a new shift** alongside an optional **Retry closing**. *(An already-**open** register still goes straight to selling and won't ask you to open.)* |
| 0.19.2 | **"You still have another register open" warning.** Since multiple outlets can be open at once, the Open Register dialog now shows a warning banner if you already hold an **open shift on another outlet**, listing each one (outlet + session), so you don't forget to close a drawer elsewhere. It refreshes as you switch outlets in the dialog. |
| 0.19.1 | **Outlet choice moved into the Open Register dialog.** The outlet picker now lives **inside the "Open register" dialog** (an **Outlet** dropdown above the opening-float field) rather than in the top bar, you choose which outlet to open the register for right where you enter the float. Picking another outlet reloads it: if it's already open you go straight to selling on it, if it's closed the dialog opens that outlet. The top bar goes back to showing the current outlet as plain text. (Refines 0.19.0.) |
| 0.19.0 | **Outlet switcher. Choose which outlet you're operating.** If you're assigned to more than one POS Profile, the top bar now shows an **outlet dropdown** (next to your name) instead of fixed text. Pick another outlet and the POS reloads everything for it, its register, catalogue, prices and customers, so you can open/close and sell on whichever outlet you choose. Your choice is remembered across reloads. Switching clears the current cart (with a confirmation when it isn't empty), and the other outlet's shift stays open (pairs with the 0.18.1 multi-outlet-shifts fix). Single-outlet users see no change. The API also verifies you're assigned to an outlet before letting you operate it. |
| 0.18.1 | **Multi-outlet shifts, a shift on one outlet no longer blocks opening another.** Opening a register on a second POS Profile (e.g. **Jeddah**) while you had one open on another (e.g. **Riyadh**) failed with *"You already have register Riyadh open. Close it before opening another."* The "already open" check for a cashier's native POS Opening Entry was scoped to the **user across all outlets** instead of the **specific register**. It's now scoped to the outlet, so each register runs its own independent shift (opened and closed separately), a manager or multi-outlet user can have Riyadh **and** Jeddah open at once. Double-opening the *same* register is still blocked, as before. |
| 0.18.0 | **Per-outlet receipts (first per-profile setting).** The receipt designer (Settings → General → Receipt) now has an **"Editing receipt for"** selector: leave it on **All outlets (default)** to design the shared receipt as before, or pick a **POS Profile** to give that outlet its own receipt, its own logo, header/footer, template and shown fields, with **Save for this outlet** and **Reset to default**. Outlets with a custom receipt are marked with a •. At the till, each outlet renders its own receipt if it has one, otherwise the default. It's fully **opt-in**, with no per-outlet override set, nothing changes. This is the groundwork for making other settings per-profile too. |
| 0.17.6 | **Publisher metadata aligned to Lumen Solutions.** `app_publisher`, `app_email`, the `pyproject.toml` author, and the license copyright now read **Lumen Solutions** / **support@lumen-solutions.co**, matching the marketplace listing and website. No functional change. |
| 0.17.5 | **Cleared the Frappe Marketplace submission-gate audit (security + code quality).** Addressed all 15 findings the automated Semgrep audit reported, with no behaviour change: converted an exception passed to `.format()` to `str()`; rewrote the price-book search queries into fixed, fully-parameterized SQL (removing the injection pattern); replaced `filter()` calls with comprehensions; scoped the approval-decision realtime event to the waiting cashier instead of broadcasting it site-wide; and annotated the genuinely-safe cases, dynamic table-name queries whose user input is already bound as parameters, the intentional register-close state commits, and the no-PII approval ping, with justified `# nosemgrep` comments. Also stripped a stray UTF-8 BOM from a source file. |
| 0.17.4 | **Pricing Rules stay ignored at the till (the fix that actually sticks).** LumenPOS already set `ignore_pricing_rule` on every sale, but ERPNext's POS flow re-reads that flag from the **POS Profile** on each save and flipped it back, so a Pricing Rule could re-apply on submit, override the price book, and land the invoice "Partly Paid". LumenPOS now mirrors its always-ignore behaviour onto the profile itself: it sets the POS Profile's **Ignore Pricing Rule** to on (once, automatically) the first time it prices a sale on that profile. No manual step, and your price books, promotions and bundles are always what posts. *(ERPNext Pricing Rules keep working on non-POS documents.)* |
| 0.17.3 | **Redeeming a gift card (or store credit) no longer errors on the Receivable account.** Paying with a gift card failed with *"Customer is required against Receivable account 1310 - Debtors"*, the gift-card tender was resolving to the company's **receivable/debtors** account, and a payment posted there demands a customer party (which a tender leg doesn't carry). Now the gift-card (and store-credit) payment is pinned to **its own liability account**, so redeeming correctly *reduces the liability* we owe the holder instead of touching debtors. Also hardened setup: the gift-card account can never be a Receivable/Payable type, and the payment method's account is auto-corrected if it was previously set wrong. |
| 0.17.2 | **Gift cards (and coupons/approvals) now work in Sales-Invoice mode.** After the warehouse fix, selling a gift card in **Sales Invoice** mode hit a new error, *"Could not find Issued On Invoice: ACC-SINV-…"*. The gift-card record's "Issued On Invoice" (and the gift-card ledger, coupon "Used On", and approval-request invoice fields) were **Link → POS Invoice**, so they rejected a Sales-Invoice reference. These are read-only audit references, so they're now plain text that accepts either invoice type, gift cards, coupons and discount approvals all post correctly regardless of the profile's invoice mode. Also fixed the return-approval window check, which was silently skipped for Sales Invoices. *(Deploy runs a migration to apply the field changes; existing records are preserved.)* |
| 0.17.1 | **Bring your own receipt format (Print Format), clarified + fixed for Sales-Invoice mode.** You can already use a fully custom receipt: set any ERPNext **Print Format** (standard or custom Jinja/HTML) on the **POS Profile**, and printing uses *that* instead of the built-in designer, the receipt designer then only styles the on-screen receipt. The designer now says so clearly and, when a Print Format is set, shows a banner naming the active format. Fixed a bug where the custom Print Format print path hardcoded the `POS Invoice` doctype, so it failed for profiles running in **Sales Invoice** mode; it now uses the sale's real doctype (returned by `get_receipt`). *(Note: a configured ESC/POS thermal printer still uses the built-in thermal layout, custom Print Formats apply to browser/A4 printing.)* |
| 0.17.0 | **Offline sales log. See exactly what synced and what didn't.** A new **Offline sales log** (open it from the **Offline / Syncing pill** in the top bar, or **Settings → Status → View offline sales log**) lists every sale made offline with a live status: **Pending** (queued, not yet uploaded), **Uploaded** (posted, shows the real server invoice number), or **Needs attention** (the server rejected it, shows the reason). Cashiers can see at a glance that nothing is lost. Sync also got more robust: a sale the server rejects is now recorded with its reason and **skipped** so it can no longer block the good sales queued behind it (it still retries on the next sync), and a synced sale is matched to its real invoice number in the log. |
| 0.16.3 | **Gift-card warehouse error, final fix (stop re-saving the Item).** v0.16.2 found the right document (the gift-card Item's defaults) but blanking the stray warehouse in Python and re-saving still failed. ERPNext re-derives the warehouse during the Item's own validation, before the check runs, so a re-save can never win. Setup no longer re-saves the Item at all: it scrubs any stray default warehouse **directly in the database** (which bypasses that validation), and new sites get the item created with its own defaults preset so the Item Group's (possibly wrong-company) defaults are never copied in. The sale already posts to the gift-card liability account on the invoice line, so it doesn't depend on the item defaults. |
| 0.16.2 | **Gift-card warehouse error, actual root cause fixed.** The real failure was never in the invoice: the gift-card **Item** itself carried an *Item Default* row for one company with a **default warehouse belonging to a different company** (copied from the Item Group's defaults when the item was first created). ERPNext re-validates the whole Item Defaults table on save, so `ensure_setup` blew up with *"Row #1: Warehouse … doesn't belong to Company …"* **before an invoice was even built**, which is why the earlier invoice-side fixes couldn't help. A gift card is **non-stock** and needs no warehouse, so setup now **strips any stray default warehouse** from the item's defaults and reuses (instead of duplicating) the per-company row. The sale also now posts to the gift-card **liability account explicitly** on the line, independent of item-default resolution. |
| 0.16.1 | **Gift-card warehouse fix (multi-company), for real this time.** On a multi-company site, selling a gift card could fail with *"Warehouse … doesn't belong to Company …"*. Root cause: ERPNext resolves a line's warehouse from the invoice **header `set_warehouse` first**, and the gift-card invoice only set it **after** `set_missing_values` ran, too late, so the row had already fallen through to the **global** default warehouse (wrong company). Now the gift-card sale pins a company-owned warehouse **up front** (header + row), exactly like a regular sale, and hard-fails with a clear message if the company genuinely has no warehouse, so it can never silently fall back to the wrong-company default. |
| 0.16.0 | **Live clock + "Shift Open" timer in the top bar.** A ticking **wall clock** (HH:MM:SS) and, while a register is open, a **Shift Open: {H} Hr {M} Min {S} Sec** elapsed timer (counting from when the shift opened) now sit at the top-left, so cashiers/managers can see the time and how long the drawer's been running at a glance. Both update every second. |
| 0.15.3 | **Gift-card placeholder item hidden from the product grid.** The internal **GIFT-CARD** item (used to post a gift-card sale) is sold via the gift-card button, not tapped as a product, tapping it just added a SAR 0.00 line. It's now excluded from the sell grid, search, offline catalog cache, and the price checker. (It disappears from the grid once the offline catalog refreshes on the next load.) |
| 0.15.2 | **Real fix: gift-card sale "Warehouse … doesn't belong to Company".** The earlier fix *cleared* the warehouse on non-stock sales, but ERPNext then falls back to the **global default warehouse**, which on a multi-company site can be another company's, so the error came back. Both the gift-card sale and every non-stock line now **pin the profile's own warehouse** (which belongs to the profile's company, exactly like regular sales do), with a company-warehouse fallback if a profile's warehouse is mismatched. Non-stock lines carry a harmless (no stock moves) but company-valid warehouse, so the validation passes on any company. |
| 0.15.1 | **X-report moved to the top bar.** The **X-report** button now lives in the top bar (shown whenever a register is open + the feature is on), so a cashier can pull a mid-shift drawer read from any screen without opening the Register page. It fetches a fresh read-only session summary on demand. Removed the duplicate button from the Register page. |
| 0.15.0 | **Offline customer *create* + safe sync (Phase 3).** You can now **create a new customer while offline**: it's saved on the device (searchable for the rest of the offline session) and the sale is queued against a temporary id. On reconnect, the flush **reconciles each offline customer by mobile**, if a customer with that number already exists (created on another till, or a duplicate) the sale is **linked to it**, otherwise the customer is **created**, then the queued invoice is remapped and posted. Everything is **idempotent**: each queued sale carries a client key (`lumenpos_idempotency_key`, unique on the invoice), so a retried sync after a lost server ACK **returns the existing receipt instead of duplicating** the invoice; customer resolution is match-or-create so it never duplicates a customer either. **Editing** an existing customer stays online-only (the vendor consensus). Completes the offline-customer work (Phases 1 to 3: durable queue → offline select → offline create). |
| 0.14.0 | **Offline customer *select* (Phase 2).** LumenPOS now caches a **capped recent/frequent customer subset** (`catalog.recent_customers`, customers this outlet's company recently transacted with, topped up with the newest, default ~2,000; deliberately *not* the full directory) into IndexedDB in the background, so a cashier can **search and pick existing customers while offline**, previously only the walk-in customer was usable offline. Online search still hits the server (full directory). The customer modal searches the cache when offline; **Settings → Status** shows the cached-customers count, and *Refresh offline catalog* refreshes customers too. Creating a *new* customer offline is cleanly gated ("needs a connection"), that's Phase 3 (offline create + match-or-create-by-mobile on sync). |
| 0.13.0 | **Offline queue durability hardening** (Phase 1 of offline-customer work). Two facts made the offline queue evictable: browsers evict "best-effort" storage whole-origin under disk pressure (LRU), and Chrome 121+ acks IndexedDB writes *before* they hit disk. LumenPOS now requests **persistent storage** (`navigator.storage.persist()`) at startup so a queued sale can't be evicted, and writes each queued sale with **`durability: 'strict'`** so a power-cut right after a sale can't drop it. **Settings → Status** shows **Offline storage: Persistent / Best-effort** so a manager can verify durability at a glance. (Grounded in a cited research pass on how Shopify/Loyverse/Lightspeed handle offline + MDN/WebKit/Chrome storage docs.) Next phases: cache a recent-customers subset for offline select, then offline customer *create* with match-or-create-by-mobile on sync. |
| 0.12.1 | **Fix: "Require scanning for serial numbers" was bypassable from the search box.** The serial **modal** enforced scan-only, but typing a serial straight into the sell **search box** and pressing Enter resolved + added it without the check. The search-box path now applies the **same scan-vs-typed guard** (`scanGuard`): a serial that was *scanned* (fast burst) is accepted, a *typed* one is rejected with "Manual entry is off. Scan the serial with the scanner." when the setting is on. |
| 0.12.0 | **POS sales always ignore ERPNext Pricing Rules** (the *Ignore ERPNext Pricing Rules* POS-Profile toggle is retired). LumenPOS prices every sale with its own **price books + promotion engine**, and the till/cart never applies ERPNext Pricing Rules, so letting them touch the invoice could only ever make it diverge from what the cashier collected (the 0.11.x "Partly Paid" bug). POS sales now bypass them unconditionally; the now-pointless toggle is removed on migrate. **ERPNext Pricing Rules still work normally for non-POS documents.** Do POS discounting with **price books / LumenPOS promotions**. |
| 0.11.3 | **Fix: ERPNext Pricing Rule overriding the price book → "Partly Paid".** With *Ignore ERPNext Pricing Rules* ON, a sale could still post with the Pricing Rule's price instead of the price book: `set_missing_values` stamps the rule on the item row, and ERPNext **re-applies it on submit**, overriding the price LumenPOS set. The till had already collected the LumenPOS price, so the posted invoice diverged and landed **Partly Paid**. LumenPOS now **clears the stamped Pricing Rule** from each line when *Ignore* is on, so the price book / promotion price is what posts (and the payment matches → fully paid). *Note: with the toggle OFF, ERPNext Pricing Rules apply to the invoice but the till/cart never does, so they'll mismatch and partial-pay; keep the toggle ON unless you stop using LumenPOS price books/promotions.* |
| 0.11.2 | **Non-stock items (services, fees) never carry a warehouse.** Extends the 0.11.1 gift-card fix to every sale: after building the invoice, any **non-stock** line (a service like *Installation*, a fee, etc.) has its warehouse cleared, it never moves stock, so a warehouse is meaningless and it should never be subject to the warehouse↔company check. **Stock** items keep the POS Profile's warehouse (which must belong to the profile's company). So a multi-company site can sell services on any company's profile without a warehouse error. |
| 0.11.1 | **Fix: selling a gift card failed on a multi-company site** with *"Warehouse … doesn't belong to Company …"*. A gift card is a non-stock liability sale (no stock moves), but `set_missing_values` was defaulting a warehouse onto the line, and on a multi-company site that could be another company's warehouse, tripping ERPNext's warehouse↔company check. The gift-card sale now clears the line + `set_warehouse` after building (no warehouse is needed), so it posts cleanly regardless of company. |
| 0.11.0 | **Multi-company accounts (Settings → General → Company Accounts).** Fixes account pickers listing *every* company's chart of accounts (which could post a sale to the wrong company's GL). A new **Company** dropdown scopes the company-specific accounts, the **gift-card liability account** and **service-charge account**, and the account lists now show **only the selected company's** accounts (new `company` filter on the link lookup). At sale time each is resolved from the **POS Profile's company** (per-company override → global fallback → auto-create), and gift cards now **refuse to use an account that doesn't belong to the sale's company** (auto-creates the right one instead), so several companies can share one site safely. New child doctype *LumenPOS Company Setting*; the global gift-card/service-charge account fields remain as fallbacks. |
| 0.10.0 | **Receipt designer (Settings → General → Receipt).** Choose one of **three templates**: *Compact*, *Standard*, *Detailed* (layout/density), and tick exactly what each receipt shows: **item code, barcode, serial numbers, unit price (qty × rate), payment methods, the sale note, tax/VAT ID, store address, terms & conditions**, plus the existing logo / header / footer. A **live preview** renders as you change options. The on-screen and browser-printed receipt (a shared `ReceiptView` component) honours all of it; the sale note is now stored on the invoice (`lumenpos_note`) and barcodes/serials are returned with the receipt. (The optional ESC/POS thermal-printer path keeps its fixed layout for now.) |
| 0.9.1 | **Brand-colour cleanup.** The fork left the old VPOS indigo `#2E5BFF` hardcoded as `rgba(46,91,255,…)` in ~22 places (cart chips, tags, hovers, badges, the register pill, receipts…) and used a washed-out periwinkle `--brand-soft` (`#7fa8ff`) for *active* states (Settings tab, promo-type selector, selected refund serial, active customer row). All now use the real Lumen blue **#1463FF**, crisp brand fills on active/selected states, correct-hue tints everywhere else. The dark nav rail + top bar were retuned to a cleaner **Lumen navy** (blue undertone, brand-blue-tinted active rail item) instead of flat charcoal. No layout changes. |
| 0.9.0 | **POS Opening/Closing Entries in Sales Invoice mode (cash control).** New POS Profile option **Use POS Opening/Closing Entries** (LumenPOS Options, shown only in *Sale posts as = Sales Invoice*). When on, opening the register creates a real **POS Opening Entry** and closing creates a **POS Closing Entry**, opening float, expected-by-payment (sourced from the shift's *Sales Invoices*), counted amounts, differences, cash in/out, so cash is supervised on the standard ERPNext POS documents/reports. There is **no consolidation** (sales already post as Sales Invoices; the closing entry's invoice table stays empty and the close finalizes directly). Off (default) keeps the lightweight cash shift. The register screen behaves like POS Invoice mode (close → finalising → Closed with a POS Closing Entry link). |
| 0.8.1 | **Fix: sales failing with `'POSProfile' object has no attribute 'update_stock'`.** Some ERPNext versions don't expose `update_stock` on the POS Profile, so the direct attribute read threw and blocked every sale at *Complete Sale*. LumenPOS now reads it defensively, it honours the profile's setting when the field exists, and otherwise defaults to **Update Stock = on** (a POS reduces stock at the point of sale; Sales-Invoice-direct mode needs it to move stock at all). |
| 0.8.0 | **Lock screen (PIN to unlock)** (Settings → General → *Features*). A **Lock** button in the top bar (and optional **auto-lock after N minutes** of inactivity) covers the whole till with a PIN screen, protecting an unattended register. A **manager** (System / LumenPOS Manager) always unlocks; everyone else enters a **manager/approver PIN** (the same PINs used for discount approval), so set a Master passcode or an approver PIN first. Unlocks are throttled server-side and recorded in the audit log. *Note: this is a screen lock for a shared till, not per-cashier login/session switching.* |
| 0.7.0 | **Customer-facing display** (Settings → General → *Features* → Customer-facing display). A **Display** button on the sell screen opens a chrome-free second-screen window (`#/display`) that mirrors the live cart for the customer, item lines, savings and a big running total, with the store logo and a welcome screen when idle. Sync is local-only over a **BroadcastChannel** (no server round-trips); a display opened later asks the till for the current cart so it's never blank. Designed for a second monitor on the same machine/browser. |
| 0.6.0 | **Three more toggleable features** (Settings → General → *Features*). **Quick keys / favourites**. Pick favourite items in Settings; a *Favourites* tab on the sell screen adds any of them with one tap (each shows live price + stock). **Email receipt**, an *Email receipt* button on the receipt sends a copy (with the POS Profile's Print Format attached) to the customer's email, or any address you type; needs an outgoing Email Account on the site. **Audit log**, sensitive actions (over-limit discounts, returns, register open/close, emailed receipts, settings changes) are recorded to a new **LumenPOS Audit Log**, viewable by managers in a new **Audit Log** settings tab with action/date filters. New doctypes: *POS Quick Key*, *LumenPOS Audit Log*. |
| 0.5.0 | **Five new till features, each with its own on/off control** (Settings → General → *Features*). **Order-level discount**, one whole-cart discount field, spread proportionally across every non-bundle line, policed by the same discount limit + edit-price role as a line discount. **Service charge / tip**, a flat percent added to every sale as a final non-taxed charge, posted to a chosen income account (account is required when on). **Price / stock checker**, a *Price check* button on the sell screen looks up any item's live price + stock (here and across all stores) by barcode, serial, code or name, without touching the cart. **X-report**, a *read-only* mid-shift drawer snapshot on the Register screen (sales, takings, discounts, expected by payment, cash in/out) that prints but does **not** close the shift. **Receipt branding**, optional logo, header line and footer line on the on-screen + browser-printed receipt. Every control is independent and persists in LumenPOS Settings. |
| 0.4.0 | **Invoice backend choice** (POS Profile → *LumenPOS Options* → **Sale posts as**). **POS Invoice** (default) keeps the shift + consolidation flow unchanged. **Sales Invoice** posts each sale as a Sales Invoice **directly** (GL immediately, no consolidation) with a **lightweight LumenPOS cash shift**. Open a float, cash in/out, close with counts + X/Z, **no POS Opening/Closing Entry** (so it works on v14/v15). Sales, returns, history, the customer ledger and the close report are all backend-aware; the self-healer/consolidation never touches a direct-mode shift. |
| 0.3.0 | **Granular permissions** (Settings → General → *Permissions*). Three role gates, each enforced server-side and mirrored in the UI; managers always pass, blank role = anyone: **Edit price / discount** (who may apply a manual discount, the field is disabled otherwise), **Make returns** (who may refund, the Refund button hides otherwise), and **Exceed return window** (this role returns past the window *directly*; everyone else still uses the approval-request flow). |
| 0.2.0 | **Removed warranty Exchange.** Added: a per-POS-Profile **"Ignore ERPNext Pricing Rules"** toggle (on by default, LumenPOS uses its own promotion engine; off lets Pricing Rules apply); **add-item-on-scan**, a scanned barcode now adds the item instantly without pressing Enter (typed searches still use Enter). |
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
| 0.8.4 | **Real discount fix**: with Pricing Rules off ERPNext honours only `discount_percentage` (not `discount_amount`), so all LumenPOS discounts are now posted as a percentage and survive onto the invoice, promotion/bundle sales complete. Register close panel hardened: never strands the cashier (shows a warning + lets you count and close even if the expected-takings summary fails to load) |
| 0.8.5 | Delivery-app sales write to the site's **existing** fields (`pick_customer`, `custom_app_type`, `pick_order_no`, `is_exchange`) instead of creating new `lumenpos_*` fields; history search/receipt read them too |
| 0.8.6 | **Register close no longer times out (504)**: the session is closed and saved immediately, and the POS Closing Entry consolidation runs in a background job; the POS polls for the entry and shows a "Generate closing entry" retry on any closed session missing one |
| 0.9.0 | **Dark mode**, theme toggle in the nav rail, persisted per device, defaults to the OS preference; full dark palette across every screen with #2E5BFF kept as the accent; receipts still print black-on-white |
| 0.9.1 | The open-register prompt no longer blocks the whole app, it covers only the Sell screen, so the nav rail and other tabs stay usable; the register can also be opened from the Register tab |
| 0.10.0 | **Warranty exchanges**, one guided ⇄ Exchange screen: find the original sale, pick the damaged item (credited at its original price) and the replacement, see the net difference, and confirm. Creates the damaged return (is_return+is_exchange) and replacement sale (is_exchange) atomically; only the net hits the drawer via an internal Exchange Credit clearing account |
| 0.10.1 | Exchange warranty now comes from each **item's warranty days** (per-line check, not a global setting); the warranty shows on every cart line during sales; exchanges are a toggleable feature (Settings → General → Enable warranty exchanges), the ⇄ button hides when off |
| 0.10.2 | **Dark mode now follows your ERPNext desk theme** (Light/Dark/Automatic) on first load, so LumenPOS matches the look you already set in ERPNext; the in-POS Dark/Light toggle still overrides it per device |
| 0.10.3 | Item pickers in **promotions, bundles and price books** now search by **name, item code or barcode** (barcode shown in the dropdown); price-book editor gains **Excel/CSV import & export**; **delivery apps can have their own editable price list** (per-app prices, e.g. Jahez) with the same editor + import/export; new price books default to **Standard Selling** (changeable) |
| 0.28.2 | **Scan-only scope.** *Require scanning for serial numbers* now applies only to **selling** and **returns**, not exchanges, in an exchange the cashier may type the damaged item's serial, which must still **match one sold on the original invoice** (enforced client- and server-side). |
| 0.28.1 | **Clearer offer suggestions.** The "Add X, get free" promotion suggestion chips (cart line + basket) now have a proper tinted background and border, and a **lighter purple on a stronger tint in dark mode**, so they're legible instead of faint purple-on-dark. |
| 0.28.0 | **Return sets together · serial scan-only.** Items sold together, a **bundle** or a **Buy X Get Y** offer, must now be **returned as a whole on a regular return** (all members, full quantity, or none); the refund screen marks them with a *Set, return together* badge and steps the whole set at once, and the server enforces it. **Exchanges are exempt** (you can still swap one item of a set). Each line carries a `lumenpos_return_group` stamped at sale time. New setting **Require scanning for serial numbers** (Settings → General, default off): when on, serials must be **scanned** with a barcode scanner when **selling** and on **returns**, manual typing is blocked. **Exchanges are exempt** (the damaged serial just has to match one on the original invoice). |
| 0.27.0 | **Bundle expiry · expired badges · exchange warranty from original · sale note.** Bundles now have **Valid From / Valid To** dates, past Valid To a bundle stops being offered at the till (like a promotion's end date). Promotions, bundles and price books show an **Expired** badge in their Settings list when past their end/valid-to date. Warranty **exchanges now count the replacement's warranty from the ORIGINAL purchase date** (chained across repeat exchanges via a new `lumenpos_warranty_start_date`), so a replacement carries only the remaining term, not a fresh one. The cart has a **note field** (flows to the invoice `remarks`). |
| 0.26.2 | **Approval requests fix.** Pending requests weren't reaching the Approvals tray because the list was **scoped to the approver's own POS profile**, now an approver sees **every open-shift request** regardless of which till/profile raised it. A **manager** may now approve their **own** request (manager override; also lets a single owner test the flow), role-only approvers still can't (separation of duties). The over-limit prompt now commits the typed discount immediately (`@input`), so it triggers reliably instead of intermittently. Approvals badge polls every 10s (was 20s). |
| 0.26.1 | `exchange_against_invoice` already exists on POS Invoice (a site field), so LumenPOS no longer creates it, it just writes the original invoice to the existing field on both exchange legs. |
| 0.26.0 | **Exchange traceability + cash movements on the Z-report.** Both legs of a warranty exchange (the credit note and the replacement sale) are now stamped with **`exchange_against_invoice`** = the original invoice, so an exchange always traces back to its source (written to the site's existing `exchange_against_invoice` field). And drawer **cash in / out** is now **declared on the POS Closing Entry**, a Cash In / Cash Out total plus a Cash Movements table beside the payment reconciliation, in addition to being netted into the expected cash (the netting already existed; this makes the movements visible/auditable on the official close). |
| 0.25.0 | **Customers screen (client lookup).** New **Customers** tab: search clients by name / phone / code / email / tax ID, filter by customer group, and open any client to see their profile, balances (loyalty + store credit), lifetime stats and full **POS transactions** (filter by type + date range, click to view/print). Built performance-first, server-paginated, indexed lookups, per-customer totals computed only on open, and no background work, so it doesn't touch the till. Hidden unless the user has **Customer → read**. |
| 0.24.0 | **Return window + generalised approval requests.** Regular returns can be limited to a **time window** (Settings → General → Returns → *Limit regular returns to a time window* + **Return window (days)**, default 14, 0 = no limit). Past the window the till blocks the refund and the cashier sends a **return approval request** that an **Approver Role** holder clears from the **Approvals** tray while the register is open, single-use, tied to the invoice, server-enforced. The approval request system from 0.23.0 was generalised: one **POS Approval Request** doctype with a **request type** (Discount or Return), and the approver role setting is now shared by both (renamed *Approver Role*). |
| 0.23.0 | **Discount approval as a role-based request (not just a passcode).** Settings → General → *Discount approval* now has an **over-limit approval method**: *Passcode only* (today's behaviour), *Request only*, or *Passcode or request*. With requests on, a cashier hitting the limit taps **Send approval request** and the till waits; a holder of the configured **Approver Role** (plus LumenPOS/System Managers) sees a live **Approvals** tray in the left rail (with a count badge) and **Approves/Rejects** it. Requests are tied to the **open register session**, are **single-use**, and **expire when the register closes**, and approvals are re-checked server-side, so the limit can't be bypassed from the client. (The audit doctype shipped as **POS Approval Request**. See 0.24.0.) |
| 0.22.0 | **Out-of-stock hiding · serial re-scan on returns · exchange from the invoice.** The sell grid now **hides out-of-stock items** by default (toggle *Show out-of-stock items* in Settings → General; non-stock items always show). On returns **and** exchanges, serialized items must be **scanned/typed** (validated against the sold serials) instead of tapped from a list, so the cashier verifies the actual unit. The **Exchange** action moved off the cart to **History → open the invoice → Exchange** (beside Refund), launching the exchange pre-loaded with that sale. |
| 0.21.1 | **Real payment method in history + clearer tags.** Sales/returns/exchanges now store only the **tenders actually used**. ERPNext pre-fills a zero row for every payment method on the profile, which made the invoice (and history) list all eleven; LumenPOS now drops the unused zero rows on save, and history only shows/filters non-zero tenders (fixes existing invoices too). The REFUND / EXCHANGE / channel tags are now legible in **dark mode** (brighter text on stronger tints). |
| 0.21.0 | **Settings redesign (same features, calmer layout).** The whole settings page was reorganised: a segmented tab bar; Promotions / Bundles / Price books are now **list → editor** (searchable cards that open a focused editor); each editor is split into clean **section cards** (Basics · Offer · Products · When & where · Coupons) with a **type-aware Offer** (only the fields for the chosen promo type show), compact day/outlet pickers, and a sticky Save/Cancel/Delete footer. General / Loyalty / Channels became tidy two-column cards; Status shows metric cards. No behaviour change, every field, toggle and tool is the same, just easier to scan. The Offer also now exposes the engine's **Amount** discount type. |
| 0.20.0 | **Payment method in history + coupon polish.** Sales history rows now show the **payment method(s)** next to the total, and a **Payment method filter** lets you list invoices by tender. Coupons: fixed the stats line showing a literal `{redemptions}`, and clarified that the single **shared code is optional** (no limit, always works) while generated/imported codes are unique and limited; when the pool runs out only the shared code keeps working (or none, if left empty). |
| 0.19.0 | **Coupon use limit + bulk price-book discount.** Coupons now have a **use limit**, how many times each code may be redeemed (1 = single use, 0 = unlimited), set per batch and counted as they're spent (replaces the single-use checkbox; the desk shows Times Used / Fully Used). Price books get **"Discount all prices by X%"** with a rounding choice (none / 0.05 / 0.25 / 0.50 / 1 / 5) to reprice every item in the book at once. |
| 0.18.0 | **Bulk coupons.** A coupon-locked promotion can now have a whole **pool of codes**, not just one: **Generate** N unique random codes (optional prefix) or **Import** an Excel/CSV list, choosing **single-use** (spent after one redemption) or **reusable** (until an optional expiry) per batch. Codes unlock the promotion at the till exactly like the single code; single-use ones are marked spent on the sale. **Export codes** downloads the batch as CSV (to print/distribute), and **Delete unused** clears a batch. New `POS Coupon` doctype. |
| 0.17.0 | **Tags in promotions + bulk price-book add.** Promotions can now target a product **Tag** (ERPNext item tags) alongside Item / Item Group / Brand, handy when items span many groups/brands; the tag flows through both the live cart and the server engine (parity-tested). Price books gain **"Add all by" brand / item group / tag**, one click pulls every matching sellable item (each defaulted to its current selling price, so nothing accidentally sells at 0) ready for you to discount. |
| 0.16.0 | **Sales history clarity + default exchange item.** History rows now show the **cashier who made the sale**, a clean timestamp (no microseconds), and an **EXCHANGE** badge so warranty swaps are obvious at a glance (alongside REFUND). On the Exchange screen, ticking a damaged item now **auto-adds a replacement of the same item at the original price** (a net-zero warranty swap), the cashier can change the item, qty or price, or delete it. (Also removed the temporary refund diagnostic now that refunds post correctly.) |
| 0.15.7 | **Exchange invoice search is fast again**, the lookup was doing a full document load (plus per-serial queries) for every candidate sale, i.e. dozens of round-trips. Rewritten to a handful of batched queries (items, prior returns, warranty, serials fetched once for all candidates), no per-invoice `get_doc`. The exchange still re-validates returnable quantities authoritatively when you confirm, so the faster preview is safe |
| 0.15.6 | **Refund rejection, actually fixed (root cause).** Diagnostics revealed the credit note's `paid_amount` field held the *original sale's full paid amount* (e.g. −274.50), because `make_return_doc` copies it and `calculate_taxes_and_totals` doesn't recompute it for returns, so it never matched the refund's payment rows (−137.24), tripping "Paid amount … greater than Grand Total". LumenPOS now forces `paid_amount`/`base_paid_amount` to equal the actual refund rows on returns and exchange credit notes. (0.15.1/0.15.3 had targeted the wrong variable.) |
| 0.15.5 | **Refund diagnostic**, if a refund still fails, the error now reports the running version and the exact `paid / grand_total / rounded_total / write_off / payments` figures (also written to Error Log) so the cause can be read, not guessed. Temporary instrumentation, removed once the refund is confirmed working |
| 0.15.4 | **No more phantom "change" on the till**, the payment screen now pulls the exact payable from the server (new `quote_sale`, the same pricing path as the real sale) before you collect, so a card payment equals the posted invoice to the cent. Previously a VAT-inclusive promo line could round a couple of halalas differently on the till vs the invoice, leaving a stray SAR 0.02 "change". Cash can still over-tender for real change. `submit_sale` and the quote now share one builder so they can never drift |
| 0.15.3 | **Rounding fix, done right**, the v0.15.1 attempt relied on `disable_rounded_total`, which POS Invoice doesn't have, so refunds of tax-inclusive items still failed with *"Paid amount … greater than Grand Total"*. ERPNext validates a return's payment against `rounded_total or grand_total`; LumenPOS now refunds **exactly** that figure (and forces `write_off_amount = 0`) on returns and both exchange documents, so the difference is always zero regardless of how rounding is configured |
| 0.15.2 | **Refund consolidated sales from the till**, a sale whose shift already closed (merged into a Sales Invoice) is no longer blocked from the POS refund/exchange screen. LumenPOS posts the credit note against the original POS sale tied to the **current** open shift (refund from the current drawer); ERPNext merges it into a consolidated credit note at the next close, no ERPNext-desk trip for everyday post-close returns. Refund each sale through one channel only |
| 0.15.1 | **Refund & exchange fixes**, (1) returns/exchanges no longer fail with *"Paid amount … greater than Grand Total"*: the credit note now disables the rounded-total adjustment and pays the grand total to the cent, so a tax-inclusive half-cent can't break it. (2) Warranty exchanges no longer fail with *"Is Exchange … should be one of Yes, No"*: LumenPOS now writes boolean flags (is_exchange, pick_customer) in the form the site's field expects, `1` for a Check, `Yes`/`No` for a Yes/No Select, and reads them back either way (EXCHANGE receipt stamp still shows) |
| 0.15.0 | **Arabic / full RTL**, a one-tap language switch in the top bar flips the entire interface between English and Arabic, including right-to-left layout, and translates every label, button, toast and tooltip across the till, register, history and settings. **Master data is never translated** (item/customer names, codes, barcodes stay as entered). Language is remembered per device and defaults to the browser language. Built on a lightweight in-app i18n layer (no desk-language dependency) |
| 0.14.0 | **Return reasons**, refunds now require a reason picked from a configurable list (**Settings → General → Return reasons**, add/remove freely) or a free-text **Other**; it's stored on the credit note (*Return Reason* field). Warranty **exchanges default to "استبدال ضمان"** (changeable). **Start a new shift after a failed close**, if a close keeps *Failing* (e.g. overnight), a manager can open a fresh shift anyway while the failed one keeps retrying in the background, so the till is never stuck shut. Also fixes a latent bug where a retry/closing control response could momentarily flip the register to "open" |
| 0.13.0 | **Price books reworked to plain item overrides**, a price book is now just a list of items with a special price (added manually or by Excel/CSV) that applies for a period by priority/outlet/customer group. It **no longer creates or uses an ERPNext Price List** and never touches Standard Selling; reopening a book shows its items. Existing dedicated-list books are migrated automatically |
| 0.12.0 | **Promotions can be calculated on the standard price or the price-book price**, a new per-promotion "Calculate discount on" option. "Standard Price" gives the customer the lower of the price-book price or (standard − promo), never stacking with the book and using the highest-priority active book; "Price Book Price" (default) keeps stacking. Plumbed through both the live cart and the server engine (parity-tested) |
| 0.11.9 | **Price books can no longer touch base selling lists**. Standard Selling and outlet selling lists are blocked from price-book/app editing (server + UI) so setting a "book price" can never overwrite real master prices; the book editor now **shows the book's own items on open** (loads the dedicated list, not the whole catalogue), and base lists are hidden from the price-list picker |
| 0.11.8 | **Gift card accounting is mappable** (Settings → General → Gift cards): choose the mode of payment, liability account and item, or leave blank to auto-create defaults. **Exchange price override**, replacement lines have an editable unit price and a one-tap "Give as even swap" that waives the difference (give a pricier item at the same price) |
| 0.11.7 | **Exchange fixes**, auto-provisioned clearing modes of payment (Exchange Credit, Store Credit, Gift Card) now fill any **mandatory custom fields a site adds to Mode of Payment / Item** (e.g. an Arabic name), so completing an exchange/sale no longer fails with "Value missing for Mode of Payment"; the exchange **invoice search is much faster** (single combined query, mobile lookup via the customer table, no double doc-load, and the UI waits for 3+ characters) |
| 0.11.6 | A new **price book now gets its own dedicated price list** (auto-created on save, named after the book) instead of defaulting to Standard Selling, so overrides never touch the master list, and the editor genuinely starts empty (only items you add/import belong to the book) |
| 0.11.5 | Sales history gains an **Online order** filter (online only / in-store only) reading the site's `online_order` field; rows show an ONLINE badge |
| 0.11.4 | Fixed the price-book **Import/Export buttons** rendering their icon markup as literal text (the v0.11.2 icon swap had injected it inside a text expression); the price editor now **starts empty** instead of auto-loading the whole price list, search / add / import to populate it |
| 0.11.3 | **Payment tiles show real scheme logos**. Visa, Mastercard, mada, American Express, Tamara, Tabby, STC Pay and Apple Pay are detected from the Mode of Payment name and rendered as their brand mark on a white chip (via the new `PaymentBrand` component); other methods keep a generic line icon |
| 0.11.2 | **Emojis replaced with professional line icons**, a new `Icon` component (same SVG line style as the nav rail, themed to the brand colour) replaces every emoji/pictograph across the till (gift, delivery, warranty shield, coupon, walk-in, customer type, payment-method, exchange, refresh, import/export, barcode, loyalty star, etc.). Standard status marks (✓ ✗ ⚠) and prose arrows are kept as typography |
| 0.11.1 | **No green anywhere**, the legacy `--green`/`--teal` CSS tokens and `btn-green` class are renamed to brand tokens (`--brand` `#2E5BFF`, `--brand-dark`, `--brand-soft`, `.btn-primary`) across the whole frontend, so every primary action (Open Register, Retry closing, Continue shift, Pay, Save, etc.) is brand blue with no green identifier left to regress |
| 0.11.0 | **Role-based permissions**, every tab, action and the Pay button is governed by standard ERPNext DocType permissions (Role Permissions Manager); ships **LumenPOS Cashier / LumenPOS Manager** roles and a POS-access gate (no POS Invoice read = no entry). **Robust register closing**, a strict Open→Closing→Closed state machine: a closed shift can never be sold-on or resumed even if consolidation is slow or fails; consolidation is serialized cluster-wide (no concurrent-close deadlocks), runs synchronously under our control, is fully retryable, and a scheduled **self-healer** re-drives any stuck shift. A sell-time row lock stops a sale landing on a shift mid-close, so no invoice is ever left un-consolidated; cashiers can only close/alter **their own** till. **Refund method rules**, refunds are restricted to the tender the customer paid with (configurable per method, e.g. paid Mada → refund Mada or Cash). Cleaner **General settings** layout |
