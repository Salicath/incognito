# Incognito

Self-hosted tool that automates GDPR and CCPA personal data removal requests.

[![CI](https://github.com/Salicath/incognito/actions/workflows/ci.yml/badge.svg)](https://github.com/Salicath/incognito/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-green.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-236_passing-brightgreen.svg)](tests/)

## What It Does

Incognito scans for your personal data across 201 data brokers in 22 countries, sends legally-binding GDPR Art. 17 and CCPA deletion requests, tracks the 30-day compliance deadline, monitors for broker replies via IMAP, and generates DPA complaints when brokers fail to respond. Everything runs on your own machine — no cloud, no telemetry, no third-party accounts.

**Free alternative to DeleteMe ($129/year) and Incogni ($78/year).**

## Why Self-Host?

- **Your data never leaves your machine.** Profile encrypted at rest with AES-256-GCM (Argon2id KDF). Zero external dependencies.
- **No subscription.** $0/year, forever.
- **No conflicts of interest.** Commercial removal services are funded by the same data broker industry.
- **Full transparency.** Every email is generated from auditable Jinja2 templates. You see exactly what gets sent.
- **Complete audit trail.** Export your full GDPR paper trail as CSV — something no commercial tool offers.

## Key Features

- **201 data brokers** across 22 countries (EU-focused, plus US and international)
- **Exposure scanning** — DuckDuckGo search, Have I Been Pwned breach check, Holehe account detection
- **8 languages** — English, German, French, Spanish, Italian, Dutch, Polish, CCPA
- **IMAP reply monitoring** — auto-detect broker responses in your inbox
- **30-day deadline tracking** with automatic follow-up and escalation emails
- **DPA complaint generation** — pre-filled complaints for 23 supervisory authorities
- **Privacy score** — A-F grade with exposure report and audit trail CSV export
- **Push notifications** — Ntfy, Gotify, or webhook alerts for replies, deadlines, and exposures
- **Web form automation** — Playwright-based opt-out for web_form brokers (with YAML scripts)
- **CSV import** — migrate history from DeleteMe, Optery, or other services
- **Prometheus metrics** — `/api/metrics` for Grafana dashboards
- **Reverse proxy auth** — Authentik/Authelia/Traefik ForwardAuth support
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
2. **Scan** — Check where your data is exposed (DuckDuckGo + HIBP + Holehe)
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

## Integrations

| Integration | How |
|---|---|
| **Ntfy / Gotify** | Set `INCOGNITO_NOTIFY_URL` |
| **Prometheus / Grafana** | Scrape `GET /api/metrics` |
| **Authentik / Authelia** | Set `INCOGNITO_TRUSTED_PROXY_HEADER=Remote-User` |
| **Traefik** | Uncomment labels in `docker-compose.yml` |
| **Proton Bridge** | IMAP with STARTTLS on localhost:1143 |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The easiest way to contribute is adding a new broker — just create a YAML file and open a PR. CI validates all broker files automatically.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v      # 236 tests
ruff check .          # Lint
cd frontend && npm run dev  # Frontend dev server
```

## Security

- Profile encrypted at rest (AES-256-GCM, Argon2id with 64MB memory cost)
- Login rate limiting: 5 failures = 10-minute lockout
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
