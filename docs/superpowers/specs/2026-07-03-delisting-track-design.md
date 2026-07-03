# Delisting Track — Design

**Date:** 2026-07-03
**Plan item:** Phase 3 — `delisting` track (Google + Bing RTBF)

## Goal

Turn a web-search exposure (a URL found by the DDG name scanner that surfaces the
user's personal data) into an actionable **search-engine delisting** request. Because
every delisting channel is a manual web form with an ID upload and no API, the tool's
role is **assist-and-track, not auto-submit**: generate the per-engine deep-link plus a
drafted Article 17 justification the user can paste, and make the manual ID-upload
boundary explicit.

## Research summary (verified against primary sources)

- **Manual-only everywhere.** Google RTBF, Bing RTBF: web forms, ID upload + signed
  affirmation. Brave: email. No API; the Data Rights Protocol does not cover search
  engines. Practical automation is limited to deep-link + copy-paste kit.
- **Surface = Google + Bing** for a Dane. DuckDuckGo/Ecosia/Yahoo resell Bing;
  Startpage resells Google — delisting the upstream covers them. Brave + Mojeek run
  independent indexes (optional email requests). Yandex: excluded for DK.
- **Query-scoped, not URL-wide** (CJEU C-131/12): delisting hides a URL only for
  searches of the user's *name*, so a target is a `(URL, name-query, engine, locale)`
  tuple; the page stays online (delisting ≠ deletion).
- **EU-scoped** (C-507/17): removed across EU domains + geoblocked, not worldwide.
- **Reason vocabulary** shared by both forms: inaccurate / inadequate / out-of-date /
  excessive. Refusal → national DPA (Datatilsynet), Art. 12(3) one-month clock.

## Scope (this slice)

Core value first: the **delisting kit generator** + API + Exposures UI. Deferred to a
follow-on: request-state-machine tracking, IMAP decision-email matching, quarterly
re-verification, and auto-generated Datatilsynet escalation.

## Architecture

### `backend/core/delisting.py`
- `Reason` enum-like keys → human phrasing, with `en` and `da` locale text
  (Datatilsynet-correct Danish; en fallback).
- `DelistingEngine(key, name, action, target, id_required, note)` registry:
  Google (form), Bing (form), Brave (email). Notes carry which resellers each covers.
- `build_delisting_kit(url, name_queries, reason, locale) -> dict` returning:
  `{url, name_queries, reason, justification, engines[], coverage_note}`. The
  justification is a locale-aware Art. 17 paragraph citing C-131/12 and the chosen
  reason, scoped to the user's name.

### API (`backend/api/scan.py`)
- `GET /exposures/{id}/delisting-kit?reason=<key>` — loads the exposure's URL and the
  user's name variants (profile `full_name` + `previous_names`), returns the kit.

### Frontend (`Exposures.tsx`)
- For exposures carrying a URL, a "Delisting kit" panel: a reason selector, the
  copyable justification, and per-engine deep-links (form/email) with the
  "ID upload required — manual step" caveat and the coverage note.

## Out of scope (follow-on)
- Delisting request lifecycle in the state machine (OVERDUE/ESCALATED, DPA complaint).
- IMAP matching of Google/Bing decision emails.
- Quarterly name-search re-verification via the rescan timer.
- Mojeek/Qwant/Yandex; "Results about you" (EU availability unconfirmed).
