# Money decisions

One line per purchase: date + amount + outcome. Referenced by PLAN.md conventions.

**Hard constraint (Malte, 2026-07-09):** do not hand photos or personal
information to a company that retains it. This is a filter, not a preference —
it eliminates options rather than trading against them.

## Verdicts (researched 2026-07-09, primary sources)

### HIBP paid API — **DON'T BUY**

The plan said *"$3.95/mo, removes rate limits."* Both halves were wrong.

- The key is not an optimisation, it is **mandatory**: `/api/v3/breachedaccount/`
  returns **401 without a key** (verified by live request). Without it the breach
  feature does not work at all. The free endpoints are breach *metadata* only.
- Current tiers (haveibeenpwned.com/Subscription, rendered 2026-07-09):
  **Core 1 $4.39/mo** ($52.68/yr) · **Pro 1 $379/mo** · High RPM $1,150/mo.
- **k-anonymity email search** (send a 6-char SHA-1 prefix; HIBP never receives
  the address) is listed **only on Pro and High RPM**. Core sends your plaintext
  email on every query, protected by a policy promise, not by architecture.
- **Stealer logs** (which sites your credentials leaked from — the one genuinely
  new account-discovery signal) are **Pro-only**, and the endpoint is
  **domain-scoped**: it requires *verified control of the domain*. `pm.me` is
  Proton's domain. **That data is unreachable for this address at any price.**

So the only architecturally-private option costs ~€4,200/yr, and the affordable
one violates the hard constraint. Don't buy. Note the free individual path (verify
your address in HIBP's UI to view your own stealer logs) also fails the filter —
the notification service must store the address in order to notify you.

### PimEyes — **DON'T BUY, and you cannot cleanly opt out either**

The plan said *"~€30 one-time."* There is no €30 one-time. Rendered live from
pimeyes.com/en/premium (da-DK locale, 2026-07-09):

| Plan | Price |
|---|---|
| "Unlock Current Results" (1 search, sources + PDF) | **16,99 € one-time** |
| Open Plus | **32,99 € / month, recurring** |
| PROtect | 38,99 €/mo (promo 27,29) |
| Advanced | 329,99 €/mo (promo 230,99) |

The €30 figure matches Open Plus *monthly*, not a one-off. But price is not the
reason to decline:

- You upload your face and see blurred results **before** paying. The biometric
  disclosure happens regardless of purchase.
- Non-account uploads are *"securely stored for 48 hours"* (privacy policy).
- **The opt-out form requires a face photo AND an anonymized passport/ID scan.**
  You cannot remove yourself without surrendering *more* than a search costs.
- Named entity: **EMEA Robotics LTD, Dubai (UAE)**. No EU establishment and no
  Art. 27 representative identified in the policy; no clear legal basis stated
  for biometric processing.
- Their position is that they hold *"no name or email, only face fingerprints"* —
  which under **GDPR Art. 11** means they need not honour Arts. 15–20 unless you
  supply identifying data, i.e. your face. Biometric disclosure is the price of
  every right you would want to exercise against them.

Treat the face-search axis as a **documented gap**, not a purchase. It belongs in
the `restriction_only` framing: honest "here is what you cannot do, and why."

## Recommended direction instead

The largest disclosure this tool creates is not a scanner — **it is the tool
itself.** Every Art. 17 email sends `From: salicath@pm.me` to 228 brokers and 16
tech giants: companies whose business is retaining personal data. That is a far
bigger leak than any HIBP query, and it is self-inflicted.

**Proposal (needs Malte's approval before building): per-recipient aliases.**
SimpleLogin is Proton-owned and has a REST API (`POST /api/v3/alias/custom/new`,
`GET /api/v2/aliases`, toggle, delete; API-key auth). Included with Proton
Unlimited / Pass Plus.

1. A unique alias per broker → no broker learns the real address.
2. Inbound mail to alias *X* is **proof that broker X leaked or sold it** —
   evidence for a complaint, not a suspicion.
3. Revoke per broker: disable the alias and they can never reach you again.
4. IMAP reply matching is unaffected (it keys on `[REF-…]` / Message-ID).
5. `send_from_account_email` already exists for platforms like Reddit that
   demand the account's own address — the architecture anticipates the carve-out.

**Cost:** a domain (~€10/yr) if using a custom domain; otherwise €0 marginal on a
paid Proton plan. Cheaper than HIBP Core, and it *reduces* disclosure instead of
buying more.

**Unresolved engineering question:** sending *from* an alias. SimpleLogin's
reverse-alias mechanism rewrites outbound mail, but wiring it to the SMTP sender
needs verification before committing. Do not start building until that is
checked.

## Pending (blocked on Malte)

- Confirm whether a paid Proton plan is active. If yes, Dark Web Monitoring is
  already included (any paid plan) and covers breach alerts — UI/notification
  only, no API or export, so it cannot feed the Exposures inbox automatically.
  It is partly backed by HIBP **and Constella**, a vendor this plan already
  rejected; whether Proton forwards the address to Constella or merely ingests
  their corpus is **unverified**.
- Decide on the alias proposal above.

## Decided

- 2026-07: SearXNG sidecar — €0 (self-hosted Quadlet). Replaced the planned
  Brave Search API top-ups as the primary DDG alternative.
- 2026-07-09: HIBP paid tier — **not bought** (see above).
- 2026-07-09: PimEyes — **not bought** (see above).

## Substitutes considered and rejected

- **XposedOrNot** — free, no API key, MIT-licensed self-hostable code. But
  self-hosting **does not ship the breach corpus**; queries still resolve against
  `api.xposedornot.com`, so it does *not* give query privacy. Fails the filter.
- **Hudson Rock (free Cavalier API)** — real and live, but returns per-infection
  metadata and aggregate service *counts* only, not the specific sites. The
  which-sites data is paid-gated. Useless for the account-deletion track.
- **Mozilla Monitor** — HIBP-backed, free, no API.
- **Self-hosted breach corpus** — holding a leaked dataset containing millions of
  *other people's* personal data would make Malte a controller of that data under
  GDPR. Legally and ethically the wrong answer for a privacy tool. Rejected.
