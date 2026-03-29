# Incognito — Developer Guide

Self-hosted GDPR/CCPA personal data removal tool. Python FastAPI backend + React/TypeScript frontend.

## Quick Reference

```bash
# Run backend
python cli.py serve

# Run tests (242 tests, 201 brokers, 23 DPAs)
python -m pytest tests/ -v

# Lint
ruff check .

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
- `api/` — FastAPI routes (auth, blast, brokers, requests, scan, settings, setup)
- `core/` — Business logic (crypto, profile vault, broker registry, request state machine, scheduler, rescan, templates, DPA registry, IMAP poller)
- `db/` — SQLAlchemy models + Alembic migrations. SQLite with WAL mode.
- `scanner/` — DuckDuckGo search, Holehe account discovery, HIBP breach check
- `senders/` — Email sender (SMTP), web form sender (Playwright), base result types

**Frontend** (`frontend/src/`):
- `pages/` — Dashboard, Requests, RequestDetail, Brokers, Scan, Settings, SetupWizard, Report
- `components/` — Layout, StatusBadge, ProgressRing, EmailThread
- `hooks/` — useAsyncTask (polling for scanners), useSettingsSection (settings state)
- `api/client.ts` — Typed API client

**Key patterns:**
- Profile encrypted at rest with AES-256-GCM (Argon2id KDF). Vault in `~/.incognito/profile.enc`
- Session store holds derived keys, never raw passwords
- Each API router is a factory function receiving its dependencies (no global state)
- Broker registry loaded from YAML files in `brokers/`
- Templates are Jinja2 with locale support (`templates/locales/{lang}/`) — en, de, fr, es, it, nl, pl, ccpa
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
- File permissions: 0600 on vault/db/keys, 0700 on data dir
- Backup export/import requires password re-entry
- Setup uses atomic file creation (O_CREAT|O_EXCL)
- Empty password protection on vault save/create
- CORS locked to localhost by default (configurable via INCOGNITO_CORS_ORIGINS)
- Swagger/ReDoc disabled in production
- Reverse proxy auth header support (Authentik/Authelia/Traefik ForwardAuth)
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
```

## Dependencies

Core deps in `pyproject.toml`. Optional extras:
- `pip install -e ".[scanner]"` — holehe for account discovery
- `pip install -e ".[automation]"` — Playwright for future web form automation
- `pip install -e ".[dev]"` — pytest, ruff, mypy

## Deployment

Docker Compose file in project root (`docker-compose.yml`).
Rootless Podman with Quadlet systemd units in `deploy/`.
Container builds via `deploy/Containerfile` (multi-stage: Node frontend + Python backend).
Container includes HEALTHCHECK on `/api/health`.
Prometheus metrics at `/api/metrics`.
CI builds and smoke-tests the container on every push.
Systemd timers: follow-up (daily 9am), rescan (weekly Monday 10am), check-replies (every 15 min).
Timer services use `EnvironmentFile` for password (`~/.config/incognito/env`).

## What's Not Built Yet

- Form definitions for individual web_form brokers (`brokers/forms/*.yaml`)
- API sender (`senders/api.py`, Data Rights Protocol)
- Multi-profile / family support
