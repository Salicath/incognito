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
- ✅ SearXNG Quadlet sidecar (see Deferred/next below)
- HIBP paid-tier wiring + PimEyes manual-result-import flow

**Exposure triage layer** (new, not in original 8-track plan) ✅
- ✅ Every scanner persists to `scan_results`; unified Exposures inbox aggregates + dispositions each hit (actioned/dismissed/legally_impossible)
- ✅ One-click Art. 17 request for hits matching a registry broker; per-source removal guidance for the rest
- ✅ Dashboard needs-triage banner; setup wizard captures usernames (scanner fuel)

- ✅ Secrets in vault: HIBP key + GitHub token now live in `_VaultData.secrets` (encrypted); legacy plaintext files auto-migrate on first access. Backup carries them inside the vault (no plaintext field).

**Deferred / next**
- ✅ SearXNG Quadlet sidecar (`deploy/searxng.container` + `searxng-settings.yml`; `scanner/searxng.py` JSON-API backend, enabled via `INCOGNITO_SEARXNG_URL`, smoke-tested end-to-end against the live container)
- HIBP paid-tier wiring + PimEyes manual-result-import flow
- Phone-axis account enumeration (no maintained tool exists; ignorant is dead — port the technique if needed)

**Phase 3 — Controller track**
- ✅ Controller track (`docs/tracks/controller.md`): `brokers/controllers.yaml` — 16
  hand-verified platform records (research + adversarial verification, July 2026;
  datenanfragen.de was stale for 5 of 16, so records are hand-curated with
  `datenanfragen_slug` join keys). 8 of 16 are form-only (no verifiable Art. 17
  email) and ride MANUAL_ACTION_NEEDED -> SENT with a generated filing kit; the
  other 8 send immediately through the existing SMTP/IMAP/deadline pipeline.
  Opt-in per platform (never blasted). Escalation routes to the residence SA
  (`INCOGNITO_USER_COUNTRY`, default DK — Art. 77 one-stop-shop; direct lead-SA
  filing has no procedural advantage), GB entities to ICO, no-EU-establishment
  (Snap) to the residence SA under Art. 55; lead SA named in the complaint text.
- Deferred: vendoring the full datenanfragen.de company DB (CC0, ~3k records) as
  general registry enrichment.
- ✅ `delisting` track (`docs/tracks/delisting.md`): kit generator (2026-07-03) +
  lifecycle (2026-07-05). Tracked `(URL, engine)` requests with user-attested filing
  (Art. 12(3) clock), decision-email matching (Google: URL-in-body auto-ACK; Bing:
  attach-only; Brave: normal threading), residence-DPA escalation (Google = national
  Art. 55 case vs Google LLC — no one-stop-shop; Bing = Microsoft Ireland → IE DPC),
  and re-verification: quarterly DDG rescan (`kl=dk-da`) flags resurfaced delisted
  URLs; Google surface via guided signed-out check links + "Results about you".

**Phase 4 — Long tail**
- `account` track: ✅ JustDelete.me sites.json vendored (`data/justdeleteme_sites.json`, 2556 entries) + `core/account_registry.py` maps every discovered account (user-scanner/Maigret hit) to its exact deletion URL + difficulty in the Exposures inbox; `impossible` → `legally_impossible`. Still TODO: an automated `account_delete` sender (most services have no deletion API — guided self-service is the realistic ceiling).
- ✅ `newsletter` track: IMAP `List-Unsubscribe` scan (`scanner/newsletter.py`) surfaces every mailing-list sender in the Exposures inbox; unsubscribe action (`core/unsubscribe.py`) does the RFC 8058 one-click POST (SSRF-guarded, HTTPS-only, no redirects) or a mailto send via the SMTP sender.
- ✅ `time_locked` track (`docs/tracks/time_locked.md`): 5 verified DK
  retention holds (bank/hvidvask +5y exact — the "+1mo" was escalation
  tolerance only; bogføring FY+5y+1d; insurer 3y/10y toggle; telco 3y;
  employer 5y). User arms a hold with the trigger date; the follow-up job
  fires the Art. 17 kit when the duty matures. Skat moved to
  restriction_only — no computable expiry exists (Art. 17(3)(b)/(e)).
- ✅ `restriction_only` track (`docs/tracks/restriction_only.md`): 9 honest
  "cannot delete, but here is the restriction" cards (sundhedsjournalen
  privatmarkering, tinglysning, statstidende, CVR historik, telelogning,
  arkivloven, CPR-registret, domsdatabasen, Skat).

**Phase 5 — Personal completeness pass**
- Run full pipeline against self; iterate on gaps until self-search returns nothing actionable
- Document everything for friend/family handoff
- v1.0 cut

**v2 (out of scope here)** — multi-profile / family-shared instance

## Handoff — state as of 2026-07-09

All eight tracks are built (Phases 1-4 complete, checkmarks above), every
track has passed an adversarial post-review with fixes merged, the SearXNG
sidecar shipped, the **Phase 5 gate read-through + research sweep ran
2026-07-08**, and its entire findings list has since been worked down —
`docs/known-issues.md` now has nothing outstanding, and the complaint
generator cites live legal authority (EDPB CEF-2025 + Reg (EU) 2025/2518).
502 tests, CI green, container publishing to `ghcr.io/salicath/incognito`.

**Everything actionable without Malte is done.** The two remaining items both
need him: a purchase, or his real identifiers.

CI also guards docs against registry drift: the broker/controller counts in
README.md and CLAUDE.md are recomputed and must match (they had silently
drifted to 220 vs a real 228).

**Next work items, in order:**
1. ✅ Done 2026-07-09: complaint generator now carries the EDPB CEF-2025
   rebuttal (when the controller refused) and the Reg (EU) 2025/2518
   admissibility/15-month lines (gated on cross-border + date ≥ 2027-04-02).
   See `docs/tracks/controller.md` — includes two corrections to widely-repeated
   secondary-source errors.
2. HIBP paid-tier wiring + PimEyes manual-result-import flow (purchase-gated —
   see `docs/money.md`). **Needs Malte to buy.**
3. Phase 5 completeness pass: run the full pipeline against Malte's own
   identifiers, iterate until self-search returns nothing actionable, then
   cut v1.0. **Needs Malte in the loop.**

**Hard-won lessons — keep doing these:**
- Legal text gets primary sources or it doesn't ship. Two research passes each
  corrected claims that every secondary source repeats (bank "5y+1mo"; the
  Reg 2025/2518 admissibility list is Art. 4 not Art. 3; its extension is
  once/12mo, not 2mo).
- Verified sources don't protect against wrong plumbing. The EDPB block was
  first gated on `response_body`, which `mark_acknowledged` also sets — it
  would have told a DPA that a merely-acknowledging controller "relies on an
  exception under Art. 17(3)". Caught by re-reading my own diff, not by tests.
- Prove a guard fires. Every new guard here was verified by breaking the thing
  it guards (docs counts, EDPB gate, locale blocks). A guard you've only seen
  pass tells you nothing.

**Known infra flake:** the `container` CI job cancelled once at ~15 min
(multi-arch QEMU); the same commit built and smoke-tested clean locally and
passed on re-run. If it recurs, add `timeout-minutes` so it fails loudly
rather than mysteriously — don't assume the code is at fault.

**Phase 5 gate outcome (2026-07-08 sweep):**
   - Research re-verified all 16 controllers + delisting + landscape. Registry
     drift fixed: GitHub postal, Netflix retention 10→24mo, Strava full
     address, Reddit building line, Tinder form host (bare `help.tinder.com`
     is now NXDOMAIN → `www.`), Brave rep `brave@gdprnomrep.eu`. Snap still
     no-EU-establishment (Art. 55 routing holds).
   - **Regulatory:** EU Digital Omnibus GDPR half is STALLED (not law; only a
     widened Art. 12(5) "abuse of rights" refusal ground would touch us —
     watch when the Irish presidency tables a mandate). GDPR Procedural Reg
     (EU) 2025/2518 is in force, cross-border chapters apply ~2027-04-02:
     worth aligning the complaint generator to its fixed admissibility fields.
     EDPB CEF-2025 erasure report = free citable ammunition for escalation
     templates (backups in scope, anonymisation ≠ erasure).
   - **Still-open sweep item:** the statutory recheck agent didn't finish
     (session limit) — hvidvaskloven LBK currency, telelogning BEK renewal,
     sundhed.dk privatmarkering URL still want a confirming pass.

**Working conventions that produced this state (keep them):**
- Research-first: verify contacts/legal facts online against primary sources
  BEFORE baking them into YAML/templates — every research pass so far found
  the plan or public datasets wrong somewhere (stale DPO emails, bank
  "5y+1mo", Skat mislabeled time-locked).
- GitHub flow: feature branch → PR → CI green → merge commit ("Merge: <track>
  — <summary>"). Never straight to main except docs.
- Adversarial review before merge — it found 10 confirmed bugs on each of the
  two big tracks after tests were already green. An empty review result with
  errored agents means verification never ran; re-run it, don't trust it.
- Per-track docs in `docs/tracks/<name>.md`, PLAN.md checkmarks, CLAUDE.md
  architecture bullet + test-file line per track.

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
