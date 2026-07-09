# Incognito

Self-hosted tool that automates GDPR and CCPA personal data removal requests.

[![CI](https://github.com/Salicath/incognito/actions/workflows/ci.yml/badge.svg)](https://github.com/Salicath/incognito/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-green.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-526_passing-brightgreen.svg)](tests/)

## What It Does

Incognito scans for your personal data across 228 data brokers, 16 tech giants and the open web, sends legally-binding GDPR Art. 17 and CCPA deletion requests, tracks the 30-day compliance deadline, monitors for broker replies via IMAP, and generates DPA complaints when controllers fail to respond. Beyond brokers it covers tech-giant account erasure, search-engine delisting (RTBF), Danish registry-level protections (CPR levers), statutory retention holds that fire the moment erasure becomes demandable, and honest "this is legally undeletable — here is what you can do" guidance. Everything runs on your own machine — no cloud, no telemetry, no third-party accounts.

**Free alternative to DeleteMe ($129/year) and Incogni ($78/year).**

## Why Self-Host?

- **Your data never leaves your machine.** Profile encrypted at rest with AES-256-GCM (Argon2id KDF). Zero external dependencies.
- **No subscription.** $0/year, forever.
- **No conflicts of interest.** Commercial removal services are funded by the same data broker industry.
- **Full transparency.** Every email is generated from auditable Jinja2 templates. You see exactly what gets sent.
- **Complete audit trail.** Export your full GDPR paper trail as CSV — something no commercial tool offers.

## Key Features

- **228 data brokers** (EU/Nordic-focused, plus US and international)
- **Tech-giant erasure** — 16 hand-verified controllers (Meta, Google, Reddit, ...) with per-platform filing kits and jurisdiction-aware DPA escalation
- **Search-engine delisting** — Google/Bing/Brave RTBF kits with tracked lifecycle, decision-email matching and resurfacing alerts
- **Danish CPR levers & statutory tracks** — one MitID action covers whole broker clusters; retention holds fire an Art. 17 the day the legal duty matures
- **Exposure scanning** — DuckDuckGo or a self-hosted SearXNG sidecar, Have I Been Pwned, Wayback Machine ghost profiles, GitHub code-leak search, account discovery by email (user-scanner) and username (Maigret, ~3000 sites), newsletter discovery via IMAP
- **Exposures inbox** — every hit triaged to a one-click request, guided removal steps, or an honest "legally impossible"
- **9 languages** — English, Danish, German, French, Spanish, Italian, Dutch, Polish, CCPA
- **IMAP reply monitoring** — auto-detect broker responses in your inbox
- **30-day deadline tracking** with automatic follow-up and escalation emails
- **DPA complaint generation** — pre-filled complaints for 23 supervisory authorities
- **Privacy score** — A-F grade with exposure report and audit trail CSV export
- **Push notifications** — Ntfy, Gotify, or webhook alerts for replies, deadlines, and exposures
- **Web form automation** — Playwright-based opt-out for web_form brokers (with YAML scripts)
- **CSV import** — migrate history from DeleteMe, Optery, or other services
- **Prometheus metrics** — `/api/metrics` for Grafana dashboards
- **Reverse proxy header** — surfaced on `/api/auth/status` (Authentik/Authelia/Traefik); the master password is still required
- **Encrypted vault** — Argon2id (64MB, 3 iterations) + AES-256-GCM
- **Web UI + CLI** — setup wizard, dashboard, dark mode, privacy report
- **Re-scan monitoring** — detect data reappearing after removal

## Quick Start

### Docker Compose (recommended)

```bash
git clone https://github.com/Salicath/incognito.git
cd incognito
docker compose up -d
```

Open http://localhost:8080 and complete the setup wizard.

### From Source

```bash
git clone https://github.com/Salicath/incognito.git
cd incognito
pip install -e .
cd frontend && npm ci && npm run build && cd ..
python cli.py serve
```

### Container (Podman/Docker)

```bash
docker run -d --name incognito \
  -p 127.0.0.1:8080:8080 \
  -v incognito-data:/home/incognito/.incognito \
  ghcr.io/salicath/incognito:latest
```

Multi-arch images available: `linux/amd64` and `linux/arm64`.

## How It Works

1. **Setup** — Create a master password and enter your identity details
2. **Scan** — Check where your data is exposed (web search, breaches, archives, accounts)
3. **Send** — Dispatch GDPR Art. 17 deletion requests to all brokers
4. **Track** — Monitor the 30-day legal deadline; system sends follow-ups automatically
5. **Escalate** — Generate DPA complaints when brokers fail to respond

## CLI Commands

```bash
incognito serve              # Start web server
incognito status             # Show request stats
incognito report             # Privacy score and exposure report
incognito send --no-dry-run  # Create requests for all brokers
incognito follow-up --auto   # Check deadlines, send follow-ups
incognito check-replies      # Check IMAP inbox for broker replies
incognito rescan             # Re-scan for data reappearing
incognito brokers list       # List all brokers
incognito brokers stats      # Registry statistics
incognito brokers update     # Update brokers from GitHub
```

## Configuration

Environment variables (prefix `INCOGNITO_`):

| Variable | Default | Description |
|---|---|---|
| `INCOGNITO_DATA_DIR` | `~/.incognito` | Data directory |
| `INCOGNITO_HOST` | `127.0.0.1` | Bind address |
| `INCOGNITO_PORT` | `8080` | Listen port |
| `INCOGNITO_PASSWORD` | — | Master password for automated tasks |
| `INCOGNITO_NOTIFY_URL` | — | Ntfy/Gotify/webhook URL |
| `INCOGNITO_TRUSTED_PROXY_HEADER` | — | Reverse proxy auth header (e.g. `Remote-User`) |
| `INCOGNITO_SECURE_COOKIES` | `false` | Set `true` behind HTTPS reverse proxy |
| `INCOGNITO_SESSION_TIMEOUT_MINUTES` | `30` | Session idle timeout |
| `INCOGNITO_GDPR_DEADLINE_DAYS` | `30` | GDPR response deadline |
| `INCOGNITO_RATE_LIMIT_PER_HOUR` | `10` | Max emails per hour |
| `INCOGNITO_USER_COUNTRY` | `DK` | Residence supervisory authority for complaints |
| `INCOGNITO_SEARXNG_URL` | — | Self-hosted SearXNG sidecar for discovery scans |
| `INCOGNITO_CORS_ORIGINS` | — | Extra allowed origins (comma-separated) |
| `INCOGNITO_METRICS_TOKEN` | — | If set, `/api/metrics` requires `Authorization: Bearer <token>` |

## Integrations

| Integration | How |
|---|---|
| **Ntfy / Gotify** | Set `INCOGNITO_NOTIFY_URL` |
| **Prometheus / Grafana** | Scrape `GET /api/metrics` (set `INCOGNITO_METRICS_TOKEN` before exposing it) |
| **Authentik / Authelia** | Set `INCOGNITO_TRUSTED_PROXY_HEADER=Remote-User` (surfaced on the status endpoint; does not replace the vault unlock) |
| **Traefik** | Uncomment labels in `docker-compose.yml` |
| **Proton Bridge** | IMAP with STARTTLS on localhost:1143 |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The easiest way to contribute is adding a new broker — just create a YAML file and open a PR. CI validates all broker files automatically.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v      # 526 tests
ruff check .          # Lint
cd frontend && npm run dev  # Frontend dev server
```

## Security

- Profile encrypted at rest (AES-256-GCM, Argon2id with 64MB memory cost)
- Login rate limiting: 5 failures = 10-minute lockout (keyed on the real client IP behind a configured reverse proxy)
- Max 3 concurrent sessions, 30-minute idle timeout
- Binds to localhost only by default
- SMTP/IMAP credentials stored in the encrypted vault
- File permissions enforced: 0600 on sensitive files, 0700 on data directory
- Security headers on all responses
- Empty password protection on vault operations

## Legal

This tool helps you exercise your existing rights under GDPR (Art. 15, Art. 17) and CCPA. It does not constitute legal advice.

## License

[MIT](LICENSE)
