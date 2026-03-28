# Incognito

Self-hosted GDPR personal data removal tool. Send legally-binding data access and erasure requests to 145+ data brokers with one click.

## What it does

Incognito automates the process of exercising your EU GDPR rights:

- **Art. 15 — Right of Access**: "Do you have my data?" Brokers must respond within 30 days.
- **Art. 17 — Right to Erasure**: "Delete my data." Brokers must comply or provide legal justification.
- **Automated follow-ups**: Tracks deadlines, sends reminders, escalates to Data Protection Authorities.

### Features

- **One-click blast** — Send GDPR requests to all 145 brokers simultaneously
- **Account scanner** — Check which services have accounts registered with your email (powered by Holehe)
- **Breach checker** — Optional Have I Been Pwned integration to find which breaches contain your data
- **Request tracking** — Full lifecycle management with audit trail (Created → Sent → Acknowledged → Completed)
- **Follow-up automation** — Automatic deadline monitoring, follow-up emails, and escalation warnings
- **Encrypted storage** — Profile data encrypted at rest with AES-256-GCM (Argon2id key derivation)
- **Self-hosted** — Your data never leaves your machine except for the removal requests themselves
- **145+ brokers** — Data brokers, people-search sites, marketing companies, credit agencies

## Quick Start

### Using Podman (recommended)

```bash
mkdir -p ~/.config/containers/systemd
cp deploy/incognito.container deploy/incognito-data.volume ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start incognito
```

Open http://localhost:8080

### From source

```bash
git clone https://github.com/your-username/incognito.git
cd incognito

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && npm install && npm run build && cd ..

# Run
python cli.py serve
```

Open http://localhost:8080

## Usage

1. **Setup** — Enter a master password and your identity (name, email)
2. **Scan** — Check which services know about you (Account Scanner + optional HIBP)
3. **Blast** — Click "Send Art. 15 to all brokers" on the Dashboard
4. **Configure SMTP** — Go to Settings, add your email provider's SMTP credentials
5. **Send** — Click "Send all requests now" to dispatch emails
6. **Monitor** — Check the Requests page for responses. The tool tracks 30-day GDPR deadlines
7. **Follow up** — Click "Check Deadlines" to auto-send reminders to non-responsive brokers

## Configuration

### SMTP Providers

| Provider | Server | Port | Notes |
|----------|--------|------|-------|
| Proton Mail | smtp.protonmail.ch | 587 | Requires Bridge or paid plan |
| Gmail | smtp.gmail.com | 587 | Use App Password |
| Outlook | smtp.office365.com | 587 | Use App Password |
| Fastmail | smtp.fastmail.com | 587 | Use App Password |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `INCOGNITO_DATA_DIR` | `~/.incognito` | Data directory |
| `INCOGNITO_LOG_LEVEL` | `info` | Log level |
| `INCOGNITO_RATE_LIMIT_PER_HOUR` | `10` | Max emails per hour |
| `INCOGNITO_SESSION_TIMEOUT_MINUTES` | `30` | Session idle timeout |
| `INCOGNITO_PASSWORD` | - | Master password (for cron automation) |

### Have I Been Pwned (optional)

To use the breach checker, get an API key ($4.39/month) from [haveibeenpwned.com/API/Key](https://haveibeenpwned.com/API/Key) and add it in Settings.

## Deployment

### Rootless Podman + Quadlet

The recommended deployment uses rootless Podman with systemd Quadlet:

- `deploy/incognito.container` — Container unit
- `deploy/incognito-data.volume` — Persistent data volume
- `deploy/incognito-followup.timer` — Daily follow-up check at 9am
- `deploy/incognito-followup.service` — Follow-up service unit

### Automated follow-ups

```bash
# Install the timer
cp deploy/incognito-followup.timer deploy/incognito-followup.service ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user enable --now incognito-followup.timer
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Pydantic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | SQLite (WAL mode) |
| Encryption | AES-256-GCM, Argon2id |
| Scanner | Holehe, Have I Been Pwned API |
| Container | Rootless Podman, Quadlet |

## Contributing

### Adding brokers

Each broker is a YAML file in `brokers/`. To add one:

```yaml
name: Company Name
domain: company.com
category: data_broker  # data_broker | people_search | marketing | credit_agency
dpo_email: privacy@company.com
removal_method: email  # email | web_form | api
country: DE
gdpr_applies: true
verification_required: false
language: en
last_verified: "2026-03-01"
notes: "Optional notes"
```

### Running tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Legal

This tool helps you exercise your existing legal rights under the GDPR. It does not constitute legal advice. The authors are not responsible for how you use this tool or for any consequences of sending data requests.

## License

MIT
