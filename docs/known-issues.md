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

## Low severity

_(none outstanding — the Phase 5 read-through list is cleared.)_

New findings should be appended here with a file anchor and a concrete
failure scenario, the same way the read-through recorded them.

## Fixed in this pass (for reference)

WAL backup export/import; create-request reusing terminal requests; SSRF CGNAT gap;
rescan ordering + notify-on-GET spam; scan errors surfaced; scan stuck_timeout;
CPR mutual-exclusion dead-end; newsletter unsubscribe button gate; App loading hang;
Requests `?status=` filter; Brokers/DelistingKit error handling; HIBP "plain text"
copy; imap status `last_error`; maigret `--folderoutput`; arm-past-expiry
notification; Settings destructive-action confirms; CprLevers shared defer note;
address capture (SetupWizard + Settings fields, preserve-on-save);
`escalation_after_days` surfaced as kit guidance; scan-result dedup
(dismissed exposures no longer resurrect each rescan); deep-scan results
accumulate across all usernames; proxy-aware login rate limiting;
optional `/api/metrics` bearer token; email header CR/LF sanitization;
dedicated `RETENTION_LAPSED` event; `verify_delisted_urls` region follows
`INCOGNITO_USER_COUNTRY`; accessible `<Modal>` (role/aria/Esc/backdrop) for
both filing kits; `EmailThread` dark mode; dead client methods and
always-null `AccountHit` recovery fields removed; `total_breaches` contract.
