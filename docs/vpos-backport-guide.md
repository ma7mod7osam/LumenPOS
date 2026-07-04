# LumenPOS → VPOS backport guide

Everything changed in LumenPOS since it forked from VPOS (`0.1.0` → `0.17.6`), organised so you can apply the **fixes** to VPOS without re-debugging them, and cherry-pick the **features** you want.

> **Context.** LumenPOS forked from VPOS and then diverged; VPOS has kept developing on its own (currently `v0.28.2`), so it may already have some of the *features* below. The **bug fixes** are the high-value part — each was a real ERPNext gotcha that cost several attempts to nail. VPOS shares the same gift-card / register / sales machinery, so most fixes apply directly.
>
> **Naming.** LumenPOS renamed everything `vpos*→lumenpos*`. When porting *back*, reverse it: `lumenpos.api.*` → `vpos.api.*`, custom fields `lumenpos_*` → VPOS's convention (`vpos_*` / `custom_*`), `LumenPOS Settings` → `VPOS Settings`, etc. See the cheatsheet at the end.

---

## Part 1 — Critical bug fixes (port these)

These are ERPNext behaviours that bite any POS app. Each entry: **symptom → root cause → fix → where**.

### 1.1 Sale crash: `'POSProfile' object has no attribute 'update_stock'`
- **Symptom:** every sale throws on some ERPNext versions whose POS Profile lacks the `update_stock` field.
- **Cause:** direct attribute access `profile.update_stock`.
- **Fix:** read defensively — `profile.get("update_stock")`, default to `1` when `None`.
- **Where:** `sales.py` `_build_sale_invoice` (and anywhere you read it). *(LumenPOS 0.8.1)*

### 1.2 Gift-card sale: `Row #1: Warehouse … doesn't belong to Company …` ⭐ (took 4 tries)
- **Symptom:** selling a gift card on a multi-company site fails with a warehouse/company mismatch. Clearing or pinning the *invoice* warehouse didn't help.
- **Root cause (the real one):** the failure is **not on the invoice** — it's raised when `ensure_setup` calls `item.save()` on the gift-card **Item**. ERPNext's `validate_item_default_company_links` re-validates the whole `item_defaults` table, and the gift-card item had an **Item Default row whose `default_warehouse` belonged to another company** (copied from the **Item Group's** defaults on first `insert()`, via `update_defaults_from_item_group`). Re-saving to blank the field doesn't hold — ERPNext re-derives it during `validate` before the check runs.
- **Fix (final, 0.16.3):**
  1. In `gift_cards.ensure_setup`, **do not re-save the Item.** Scrub any stray warehouse straight in the DB: `frappe.db.set_value("Item Default", <row>, "default_warehouse", None)` (bypasses validation).
  2. On **create**, preset the item's `item_defaults` (`[{company, income_account}]`) so ERPNext skips copying the Item Group's defaults.
  3. Set `income_account` **directly on the invoice line** so posting never depends on item defaults.
  4. Helper `_company_warehouse(profile)` — a warehouse that belongs to the profile's company (profile's own, else any non-group company warehouse); used to pin a valid warehouse on the header + rows.
- **Where:** `gift_cards.py` `ensure_setup` / `_account`, `sales.py` `sell_gift_card` + `_company_warehouse`. *(0.11.1 → 0.15.2 → 0.16.1/2 → **0.16.3** final)*
- **Lesson:** for a `ValidationError`, read the **full server traceback first** — the frames name the exact function. Don't pattern-match the message.

### 1.3 Pricing Rule overrides the price book → invoice posts "Partly Paid" ⭐ (took 3 tries)
- **Symptom:** cart charges the price-book price (e.g. 30), but the posted invoice uses an ERPNext Pricing Rule price (e.g. 99) → underpaid → **Partly Paid**.
- **Root cause:** two layers. (a) ERPNext **re-applies a stamped `item.pricing_rules` on submit**. (b) Even with `ignore_pricing_rule=1` set on the invoice, ERPNext's POS `set_pos_fields` **re-reads that flag from the POS Profile on every save** and flips it back to the profile's value.
- **Fix:**
  1. Always set `ignore_pricing_rule = 1` on the invoice **and** clear `item_row.pricing_rules = ""` on every line. *(0.11.3 / 0.12.0)*
  2. **Set the POS Profile's `ignore_pricing_rule = 1`** so the flag survives `set_pos_fields`. Helper `_ensure_ignore_pricing_rule(profile)` — idempotent, `has_field`-guarded, `frappe.clear_document_cache` after — called at the top of `_build_sale_invoice` and `sell_gift_card`. *(**0.17.4** — the fix that actually sticks)*
- **Where:** `sales.py` `_build_sale_invoice`, `_ensure_ignore_pricing_rule`, `sell_gift_card`.
- **Note:** LumenPOS decided POS sales **always** ignore Pricing Rules (the till never applies them). If VPOS wants a per-profile toggle, gate step 2 on it.

### 1.4 Gift-card / store-credit redemption: `Customer is required against Receivable account …`
- **Symptom:** paying with a gift card (or store credit) fails on the Receivable/Debtors account.
- **Root cause:** the tender's payment leg resolved to the company **Receivable** account; a GL line on a Receivable/Payable account demands a party, but a payment leg carries none.
- **Fix:**
  1. **Pin** the gift-card / store-credit payment row to **its own liability account** in `submit_sale` (`row.account = <liability>`, captured from `ensure_setup` / `ensure_mode_of_payment`, applied after `_drop_empty_payments`, before insert).
  2. `gift_cards._account` refuses any configured account whose `account_type` is `Receivable`/`Payable`.
  3. `ensure_setup` / `ensure_mode_of_payment` **correct** an existing wrong mode-of-payment company account (were add-only) and **return** the account.
- **Where:** `sales.py` `submit_sale`, `gift_cards.py`, `store_credit.py`. *(0.17.3)*
- **General rule:** a liability-backed POS tender must post to its **liability** account, never debtors.

### 1.5 Serial "scan-only" was bypassable via the search box
- **Symptom:** with scan-only on, a cashier could still add a serialised item by typing the serial in search.
- **Fix:** capture `wasScan` **before** the input resets, and enforce it in `onSearchEnter`.
- **Where:** frontend `SellView.vue`. *(0.12.1)*

### 1.6 The `set_pos_fields` / `set_missing_values` override family (the meta-lesson)
Several bugs above share one root: **a value LumenPOS sets on the POS invoice that also exists on the POS Profile gets overwritten by ERPNext's `set_pos_fields` on save.** Warehouse (1.2), `ignore_pricing_rule` (1.3), and payment accounts (1.4) all hit variants of this. **Rule of thumb: set it on the PROFILE (or pin it after `set_missing_values`), not just on the invoice.**

---

## Part 2 — Sales-Invoice-mode / dual-doctype support (port if VPOS adds SI mode)

LumenPOS can post sales as **POS Invoice** *or* **Sales Invoice** per profile. If VPOS only uses POS Invoice, skip this. If you add SI mode, you need all of it, because ERPNext and custom code hardcode `POS Invoice` in many places.

- **Invoice backend abstraction** — helpers `_sale_doctype(profile)` / `_doctype_of(name)` / `_table_doctype(profile)`; parameterise build, return, history, receipt, register open/close. *(0.4.0)*
- **Custom Print Format** — the print view must use the sale's real doctype, not a hardcoded `POS Invoice`; `get_receipt` returns `doctype`. *(0.17.1)*
- **Link fields → Data** — `POS Gift Card.issued_invoice`, `POS Gift Card Entry.invoice`, `POS Approval Request.invoice` + `return_invoice`, `POS Coupon.used_on` were `Link → POS Invoice` and threw `LinkValidationError` for a Sales-Invoice name. Convert to **Data** (accepts either; `bench migrate` preserves rows). *(0.17.2)*
- **Return-window check** — `approval_requests.py` did `get_value("POS Invoice", …)` (returns None for a Sales Invoice, silently skipping the window). Resolve the doctype. *(0.17.2)*
- **POS Opening/Closing in SI mode** — optional per-profile cash control without consolidation. *(0.9.0)*
- **Still hardcoded (known, not yet fixed in LumenPOS):** `printing.py` thermal (`get_value("POS Invoice", …)`), `_require_sell` permission gate. Fix with `_doctype_of` / `_sale_doctype` if you go SI.
- **Custom fields on both doctypes:** add your `*_session` / `*_idempotency_key` / `*_note` custom fields to **both** `POS Invoice` **and** `Sales Invoice` (LumenPOS's `install.py` does this).

---

## Part 3 — Marketplace security & code-quality fixes (port if VPOS goes to the marketplace)

The Frappe Marketplace **Submission Gate** runs `frappe/semgrep-rules` and fails on any Major finding. LumenPOS cleared 15; VPOS will hit the same rules. *(0.17.5)*

- `frappe-format-string-injection` — pass `str(e)` into `.format()`, never a raw exception object.
- `frappe-sql-format-injection` — remove f-strings/`.format()` from `frappe.db.sql`. Rewrite to fixed **parameterized** literals where possible. Where only a **fixed doctype/table identifier** is interpolated (can't be a bound param) and all user input is already bound, add a **bare `# nosemgrep`** on the `frappe.db.sql(` line **with a why-comment** (the auditor honours bare `# nosemgrep`).
- `frappe-realtime-pick-room` — `publish_realtime` without `user`/`room`/`doctype` broadcasts site-wide. Scope to `user=…` where the message has a target; `# nosemgrep` a genuinely-broadcast, no-PII ping.
- `frappe-no-functional-code` — replace `filter(None, …)` / `map(...)` with comprehensions.
- `frappe-manual-commit` — `frappe.db.commit()` is flagged; `# nosemgrep` with a why-comment where the commit is intentional (e.g. register-close state persistence).
- **Hygiene:** strip any stray UTF-8 **BOM** from `.py` files (harmless at runtime, trips strict parsers); align `app_publisher` / `app_email` / `pyproject.toml` author / license copyright to your real publisher. *(0.17.6)*
- **Metadata that must be present:** `hooks.py` (`app_name/title/publisher/description/email/license`), `README.md`, `license.txt`, `pyproject.toml`.

---

## Part 4 — Features (optional — VPOS may already have some)

Toggle-gated where noted. Port what VPOS lacks.

| LumenPOS | Feature | Notes |
|---|---|---|
| 0.3.0 | Granular permissions (price-edit / return / exceed-window role gates) | `api/permissions.py` |
| 0.5.0 | Order-level discount, service charge/tip, price/stock checker, X-report, receipt branding | each a Settings → Features toggle |
| 0.6.0 | Quick keys/favourites, email receipt, audit log | `POS Quick Key`, `email_receipt`, `Audit Log` doctype |
| 0.7.0 | Customer-facing display | chrome-free `#/display` route + BroadcastChannel |
| 0.8.0 | PIN lock screen + idle auto-lock | `LockOverlay`, `session.unlock_till` |
| 0.10.0 | Receipt designer (3 templates + field toggles + live preview) | shared `ReceiptView.vue` |
| 0.11.0 | Multi-company accounts (per-company account scoping) | `Company Setting` child table |
| 0.13.0–0.15.0 | **Offline layer** — durable IndexedDB queue, offline customer select + create, **idempotent sync** (match-or-create by mobile + idempotency key) | research-backed; big win for flaky connections |
| 0.15.1 | X-report in the top bar | |
| 0.16.0 | Live clock + "Shift Open" elapsed timer | top bar |
| 0.17.0 | **Offline sales log** — Pending / Uploaded / Needs-attention, so cashiers see nothing is lost | `sale_log` store + `OfflineLogModal.vue` |
| 0.17.1 | Bring-your-own receipt via ERPNext **Print Format** on the POS Profile | 3-tier print priority |

---

## Part 5 — Do **NOT** port (LumenPOS-specific)

- **Rename to `lumenpos` + Lumen brand recolour** (`#1463FF`, Plus Jakarta Sans). VPOS keeps its identity (`#2E5BFF`). *(0.1.0, brand commit, 0.9.1)*
- **Exchange removal** (0.2.0). LumenPOS deleted warranty Exchange; **VPOS still uses it** (VPOS `v0.28.2` = "scan-only applies to sell + return only, not exchange"). Keep VPOS's Exchange.
- **Marketplace generalisation** — LumenPOS is being generalised for any business; VPOS stays KSA/Mokab-specific.

---

## Part 6 — Naming cheatsheet (LumenPOS → VPOS)

| LumenPOS | VPOS |
|---|---|
| `lumenpos.api.*` | `vpos.api.*` |
| custom fields `lumenpos_session`, `lumenpos_idempotency_key`, `lumenpos_note`, `lumenpos_promotions`, `lumenpos_return_group` | VPOS's convention (`vpos_*` / `custom_*`) |
| `LumenPOS Settings` (single doctype) | `VPOS Settings` |
| Roles `LumenPOS Cashier` / `LumenPOS Manager` | VPOS roles |
| asset path `/assets/lumenpos/pos/` | `/assets/vpos/pos/` |
| Other doctypes kept `POS *` names (POS Gift Card, POS Coupon, POS Promotion, POS Register Session, POS Approval Request …) | same — likely identical in VPOS |

**Also remember:** the **dual promotion engine** (`promotions/engine.py` + `frontend/src/promotions.js`) must stay in sync — if you port a promotion change, change both.

---

## Appendix — full LumenPOS version log

| Ver | Summary |
|---|---|
| 0.1.0 | Standalone fork (rename + brand) — *don't port* |
| 0.2.0 | Remove Exchange (*don't port*); pricing-rule toggle; add-on-scan |
| 0.3.0 | Granular permissions |
| 0.4.0 | Invoice backend: POS Invoice **or** Sales Invoice per profile |
| 0.5.0 | Order discount, service charge, price checker, X-report, receipt branding |
| 0.6.0 | Quick keys, email receipt, audit log |
| 0.7.0 | Customer-facing display |
| 0.8.0 | PIN lock screen |
| **0.8.1** | **Fix: POS Profile `update_stock` crash** |
| 0.9.0 | POS Opening/Closing in Sales-Invoice mode |
| 0.9.1 | Brand-colour cleanup — *don't port* |
| 0.10.0 | Receipt designer |
| 0.11.0 | Multi-company accounts |
| **0.11.1–0.11.3** | **Fixes: gift-card warehouse (attempts); Pricing-Rule-vs-price-book** |
| **0.12.0** | **POS sales always ignore Pricing Rules** |
| **0.12.1** | **Fix: serial scan-only bypass** |
| 0.13.0–0.15.0 | Offline layer (queue durability, offline customers, idempotent sync) |
| 0.15.1 | X-report to top bar |
| **0.15.2–0.16.3** | **Fix: gift-card warehouse — real root cause (Item Default) + final DB-scrub fix** |
| 0.15.3 | Hide gift-card placeholder item from grid |
| 0.16.0 | Live clock + Shift Open timer |
| 0.17.0 | Offline sales log |
| **0.17.1** | Print Format support **+ fix: SI-mode print doctype** |
| **0.17.2** | **Fix: gift cards/coupons/approvals in SI mode (Link→Data)** |
| **0.17.3** | **Fix: gift-card/store-credit redemption Receivable party error** |
| **0.17.4** | **Fix: Pricing Rules stay ignored (set on POS Profile)** |
| **0.17.5** | **Marketplace audit: 15 Semgrep security/correctness fixes** |
| 0.17.6 | Publisher metadata → Lumen Solutions |

*Bold = bug fix / hard-won ERPNext gotcha — highest backport value.*
