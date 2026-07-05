# Track: `delisting`

Search-engine RTBF (Art. 17 as applied by CJEU C-131/12 Google Spain). The kit half
shipped 2026-07-03 (assist-only: per-engine deep-links + drafted justification);
this doc covers the lifecycle half — tracked requests, decision-email matching,
escalation, re-verification. Facts verified July 2026.

## Shape

A delisting request is a `(URL, engine)` pair — query-scoped to the user's name
(C-131/12), EU/geo-scoped (C-507/17). Tracked as a normal `Request` with
`broker_id = delisting-<engine>` and `target_url`, resolved through the
`RegistryUnion` via `DelistingRegistry` pseudo-targets. Never blasted.

```
user files the form/email themselves (ID-gated, no API)
  └→ "I filed it" in the Exposures kit panel
       └→ CREATED → MANUAL_ACTION_NEEDED → SENT   (attested; Art. 12(3) one-month clock)
            ├→ ACKNOWLEDGED   (decision email matched, or user confirms)
            │    └→ COMPLETED (granted) / REFUSED → ESCALATED
            └→ OVERDUE (silence past one month = actionable Art. 12(3)/(4) inaction)
                 └→ ESCALATED  (Google/Bing have no chase channel: scheduler Step 3
                                auto-escalates after the window → DPA complaint)
```

Brave is the exception: email channel (`privacy@brave.com`), so overdue requests
get chased by the normal follow-up emails, and replies thread via Message-ID.

## Decision-email matching (`ImapPoller._match_delisting_decision`)

Google/Bing decisions are **form-triggered mail, not replies** — Message-ID and
`[REF-...]` matching can never fire. New matcher, gated on open delisting requests:

| Engine | Sender | Signal | Action |
|---|---|---|---|
| Google | Exact-address allowlist (`removals@google.com` + variants) — **never** the whole google.com domain: Google Alerts / "Results about you" notifications quote the same URL and would auto-ACK the request and disarm the Art. 12(3) clock | Decision mail enumerates the requested URLs | allowlisted sender **and** `target_url` in body → attach + auto-ACKNOWLEDGED (`delisting_decision` tier); anything else → untouched, user confirms |
| Bing | — | None reliable — no case number, no URLs, and domain-wide matching would file Microsoft security codes onto the legal thread and mark them read | No auto-matching at all; user confirms manually |
| Brave | `privacy@brave.com` | Normal reply threading | Existing tiers 1–2, no new code |

Granted/refused body phrases ("decided not to take action on the following
URL(s)") are practitioner-reported, not documented — they stay out of the code;
the user classifies via the normal transition buttons. Precision over recall
throughout: a missed auto-ACK costs a manual click; a false auto-ACK silently
kills the deadline chase.

## Escalation (Danish user)

| Engine | Controller to name | Route |
|---|---|---|
| Google | **Google LLC** (Mountain View) | **Datatilsynet decides itself** — no EU main establishment for Search RTBF processing, so no one-stop-shop; pure national Art. 55 case. Precedent: IMY DI-2018-9274 fined Google LLC (upheld); Brussels Market Court 2021 annulled an APD fine *because* Google Belgium wasn't the controller |
| Bing | Microsoft Ireland Operations Ltd | Datatilsynet → IE DPC as lead SA (Arts. 56/60); slower OSS timelines |
| Brave | Brave Software Inc. (US, Art. 27 rep `gdprnomrep@brave.com`) | Datatilsynet, Art. 55 |

Implemented via `dpa.get_dpa_for_request` (category `delisting` routes by residence)
and the complaint template's localized controller/Art. 55 block plus a delisting
paragraph carrying the URL and name-query scope. Datatilsynet prerequisites: prior
application to the engine, the refusal or 12(3)/(4) silence, exact URL(s) + the
name query, screenshots. DK scope calibration: complaints succeed on
private-life/outdated content, not professional-role content (Datatilsynet 2019,
upheld by Østre Landsret).

## Re-verification

- **Bing surface — automatic.** `verify_delisted_urls` (run by the rescan
  command/timer) issues bare name queries via DDG (DDG resells Bing; the
  region param `kl=dk-da` makes the EU RTBF filter reliable — it is set ONLY
  here, since region-biasing the broker discovery scan costs recall on US
  brokers). A COMPLETED delisting whose `target_url` resurfaces (scheme/www
  insensitive) raises `DATA_REAPPEARED`. Syndication lag after a grant is 2–4
  weeks — don't panic on an early hit.
- **Google surface — manual, guided.** No ToS-safe programmatic option exists
  (Custom Search JSON API closed to new customers, retires 2027; SERP APIs break
  DK geoscoping). The kit carries signed-out check links
  (`google.com/search?q="Name"&pws=0` from a DK connection — vantage IP decides,
  google.dk is just a redirect) and the Google "Results about you" enrollment
  link (ambient name monitoring; policy track, complements the Art. 17 form).
- Reappearance semantics: same URL back → re-file citing the prior grant; same
  content at a **new** URL → new request (delisting is exact-URL).

## Known limits / re-verify at refresh

- Google/Bing sender addresses are practitioner-verified, not documented —
  re-check on the next research sweep. `bingeuprivacyrequests@microsoft.com`
  circulates but is unverified.
- The Google confirmation email carries a bracketed case ID reused in the
  decision subject — capturing it would strengthen matching (future).
- T+7/T+30 post-grant verification reminders are folded into the quarterly
  rescan for now.
