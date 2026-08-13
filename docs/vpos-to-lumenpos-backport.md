# VPOS → LumenPOS backport guide (work of 2026-08-05)

Everything VPOS gained on **2026-08-05** (v0.43.0 → v0.50.1), written as a
port list for **LumenPOS v0.21.0**. **All Exchange work is excluded by
request** — the excluded items are listed at the end so nothing is silently
dropped.

VPOS repo: `../vpos` · commits `b334254..89c1b0f` (13 releases).

## Naming map (apply to every snippet)

| VPOS | LumenPOS |
|---|---|
| `vpos.api.*` | `lumenpos.api.*` |
| `VPOS Settings` | `LumenPOS Settings` |
| `vpos_session`, `vpos_*` custom fields | `lumenpos_session`, `lumenpos_*` |
| `VPOS Manager` / `VPOS Cashier` roles | LumenPOS equivalents |
| `INVOICE_DOCTYPE` fixed to POS Invoice | LumenPOS passes `doctype=` around (SI mode) — keep that parameter everywhere |

Two structural differences to respect while porting:
1. **LumenPOS supports Sales-Invoice mode**, so helpers carry a `doctype`
   argument VPOS doesn't have. Add new parameters *alongside* it, never
   replace it.
2. **LumenPOS has extras VPOS lacks** (audit log, quick keys, offline log,
   per-company settings, receipt designer). None of the ports below touch
   them, but the audit log is a natural hook for items 1.2 and 3.1.

---

# Priority 0 — a live bug LumenPOS has right now

## 0.1 · X-report throws "You can only manage your own register" (VPOS v0.49.1)

**LumenPOS is affected today.** `lumenpos/api/register.py:360`
`get_session_summary()` calls `_assert_owner_or_manager(doc)`, and
`frontend/src/App.vue:150` `openXReport()` calls that endpoint — so any
cashier working a till a colleague opened gets a red permission toast on the
Sell screen and no X-report.

**Fix:** delete the `_assert_owner_or_manager(doc)` line from
`get_session_summary` only. Reading a shift's figures is not a mutation;
`add_cash_movement` and `close_register` keep their own checks (they each
call it directly, so security is unchanged).

---

# Priority 1 — Shift lifecycle (VPOS v0.50.0, commit `69a2280`)

The largest and most valuable block: seven agreed rules that make the register
state machine honest. Port as one unit — items 1.1 and 1.2 assume each other.

## 1.1 · Opening is ALWAYS a fresh shift — resume is deleted

*The problem:* a failed/slow POS Closing Entry leaves the native POS Opening
Entry "Open", so the next cashier is offered "continue the previous shift" —
resurrecting a dead shift. This is the #1 complaint about ERPNext POS.

*The rule:* the **register session status is the only truth**. Native opening
entries are downstream paperwork and are never consulted.

`lumenpos/api/register.py` — `open_register` becomes exactly:
1. permission check → `_assert_lumenpos_enabled(profile)` → float
2. live session on this register? `Open` → throw; `Closing` →
   `_force_new_after_failure(...)` (opens a fresh shift immediately, nudges
   the stuck consolidation)
3. otherwise → `_create_fresh_session(profile, float)`

Delete: `_resume_opening()`, `_retry_response()`, the whole orphan-opening
`requires_choice` branch, and the `allow_multiple_opening` setting (doctype
field, `get_settings`/`save_settings` keys, SettingsView toggle). Keep
`resume_opening_entry`/`force_new` in the signature as ignored parameters so
cached browsers don't 417.

New helper `_create_fresh_session(profile, opening_float,
bypass_live_guard=False)` builds the POS Opening Entry + session; it sets
`opening_entry.flags.ignore_validate = True` **always** (ERPNext blocks a
second open entry per cashier — an old native-POS leftover must never block a
new shift), and `session.flags.ignore_validate` only when jumping over a
`Closing` shift.

Also drop the `POS Closing Entry create` permission requirement from
`_force_new_after_failure` — the cashier opening the store must not be blocked
by a colleague's stuck close.

Frontend: `OpenRegisterOverlay.vue` and `RegisterView.vue` lose the
choice/retry branches; the "previous shift not finished" banner becomes purely
informational (with a Retry button) and the open form is **always** available
below it. `stores/session.js` → `openRegister()` no longer returns control
objects.

*Migration note for the go-live:* close stale native "Open" POS Opening
Entries once from the desk. LumenPOS ignores them, but tidy is better.

## 1.2 · Owner-only selling (no manager bypass)

Every sale, return and gift-card sale lands in the drawer of whoever opened
the shift, so only that cashier may ring one up. Enforced at the single
chokepoint `sales._open_session(pos_profile)` (also used by returns), right
after the "no open session" throw:

```python
if session.get("opened_by") and session["opened_by"] != frappe.session.user:
    frappe.throw(_("This shift belongs to {0}. Only the cashier who opened the "
                   "register can sell on it — close that shift and open your own.")
                 .format(frappe.utils.get_fullname(session["opened_by"])),
                 frappe.PermissionError)
```

Deliberately **no manager bypass**: selling is operational, not supervisory
(supervision — cash in/out, closing — keeps `_assert_owner_or_manager`).
Handover = close + reopen, which is instant now.

Frontend: `stores/session.js` getter `sellBlocked` (session.opened_by !==
user) → red banner at the top of `SellView.vue`, Pay + gift-card buttons
disabled in `CartPanel.vue`, and `RegisterView.vue` hides the cash-movement
and close panels for non-owners (showing a short note instead).

## 1.3 · Stale-closing-screen guard

A cashier counts the drawer against the figures on screen; if a sale lands
from another window/device in between, those figures are stale.

`close_register(session, counted, closing_note=None, expected_invoice_count=None)`:
after `_assert_owner_or_manager`, take the **same row lock the sell path
takes** (`SELECT status ... FOR UPDATE`) so nothing can slip in behind you,
then:

```python
if expected_invoice_count is not None and str(expected_invoice_count) != "":
    current = frappe.db.count(INVOICE_DOCTYPE, {"lumenpos_session": doc.name, "docstatus": 1})
    if cint(expected_invoice_count) != current:
        frappe.throw(_("New sales were recorded after the closing screen was "
                       "loaded. Refresh the closing screen, re-check the counts, "
                       "then close again."), title=_("Closing figures out of date"))
```

Client sends `expected_invoice_count: summary.sales_count`; on that error it
re-runs `load()` and toasts "re-check the counts". Optional parameter, so an
old cached client simply skips the check.

*Chosen over blocking sales while the closing screen is open* — a second
browser or device never knows about that screen, the server check covers all.

## 1.4 · Queued offline sales block closing

If sales are still queued in the browser, closing would push them onto the
**next** shift's drawer. In `RegisterView.vue`: a red panel with the count and
an **Upload now** button (calls `flushQueue()` then reloads the summary), the
Close button disabled while `session.queuedCount > 0`, plus a
`refreshQueueCount()` re-check inside `close()` before calling the server.
Client-side by nature (the queue lives in IndexedDB).

## 1.5 · Count-variance email alert

`LumenPOS Settings` → new fields `variance_alert_enabled` (Check),
`variance_alert_threshold` (Currency), `variance_alert_role` (Link Role).

`register._maybe_alert_variance(doc)` runs **after** the Closing flip commits
(an email hiccup must never undo a close), inside a broad `try/except` that
only logs. If any `payment_counts` row exceeds the threshold in either
direction, it emails every enabled holder of the role an HTML table of
expected/counted/difference, plus who opened and who closed the shift.
Helper `_role_emails(role)` reads `Has Role` → enabled users with an email.

*The user explicitly rejected an approval gate here* — record and notify, do
not block the close.

## 1.6 · Shift schedules + forgotten-shift alert

Two new doctypes:
- **POS Shift Schedule** (`schedule_name` unique + `slots` table) — a reusable
  timetable; one template can serve many outlets.
- **POS Shift Schedule Slot** (child): `day` (Select: Every Day + weekdays),
  `shift_name`, `start_time`, `end_time`. **`end_time <= start_time` means the
  shift crosses midnight.**

Custom field on POS Profile: `lumenpos_shift_schedule` (Link → POS Shift
Schedule), inserted after the outlet-enable checkbox.

Settings: `overdue_alert_enabled`, `overdue_alert_role`, `overdue_alert_hours`
(fallback, default 14), `overdue_grace_minutes` (default 60).
Session doctype: hidden Check `overdue_notified` (de-dupes the email).

`register.notify_overdue_sessions()` on an **hourly** cron
(`"0 * * * *"` in `hooks.py`, next to the existing `*/10` self-healer): for
every `status=Open, overdue_notified=0` session, deadline =
`_scheduled_end(schedule, opened) + grace` or `opened + fallback_hours`; past
it → email the role once and set the flag.

`_scheduled_end()` builds candidate windows from **the opening day and the
previous day** (so overnight shifts resolve), returns the end of the window
containing the open time, else the next window starting later that day (a
cashier opening a few minutes early). Returns `None` → caller uses the
fallback. `_as_time()` normalises the `timedelta` that `frappe.get_all`
returns for Time fields.

**No auto-close** — the user rejected it: a close without a real cash count
produces untrustworthy figures. Alert only.

Ported unit test (runs without a site — stub `frappe`, exec the two helpers):
morning shift, overnight shift, early open, post-midnight open, day-specific
match and non-match. Keep it; it caught the timedelta issue.

## 1.7 · Personal per-user PIN (replaces the shared unlock passcode)

New doctype **LumenPOS User PIN**: `user` (Link, unique, autoname
`field:user`), hidden `pin_hash`, `reset_code_hash`, `reset_expires`. System
Manager permissions only — it is written exclusively through the API.

New module `lumenpos/api/pin.py`:
- `_hash`/`_verify` — PBKDF2-HMAC-SHA256, 60k iterations, `salt$digest`,
  compared with `secrets.compare_digest`
- `set_pin(pin, current_pin=None)` — 4–8 digits; changing an existing PIN
  needs the current one
- `check_own_pin(pin)` → `ok` / `wrong` / `no_pin` (used by `unlock_till`)
- `request_pin_reset()` — 6-digit code, 15 min, emailed with `now=True` so a
  site without outgoing email fails loudly; throttled 3 per 10 min
- `reset_pin_with_code(code, new_pin)` — throttled 8/min
- `pin_is_set()` — fail-open if the table doesn't exist yet (pre-migrate)

`session.unlock_till(passcode)` now verifies the caller's **own** PIN only —
no manager bypass, no shared passcode (the *approvals* passcode stays a
separate mechanism, untouched). Keep the 8-attempts/minute cache throttle.
`get_bootstrap` exposes `pin_set`.

Frontend: `LockOverlay.vue` gains three modes (`enter` / `create` / `forgot`
with the emailed code), and a new `PinSetupModal.vue` is rendered from
`App.vue` when `enable_till_lock && !pinSet` — mandatory, non-dismissible,
shown once per user.

---

# Priority 2 — Approval requests (v0.47.0 `f03c73f`, v0.48.0 `e3f519c`)

LumenPOS already has `POS Approval Request` and `create_request(...)`, so
these are additive.

## 2.1 · Requests carry their details (v0.47.0, non-exchange part)

An approver was being asked to approve a discount **without seeing what was
being discounted**. Add a `request_details` (Small Text) field, accept
`details=None` in `create_request` and store `details[:2000]`; also store
`return_invoice` for the return type.

`PasscodeModal.vue` builds the detail lines (cart lines with per-line
discount) when raising a request; `RefundModal.vue` does the same for
return-window requests. `ApprovalsModal.vue` shows a type chip, a headline,
the cashier / customer / outlet facts, and the details in a scrollable block.

*(The exchange-exception half of this commit is excluded.)*

## 2.2 · Requests wait in the background — TTL + shift-close voiding (v0.48.0)

The scenario: one busy approver, and the cashier must not lose the cart or
re-enter it.

- Setting `approval_request_ttl_minutes` (0 = no expiry).
  `request_ttl_minutes()` + `_expire_if_stale(doc)` enforced inside
  `request_status`, `pending_requests` and `_decide`; `request_status`
  returns `expires_in` so the client can count down.
- `my_requests(pos_profile)` — the cashier's own Pending / Approved-unused
  requests on open sessions → new `MyRequestsModal.vue` with **Withdraw**,
  reachable from an amber badge in `NavRail.vue` (which polls both trays
  every 10s).
- `expire_session_requests(session_name)` — called from `close_register`
  **before** the Open→Closing flip: every Pending or Approved-but-unused
  request is voided. *The user's rule: nothing unconfirmed survives the
  shift.*
- `PasscodeModal.vue` closing no longer cancels the request (it stays pending
  and notifies).

*Known gap carried over:* `MyRequestsModal`'s "Use it" emits an event that
nobody handles yet — approving still requires the cashier to rebuild the
cart. Worth finishing during the port.

---

# Priority 3 — Payments (v0.43.0 `b334254`, v0.49.0 `4d7c52a`)

## 3.1 · Payment method rules: logos, mandatory transaction IDs, field mapping

Three related pieces from v0.43.0. New child doctype **POS Payment Method
Rule** on Settings: `mode_of_payment`, `brand` (Select: auto/none/visa/
mastercard/mada/amex/tamara/tabby/stcpay/applepay/cash/bank/card/gift),
`require_reference` (Check), `reference_label` (Data).

**(a) Logos.** LumenPOS's `PaymentBrand.vue` still uses per-brand viewBoxes
(`0 0 40 24`, `0 0 60 20`, …) so marks render at different sizes and misalign.
Port the VPOS version: every mark drawn on a **uniform 120×40 canvas**, a
fixed 3:1 chip, plus name-based `ALIASES` regexes for `brand: 'auto'`.
`PaymentOverlay.vue` gets start-aligned tiles with a fixed 84px logo column so
method names stay visible.

**(b) Mandatory transaction IDs.** `sales._payment_rules()` +
`_apply_payment_references(doc, payments)` write `row.reference_no` and throw
when a rule marks the reference required. `get_bootstrap` carries `brand`,
`require_reference`, `reference_label` per mode; the payment overlay renders a
per-split reference input, highlights a missing one and blocks completion.

**(c) Invoice field mapping.** So the POS writes to the site's **existing**
fields instead of creating duplicates (the user's requirement: "don't create a
second app-type/order-id field"). Settings gains `map_app_type_field`,
`map_order_id_field`, `map_channel_flag_field` (+ `map_exchange_field` —
optional for LumenPOS; the purpose infrastructure is worth having even if the
exchange purpose is unused). `sales.mapped_field(purpose)` resolves them, and
`_set_custom` / `_get_custom` / `_first_column` take `purpose=None` and prefer
the configured field when it exists, else auto-detect from candidates.
`settings._field_mapping_status()` shows the admin exactly which real field
each purpose resolves to, and a virtual **"POS Invoice Field"** LinkPicker
doctype makes them pickable instead of free text.

> ⚠ **`_first_column` has two traps in LumenPOS specifically — read 3.1-TRAP
> below before touching `sales.py`.** One of them fails *silently*.

### ⚠ 3.1-TRAP · How to port `_first_column` without breaking History

Part (c) teaches `search_sales` to pass a mapping *purpose*, which means three
helpers must learn `purpose` together: `_set_custom`, `_get_custom` and
`_first_column`. In LumenPOS the last one is a minefield, because its
signature already differs from VPOS **and its callers pass positionally**.

**What LumenPOS has today** (`lumenpos/api/sales.py`):

```python
# line 885 — second parameter is `doctype`, NOT `purpose`
def _first_column(candidates, doctype=INVOICE_DOCTYPE):
    for fieldname in candidates:
        if frappe.db.has_column(doctype, fieldname):
            return fieldname
    return None

# lines 1274-1277 — every caller passes `doctype` POSITIONALLY
app_field      = _first_column(("custom_app_type", "lumenpos_app_type"), doctype)
order_field    = _first_column(("pick_order_no", "custom_order_id", "lumenpos_order_id"), doctype)
online_field   = _first_column(("online_order", "custom_online_order", "is_online_order"), doctype)
exchange_field = _first_column(("is_exchange", "custom_is_exchange"), doctype)
```

Note also that `_set_custom` (line 836) and `_get_custom` (line 865) currently
take **no** `purpose` at all, and `mapped_field()` does not exist yet — all
three come with this port.

#### Trap 1 — the loud one (this is what shipped to production in VPOS)

Update the call sites to pass `purpose=` but forget the `def`, and **every
History and Customers search dies**:

```
File "apps/vpos/vpos/api/sales.py", line 1156, in search_sales
    app_field = _first_column(("custom_app_type", "vpos_app_type"), purpose="app_type")
TypeError: _first_column() got an unexpected keyword argument 'purpose'
```

It survived a full release because `search_sales` is only reached from the
History/Customers screens — the sell path never calls it, so a smoke test of
"can I ring up a sale" passes cleanly.

#### Trap 2 — the silent one (LumenPOS only, and worse)

Copy the VPOS signature **verbatim** and the code still runs — wrongly:

```python
def _first_column(candidates, purpose=None):   # ❌ VPOS's signature, pasted into LumenPOS
```

Now `_first_column(candidates, doctype)` binds the doctype string into
`purpose`. The result: `mapped_field("POS Invoice")` is asked for a mapping
purpose that doesn't exist (returns nothing, so no crash), and the column
lookup silently falls back to VPOS's hard-coded `INVOICE_DOCTYPE` — **so
Sales-Invoice mode reads columns off the wrong doctype** and channel/order-id
filters quietly stop matching. No exception, no log line, wrong results.

#### The correct port

Keep `doctype` in **position 2** so the existing positional calls stay valid,
and add `purpose` as a third keyword-only-in-practice parameter:

```python
def _first_column(candidates, doctype=INVOICE_DOCTYPE, purpose=None):
    """First candidate fieldname that exists as a column on the given sale
    doctype, or None. With `purpose`, an admin-configured mapping (LumenPOS
    Settings → Field Mapping) wins when its column exists — the same
    precedence _set_custom/_get_custom use, so search reads the very field
    sales write to."""
    if purpose:
        configured = mapped_field(purpose)
        if configured and frappe.db.has_column(doctype, configured):
            return configured
    for fieldname in candidates:
        if frappe.db.has_column(doctype, fieldname):
            return fieldname
    return None
```

Call sites keep `doctype` positional and add the purpose by name:

```python
app_field      = _first_column(("custom_app_type", "lumenpos_app_type"), doctype, purpose="app_type")
order_field    = _first_column(("pick_order_no", "custom_order_id", "lumenpos_order_id"), doctype, purpose="order_id")
online_field   = _first_column(("online_order", "custom_online_order", "is_online_order"), doctype)
```

Apply the same "add, never replace" rule to `_set_custom(doc, candidate_fields,
value, purpose=None)` and `_get_custom(doc, candidate_fields, purpose=None)`
— both are called positionally elsewhere too.

#### Verify before you commit

**1) Open History and Customers.** They are the only screens that exercise
`search_sales`; a sell-path smoke test proves nothing here.

**2) Run the AST sweep** that caught this class of bug in VPOS. It compares
every keyword argument in the app against the signature of the function it
targets — one command, no site needed:

```bash
python - <<'PY'
import ast, pathlib
defs, calls = {}, []
for f in pathlib.Path("lumenpos").rglob("*.py"):
    tree = ast.parse(f.read_text(encoding="utf-8-sig"))   # utf-8-sig: some files carry a BOM
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = node.args
            names = {x.arg for x in a.posonlyargs + a.args + a.kwonlyargs}
            defs.setdefault(node.name, []).append((names, a.kwarg is not None))
        elif isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            kw = [k.arg for k in node.keywords if k.arg]
            if name and kw:
                calls.append((name, kw, str(f), node.lineno))
bad = [f"{f}:{ln} -> {n}({', '.join(k+'=' for k in kw)})"
       for n, kw, f, ln in calls if n in defs
       and not any(has_kw or all(k in acc for k in kw) for acc, has_kw in defs[n])]
print("\n".join(bad) if bad else f"CLEAN — {len(calls)} keyword calls match their defs")
PY
```

It only catches Trap 1 (keyword mismatches). **Trap 2 is invisible to it** —
positional arguments are always "valid" — so for that one the guard is the
rule itself: *never reorder or remove an existing parameter; append new ones.*

## 3.2 · Split payments on refunds (v0.49.0, refund half only)

New shared component `SplitPayments.vue` (props `modelValue`, `total`,
`collecting`, `allowedModes`, `extraModes`): method tiles drop the remaining
amount on tap, each line has an amount + `reference_no` honouring the
require-reference rule, and the sum must match to the cent.

**Direction matters** (the user's explicit rule, "نعم اريد هذه التفرقة"):
- **collecting** money → any tender allowed
- **refunding** money → restricted to the refund-method rules

Backend `create_return(..., refund_payments=None)`: `_refund_splits()`
normalises the rows (sum must equal the refund ±0.005, legacy single-mode
fallback kept), **every** requested tender is validated against
`_allowed_refund_modes`, store credit is issued from the split rows only, and
`_apply_payment_references` stamps the references. `RefundModal.vue` uses
`SplitPayments` with `collecting=false` and gates the submit button on
`splitCovered`.

*(The ExchangeModal half of this commit is excluded.)*

---

# Priority 4 — Screens & UX (small, independent)

| # | VPOS | What to port |
|---|---|---|
| 4.1 | v0.43.1 `d300446` | **Top-bar clock + shift timer as two separate pills** — a neutral wall-clock pill and a brand-tinted "shift open for" pill with an hourglass icon, so they don't read as one number. Ticks every second in `App.vue`. |
| 4.2 | v0.44.0 `70ff27f` | **Price checker → per-warehouse stock.** New `catalog.stock_by_warehouse(item_code, pos_profile)` returns per-Bin qty / reserved / available + company + `is_here`, sorted this-store-first; `PriceCheckModal.vue` makes the stock number expandable. LumenPOS has the modal but not this endpoint. |
| 4.3 | v0.45.0 `bf1105e` | **"Open in History" from a customer's invoice.** `ReceiptModal.vue` gains a `show-open-in-history` prop; `CustomersView.vue` pushes `/history?invoice=…`; `HistoryView.vue` reads `route.query.invoice` on mount, sets the search + all-outlets filter and opens that invoice. *The user chose navigation over duplicating the refund flow into Customers — one money-flow path only.* |
| 4.4 | v0.45.1 `ef8c0c7` | **Selected-customer-row readability.** VPOS's bug was a solid `--brand-soft` background with dark text. LumenPOS already uses a 10% tint, so mostly verify: confirm explicit text colours in **both** light and dark themes. |

---

# Priority 5 — Performance (v0.46.0 `bb4f631`, non-exchange half)

`get_returnable` issued **one `Serial No` query per serial**, so a serialized
invoice crawled. Batch it:

```python
delivered = set()
all_serials = list({s for serials in sold_serials.values() for s in serials})
if all_serials:
    delivered = set(frappe.get_all("Serial No",
        filters={"name": ["in", all_serials], "status": "Delivered"}, pluck="name"))
...
returnable_serials = [s for s in sold_serials.get(row.item_code, []) if s in delivered]
```

*(The `exchanges.lookup` fast-path half of this commit is excluded — but if
LumenPOS ever does leading-wildcard `LIKE` scans over the invoice table in
its own lookup, the same trick applies: exact-PK check first, prefix match
for numbers, and only then the wildcard scan.)*

---

# Deliberately excluded (Exchange work, per request)

| VPOS | Why it's excluded |
|---|---|
| v0.46.1 `16fe8b5` | Free (zero-value) item under warranty is exchangeable — pure exchange |
| v0.47.0 (part) | Exchange **exception requests** (warranty-refused swaps approved by a role) |
| v0.49.0 (part) | `ExchangeModal.vue` split payments + `exchanges.py` settle/refund normalisers |
| v0.46.0 (part) | `exchanges.lookup` fast path |
| v0.43.0 (part) | `map_exchange_field` / `is_exchange` mapping purpose — optional; keep the purpose infrastructure, skip the exchange purpose |

Also excluded from earlier in the session (not today's work, listed for
completeness): exchange traceability (`exchange_against_invoice`), warranty
counted from the original invoice, warranty-depreciated exchange credit, and
exchange-specific serial rules.

---

# Suggested order

1. **0.1** — the live X-report bug (5 minutes, real impact)
2. **Priority 1** as one release — the shift lifecycle is the highest-value
   block and internally coupled
3. **3.1** — payment rules + field mapping. **Read §3.1-TRAP first**: the
   field-mapping half rewires three helper signatures, and in LumenPOS one of
   the wrong ways to do it fails *silently* (wrong doctype in Sales-Invoice
   mode) instead of raising. Verify by opening History + Customers, and run
   the AST sweep printed there.
4. **2.1 + 2.2** — approvals
5. **3.2** — refund split payments (depends on 3.1's reference rules)
6. **Priority 4 + 5** — independent, ship whenever

Every backend change above was compile-checked in VPOS, and the schedule
matcher and PIN hashing carry unit tests worth porting with them.
