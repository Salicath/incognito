# Contributing to Incognito

Thank you for your interest in helping people take control of their personal data.

## Adding a Broker

The easiest way to contribute is adding a new data broker. Create a YAML file in `brokers/`:

```yaml
name: Company Name
domain: example.com
category: data_broker  # or: people_search, marketing, credit_agency
dpo_email: privacy@example.com
removal_method: email  # or: web_form, api
removal_url: null  # URL for web form opt-out, if applicable
country: DE  # ISO 3166-1 alpha-2
gdpr_applies: true
verification_required: false
language: en  # Template language: en, de, fr, es, it, nl, pl
last_verified: "2026-03-29"
notes: "Any relevant details about the opt-out process"
```

Run `python -m pytest tests/ -v` to validate, then open a PR.

## Adding a Form Definition

For `web_form` brokers, you can add Playwright automation in `brokers/forms/`:

```yaml
broker_domain: example.com
url: "https://example.com/optout"
notes: Description of the form
verify_selector: ".success-message"
steps:
  - action: fill
    selector: "#email"
    value: "{profile.email}"
  - action: click
    selector: "button[type=submit]"
```

See `brokers/forms/schema.yaml` for the full reference.

## Adding a Template Translation

Templates are Jinja2 files in `templates/locales/{lang}/`. Copy from `templates/` (English) and translate. Each template must:
- Start with `Subject: ...` line
- Use the same Jinja2 variables as the English version
- Reference the correct local regulation name (GDPR, DSGVO, RGPD, AVG, RODO, etc.)

## Development Setup

```bash
git clone https://github.com/Salicath/incognito.git
cd incognito
pip install -e ".[dev,scanner]"
cd frontend && npm install && cd ..

# Run tests
python -m pytest tests/ -v

# Lint
ruff check .

# Dev server (backend)
python cli.py serve

# Dev server (frontend with hot reload)
cd frontend && npm run dev
```

## Code Style

- Python: formatted by ruff, max line length 100
- TypeScript: Tailwind CSS, no CSS modules
- No unnecessary abstractions — simple is better
- Tests required for new backend features

## Pull Requests

- One feature per PR
- Include tests for backend changes
- Run the full test suite before submitting
- Keep PRs focused and reviewable
