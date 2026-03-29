# Incognito

Self-hosted tool that automates GDPR and CCPA personal data removal requests.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-green.svg)](https://python.org)
[![Tests](https://img.shields.io/badge/Tests-168_passing-brightgreen.svg)](tests/)

## What It Does

Incognito scans for your personal data across 197 data brokers, sends legally-binding GDPR Art. 17 and CCPA deletion requests, tracks the 30-day compliance deadline, monitors for broker replies via IMAP, and generates DPA complaints when brokers fail to respond. Everything runs on your own machine.

## Why Self-Host?

- **Your data never leaves your machine.** Profile data is encrypted at rest with AES-256-GCM (Argon2id key derivation). No cloud, no third-party accounts.
- **No subscription.** $0 vs $129/year for DeleteMe or $78/year for Incogni.
- **No conflicts of interest.** Commercial removal services are funded by the same data broker industry they claim to fight. Incognito has no business relationships to protect.
- **Full transparency.** Every email is generated from auditable Jinja2 templates. You can see exactly what gets sent and to whom before anything leaves your machine.

## Key Features

- **Exposure scanning** -- DuckDuckGo search, Have I Been Pwned breach check, Holehe account detection
- **197 data brokers** across 22 countries (EU-focused, plus US and international)
- **Multi-language GDPR templates** -- English, German, French, and CCPA
- **IMAP reply monitoring** -- auto-detect broker responses in your inbox
- **30-day deadline tracking** with automatic follow-up emails
- **DPA complaint generation** -- pre-filled complaints for 14 EU supervisory authorities (no commercial service offers this)
- **Re-scan monitoring** -- detect data reappearing after removal
- **Encrypted profile vault** -- Argon2id (64MB memory, 3 iterations) + AES-256-GCM
- **Web UI + CLI** -- setup wizard, progress dashboard, dark mode
- **Rootless Podman deployment** with Quadlet systemd units

## Quick Start

### From Source

```bash
git clone https://github.com/Salicath/incognito.git
cd incognito
pip install -e .

# Build the frontend
cd frontend && npm ci && npm run build && cd ..

# Start the web server
python cli.py serve
```

Open http://localhost:8080 and complete the setup wizard.

### Container Deployment

```bash
podman run -d --name incognito \
  -p 127.0.0.1:8080:8080 \
  -v incognito-data:/home/incognito/.incognito:Z \
  ghcr.io/salicath/incognito:latest
```

Or use the Quadlet systemd units in `deploy/` for a managed service:

```bash
cp deploy/incognito.container deploy/incognito-data.volume ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start incognito
```

## How It Works

1. **Setup** -- Create a master password and enter your identity details
2. **Scan** -- Check where your data is exposed (DuckDuckGo + HIBP + Holehe)
3. **Send** -- Dispatch GDPR Art. 17 deletion requests to all brokers that have your data
4. **Track** -- Monitor the 30-day legal deadline; system sends follow-ups automatically
5. **Escalate** -- If brokers don't respond, generate a DPA complaint and file it with the relevant supervisory authority

## CLI Commands

```bash
incognito serve              # Start web server
incognito status             # Show request stats
incognito send --no-dry-run  # Create requests for all brokers
incognito follow-up --auto   # Check deadlines, send follow-ups
incognito check-replies      # Check IMAP inbox for broker replies
incognito rescan             # Re-scan for data reappearing
incognito brokers list       # List all 197 brokers
incognito brokers stats      # Registry statistics
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Pydantic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | SQLite with WAL mode |
| Templates | Jinja2 with locale support |
| Encryption | AES-256-GCM, Argon2id KDF |
| Scanner | DuckDuckGo, Holehe, Have I Been Pwned |
| Deployment | Rootless Podman, Quadlet systemd units |

## Configuration

Environment variables (prefix `INCOGNITO_`):

| Variable | Default | Description |
|---|---|---|
| `INCOGNITO_DATA_DIR` | `~/.incognito` | Data directory |
| `INCOGNITO_HOST` | `127.0.0.1` | Bind address |
| `INCOGNITO_PORT` | `8080` | Listen port |
| `INCOGNITO_SESSION_TIMEOUT_MINUTES` | `30` | Session idle timeout |
| `INCOGNITO_GDPR_DEADLINE_DAYS` | `30` | GDPR response deadline |
| `INCOGNITO_RATE_LIMIT_PER_HOUR` | `10` | Max emails per hour |
| `INCOGNITO_CORS_ORIGINS` | -- | Extra CORS origins (comma-separated) |

## Contributing

Brokers are defined as YAML files in `brokers/`. Adding a new broker is as simple as creating a YAML file:

```yaml
name: Company Name
domain: company.com
category: data_broker
dpo_email: privacy@company.com
removal_method: email
country: DE
gdpr_applies: true
language: en
last_verified: "2026-03-01"
```

CI validates all YAML files against the schema on every PR. PRs welcome.

### Development

```bash
pip install -e ".[dev]"
pytest tests/ -v      # 168 tests
ruff check .          # Lint
cd frontend && npm run dev  # Frontend dev server (proxies to :8080)
```

## Security

- Profile encrypted at rest (AES-256-GCM, Argon2id with 64MB memory cost)
- Login rate limiting: 5 failures = 10-minute lockout
- Max 3 concurrent sessions, 30-minute idle timeout
- Binds to localhost only by default
- SMTP credentials stored in the encrypted vault
- File permissions enforced: 0600 on sensitive files, 0700 on data directory
- Security headers on all responses

## Legal

This tool helps you exercise your existing rights under GDPR (Art. 15, Art. 17) and CCPA. It does not constitute legal advice.

## License

[MIT](LICENSE)
