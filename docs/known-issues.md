# Known issues / deferred findings

From the Phase 5 whole-repo read-through (2026-07-08). The correctness/security
and cheap items were fixed (see the `fix(review)` and follow-up commits); these
remain, ranked. Each is anchored to a file so the next maintainer can pick one up.

## Worth doing

- **`time_locked` `escalation_after_days` has no automatic action.** It is now
  surfaced as guidance in the kit modal ("no reply within a month → Datatilsynet
  complaint"), which matches the assist-only design. A fully-automatic escalation
  would need a `fired_at`/reminder-stage on `TimeLockedState` (migration) — do that
  only if the manual nudge proves insufficient.
- **Web `/rescan` new-exposure detection is still cosmetic-only.** The scheduled
  CLI path was fixed (check-before-save); the web GET reads already-saved hits so
  `new_exposures` stays empty there. Fixing needs the check moved into `_run_scan`
  before the save, stashing the result in `_state`. Low urgency — the timer runs
  the CLI path, which is correct.
- **Web `/rescan` never runs `verify_delisted_urls`** (`api/scan.py`). Only the CLI
  rescan does. The scheduled timer runs the CLI, so real monitoring works; the web
  view just doesn't re-verify delisted URLs live. Wiring it means calling the async
  helper from the sync GET (asyncio.run) — acceptable but adds latency.
- **Deep-scan results show only the last username** (`api/scan.py` `_run_deep_scan`).
  `_deep_state["report"]` is overwritten per username; earlier usernames' hits/errors
  are dropped. Accumulate across the loop.
- **`save_scan_results` has no dedup** (`core/rescan.py`). Every weekly rescan
  re-inserts hits, so a dismissed exposure reappears as a fresh `needs_triage` row.
  Carry disposition forward by (source, url) or dedup on insert.

## Low severity

- **`/api/metrics` is unauthenticated** (`main.py`) — leaks per-status request
  counts, broker total, scan-result count. Fine on the default loopback bind; add a
  token/allowlist before exposing via the documented Traefik setup.
- **Login rate-limit keys on `request.client.host`** (`api/auth.py`), ignoring
  `X-Forwarded-For`. Behind the documented reverse proxy every client shares the
  proxy IP, so 5 failures from anyone locks out the real user. Extract the real IP
  when a trusted proxy header is configured.
- **`time_locked` fire notification reuses `EventType.REQUEST_OVERDUE`**
  (`core/time_locked.py`) — webhook/ntfy consumers see a "request_overdue" warning
  for a "retention lapsed, send now" prompt. Add a dedicated event type.
- **Newsletter `mailto` subject with a percent-encoded CR (`%0D`) can 500 the
  unsubscribe endpoint** (`senders/email.py`) — `build_message()` runs outside
  `send()`'s try block, so `EmailMessage` raises `ValueError` unhandled. Sanitize
  the subject or move construction inside the guard.
- **`verify_delisted_urls` hardcodes `region="dk-da"`** (`core/rescan.py`), ignoring
  `INCOGNITO_USER_COUNTRY`. A GB/DE user's RTBF filter is market-scoped (C-507/17),
  so DK region is wrong for them. Needs a country→`kl` map (DK→dk-da, GB→uk-en, ...).
- **Modal a11y** (`Controllers.tsx`, `Statutory.tsx`) — the filing-kit overlays are
  plain fixed `div`s with no `role="dialog"`/`aria-modal`/focus trap/Esc close.
  Legally significant "I filed it" actions live in them.
- **`EmailThread.tsx` is unreadable in dark mode** — `bg-blue-50`/`bg-green-50` have
  no dark variants while the text switches to light shades (light-on-light).
- **Dead code**: `AccountHit.email_recovery`/`phone_recovery` (always null, holehe
  legacy), and unused `api/client.ts` methods (`exportBackup`, `importBackup`,
  `getBroker`, `getScanHistory`, `getImapPollerStatus`, `getAuditTrail` — Settings
  re-implements backup with raw `fetch`). `BreachResults.total_breaches` is typed
  required but omitted in the no-report branch.

## Fixed in this pass (for reference)

WAL backup export/import; create-request reusing terminal requests; SSRF CGNAT gap;
rescan ordering + notify-on-GET spam; scan errors surfaced; scan stuck_timeout;
CPR mutual-exclusion dead-end; newsletter unsubscribe button gate; App loading hang;
Requests `?status=` filter; Brokers/DelistingKit error handling; HIBP "plain text"
copy; imap status `last_error`; maigret `--folderoutput`; arm-past-expiry
notification; Settings destructive-action confirms; CprLevers shared defer note;
address capture (SetupWizard + Settings fields, preserve-on-save);
`escalation_after_days` surfaced as kit guidance.
