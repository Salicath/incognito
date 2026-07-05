# Maximal Account-Discovery Scanner Layer — Design

**Date:** 2026-07-03
**Owner:** Malte
**Plan item:** Phase 2 — "Maigret + user-scanner integration (replace Holehe)"

## Goal

Maximize discovery of accounts and profiles tied to the user's identifiers (email,
username), feeding the existing Exposures triage inbox so each hit is driven to
deletion (Art. 17) or removal guidance. Replace the dead `holehe` engine.

The deletion machinery already exists: every scanner persists hits via
`save_scan_results(db, hits, source=<label>)` → `scan_results` table →
`GET /api/scan/exposures` aggregates → triage disposition → matched broker gets a
one-click Art. 17 request, others get per-source `removal_guidance.py` steps. This
work adds scanners at the *front* of that pipeline; it does not touch the pipeline.

## Tool decisions (research-backed, 2026-07-03)

| Tool | Axis | Verdict | Why |
|---|---|---|---|
| holehe | email→account | **Drop** | Dead (last commit 2024-09-10), `trio`-based, masks failures as `rateLimit:True` → false negatives |
| **user-scanner** (kaifcodec) | email + username → account | **Adopt, in-process** | MIT, commits landing this week, asyncio/httpx-native (drops into the FastAPI loop), lightest deps of any maintained option (`httpx[http2]`, `socksio`, `colorama` — no compiled deps). 105 email + 185 username vectors. Retires dead modules instead of returning garbage. |
| **Maigret** (soxoj) | username → account | **Adopt, isolated subprocess** | MIT, 3000 sites, *verifies* profiles (low false-positive) and extracts profile data. Heavy dep tree (flask/lxml/curl-cffi/reportlab/pyvis/networkx) — kept out of the app env by running in its own venv via the CLI `--json`. |
| WMN dataset | username → account | **Skip** | Maigret's corpus supersets its 719 sites and verifies them; redundant once Maigret is in. |
| Wayback / DDG / HIBP / GitHub | archived profiles / name / breach / code-leak | **Keep unchanged** | Distinct axes; complement account existence. |
| phone axis | phone → account | **Documented gap, deferred** | No maintained tool exists (ignorant dead, 3 sites). GitHub scanner still catches phone-in-code. |

## Architecture

Two scanner modules under `backend/scanner/`, each following the established pattern
(async run in a FastAPI `BackgroundTask` → `save_scan_results(source=...)` → Exposures
inbox). No changes to the request state machine, registry, or triage layer.

### 1. `backend/scanner/user_scanner.py` (replaces `holehe_scanner.py`)

Thin adapter around the internal `user_scanner.core.engine.check_all(target, is_email=...)`.
The internal import is isolated to this one module so that if user-scanner's (currently
unstable) API churns, the fix is one file.

- Keeps the `AccountHit` / `AccountReport` dataclass shapes so downstream mapping is
  unchanged.
- Exposes `check_email_accounts(email, on_progress)` — a **1:1 email-axis replacement**
  for holehe. The username axis is intentionally *not* exposed here: Maigret's 3000-site
  sweep supersets user-scanner's 185 username vectors, so a second username scanner in
  the UI would be pure redundancy. One tool per axis: user-scanner owns email, Maigret
  owns username.
- Per-site exceptions suppressed (as holehe did); `ImportError` recorded in
  `report.errors`, never raised.
- Source label: `userscan:<email>`.

### 2. `backend/scanner/maigret_scanner.py` (new)

Subprocess wrapper — never imports maigret into the app process.

- Locates the maigret binary via `INCOGNITO_MAIGRET_BIN` env var, default `maigret`
  on `PATH`.
- Runs `maigret <username> --json simple --top-sites <N> --timeout <T> --no-recursion
  --no-color --folder <tmpdir>`, then parses the emitted JSON report.
- Maps found sites (`status.is_found()` equivalent in the JSON) → `AccountHit`
  (service, url, profile data where present).
- Bounds `--top-sites` (default 500, configurable) to keep runtime sane; the "deep"
  ceiling (up to 3000) is an explicit opt-in.
- Degrades gracefully: missing binary → `report.errors = ["maigret not installed"]`;
  subprocess timeout / non-zero exit / malformed JSON → recorded error, no crash.
- Source label: `maigret:<username>`.

### Integration points

- **`pyproject.toml`**: `[scanner]` extra — drop `holehe`, add `user-scanner>=1.4`.
  New `[scanner-deep]` extra = `maigret>=0.6.2` (installed into an isolated venv in the
  container, not the app env).
- **`deploy/Containerfile`**: `python -m venv /opt/maigret && /opt/maigret/bin/pip
  install maigret`; set `ENV INCOGNITO_MAIGRET_BIN=/opt/maigret/bin/maigret`.
- **`backend/api/scan.py`**:
  - Repoint the existing `/accounts/*` endpoints from `holehe_scanner` to
    `user_scanner` (email axis), preserving the API shape.
  - Add a username capability: either an `is_email`/`username` param on the account
    endpoints or a sibling `/accounts/username/*` set (decided in plan).
  - Add `/deep-scan/*` endpoints (start/status/results) for Maigret, mirroring the
    Wayback endpoint trio.
  - Source-label handling in `list_exposures` / the source→display mapping: add
    `userscan` and `maigret` → "Account".
- **`backend/core/removal_guidance.py`**: add `userscan` and `maigret` source prefixes
  → the same "Account" guidance holehe used.
- **Frontend** (`frontend/src/pages/Scan.tsx`): extend the account-scan card to accept a
  username target; add a "Deep username scan" card (opt-in, slow). `Exposures.tsx`:
  extend the source-label display map.

## Data flow

```
identifiers (email / username)
  → scanner (user_scanner in-process | maigret subprocess)
  → hits [{broker_domain, broker_name, url, email|username, profile fields}]
  → save_scan_results(db, hits, source="userscan:…" | "maigret:…")
  → scan_results table
  → GET /api/scan/exposures  (aggregate + dedup)
  → triage disposition (actioned / dismissed / legally_impossible)
  → matched registry broker → one-click Art. 17 request
     else                    → per-source removal guidance
```

## Error handling

- **user-scanner**: internal-API import guarded (`ImportError` → error field); per-site
  exceptions suppressed; no API key needed.
- **maigret**: missing binary, subprocess timeout, non-zero exit, malformed JSON all
  caught → error field; the scan card shows the error, the process never crashes.
  Bounded `--top-sites` prevents runaway runtime. No API key needed.
- Neither tool requires credentials or paid tiers.

## Testing

- `tests/unit/test_user_scanner.py` — mock `engine.check_all`; assert email + username
  hit mapping, source labels, `ImportError` path.
- `tests/unit/test_maigret_scanner.py` — mock subprocess + a sample JSON report; assert
  hit mapping, missing-binary path, timeout/malformed-JSON paths.
- Replace `tests/unit/test_holehe_scanner.py`.
- Update `tests/unit/test_exposures.py` and `tests/unit/test_removal_guidance.py` for
  the `userscan` / `maigret` sources.
- Full suite (`pytest tests/ -q`) + `ruff` + `bandit` green before merge.

## Sequencing

1. **user-scanner swap** — self-contained, unblocks holehe removal. Ship first.
2. **Maigret deep scan** — subprocess module + container venv + frontend card.

## Out of scope

- Phone-axis account enumeration (no maintained tool; deferred).
- SearXNG sidecar, HIBP paid tier, PimEyes import (separate Phase 2 items).
- Any change to the triage/registry/state-machine layers.
