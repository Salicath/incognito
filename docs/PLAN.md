# Incognito v1 — Personal EU Data Sovereignty Workbench

**Owner:** Malte. **Audience:** self + family/friends. **Not for public adoption.**
**Goal:** Run Incognito against yourself. A manual web search for your name/email/phone afterward returns nothing actionable that the tool didn't already drive to deletion, restriction, or DPA escalation.

## Why rework

Current architecture models a single workflow: broker → email → IMAP reply → DPA escalate. Research showed real EU/DK erasure spans eight distinct workflows. The compliance pipeline is the moat — keep it. The registry, scanner, and request-track shapes are wrong for a Dane targeting "complete" erasure.

## Eight tracks

| Track | Purpose | Notes |
|---|---|---|
| `broker` | Traditional Art. 17 → email/form → IMAP → DPA | ✅ Built. Best-in-class. |
| `controller` | Tech-giant deletion (Meta, Google, MSFT, Apple, Amazon, X, TikTok, Reddit, GitHub, Discord, Snap, Spotify, Netflix, Match, Strava) | Per-platform process; jurisdictions vary (IE DPC, LU CNPD, NL AP, SE IMY, UK ICO) |
| `delisting` | Google/Bing search-result RTBF — URL-targeted, requires ID upload | Distinct from controller account deletion |
| `cpr_lever` | DK upstream: navne-/adressebeskyttelse (free, 1y renewal, cascades to CVR), Robinsonlisten, `opdater.krak.dk/person` | One MitID action kills Krak + DGS + 118 + CVR address |
| `account` | Old/dead accounts (JustDelete.me MIT seed, ~200 entries; tag `confidence: stale-2017`) | |
| `newsletter` | IMAP scan + RFC 8058 one-click unsubscribe | Reuses existing IMAP plumbing; universal compliance since 2024 Gmail/Yahoo mandate |
| `time_locked` | Bank Hvidvaskloven (5y+1mo), Skat (5–10y); fires Art. 17 when retention expires | |
| `restriction_only` | Info-only: Sundhed.dk spærring, Tinglysning, Statstidende, telco logning, public-sector Arkivloven 75y | Honest "you cannot delete this" surfacing |

## Scanner additions (today → seven sources)

Today: DDG + Holehe + HIBP.

1. **Wayback CDX API** — free, no key, surfaces deleted-but-archived exposure. Single highest-ROI addition.
2. **Maigret** — 2,500 sites by username; replaces decaying Holehe.
3. **user-scanner (kaifcodec)** — Holehe successor for email-based account existence.
4. **GitHub Code Search API** — surfaces own email/phone in old `.env` commits, gists.
5. **SearXNG sidecar** — self-hosted meta-search Quadlet; replaces DDG-only.
6. **HIBP paid tier** — $3.95/mo, removes rate limits.
7. **PimEyes one-time scan** — ~€30, fills face-search gap nothing OSS can.

## Registry rebuild

Default profile run today: 201 brokers, 55% US-irrelevant. Replace with ~80 EU-relevant entries centered on:

- **Nordic chokepoints** — Eniro Group cluster (Krak/DGS/118/Proff/1881/Gule Sider), D&B/Bisnode Nordic (Risika, Experian DK, Creditsafe DK), UC AB, Asiakastieto/Enento
- **DK-specific** — Risika, ErhvervsKrak, NN Markedsdata, RKI/Debitor Registret
- **DE big four** — Schufa, Creditreform/Boniversum, CRIF Bürgel, Arvato Infoscore
- **EU-active US brokers** under DPC IE / ICO — Acxiom, LiveRamp, Experian plc, LexisNexis Risk NL, Oracle/BlueKai, Adobe, Salesforce DMP, Epsilon
- **Adtech with EU controllers** — Criteo (FR), Adform (DK), Outbrain (NL), Quantcast, Lotame, Xandr/Microsoft Ads

Add `da` locale to `templates/locales/` (5 template types).

## Money plan (~€15/mo + ~€30 one-time)

- HIBP API $3.95/mo — buy
- PimEyes one-time deep scan ~€30 — buy once at baseline
- Brave Search API $5/1k — top up ad-hoc as SearXNG fallback
- Optional: own-domain SMTP (~€3/mo) so Art. 17 doesn't leak `salicath@pm.me`
- Skip: DeHashed, Constella, DomainTools, Onerep/DeleteMe

## Phases

**Phase 0 — Baseline (read-only)**
- Run current scanner against full seed set: email + alt emails + phone(s) + usernames + name/address + any domains
- Tag current state as `v0.3.0` for revert point
- Capture exposure map → drives Phase 1+ scoping

**Phase 1 — Danish foundation** ✅ complete
- ✅ Add `da` locale (5 templates, Datatilsynet-style phrasing)
- ✅ Build `cpr_lever` track end-to-end (deep-links + MitID handoff + renewal reminders: T-30/T-7/expiry)
- ✅ DK/Nordic registry expansion (Eniro cluster, D&B-DK cluster, RKI, Risika, etc.)
- ✅ DE registry expansion (Schufa, Creditreform, etc.)

**Phase 2 — Discovery rebuild**
- ✅ Wayback CDX scanner (backend/scanner/wayback.py — ghost-profile detection, 15 platforms)
- ✅ Maigret + user-scanner integration (replace Holehe): user-scanner is the
  in-process email-axis holehe successor (light deps, asyncio-native); Maigret runs
  as an isolated subprocess against its own `/opt/maigret` venv for deep 3000-site
  username enumeration (`/api/scan/deep-scan/*`). WMN dataset dropped (Maigret
  supersets it and verifies profiles). Phone-axis account enumeration remains a gap
  (no maintained tool). Design/plan: `docs/superpowers/{specs,plans}/2026-07-03-account-discovery-scanners*`.
- ✅ GitHub Code Search scanner (backend/scanner/github_scanner.py — PAT via Settings)
- SearXNG Quadlet sidecar
- HIBP paid-tier wiring + PimEyes manual-result-import flow

**Exposure triage layer** (new, not in original 8-track plan) ✅
- ✅ Every scanner persists to `scan_results`; unified Exposures inbox aggregates + dispositions each hit (actioned/dismissed/legally_impossible)
- ✅ One-click Art. 17 request for hits matching a registry broker; per-source removal guidance for the rest
- ✅ Dashboard needs-triage banner; setup wizard captures usernames (scanner fuel)

- ✅ Secrets in vault: HIBP key + GitHub token now live in `_VaultData.secrets` (encrypted); legacy plaintext files auto-migrate on first access. Backup carries them inside the vault (no plaintext field).

**Deferred / next**
- SearXNG Quadlet sidecar
- HIBP paid-tier wiring + PimEyes manual-result-import flow
- Phone-axis account enumeration (no maintained tool exists; ignorant is dead — port the technique if needed)

**Phase 3 — Controller track**
- Per-platform Art. 17 templates + state machine for the 15-platform tech-giant set
- Jurisdiction-aware DPA escalation routing (IE DPC, LU CNPD, NL AP, SE IMY, UK ICO, Norwegian Datatilsynet for special-category)
- 🟡 `delisting` track: Google + Bing RTBF. Shipped — the delisting-kit generator
  (`core/delisting.py`, `GET /api/scan/exposures/{id}/delisting-kit`): per-engine
  deep-links (Google/Bing forms + Brave email, with reseller coverage notes) and a
  drafted locale-aware Art. 17 justification, surfaced on any URL exposure. Assist-only
  (every engine is a manual ID-gated form; no API/DRP). TODO: request-lifecycle tracking
  (Art. 12(3) one-month clock → OVERDUE → ESCALATED = Datatilsynet complaint), IMAP
  decision-email matching, and quarterly name-search re-verification via the rescan timer.

**Phase 4 — Long tail**
- `account` track: ✅ JustDelete.me sites.json vendored (`data/justdeleteme_sites.json`, 2556 entries) + `core/account_registry.py` maps every discovered account (user-scanner/Maigret hit) to its exact deletion URL + difficulty in the Exposures inbox; `impossible` → `legally_impossible`. Still TODO: an automated `account_delete` sender (most services have no deletion API — guided self-service is the realistic ceiling).
- ✅ `newsletter` track: IMAP `List-Unsubscribe` scan (`scanner/newsletter.py`) surfaces every mailing-list sender in the Exposures inbox; unsubscribe action (`core/unsubscribe.py`) does the RFC 8058 one-click POST (SSRF-guarded, HTTPS-only, no redirects) or a mailto send via the SMTP sender.
- `time_locked` track: scheduled-fire requests for bank/Skat retention windows
- `restriction_only` track: info pages for legally-undeletable sources

**Phase 5 — Personal completeness pass**
- Run full pipeline against self; iterate on gaps until self-search returns nothing actionable
- Document everything for friend/family handoff
- v1.0 cut

**v2 (out of scope here)** — multi-profile / family-shared instance

## Definition of done (v1)

- Pipeline run against Malte's identifiers finishes; all surfaced exposures routed to one of the eight tracks or marked `legally_impossible`
- Renewal reminders (CPR navnebeskyttelse, HIBP/SearXNG infra) on schedule
- Quarterly rescan returns no new actionable exposures
- One Pi/VPS-hostable Quadlet bundle, single-user, locked-down

## Conventions

- All amounts/dates in DKK and ISO 8601
- All templates Datatilsynet-correct DA; EN as fallback only
- Money decisions tracked in `docs/money.md` (one-line per purchase, date + amount + outcome)
- Per-track state machines documented in `docs/tracks/<name>.md` as they're built
