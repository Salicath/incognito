# Track: `time_locked`

Danish statutory retention holds that block Art. 17 until they lapse. The user
arms an entry with the trigger date; the tool computes `fires_at` and raises
the Art. 17 kit the day the holder's retention duty matures. For the bank and
telco entries the statute itself mandates deletion at that point — the request
enforces a matured duty, so "we must keep it" is no longer a valid refusal.
Facts verified against primary sources 2026-07-05.

## State machine

```
(entry template in brokers/time_locked.yaml — the holder is the USER'S OWN
 bank/insurer/employer, so a hold is armed per institution)

ARMED (trigger date + institution entered; fires_at computed)
  └→ FIRED     (fires_at reached — follow-up job notifies once; Art. 17 kit
  │             available, assist-only: user sends from their own mailbox)
  └→ DISMISSED (user closes the hold)
```

Arming with a trigger date whose retention already lapsed fires immediately.

## Entries (5)

| id | fires_at | Notes |
|---|---|---|
| `dk-bank-hvidvask` | trigger + 5y (Feb 29 → Feb 28) | Hvidvaskloven § 30, stk. 2, 2. pkt. mandates deletion at exactly 5 years. Escalate 1 month after fire (Finanstilsynet batch tolerance — guidance, not statute). **Citation trap:** never cite LBK 1463/2025 (defective § 30 consolidation); use LBK 433/2026+. |
| `dk-company-bogfoering` | fiscal-year-end(trigger) + 5y + 1 day | Pure retention duty, no deletion mandate — Art. 5(1)(e)/17 takes over at expiry. FY assumed 31 Dec. |
| `dk-insurer-foraeldelse` | trigger + 3y; conservative toggle + 10y | 3y is a legitimate opening move, not a guaranteed win (forældelsesloven § 3, stk. 2 suspension); 10y is the cannot-refuse point. Personal-injury files may persist 30y from injury. |
| `dk-telco-billing` | last invoice due + 3y | BEK 1882/2020 § 10, stk. 2 commands deletion — strongest entry. Logning data is out of scope (restriction_only). |
| `dk-employer-post-employment` | employment end + 5y | Datatilsynet-guidance ceiling; salary bookkeeping tail may persist to FY+5y; arbejdsskade docs carved out. Public employers → restriction_only (notatpligt + arkivloven). |

## PLAN.md corrections from research

- Bank was "5y+1mo" — **wrong**: fire at exactly +5y; the month is only the
  escalation threshold.
- Skat was listed as time-locked "5-10y" — **wrong framing**: the windows
  govern how long data is needed, never when erasure becomes demandable.
  Art. 17(3)(b)/(e) + arkivloven defeat erasure at any time → Skat lives in
  `restriction_only` with Art. 16/18 mitigation instead.

## Implementation

- `brokers/time_locked.yaml` + `core/time_locked.py` (registry, expiry math,
  `check_time_locked_expiries` fired from the `follow-up` command)
- `time_locked_state` table (migration `c9e5f2a7b4d1`)
- `api/statutory.py`: list / arm / dismiss / kit endpoints
- Kit renders `templates/time_locked_erasure.txt.j2` (da primary, en fallback)
  citing the statute and the matured deletion duty — assist-only; the holder
  is personal, not a registry entry, so there is no tracked Request

## Re-verify at refresh

- Finanstilsynet's +1-month batch tolerance is from the Nov 2020
  hvidvaskvejledning — check for a newer edition.
- Insurer +3y copy must never promise success (suspension rules).
