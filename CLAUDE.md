# Incognito — Developer Guide

Self-hosted GDPR/CCPA personal data removal tool. Python FastAPI backend + React/TypeScript frontend.

## Quick Reference

```bash
# Run backend
python cli.py serve

# Run tests (167 tests)
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
incognito rescan             # Re-scan and check for data reappearing
incognito brokers list       # List all brokers
incognito brokers stats      # Broker registry statistics
```

## Architecture

**Backend** (`backend/`):
- `api/` — FastAPI routes (auth, blast, brokers, requests, scan, settings, setup)
- `core/` — Business logic (crypto, profile vault, broker registry, request state machine, scheduler, rescan, templates, DPA registry, IMAP poller)
- `db/` — SQLAlchemy models + Alembic migrations. SQLite with WAL mode.
- `scanner/` — DuckDuckGo search, Holehe account discovery, HIBP breach check
- `senders/` — Email sender (SMTP via aiosmtplib)

**Frontend** (`frontend/src/`):
- `pages/` — Dashboard, Requests, RequestDetail, Brokers, Scan, Settings, SetupWizard
- `components/` — Layout, StatusBadge, ProgressRing
- `hooks/` — useAsyncTask (reusable polling hook for scanner UIs)
- `api/client.ts` — Typed API client

**Key patterns:**
- Profile encrypted at rest with AES-256-GCM (Argon2id KDF). Vault in `~/.incognito/profile.enc`
- Session store holds derived keys, never raw passwords
- Each API router is a factory function receiving its dependencies (no global state)
- Broker registry loaded from YAML files in `brokers/`
- Templates are Jinja2 with locale support (`templates/locales/{lang}/`)
- Request lifecycle: CREATED -> SENT -> ACKNOWLEDGED -> COMPLETED (with REFUSED/OVERDUE/ESCALATED branches)

## Security Model

- Login rate limiting: 5 failures = 10min lockout
- Sessions: max 3 concurrent, auto-expire after 30min idle
- Security headers on all responses (X-Frame-Options, CSP-adjacent, etc.)
- File permissions: 0600 on vault/db/keys, 0700 on data dir
- Backup export/import requires password re-entry
- Setup uses atomic file creation (O_CREAT|O_EXCL)
- CORS locked to localhost by default (configurable via INCOGNITO_CORS_ORIGINS)
- Swagger/ReDoc disabled in production
- Error messages sanitized (internals logged, generic messages to client)

## Testing

Tests in `tests/unit/` and `tests/integration/`. Use pytest fixtures from `tests/conftest.py`.
All tests use temp directories — no persistent state.

```bash
pytest tests/unit/test_auth_api.py -v    # Auth + rate limiting
pytest tests/unit/test_rescan.py -v      # Re-scan monitoring
pytest tests/unit/test_template.py -v    # GDPR/CCPA templates
pytest tests/unit/test_blast_api.py -v   # Blast creation
```

## Dependencies

Core deps in `pyproject.toml`. Optional extras:
- `pip install -e ".[scanner]"` — holehe for account discovery
- `pip install -e ".[automation]"` — Playwright for future web form automation
- `pip install -e ".[dev]"` — pytest, ruff, mypy

## Deployment

Rootless Podman with Quadlet systemd units in `deploy/`.
Container builds via `deploy/Containerfile` (multi-stage: Node frontend + Python backend).
CI builds and smoke-tests the container on every push.

## What's Not Built Yet

- Playwright web form sender (`senders/web.py`)
- API sender (`senders/api.py`, Data Rights Protocol)
- Multi-profile / family support
- `brokers update` command (pull latest from community repo)
