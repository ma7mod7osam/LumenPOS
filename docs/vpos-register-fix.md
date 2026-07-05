# VPOS: a stuck/slow POS Closing must never block the next shift

Apply this to VPOS. Its code is identical to LumenPOS's, so the edits below are exact. (Shipped in LumenPOS as v0.20.0.)

**The rule:** the **POS Register Session status** is the only gate for opening a register.
- Register **Open** → go straight to selling (don't ask to open).
- Register **anything else** (`Closing` with consolidation Pending / Queued / **Failed**, or `Closed`) → let the cashier open a **new** shift now. The old shift's POS Closing Entry consolidation finishes and self-heals in the background, so no invoice is lost.

Today VPOS blocks opening while a session is `Closing` (`LIVE_STATES = ["Open", "Closing"]`), forcing a "retry the closing" gate — a slow or failed consolidation locks the outlet.

---

## 1. Backend — `vpos/api/register.py`, function `open_register`

**Find** this block (≈ lines 85–100):

```python
    if existing:
        if existing.status == "Closing":
            closing_status = frappe.db.get_value(
                "POS Register Session", existing.name, "closing_status"
            )
            # A genuinely FAILED close (not one still in progress) can be left
            # to the self-healer while a fresh shift is started — so a stuck
            # consolidation can't keep the store shut the next day.
            if cint(force_new) and closing_status == "Failed":
                return _force_new_after_failure(profile, opening_float, existing.name)
            resp = _retry_response(existing.name)
            resp["can_force_new"] = closing_status == "Failed"
            return resp
        frappe.throw(
            _("Register {0} already has an open session ({1}).").format(profile.name, existing.name)
        )
```

**Replace** it with:

```python
    if existing:
        if existing.status == "Open":
            frappe.throw(
                _("Register {0} already has an open session ({1}).").format(
                    profile.name, existing.name
                )
            )
        # status == "Closing": the cashier already closed this shift. Its POS
        # Closing Entry consolidation runs (and self-heals) in the background and
        # must NEVER block the store from opening the next shift — no matter the
        # closing_status (Pending / Queued / Failed). Open a fresh shift now; the
        # stuck close keeps retrying independently, so no invoice is lost.
        return _force_new_after_failure(profile, opening_float, existing.name)
```

`_force_new_after_failure` needs **no** change — it already opens a fresh POS Opening Entry + Register Session (via `ignore_validate`) and re-nudges the stuck consolidation. Nothing else in the backend changes: `get_open_session` already returns only `Open`, and the scheduled self-healer + the `retry_closing` endpoint already finish stuck consolidations.

*(Optional: rename `_force_new_after_failure` → `_open_new_over_closing_shift`, since it now handles any `Closing` state, not just Failed.)*

---

## 2. Frontend — `frontend/src/components/OpenRegisterOverlay.vue`

**Essential change (≈ line 33):** show "open a new shift" for *any* closing status, not just Failed.

```html
<!-- change -->
<div v-if="canClose && pending.closing_status === 'Failed'" class="force-new-block">
<!-- to -->
<div v-if="canClose" class="force-new-block">
```

**Recommended wording** (so it doesn't read as "you must retry first"):

- **≈ line 13**, replace the tail `{{ t('Retry the closing before opening a new shift.') }}` with:
  `{{ t('You can open a new shift now — it keeps finalising in the background.') }}`
- **≈ line 46**, the button label `{{ busy ? t('Opening…') : t('Start a new shift anyway') }}` →
  `{{ busy ? t('Opening…') : t('Open a new shift') }}`
- Optional: make the "Open a new shift" button `btn btn-primary` and demote the "Retry closing" button (≈ line 19) to `btn btn-outline`, so opening is the emphasized action.

If VPOS is bilingual, add the new strings to its `messages.js` Arabic map:

```js
"You can open a new shift now — it keeps finalising in the background.":
  "يمكنك فتح وردية جديدة الآن — وتستمر الوردية السابقة في الإنهاء بالخلفية.",
"Open a new shift": "فتح وردية جديدة",
```

Then rebuild: `cd frontend && npm run build`.

---

## 3. ⚠ Test this — it's financial

```
open → sell a few → close → immediately reopen → sell
→ confirm BOTH shifts consolidate into the CORRECT Sales Invoices
  (no invoice pulled into the wrong shift's closing).
```

While the old consolidation is pending, that shift's POS Opening Entry stays "Open", so the outlet briefly has **two open opening entries**. Consolidation is serialized behind a cluster lock and atomic (rolls back on failure), so nothing is half-posted — this is the same machinery VPOS already uses for its force-new-after-failure path; the change just makes it routine.

---

## Naming
No rename needed — `register.py` internals and the doctype names (`POS Register Session`, `POS Opening Entry`, `POS Closing Entry`) are the same in VPOS. Only unrelated app-level custom fields elsewhere use the `vpos_*` prefix.
