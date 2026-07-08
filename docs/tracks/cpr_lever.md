# Track: `cpr_lever`

Danish-specific upstream levers. Killing data at the CPR / Eniro source layer cascades to multiple downstream brokers in one MitID action. Higher leverage than per-broker Art. 17.

## Why this track exists separately

Standard `broker` track assumes: tool composes an email/form → broker → IMAP reply → DPA escalation. CPR levers don't fit:

- The action is performed on `borger.dk` or `opdater.krak.dk` via **MitID** — the tool cannot perform it. Only the user can.
- Outcome propagates to other brokers automatically via CPR/Eniro feed refreshes (days to weeks).
- Annual renewal is required (navne-/adressebeskyttelse, 1 year).
- No DPA escalation path — these aren't broker requests, they're statutory rights at the registry layer.

## State machine

```
NEW
 ├→ ACTIVE          (user clicks "I completed this on borger.dk" — confirm_lever
 │   │               transitions straight to ACTIVE, sets activated_at/expires_at)
 │   └→ RENEWAL_DUE (T-30 from expiry: nag; T-7: escalate — check_lever_renewals)
 │       └→ EXPIRED (T=0: lever lapsed; blast re-includes the cascade brokers)
 └→ USER_DEFERRED   (user chose not to activate — recorded with reason)
```

No SENT/REPLY states. The tool tracks user confirmation, not broker correspondence.
Implementation note: `CprLeverStatus` also defines `USER_NOTIFIED`, but no code
path sets it — confirm goes NEW/deferred → ACTIVE directly. Coverage is an
aggregate skip in the blast response (`covered_broker_ids`), not a per-broker
`covered_by`/`dependent_on` status tag.

## Concrete levers (initial set)

| `lever_id` | Source | Action URL | MitID? | Cost | Expires | Cascades to |
|---|---|---|---|---|---|---|
| `dk_cpr_navnebeskyttelse` | CPR / Borger.dk | `https://www.borger.dk/bolig-og-flytning/flytning_oversigt/navne-og-adressebeskyttelse` | Yes | Free | 1 year | krak, degulesider, 118-dk, eniro-dk, CVR personal address (auto), telco-fed entries |
| `dk_robinsonlisten` | CPR / Borger.dk | `https://www.borger.dk/bolig-og-flytning/beskyttelse-mod-reklamer/Robinsonlisten-markedsfoeringsbeskyttelse` | Yes | Free | Persistent (toggle) | Addressed direct mail, cold-call telemarketing — does NOT cover unaddressed flyers, email, SMS |
| `dk_krak_selvbetjening` | Eniro DK | `https://opdater.krak.dk/person` | Yes (MitID + SMS) | Free | Persistent | krak.dk + degulesider.dk (same backend) — independent of CPR path |
| `dk_telco_hemmeligt_nummer` | TDC/YouSee/3/Telia/Telenor | per-provider | Provider login | Free | Persistent | Propagates to 118.dk on next telco feed refresh |
| `dk_nej_tak_reklamer` | PostNord / Forbrugerombudsmanden | physical "Reklamer Nej Tak" sticker + opt-out | No | Free | Persistent | Unaddressed flyers only |
| `dk_cvr_adressebeskyttelse` | Erhvervsstyrelsen | Auto-applied if `dk_cpr_navnebeskyttelse` is active. Otherwise: `https://erhvervsstyrelsen.dk/nemmere-faa-adressebeskyttelse-i-cvr` | Yes | Free | Persistent (5y post-role tail) | ErhvervsKrak, Risika, NN Markedsdata, Visma Rating (`erhvervskrak-dk`, `risika-dk`, `nnmarkedsdata-dk`, `vismarating-dk`) |

## Mutual exclusion

- `dk_robinsonlisten` ↔ `dk_cpr_navnebeskyttelse`: registry rule — having full CPR name/address protection overrides Robinsonlisten registration. Tool MUST detect this and inform the user (recommend `dk_cpr_navnebeskyttelse` as superset).

## Data model

```python
class CprLever(BaseModel):
    lever_id: str                          # e.g. "dk_cpr_navnebeskyttelse"
    name: str                              # human label
    url: str                               # action URL (deep-link)
    requires_mitid: bool
    expires_after_days: int | None         # 365 for navnebeskyttelse, None for persistent
    cascade_broker_ids: list[str]          # broker.yaml ids that this lever covers
    mutual_exclusion: list[str] = []       # other lever_ids that conflict

class CprLeverState(BaseModel):
    lever_id: str
    status: Literal["new", "user_notified", "active", "renewal_due", "expired", "user_deferred"]
    activated_at: date | None
    expires_at: date | None
    user_note: str = ""                    # why deferred, or evidence reference
```

State is per-user (single-profile in v1; per-profile in v2). Persisted in the SQLite DB alongside broker requests.

## UI flow

1. The CPR Levers page is always in the nav (not gated on a residence question — the setup wizard has no such step; see the deferred-work note below).
2. Each lever shown as a card: action, cascade list (how many brokers this covers), deep-link button.
3. User clicks deep-link → opens `borger.dk` (new tab) → completes MitID action → returns → clicks "Confirm completed" in Incognito → state transitions to `active`, `activated_at = today`, `expires_at = today + expires_after_days`.
4. Tool registers a renewal reminder at `expires_at - 30 days`.
5. While the lever is active, the blast skips its `cascade_broker_ids` (an aggregate `covered_broker_ids` set — not a per-broker status tag).

## What this saves

For a Dane activating just `dk_cpr_navnebeskyttelse` + `dk_robinsonlisten` (mutually exclusive — pick navnebeskyttelse), this single MitID action covers:
- krak.dk
- degulesider.dk
- 118.dk
- eniro.dk (DK branch)
- CVR personal-address exposure (auto-applies)
- Downstream CVR aggregators (ErhvervsKrak, Risika, NN Markedsdata, Visma Rating)

≈ 4 direct cascades + 4 indirect = **8 brokers eliminated without sending a single email.** Plus all cold-call telemarketing legally pre-blocked.

## What this does NOT do

- No effect on email/SMS marketing — those need standard Art. 17.
- No effect on US brokers, EU brokers outside Eniro/CVR feeds, or tech-giant controllers.
- No effect on telco logning (mandated, separate `restriction_only` track).
- No effect on banks within Hvidvaskloven retention window (`time_locked` track).

## Renewal scheduling

`expires_at - 30 days`: tool sends a push notification (existing notifier system) + dashboard banner.
`expires_at - 7 days`: escalated reminder.
`expires_at = today`: status transitions to `expired`, dashboard shows red, cascading brokers re-marked as `requires_action`.

## Implementation order

1. Data model + migration (add `cpr_levers` and `cpr_lever_state` tables).
2. YAML seed file: `brokers/cpr_levers.yaml` with the 6 levers above + `cascade_broker_ids` lookups.
3. API endpoints: `GET /api/cpr-levers`, `POST /api/cpr-levers/{id}/confirm`, `POST /api/cpr-levers/{id}/defer`.
4. Frontend page: `frontend/src/pages/CprLevers.tsx` — card list, deep-link buttons, confirm/defer controls.
5. Scheduler hook: nightly job checks `cpr_lever_state.expires_at` and emits renewal notifications.
6. Broker pipeline integration: skip Art. 17 send for brokers whose `id` is in any active lever's `cascade_broker_ids`.

## Out of scope for this track

- Friends/family multi-profile (v2 concern).
- Non-Danish equivalents (e.g., German `Sperrvermerk im Melderegister`, Swedish `skyddade personuppgifter`) — add later under `eu_lever` if extended.
