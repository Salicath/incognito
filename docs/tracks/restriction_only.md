# Track: `restriction_only`

Sources where GDPR erasure is legally impossible for a Dane. Honest info
cards: what it is → why it stays (Art. 17(3) ground + the Danish statute) →
what the user CAN do instead, with deep link + MitID flag. No state machine.
Facts verified against primary sources 2026-07-05.

## Entries (9)

| id | Mitigation |
|---|---|
| `sundhedsjournalen` | Privatmarkering per episode/whole record (sundhedsloven § 42 b) via Min side; FMK blocking via prescribing doctor; access audit in Min log. Emergencies bypass. |
| `tinglysning` | Discharged rights: creditor aflyser → historical register with restricted access (BEK 763/2009 § 35, stk. 4); CPR numbers never public (TL § 50 c). |
| `statstidende` | Name-search protection automatic after 1 year (§ 5, stk. 2); DB entries auto-delete after 5y (§ 15); wrong notices corrected by the editorial office (BEK 349/2014 § 8, stk. 2). Royal Library copies permanent. |
| `cvr-historik` | CPR navne-/adressebeskyttelse auto-hides the address in CVR (CVR-loven § 18, stk. 4 — see CPR lever track). Name+role history permanent (§ 18, stk. 3). |
| `telelogning` | Nothing removable; Art. 15 access + minimization advice. Rules (BEK 397/2026) run to 2027-03-29, renewed annually — re-verify at refresh. |
| `rigsarkivet-arkivloven` | Shared Art. 17(3)(d) explainer: kassation only per ministry rules (arkivloven § 10); protection = closure periods (20y/75y, §§ 22-23). |
| `cpr-registret` | Four protections: § 28 navne-/adressebeskyttelse (set BEFORE a move), § 29 lokalvejviser/Robinson/kreditadvarsel. § 28 pierced by documented legal claims (§ 42). Forskerbeskyttelse abolished 2014 — never offer it. |
| `domsdatabasen` | Extended pseudonymization (BEK 2708/2021 § 3, stk. 2) or non-publication (§ 2, stk. 4) via domsdatabasen@domstolsstyrelsen.dk. Court file stays obtainable via aktindsigt. |
| `dk-skat-restriction-only` | Moved here from time_locked (no computable expiry exists): Art. 16 rectification, Art. 18(1)(a) restriction while accuracy contested, Datatilsynet complaint for excess. |

## Implementation

`brokers/restriction_only.yaml` + `core/restriction_only.py` (loader) +
`GET /api/statutory/restriction-only` + the "Legally undeletable" section of
the Statutory page. Exposure triage's `legally_impossible` disposition is the
per-hit counterpart; these cards are the source-level explainer.

## Re-verify at refresh

- sundhed.dk privatmarkering menu path/URL (SPA — verified from help pages).
- Telelogning BEK number and expiry marker (annual renewal).
