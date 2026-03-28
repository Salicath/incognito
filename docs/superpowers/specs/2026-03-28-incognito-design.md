# Incognito — Design Specification

**Date:** 2026-03-28
**Status:** Draft
**Author:** Malte + Claude

## Overview

Incognito is a self-hosted, GDPR-first personal data removal tool. It automates the process of finding and removing personal data from data brokers by sending legally-backed requests (GDPR Art. 15 access, Art. 17 erasure) and tracking compliance.

**Goals:**
- Make privacy accessible — frictionless onboarding, polished UI, production-grade quality
- Self-hosted and local-first — no data leaves your machine except removal requests
- GDPR as the legal backbone — strongest privacy framework available
- Community-maintainable — open-source with an easy-to-contribute broker database

**Non-goals (v1):**
- Social media profile removal
- Photo/image search removal
- LLM-generated request text
- Multi-user / team support
- Paid SaaS hosting

## Architecture

### Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+, FastAPI, SQLAlchemy, Pydantic |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| Database | SQLite (WAL mode) |
| Templates | Jinja2 |
| Web automation | Playwright (Python) |
| Email | smtplib (sending), imaplib (response monitoring) |
| Encryption | AES-256-GCM, Argon2id KDF |
| Container | Rootless Podman, Quadlet systemd units |

### Project Structure

```
incognito/
├── backend/
│   ├── api/                # FastAPI routes
│   │   ├── auth.py         # Session/password authentication
│   │   ├── profile.py      # Profile CRUD
│   │   ├── brokers.py      # Broker registry endpoints
│   │   ├── requests.py     # Request lifecycle endpoints
│   │   ├── scan.py         # Scan trigger and results
│   │   └── settings.py     # App configuration
│   ├── core/
│   │   ├── config.py       # App configuration loading
│   │   ├── crypto.py       # Encryption/decryption (AES-256-GCM, Argon2id)
│   │   ├── profile.py      # Profile model and vault
│   │   ├── broker.py       # Broker registry loader
│   │   ├── request.py      # Request state machine
│   │   └── scheduler.py    # Follow-up scheduling logic
│   ├── senders/
│   │   ├── base.py         # Abstract sender interface
│   │   ├── email.py        # SMTP-based request sending
│   │   ├── web.py          # Playwright-based form submission
│   │   └── api.py          # Direct API opt-out calls
│   ├── scanner/
│   │   ├── base.py         # Abstract scanner interface
│   │   └── people_search.py # People-search site scanner
│   ├── db/
│   │   ├── models.py       # SQLAlchemy models
│   │   ├── migrations/     # Alembic migrations
│   │   └── session.py      # Database session management
│   └── main.py             # FastAPI app entry point
├── frontend/
│   ├── src/
│   │   ├── pages/          # React pages (Setup, Dashboard, Requests, Brokers, Scan, Settings)
│   │   ├── components/     # Shared UI components
│   │   └── api/            # API client (typed, auto-generated from OpenAPI)
│   └── ...
├── templates/              # Jinja2 GDPR request templates
│   ├── access_request.txt.j2
│   ├── erasure_request.txt.j2
│   ├── follow_up.txt.j2
│   ├── escalation_warning.txt.j2
│   ├── dpa_complaint.txt.j2
│   └── locales/
│       ├── de/
│       ├── fr/
│       └── nl/
├── brokers/                # YAML broker definitions
│   ├── acxiom.yaml
│   ├── ...
│   └── schema.yaml         # JSON Schema for broker YAML validation
├── deploy/
│   ├── Containerfile
│   ├── incognito.container     # Quadlet unit
│   ├── incognito-data.volume   # Quadlet volume
│   ├── incognito-followup.timer
│   └── incognito-followup.service
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── cli.py                  # CLI entry point (serve, follow-up, scan, brokers)
```

## Profile & Security

### User Profile

Stored encrypted at rest. Contains:

```python
class Profile(BaseModel):
    full_name: str
    previous_names: list[str]
    date_of_birth: date
    emails: list[str]
    phones: list[str]
    addresses: list[Address]

class Address(BaseModel):
    street: str
    city: str
    postal_code: str
    country: str  # ISO 3166-1 alpha-2
```

### Encryption

- Profile serialized to JSON, encrypted with AES-256-GCM
- Encryption key derived from master password via Argon2id (memory=64MB, iterations=3, parallelism=4)
- Stored as `~/.incognito/profile.enc`
- SMTP credentials stored in the same encrypted vault
- Decrypted only in memory when needed (sending requests, displaying profile)

### Authentication

- Single-user app — no user accounts, just a master password
- Password entered at session start, session token stored in HTTP-only cookie
- Session expires after configurable idle timeout (default: 30 minutes)
- Lock screen shown when session expires

## Broker Registry

Each broker defined as a YAML file:

```yaml
name: Acxiom
domain: acxiom.com
category: data_broker
dpo_email: privacy@acxiom.com
removal_method: email  # email | web_form | api
removal_url: null
api_endpoint: null
country: US
gdpr_applies: true
verification_required: false
language: en
last_verified: 2026-03-01
notes: "Major data broker, typically responds within 14 days"
```

**Seeding:** Ship with ~50-100 well-known brokers compiled from public registries (California, Vermont) and EU-focused sources. Community contributes more via PRs — each broker YAML is validated against `schema.yaml` in CI.

**Broker updates:** `incognito brokers update` (or UI button) pulls latest definitions from the community repository.

## Request Lifecycle

### State Machine

```
CREATED → SENT → ACKNOWLEDGED → COMPLETED
                       ↓
                   REFUSED → ESCALATED
           ↓
       OVERDUE → ESCALATED
```

- **CREATED** — request generated, ready for review/sending
- **SENT** — delivered, 30-day GDPR clock starts
- **ACKNOWLEDGED** — broker responded
- **COMPLETED** — deletion confirmed
- **REFUSED** — broker denied with reason
- **OVERDUE** — 30 days passed, no response
- **ESCALATED** — follow-up sent or DPA complaint generated
- **MANUAL_ACTION_NEEDED** — automation failed (CAPTCHA, form change, ID required); user must handle manually via the provided URL

### Request Types

| Type | GDPR Article | Purpose |
|---|---|---|
| Access Request | Art. 15 | "Do you have my data?" |
| Erasure Request | Art. 17 | "Delete my data" |
| Follow-up | Art. 12(3) | Reminder after no response |
| Escalation Warning | — | "I will file with DPA in 7 days" |
| DPA Complaint | — | Formal complaint to supervisory authority |

### Database Schema

```sql
CREATE TABLE requests (
    id TEXT PRIMARY KEY,
    broker_id TEXT NOT NULL,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    sent_at TIMESTAMP,
    deadline_at TIMESTAMP,
    response_at TIMESTAMP,
    response_body TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE request_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id TEXT NOT NULL REFERENCES requests(id),
    event_type TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    broker_id TEXT,
    found_data TEXT NOT NULL,
    scanned_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actioned BOOLEAN NOT NULL DEFAULT FALSE
);
```

## Template System

Jinja2 templates in `templates/`. Each template references GDPR articles correctly and includes:
- Profile fields (name, emails, DOB, addresses)
- Unique reference ID for response matching
- Legal deadline reminder
- Sender signature

Locale support: broker YAML specifies `language`, template engine selects matching locale directory. English fallback for all.

DPA complaint templates pre-filled per major EU supervisory authority (BfDI, CNIL, AP, DPC, etc.).

## Web UI

### Pages

**Setup Wizard** (`/setup`)
- 4-step guided flow: master password → profile details → SMTP config → confirmation
- Input validation, SMTP test button, progress indicator
- Only shown on first run; redirects to dashboard after completion

**Dashboard** (`/`)
- Overview cards: total brokers, requests pending/completed/overdue
- Recent activity timeline
- Next scheduled actions
- Alert banner for items needing attention

**Requests** (`/requests`)
- Filterable, sortable table with color-coded status badges
- Click-through to full request detail with audit trail
- Bulk actions: send all pending, follow up all overdue
- Dry-run preview before sending

**Brokers** (`/brokers`)
- Searchable broker list with per-broker status
- Add custom broker form
- Update broker database button

**Scan Results** (`/scan`)
- Where your data was found
- One-click "request removal" per result
- Re-scan trigger

**Settings** (`/settings`)
- Edit profile, SMTP config, scan schedule, rate limits
- Export/import encrypted backup
- Log viewer

## CLI Commands

```
incognito serve                 # Start the web app
incognito init                  # First-time setup (alternative to web wizard)
incognito scan                  # Trigger a scan
incognito send [--dry-run]      # Send pending requests
incognito follow-up [--auto]    # Check deadlines, send follow-ups
incognito status [--overdue]    # Show request status table
incognito brokers list          # List brokers
incognito brokers add           # Add custom broker
incognito brokers update        # Pull latest broker definitions
incognito profile show          # Display profile (requires password)
incognito profile edit          # Edit profile
incognito log                   # View audit trail
```

## Deployment

### Container

Single rootless Podman container. Multi-stage build:
1. Node stage: build frontend assets
2. Python stage: install backend + copy frontend build

Runs as UID 1000 inside the container. Exposes port 8080.

### Quadlet Units

**`incognito.container`:**
```ini
[Unit]
Description=Incognito — Personal Data Removal Service

[Container]
Image=ghcr.io/malte/incognito:latest
AutoUpdate=registry
PublishPort=127.0.0.1:8080:8080
Volume=incognito-data.volume:/home/incognito/.incognito:Z
Environment=INCOGNITO_LOG_LEVEL=info
UserNS=keep-id

[Service]
Restart=always

[Install]
WantedBy=default.target
```

**`incognito-data.volume`:**
```ini
[Volume]
User=1000
Group=1000
```

**`incognito-followup.timer`:**
```ini
[Unit]
Description=Incognito daily follow-up check

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**`incognito-followup.service`:**
```ini
[Unit]
Description=Incognito follow-up runner

[Service]
Type=oneshot
ExecStart=podman exec incognito incognito follow-up --auto
```

### Getting Started

```bash
mkdir -p ~/.config/containers/systemd
cp deploy/incognito.container deploy/incognito-data.volume ~/.config/containers/systemd/
systemctl --user daemon-reload
systemctl --user start incognito
xdg-open http://localhost:8080
```

## Error Handling & Resilience

**Email failures:** Retry with exponential backoff (3 attempts over 15 minutes). Failed sends stay in CREATED state for next run.

**Web form failures:** Playwright timeouts, layout changes, CAPTCHAs → status set to `MANUAL_ACTION_NEEDED`. UI shows the broker's opt-out URL for manual handling.

**Rate limiting:** Max 10 requests/hour by default (configurable). Prevents SMTP spam flagging.

**Data integrity:** SQLite WAL mode. Every state transition logged to `request_events` (append-only audit trail). Encrypted profile backup exportable from UI.

**Graceful degradation:** Wrong password → lock screen. Empty/corrupt broker DB → prompt to update. Playwright not available → email-only mode.

## Testing

**Unit tests:** Template rendering, state machine transitions, encryption round-trips, broker YAML validation.

**Integration tests:** Full request lifecycle against MailHog (test SMTP server) and mock broker pages.

**API tests:** All FastAPI endpoints, authenticated and unauthenticated.

**E2E tests:** Playwright browser tests against the running app — setup wizard through to request sending.

**CI pipeline:**
- Lint (ruff) + type check (mypy) + unit tests on every PR
- Integration + E2E tests on merge to main
- Container build + Trivy vulnerability scan
- Broker YAML schema validation

**Test data:** Fixture profiles with fake data. Mock broker server simulating: success, refusal, no response, ID verification. No real personal data in tests.

## Open Questions

None — all design decisions resolved during brainstorming.
