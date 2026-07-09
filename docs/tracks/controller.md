# Track: `controller`

Tech-giant erasure. Unlike the `broker` track (companies holding data about you with no
relationship), controllers are services you may have a live account with: erasure means
account deletion plus a formal Art. 17 for what survives it. Every action is a
**per-platform opt-in** — never part of the blast.

## Why this track exists separately

- Erasure is destructive to the user (account deletion), so requests are created one
  platform at a time from the Controllers page, not blasted.
- 8 of 16 platforms are **form-only** (Meta, Google, Microsoft, LinkedIn, Apple, X,
  TikTok, Match Group): no verifiable Art. 17 email exists. The widely-circulated
  addresses (`privacy@meta.com`, `data-access-requests@google.com`, `dpo@apple.com`)
  failed verification against official sources in July 2026 — the last two are stale or
  scoped to other purposes. The SMTP pipeline cannot carry these; they get an
  assist-kit flow instead (delisting-track pattern).
- Escalation routing differs: broker-track complaints go to the DPA of the broker's
  country; controller complaints go to the **user's residence DPA** (Art. 77 — file
  anywhere; Datatilsynet forwards to the lead SA under Art. 56/60 and stays the
  complainant's contact). Direct lead-SA filing confers no procedural speedup.

## State machine

Reuses the existing request lifecycle. Email-viable platforms take the normal path;
form-only platforms enter through `MANUAL_ACTION_NEEDED`:

```
email-viable (Amazon, Reddit, GitHub, Discord, Snap, Spotify, Netflix, Strava):
  CREATED → SENT → ACKNOWLEDGED → COMPLETED   (± OVERDUE / REFUSED / ESCALATED)
     └ send happens at opt-in via the controller endpoint, controller-specific template

form-only (Meta, Google, Microsoft, LinkedIn, Apple, X, TikTok, Match Group):
  CREATED → MANUAL_ACTION_NEEDED → SENT → ...
     │            │                  └ user attests "I filed it" — Art. 12(3) one-month
     │            │                    clock runs from that date, unchanged machinery
     │            └ tool renders the kit: full Art. 17 text (entity-addressed, REF code
     │              embedded) + exact form URL + per-form instructions
     └ transitioned immediately at creation
```

IMAP matching degrades gracefully for form submissions: no Message-ID threading, but
tier-2 (REF code echoed by ticket systems) and tier-3 (sender domain) still apply.

## Platform registry — `brokers/controllers.yaml`

Hand-verified July 2026 (research + adversarial verification pass; every email was
confirmed in a current official source or dropped). Not derived from datenanfragen.de:
the base dataset was stale for 5 of 16 platforms (X entity rename, Strava entity,
Reddit address, Spotify address, Apple email scope). `datenanfragen_slug` is kept as a
join key; vendoring the full 3k-record base is deferred registry enrichment.

Fields beyond the broker schema:

| Field | Purpose |
|---|---|
| `eu_entity` / `postal_address` | Request + complaint addressee; postal is the only formal fallback for form-only giants |
| `entity_country` | Main establishment (drives nothing; complaint metadata) |
| `lead_dpa` | Complaint-text metadata ("please forward under Art. 56") — never routing |
| `contact_kind` | `privacy_email` / `dpo_email` / `form_only` |
| `email_viable` | Post-verification judgment; an address existing ≠ it being processed |
| `selfservice_url` / `erasure_form_url` / `access_url` | Three distinct URL roles (Netflix's access portal is not an erasure form) |
| `retention_note` / `art17_value` | UI: "what deleting your account does NOT remove"; injected into the request text |
| `demand_content_erasure` | Reddit/Discord: posts/messages survive account deletion; template must demand content erasure explicitly |
| `special_category` | Strava: Art. 9 health data — flagged in request + complaint, raises DPA priority |
| `send_from_account_email` | Reddit hard requirement: request must come from the account's verified email |
| `no_eu_establishment` / `art27_rep` | Snap: Art. 55 direct competence branch; CC the Art. 27 rep |
| `prerequisites` | "Cancel Premium first", "transfer server ownership", "don't log in during the 30-day window" |
| `form_instructions` | e.g. Tinder: pick "another question about my data", write "DPO" in the description |

## Escalation routing (implemented in `core/dpa.py`)

```
entity_country == "GB"      → UK ICO (no OSS bridge; accepts non-residents)
no EU establishment (Snap)  → user-residence DPA, Art. 55 full competence, CC Art. 27 rep
otherwise                   → user-residence DPA (default DK Datatilsynet), which
                              forwards to the lead SA; complaint text names the lead SA
```

User residence comes from `INCOGNITO_USER_COUNTRY` (default `DK`).
Datatilsynet precondition encoded in the complaint flow: prior contact with the
controller + Art. 12(3) silence. Stable filing URL only
(`datatilsynet.dk/borger/klage/saadan-klager-du`); the virk.dk form URL is a session
URL and must never be stored.

## Recommended sequencing (baked into the UI per platform)

1. Complete `prerequisites` (cancel subscriptions, transfer servers, export data).
2. Run self-service deletion first (`selfservice_url`).
3. Then file the formal Art. 17 for the residuals (`art17_value` says what that adds).
4. On Art. 12(3) expiry: OVERDUE → escalation → residence-DPA complaint with the
   evidence bundle (request text + date + REF, any reply, one-line no-response note).

## Known limits / re-verify at refresh

- GitHub's lead SA (NL AP) is inferred from main establishment, not designated — the
  complaint says "presumably".
- Snap's no-establishment status is per its 2023 EEA notice; re-check at registry
  refresh — the Art. 55 branch must survive Snap graduating out of it.
- URL liveness is not naively checkable (X SPA returns 200 for everything, TikTok
  302s when logged out, Snap/Discord 403 to bots) — any future link-checker needs
  per-record expectations.
- Commit name/email in third-party GitHub repos will be refused (immutable history) —
  the template sets expectations.
## Complaint content (verified against primary text, 2026-07-09)

- **EDPB CEF-2025 rebuttal** (`edpb_cef` in `dpa_complaint`): rendered only when the
  controller actually REFUSED. Cites the EDPB's *2025 Coordinated Enforcement Action —
  Implementation of the right to erasure by controllers* (**adopted 10 February 2026**;
  much press coverage says 18 Feb — the cover page says 10 Feb): exceptions are often
  "treated as automatically applicable without conducting a case-by-case assessment";
  anonymisation does not substitute for erasure where only basic pseudonymisation or
  partial masking is applied; back-up data is often excluded "by default, without
  providing a justification for doing so". Usable today.
- **Reg (EU) 2025/2518** (`proc_reg`): gated on BOTH cross-border processing and
  `date.today() >= 2027-04-02`. Art. 4(1) — not Art. 3 — lists the five admissibility
  elements and says "No information additional to that referred to in the first
  subparagraph shall be required"; Art. 12(1) sets the lead-SA 15-month draft-decision
  deadline. It applies from 2 April 2027 (Art. 37(2)) to complaints **lodged** after
  that date (Art. 36). A national Art. 55 case (Google Search RTBF, Snap, any
  no-EU-establishment target) is NOT cross-border and must never carry these lines —
  there is a test for exactly that.
- **Correction to a common secondary-source error:** the 15-month cap's extension is
  *once, up to 12 months*, for case complexity (Art. 12(3)). The widely-repeated "two
  months" belongs to the separate 12-month simple-cooperation deadline (Art. 12(6)).
- National procedural modalities (language, limitation, ID means, form, signature)
  still apply alongside Art. 4(1) — Recital 33.
