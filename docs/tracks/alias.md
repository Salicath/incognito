# Track: `alias`

Per-recipient sending identities. Every Art. 17 email used to disclose the
user's real mailbox to 228 brokers and 16 tech giants — companies whose business
is retaining personal data. That was the single largest disclosure the tool
created, and it was self-inflicted.

Each recipient now gets its **own alias**. Three consequences:

1. No broker learns the real address.
2. Inbound mail to alias *X* from anyone other than *X* is **evidence that X
   leaked or sold the address** — a fact, not a suspicion.
3. Revocation is per broker: disable the alias and they can never reach you.

Backed by **SimpleLogin** (Proton-owned; Premium included with Proton Unlimited).

## Verified mechanics (2026-07-09, against the SimpleLogin source)

Getting these wrong would fail silently, so they were checked before building.

- **Create alias:** `POST /api/alias/random/new` (or `/api/v3/alias/custom/new`).
  Auth is an `Authentication: <api-key>` header.
- **Send *as* the alias:** you cannot SMTP directly from it. Create a contact for
  the recipient — `POST /api/aliases/:alias_id/contacts` — which returns a
  **`reverse_alias_address`** (`reply+<hash>@sl.co`). Mail sent *to* that address
  from the owning mailbox is rewritten so the recipient sees the alias.
  Returns **403 "Please upgrade to create a reverse-alias"** on free plans.
- **Replies break naive matching.** A forwarded reply arrives with a *SimpleLogin*
  `From:` domain, so the poller's tier-2/tier-3 domain matching would silently
  stop detecting broker replies.
- **The reliable hook is the alias, not the sender.** In `email_handler.py`:
  - `X-SimpleLogin-Envelope-To: <alias>` is set **unconditionally** (the code
    comments say why: otherwise you cannot tell which alias received the mail).
  - `X-SimpleLogin-Envelope-From` / `-Original-From` are set **only when the user
    enables `include_header_email_header`** — so they are best-effort enrichment,
    never a dependency.
  - `X-SimpleLogin-Type: Forward` marks forwarded mail.

Therefore: **match on the alias.** Recover the real sender from
`X-SimpleLogin-Envelope-From` when present; never require it.

## Design

```
send  →  alias per (broker) created lazily on first send
      →  contact created for the broker's DPO address
      →  SMTP to reverse_alias_address; broker sees From: <alias>

reply →  broker mails the alias
      →  SimpleLogin forwards to the real mailbox
      →  IMAP poller reads X-SimpleLogin-Envelope-To → alias → request
         (new ALIAS match tier, ranked with the REF-code tier)

leak  →  mail arrives at alias X from a sender unrelated to broker X
      →  raise a LEAK alert naming X; the alias is evidence
```

### The ALIAS tier does not auto-acknowledge

An alias match proves *which request* the mail belongs to. It does **not** prove
the broker replied: with `include_header_email_header` off, spam delivered to the
alias is indistinguishable from a broker reply. Auto-acknowledging would stop the
Art. 12(3) clock on the strength of a spam message. So the ALIAS tier files the
mail against the thread and leaves the status alone — the same conservatism
applied to `DOMAIN_ONLY` matches and to Bing delisting decisions.

### Leak detection requires the opt-in headers

The verdict is only ever evaluated when a real sender was recovered from the
opt-in headers. The forwarded `From:` is a SimpleLogin reverse-alias, so judging
leakage from it would brand **every ordinary broker reply** as a resale. No
real sender, no verdict. Users who want leak detection must enable
`include_header_email_header` in SimpleLogin.

Two opt-in headers, and the verdict needs BOTH to mismatch (verified against
the SimpleLogin source 2026-07-10): `X-SimpleLogin-Envelope-From` is the SMTP
MAIL FROM — for ESP-sent broker mail that is the ESP's bounce domain, not the
broker — and `X-SimpleLogin-Original-From` is the author's From address.
Matching prefers the author too, so an ESP-sent reply carrying our REF code
still auto-acknowledges.

### The verdict is triage, not an accusation

The alias proves an *unexpected sender*, not who is culpable (shared, sold, or
breached are all consistent with it). The exposure is titled "Unexpected sender
on the alias for X" and lands in needs-triage; the Art. 15(1)(c) answer in the
guidance ladder is what turns it into — or rules out — complaint-grade
language. Exposures dedup on the sender's **domain** (`mailto:<domain>` key):
VERP campaigns vary the local part per message, and a full-address key would
mint one row per spam mail and resurrect dismissals. The full sender is kept in
the row's data as evidence.

Sender-domain comparison accepts the broker's domain and its subdomains
(`mail.spokeo.com` is not a leak) but not suffix lookalikes
(`spokeo.com.evil.ru` is). The broker's REAL domain comes from the registry
(`reply_matching_sets` id→domain map) — reconstructing it from the slug id
would brand every hyphenated-domain broker's own reply a leak
(`data-axle.com` → `data-axle-com` → `data.axle.com`).

**No leak verdict on our own thread:** a message that threads via
In-Reply-To/References to one of our outbound Message-IDs is the broker
speaking through whatever pipeline it uses (OneTrust, Zendesk, an ESP). Only
the broker's mail system ever holds the full Message-ID UUID — the subject REF
code exposes 8 of its 32 hex chars — so this cannot be spoofed by whoever
bought the address. The Message-ID set is status-independent: a second
ticketing reply arriving after the first one auto-ACKed must not be branded
either. Unthreaded DSAR-portal mail (OneTrust's fresh-message flow) can still
false-positive — that class is on the backlog (triage demotion, see PLAN.md).

Confirmed leaks are filed into the **Exposure inbox** as `source="alias_leak"`,
keyed `(source, broker_id, mailto:sender)` so repeat spam refreshes one row
instead of resurrecting a dismissal. `core/removal_guidance.py` gives the
follow-up: Art. 15(1)(c) to the broker (recipients disclosure), Art. 17 + Art. 21
+ Art. 14(2)(f) to the spammer, and an Art. 77 complaint if the broker cannot
account for the disclosure.

## Coverage — who actually gets an alias

| Group | Aliased | Why not |
|---|---|---|
| 228 brokers | all | — |
| Amazon, Snap, Spotify, Netflix, Strava | yes | — |
| Reddit | no | `send_from_account_email`: SimpleLogin rewrites the sender to the alias, which is precisely the address the platform refuses |
| GitHub, Discord | no | `cc_emails`: verified against the SimpleLogin source 2026-07-10 — the reply path looks up **every** To/Cc address as a contact and raises `NonReverseAliasInReplyPhase` for anything that isn't a reverse-alias, so a plain CC through an aliased send fails outright. Lifting this would need per-CC contacts on the same alias plus a live-account test |
| 8 form-only controllers | n/a | filed by hand via the kit |

So 5 of the 8 email-viable controllers are aliased. The three exceptions are
deliberate: a partly-aliased send is worse than an honest un-aliased one, because
it leaks the real address *and* claims not to.

## Chases reuse the identity, never mint one

Follow-ups and escalation warnings (`core/scheduler.py`) resolve the recipient
in **reuse-only mode** (`resolve_recipient(..., mint=False)`): an existing live
alias is reused, so the chase arrives from the same sender as the original
request. No alias row — a pre-alias thread, a carve-out platform, a delisting
engine the user filed with from their own mail client, or a blast-time
SimpleLogin fallback — means the chase goes from the real mailbox, exactly like
the original did. Minting mid-thread would switch identity on the recipient and
orphan the conversation, and for an already-leaked thread it buys nothing.

A **disabled** alias (`disabled_at` set — the "Disable this alias" action on a
leak exposure toggles it upstream first, and only marks the row when SimpleLogin
confirms) means the user cut off contact: chases for that broker do **not** fall
back to the real mailbox — that would hand a proven-leaky recipient exactly the
address the alias hid. The request takes the same path as a form-only platform:
auto-escalate after the window, DPA complaint. A fresh send for that broker
re-mints — updating the existing row in place, because `broker_id` is UNIQUE
and a second INSERT would poison the blast session.

**The contact tracks the registry.** The reverse-alias is bound to the
dpo_email it was minted for. When `brokers update` moves a DPO address, the
next keyed send adds a contact for the new address on the *same* alias
(`broker_alias.recipient` records it; contact creation is idempotent upstream —
`200` + `existed=true` — which also heals pre-column rows). Chases never touch
the SimpleLogin API mid-thread.

Reuse needs **no API key**: sending to a reverse-alias is plain SMTP, and
SimpleLogin keeps forwarding regardless of what keys we hold. Removing the key
stops new minting; live aliased threads keep their identity (this is also what
the Settings page promises on key removal).

## Failure mode

Any SimpleLogin error (bad key, free plan, quota, network) falls back to sending
to the real recipient from the real mailbox, logged at WARNING. An erasure request
that goes out from the real mailbox beats one that never goes out.

If the alias mints but the `broker_alias` row fails to persist, the session is
rolled back (a dirty session would fail every later broker in the blast) and the
send still goes through the alias — only reuse and ALIAS-tier reply matching
degrade; Message-ID threading still routes the reply home.

## Storage

`broker_alias` table (migrations `d1f4a7c02b98` + `a91b3e5c7d20`): `broker_id`
(unique), `alias_id`, `alias_email`, `reverse_alias_address`, `contact_id`,
`recipient`, `created_at`, `disabled_at`.

The SimpleLogin API key lives in the encrypted vault under the `simplelogin`
secret name (same path as `hibp` / `github`).

## Opt-in

Aliasing is **off** unless a SimpleLogin key is configured. With no key the tool
behaves exactly as before, sending from the SMTP identity.
