# Incognito

Self-hosted GDPR personal data removal tool. Send legally-binding data access and erasure requests to 168 data brokers with one click, track compliance deadlines, and escalate to supervisory authorities when they don't respond.

**Your data, your rights, your server.**

## Why

Data brokers collect and sell your personal information without your knowledge. Under GDPR, you have the right to demand access (Art. 15) and deletion (Art. 17) of your data. They must respond within 30 days or face regulatory action.

Incognito automates this entire process:

1. **Blast** -- Send GDPR requests to all 168 brokers in the registry
2. **Track** -- Monitor 30-day deadlines automatically
3. **Escalate** -- Send follow-ups and file complaints with supervisory authorities

Commercial services like Incogni charge $7/month for this. Incognito is free, self-hosted, and keeps your data on your machine.

## Features

- **One-click blast** -- Send Art. 15 (access) or Art. 17 (erasure) requests to all brokers at once
- **168 data brokers** -- EU, US, and DACH brokers with verified DPO email contacts
- **Automated follow-ups** -- Deadline tracking, overdue detection, escalation warnings
- **DPA complaint generator** -- Pre-filled complaints for 14 EU supervisory authorities (BfDI, CNIL, AP, DPC, ICO, and more)
- **Exposure scanning** -- DuckDuckGo search, account discovery (Holehe), breach checking (Have I Been Pwned)
- **Encrypted vault** -- Profile data encrypted at rest with AES-256-GCM (Argon2id KDF)
- **GDPR + CCPA** -- Templates for both EU and California privacy regulations
- **Localized templates** -- Request emails in English, German, and French
- **Progress dashboard** -- Visual progress ring, resolution tracking, scan-first onboarding
- **Dark mode** -- System-aware with manual toggle
- **Backup/restore** -- Export and import encrypted backups
- **Self-hosted** -- Runs on your machine, data never leaves except as removal requests

## Quick Start

### With Podman (recommended)

```bash
mkdir -p ~/.config/containers/systemd
cp deploy/incognito.container deploy/incognito-data.volume ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start incognito
```

Open http://localhost:8080

### From source

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .              # core (GDPR blast, scanning, tracking)
pip install -e ".[scanner]"   # optional: holehe account discovery

# Frontend
cd frontend && npm ci && npm run build && cd ..

# Run
python cli.py serve
```

Open http://localhost:8080 and complete the setup wizard.

## Usage

1. **Setup** -- Enter a master password and your identity (name, email)
2. **Scan** (optional) -- Check which services know about you
3. **Blast** -- Click "Send Art. 15 to all brokers" on the Dashboard
4. **Configure SMTP** -- Add your email provider's SMTP credentials in Settings
5. **Send** -- Dispatch all requests via email
6. **Monitor** -- Track 30-day GDPR deadlines on the Requests page
7. **Follow up** -- Auto-send reminders to non-responsive brokers

### SMTP Providers

| Provider | Server | Port | Notes |
|---|---|---|---|
| Proton Mail | smtp.protonmail.ch | 587 | Requires Bridge or paid plan |
| Gmail | smtp.gmail.com | 587 | Use App Password |
| Outlook | smtp.office365.com | 587 | Use App Password |
| Fastmail | smtp.fastmail.com | 587 | Use App Password |

### Automated follow-ups

Set up daily deadline checks with the included systemd timer:

```bash
cp deploy/incognito-followup.{service,timer} ~/.config/systemd/user/
systemctl --user enable --now incognito-followup.timer
```

Or run manually: `incognito follow-up --auto`

## Architecture

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Pydantic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | SQLite (WAL mode) |
| Templates | Jinja2 (localized GDPR request emails) |
| Encryption | AES-256-GCM, Argon2id KDF |
| Scanner | Holehe, Have I Been Pwned API |
| Deployment | Rootless Podman, Quadlet systemd units |

```
incognito/
├── backend/          # FastAPI app
│   ├── api/          # Route handlers
│   ├── core/         # Business logic (crypto, profiles, request state machine)
│   ├── db/           # SQLAlchemy models
│   ├── scanner/      # DuckDuckGo, Holehe, HIBP scanners
│   └── senders/      # Email sender (SMTP)
├── frontend/         # React SPA
│   └── src/
│       ├── pages/    # Dashboard, Requests, Brokers, Scan, Settings
│       └── api/      # Typed API client
├── brokers/          # 168 YAML broker definitions
├── templates/        # Jinja2 GDPR email templates
│   └── locales/      # de, fr, ccpa translations
├── deploy/           # Containerfile + Quadlet units
├── tests/            # 129 unit + integration tests
└── cli.py            # CLI entry point
```

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
| `INCOGNITO_LOG_LEVEL` | `info` | Log level |
| `INCOGNITO_PASSWORD` | -- | Master password (for cron automation) |
| `INCOGNITO_CORS_ORIGINS` | -- | Extra CORS origins (comma-separated) |
| `INCOGNITO_SECURE_COOKIES` | `false` | Set `true` behind HTTPS reverse proxy |

Copy `.env.example` to `.env` to customize.

### Have I Been Pwned (optional)

Get an API key from [haveibeenpwned.com/API/Key](https://haveibeenpwned.com/API/Key) and add it in Settings to check which breaches contain your email.

## Contributing

### Adding brokers

Each broker is a YAML file in `brokers/`. To add one:

```yaml
name: Company Name
domain: company.com
category: data_broker   # data_broker | people_search | marketing | credit_agency | other
dpo_email: privacy@company.com
removal_method: email   # email | web_form | api
country: DE
gdpr_applies: true
verification_required: false
language: en
last_verified: "2026-03-01"
```

CI validates all YAML files against the schema on every PR.

### Development

```bash
pip install -e ".[dev]"

# Tests
pytest tests/ -v

# Lint
ruff check .

# Frontend dev server (proxies API to backend on :8080)
cd frontend && npm run dev
```

## Security

- Profile data encrypted at rest with AES-256-GCM
- Key derived from master password via Argon2id (64MB memory, 3 iterations)
- Session tokens: HTTP-only cookies, strict same-site
- SMTP credentials stored in the encrypted vault
- Binds to localhost by default
- HIBP API key stored as plaintext in data dir (optional feature)

## Legal

This tool helps you exercise your existing legal rights under the GDPR. It does not constitute legal advice. The authors are not responsible for how you use this tool or for any consequences of sending data requests.

## License

MIT
