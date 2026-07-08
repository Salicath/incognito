# Incognito — Developer Guide

Self-hosted GDPR/CCPA personal data removal tool. Python FastAPI backend + React/TypeScript frontend.

## Quick Reference

```bash
# Run backend
python cli.py serve

# Run tests (477 tests, 220 brokers, 16 controllers, 23 DPAs)
python -m pytest tests/ -v

# Lint
ruff check .

# Security scan
bandit -r backend/ -c pyproject.toml -ll -q

# Full quality check (lint + security + tests)
ruff check . && bandit -r backend/ -c pyproject.toml -ll -q && python -m pytest tests/ -x -q

# Frontend dev (proxies API to :8080)
cd frontend && npm run dev

# Frontend build
cd frontend && npm run build

# CLI commands
incognito serve              # Start web server
incognito status             # Show request stats
incognito send --no-dry-run  # Create requests for all brokers
incognito follow-up --auto   # Check deadlines, send follow-ups
incognito check-replies      # Check IMAP inbox for broker replies
incognito rescan             # Re-scan and check for data reappearing
incognito brokers list       # List all brokers
incognito brokers stats      # Broker registry statistics
incognito brokers update     # Update brokers from GitHub
incognito report             # Privacy score and exposure report
```

## Architecture

**Backend** (`backend/`):
- `api/` — FastAPI routes (auth, blast, brokers, controllers, cpr_levers, requests, scan, settings, setup, statutory)
- `core/` — Business logic (crypto, profile vault, broker registry, request state machine, scheduler, rescan, templates, DPA registry, IMAP poller)
- `db/` — SQLAlchemy models + Alembic migrations. SQLite with WAL mode.
- `scanner/` — DuckDuckGo search, user-scanner account discovery (email axis), HIBP breach check, Wayback CDX archived-profile scan, GitHub code-leak scan, Maigret deep username enumeration (isolated subprocess, ~3000 sites), newsletter scan (IMAP List-Unsubscribe discovery), SearXNG sidecar backend (`scanner/searxng.py`, used for discovery scans when `INCOGNITO_SEARXNG_URL` is set; delisting re-verification stays on DDG for the Bing surface)
- `senders/` — Email sender (SMTP), web form sender (Playwright), base result types

**Frontend** (`frontend/src/`):
- `pages/` — Dashboard, Requests, RequestDetail, Brokers, Controllers, CprLevers, Statutory, Scan, Exposures, Settings, SetupWizard, Report
- `components/` — Layout, StatusBadge, ProgressRing, EmailThread
- `hooks/` — useAsyncTask (polling for scanners), useSettingsSection (settings state)
- `api/client.ts` — Typed API client

**Key patterns:**
- Profile encrypted at rest with AES-256-GCM (Argon2id KDF). Vault in `~/.incognito/profile.enc`
- Session store holds derived keys, never raw passwords
- Each API router is a factory function receiving its dependencies (no global state)
- Broker registry loaded from YAML files in `brokers/`
- Templates are Jinja2 with locale support (`templates/locales/{lang}/`) — en, da, de, fr, es, it, nl, pl, ccpa
- CPR lever track (`core/cpr_lever.py`, `brokers/cpr_levers.yaml`): Danish upstream protections the user performs via MitID; active levers cover cascade brokers so blast skips them (see `docs/tracks/cpr_lever.md`). Renewal ladder (T-30/T-7/expiry) fires from the `follow-up` command via `check_lever_renewals`.
- Controller track (`core/controller.py`, `brokers/controllers.yaml`, `docs/tracks/controller.md`): opt-in tech-giant erasure — 16 hand-verified platforms, never blasted (separate `ControllerRegistry`; `RegistryUnion` feeds shared machinery). Email-viable platforms send a controller-specific Art. 17 immediately; form-only ones enter MANUAL_ACTION_NEEDED with a filing kit and the user attests "I filed it" (→ SENT starts the Art. 12(3) clock). Complaints route to the residence SA via `dpa.get_dpa_for_request` (`INCOGNITO_USER_COUNTRY`, default DK; GB→ICO), with the lead SA named in the complaint text.
- Exposure triage: every scanner (DDG, user-scanner, Wayback, GitHub, Maigret) persists hits to `scan_results`; the Exposures inbox (`GET /api/scan/exposures`) aggregates them and drives each to a disposition (actioned/dismissed/legally_impossible). Hits matching a registry broker get a one-click Art. 17 request (`create-request`); others get per-source `core/removal_guidance.py` steps. Account hits (user-scanner/Maigret) are resolved against the vendored JustDelete.me dataset (`core/account_registry.py`, `data/justdeleteme_sites.json`) to surface the exact deletion URL + difficulty; `difficulty: impossible` routes toward the `legally_impossible` disposition. Newsletter hits carry an unsubscribe action (`POST /api/scan/exposures/{id}/unsubscribe`): RFC 8058 one-click POST via `core/unsubscribe.py` (SSRF-guarded, HTTPS-only, no redirects), or a mailto send via the SMTP sender. Any URL exposure carries a delisting kit (`GET /api/scan/exposures/{id}/delisting-kit`, `core/delisting.py`): per-engine RTBF deep-links (Google/Bing forms + Brave email) plus a drafted, locale-aware Art. 17 justification — filing is manual (ID-gated forms), but the lifecycle is tracked (`docs/tracks/delisting.md`): "I filed it" creates a `(URL, engine)` request (`Request.target_url`, `DelistingRegistry` pseudo-targets in the `RegistryUnion`) with the Art. 12(3) clock; decision emails match via `ImapPoller._match_delisting_decision` (Google URL-in-body → auto-ACK, Bing attach-only); escalation routes to the residence SA (Google = Art. 55 national case vs Google LLC); the weekly rescan flags resurfaced delisted URLs.
- Statutory tracks (`core/time_locked.py`, `core/restriction_only.py`, `brokers/{time_locked,restriction_only}.yaml`, `docs/tracks/{time_locked,restriction_only}.md`): time_locked arms per-institution retention holds (bank +5y exact, bogføring FY+5y+1d, insurer 3y/10y, telco 3y, employer 5y) and the `follow-up` job fires an assist-only Art. 17 kit (da template) when the duty matures; restriction_only serves 9 honest "legally undeletable + what you CAN do" cards. Both on the Statutory page via `api/statutory.py`.
- Request lifecycle: CREATED -> SENT -> ACKNOWLEDGED -> COMPLETED (with REFUSED/OVERDUE/ESCALATED branches)
- IMAP poller runs as asyncio background task, polls for broker replies
- Outgoing emails include Message-ID header and [REF-XXXXXXXX] in subject for reply matching

## IMAP Reply Monitoring

Automatically detects broker responses to GDPR requests:
- Background poller connects to IMAP inbox on configurable interval
- 3-tier reply matching: Message-ID threading → subject reference code → sender domain
- Matched replies auto-transition requests to ACKNOWLEDGED
- Supports Proton Bridge (STARTTLS on localhost:1143) and standard IMAP (SSL on port 993)
- Email thread displayed in request detail page
- Unread reply badges on dashboard
- Config stored encrypted in vault alongside SMTP
- `check-replies` CLI command + systemd timer for non-server usage

## Push Notifications

Supports Ntfy, Gotify, and generic webhooks. Set `INCOGNITO_NOTIFY_URL` to enable.
Events: reply received, request overdue, escalation sent, data reappeared, new exposure, blast complete, follow-up complete.
Ntfy messages include priority levels and emoji tags. Notifications never crash the calling code.

## Security Model

- Login rate limiting: 5 failures = 10min lockout
- Sessions: max 3 concurrent, auto-expire after 30min idle
- Security headers on all responses (X-Frame-Options, CSP-adjacent, etc.)
- File permissions: 0600 on vault/db, 0700 on data dir
- API secrets (HIBP key, GitHub token) stored encrypted in the vault (`_VaultData.secrets` via `core/secrets.py`); legacy plaintext `*_key.txt`/`*_token.txt` files auto-migrate into the vault on first access, then are deleted
- Backup export/import requires password re-entry
- Setup uses atomic file creation (O_CREAT|O_EXCL)
- Empty password protection on vault save/create
- CORS locked to localhost by default (configurable via INCOGNITO_CORS_ORIGINS)
- Swagger/ReDoc disabled in production
- Reverse proxy header is surfaced on `/api/auth/status` as `proxy_auth` (Authentik/Authelia/Traefik), but does NOT bypass the vault unlock — the master password is always required (the vault key derives from it)
- Error messages sanitized (internals logged, generic messages to client)

## Testing

Tests in `tests/unit/` and `tests/integration/`. Use pytest fixtures from `tests/conftest.py`.
All tests use temp directories — no persistent state.

```bash
pytest tests/unit/test_auth_api.py -v         # Auth + rate limiting
pytest tests/unit/test_rescan.py -v           # Re-scan monitoring
pytest tests/unit/test_template.py -v         # GDPR/CCPA templates
pytest tests/unit/test_blast_api.py -v        # Blast creation
pytest tests/unit/test_imap.py -v             # IMAP matching + poller
pytest tests/unit/test_imap_api.py -v         # IMAP settings API
pytest tests/unit/test_scheduler_followup.py -v  # Follow-up/escalation logic
pytest tests/unit/test_scan_api.py -v         # Scan API endpoints
pytest tests/unit/test_init_db.py -v          # DB migration handling
pytest tests/unit/test_notifier.py -v         # Push notification system
pytest tests/unit/test_exposure_report.py -v  # Exposure report API
pytest tests/unit/test_brokers_update.py -v   # Broker update command
pytest tests/unit/test_cpr_lever.py -v        # CPR lever track (DK upstream protections)
pytest tests/unit/test_controller.py -v       # Controller track (registry, kit, DPA routing)
pytest tests/unit/test_controller_api.py -v   # Controller track API (opt-in flow, complaint)
pytest tests/unit/test_wayback.py -v          # Wayback CDX archived-profile scanner
pytest tests/unit/test_github_scanner.py -v   # GitHub code-leak scanner
pytest tests/unit/test_user_scanner.py -v     # Account scanner (email axis, user-scanner)
pytest tests/unit/test_maigret_scanner.py -v  # Maigret deep username scanner
pytest tests/unit/test_exposures.py -v        # Exposure triage inbox (disposition routing) + unsubscribe
pytest tests/unit/test_account_registry.py -v # JustDelete.me account-deletion lookup
pytest tests/unit/test_newsletter.py -v       # Newsletter List-Unsubscribe parsing/scan
pytest tests/unit/test_unsubscribe.py -v      # RFC 8058 one-click unsubscribe + SSRF guard
pytest tests/unit/test_delisting.py -v        # Search-engine delisting (RTBF) assist kit
pytest tests/unit/test_statutory.py -v        # time_locked + restriction_only tracks
pytest tests/unit/test_searxng.py -v          # SearXNG sidecar scanner backend
pytest tests/unit/test_delisting_lifecycle.py -v  # Delisting lifecycle (tracking, IMAP decisions, complaint)
```

## Dependencies

Core deps in `pyproject.toml`. Optional extras:
- `pip install -e ".[scanner]"` — user-scanner for email-axis account discovery
- `pip install -e ".[scanner-deep]"` — maigret for deep username enumeration (heavy deps; container installs it into an isolated `/opt/maigret` venv)
- `pip install -e ".[automation]"` — Playwright for future web form automation
- `pip install -e ".[dev]"` — pytest, ruff, mypy

## Deployment

Docker Compose file in project root (`docker-compose.yml`).
Rootless Podman with Quadlet systemd units in `deploy/` (incl. optional SearXNG sidecar: `searxng.container` + `searxng-settings.yml`).
Container builds via `deploy/Containerfile` (multi-stage: Node frontend + Python backend).
Container includes HEALTHCHECK on `/api/health`.
Prometheus metrics at `/api/metrics`.
CI builds and smoke-tests the container on every push.
Systemd timers: follow-up (daily 9am), rescan (weekly Monday 10am), check-replies (every 15 min).
Timer services use `EnvironmentFile` for password (`~/.config/incognito/env`).

## Code Quality Tooling

**Quick commands:**
```bash
# Full quality check (lint + security + tests + types)
ruff check . && bandit -r backend/ -c pyproject.toml -ll -q && python -m pytest tests/ -x -q

# Type checking
python -m mypy backend/ --config-file pyproject.toml

# Frontend type check
cd frontend && npx tsc --noEmit

# Dependency vulnerability scan
pip-audit
cd frontend && npm audit
```

**Claude Code commands** (`.claude/commands/`):
- `/audit <file-or-directory>` — Focused security + quality audit: runs bandit, mypy, ruff on target, then manual code review for OWASP issues, race conditions, data integrity, performance
- `/check` — Run full quality suite: ruff, bandit, pytest, mypy, tsc

**Claude Code hooks** (`.claude/settings.json`): Post-edit hook auto-runs ruff on changed Python files via `.claude/hooks/lint-after-edit.sh`.

**Pre-commit hooks** (`.pre-commit-config.yaml`): ruff lint+format, bandit security scan, gitleaks secret detection. Install with `pre-commit install`.

**CI pipeline** (`.github/workflows/ci.yml`): Runs ruff, bandit, pytest, TypeScript type check, broker YAML validation, container build+smoke test on every push/PR.

**Tool config** in `pyproject.toml`:
- `[tool.bandit]` — excludes tests/frontend, skips B101 (assert)
- `[tool.mypy]` — Python 3.12, `check_untyped_defs = true`, `ignore_missing_imports = true`
- `[tool.pytest.ini_options]` — asyncio_mode auto

**Dev dependencies** (`pip install -e ".[dev]"`): bandit (security), pip-audit (CVE scanning), pre-commit, mypy (type checking), ruff (lint), pytest-cov (coverage).

## What's Not Built Yet

- Form definitions for individual web_form brokers (`brokers/forms/*.yaml`)
- API sender (`senders/api.py`, Data Rights Protocol)
- Multi-profile / family support
