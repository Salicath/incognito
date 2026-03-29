# IMAP Reply Monitoring — Design Spec

**Date:** 2026-03-29
**Status:** Draft
**Purpose:** Automatically detect broker responses to GDPR requests, completing the end-to-end enforcement pipeline: send request → detect reply → track deadline → escalate via DPA complaint.

## Context

Incognito sends GDPR Art. 17 erasure requests to data brokers via email. Under GDPR, brokers must respond within 30 days. The system already tracks deadlines and generates DPA complaints for non-responsive brokers. What's missing: automated detection of broker replies. Currently, users must manually mark requests as acknowledged.

IMAP monitoring fills this gap. It is not a replacement for re-scanning (which verifies actual data removal). It tracks the *legal response timeline* — whether the broker replied at all, and what they said.

No commercial data removal service uses IMAP monitoring (they use re-scanning). But their model is different: they don't escalate to DPAs. For a GDPR enforcement tool, tracking responses is essential because the 30-day deadline and DPA complaint pipeline depend on knowing whether a response was received.

## Data Model

### New field on `Request`

```python
message_id: Mapped[str | None]  # Message-ID header set on outgoing email
```

Format: `<{request_id}@incognito.local>`

### New table: `EmailMessage`

Stores all inbound and outbound emails linked to a request.

| Column | Type | Nullable | Purpose |
|--------|------|----------|---------|
| id | Integer PK | No | Auto-increment |
| request_id | String FK → requests.id | No | Parent request |
| message_id | String | No | RFC 2822 Message-ID header |
| in_reply_to | String | Yes | In-Reply-To header (for threading) |
| direction | Enum(inbound, outbound) | No | Email direction |
| from_address | String | No | Sender address |
| to_address | String | No | Recipient address |
| subject | String | No | Subject line |
| body_text | String | No | Plain text body (or extracted from HTML) |
| received_at | DateTime | No | When sent or received |

Index on `message_id` for threading lookups. Index on `request_id` for listing emails per request.

### New config: `ImapConfig`

Stored in the encrypted vault alongside `SmtpConfig`.

```python
class ImapConfig(BaseModel):
    host: str
    port: int = 993
    username: str
    password: str
    folder: str = "INBOX"
    poll_interval_minutes: int = 5
    tls: bool = True
```

### Dashboard counter

New field in the dashboard stats response: `unread_replies: int` — count of `ACKNOWLEDGED` requests where `reply_read_at IS NULL`. Tracked via a new nullable `reply_read_at: DateTime` column on `Request`. Set when the user opens the request detail page for a request that has inbound emails.

## Reply Matching

When a new email arrives in the monitored IMAP folder, match it to an existing request using three strategies in priority order:

### Tier 1: Message-ID Threading (highest confidence)

Check the email's `In-Reply-To` and `References` headers against stored outbound `message_id` values in the `Request` table. This is standard RFC 2822 email threading and the most reliable method.

**Auto-transitions:** Yes.

### Tier 2: Subject Line Reference Code (high confidence)

Outgoing emails include a reference code in the subject: `[REF-{short_id}]` where `short_id` is the first 8 characters of the request ID, uppercased.

When checking inbound mail, scan the subject for `[REF-XXXXXXXX]` pattern. Validate that the sender's domain matches a known broker domain from the broker registry.

**Auto-transitions:** Yes (with domain validation).

### Tier 3: Sender Domain Match (low confidence)

If the sender's email domain matches a broker we have an active (SENT or OVERDUE) request with, flag the email as a potential match.

**Auto-transitions:** No. Stored as unmatched for user review.

### Outgoing Email Changes

When sending a request email via SMTP:

1. Generate a Message-ID: `<{request_id}@incognito.local>`
2. Set the `Message-ID` header on the outgoing `EmailMessage`
3. Embed `[REF-{short_id}]` in the subject line (append after existing subject)
4. Store the `message_id` on the `Request` record
5. Create an `EmailMessage` record with `direction=outbound`

## Background Poller

### Lifecycle

An `asyncio.Task` started via FastAPI's lifespan event. Only starts if IMAP is configured. If IMAP config is added/removed at runtime via the settings API, the poller starts/stops accordingly.

### Polling Loop

```
loop:
    connect to IMAP server (TLS)
    fetch unseen messages from configured folder
    for each message:
        try matching (tier 1 → 2 → 3)
        if matched (tier 1 or 2):
            store EmailMessage(direction=inbound)
            transition request to ACKNOWLEDGED
            log RequestEvent
        elif domain-matched (tier 3):
            store EmailMessage(direction=inbound, request_id=best_guess)
            log RequestEvent with low-confidence flag
        else:
            ignore (not related to any request)
    disconnect
    sleep(poll_interval_minutes)
```

### Design Decisions

- **Short-lived connections:** Connect, fetch, disconnect on each poll cycle. Avoids IMAP IDLE complexity and connection management. Works reliably with all providers including Proton Bridge.
- **`imap_tools` library:** Handles MIME parsing, multipart messages, character encoding, quoted-printable/base64 decoding. Python stdlib `imaplib` would require implementing all of this manually.
- **Mark-as-seen behavior:** Matched emails are marked as seen in IMAP. Unmatched emails are left unseen. This prevents re-processing on subsequent polls without affecting emails unrelated to Incognito.
- **Error handling:** Connection failures logged and retried on next poll cycle. No crash-on-error — the poller is resilient.
- **Proton Bridge compatibility:** Proton Bridge exposes standard IMAP on localhost. The poller's short-lived TLS connections work with Bridge's self-signed certificates (configurable TLS verification).

## Auto-Transitions

When a reply is matched to a request with high confidence (tier 1 or 2):

| Current Status | Action | New Status |
|---------------|--------|------------|
| SENT | Reply detected | ACKNOWLEDGED |
| OVERDUE | Reply detected (late response) | ACKNOWLEDGED |
| ESCALATED | Reply detected (post-escalation) | ACKNOWLEDGED |
| ACKNOWLEDGED | Additional reply | No transition (store email, log event) |
| COMPLETED | Reply | No transition (store email, log event) |
| REFUSED | Reply | No transition (store email, log event) |

On transition to ACKNOWLEDGED:
- Set `response_at` to the email's received timestamp
- Set `response_body` to the email's plain text body
- Create a `RequestEvent` with `event_type="response_detected"` and details including the matching tier and email subject

## Settings UI & API

### API Endpoints

```
GET  /api/settings/imap          → ImapConfig (password masked) or 404
POST /api/settings/imap          → Save ImapConfig, start/restart poller
DELETE /api/settings/imap        → Remove config, stop poller
POST /api/settings/imap/test     → Test connection: connect, list folders, return folder list
GET  /api/imap/status            → { enabled, last_check, next_check, matched_count, unmatched_count }
```

### Settings Page

New "IMAP Monitoring" section below the existing SMTP section:
- Host, port, username, password fields (same pattern as SMTP)
- Folder selector (populated after successful test connection)
- Poll interval dropdown (1, 2, 5, 10, 15 minutes)
- TLS toggle
- Test Connection button
- Status indicator (last check time, next check, error state)

## Dashboard Integration

### Unread Reply Badge

A notification badge on the dashboard showing the count of new, unviewed replies. Clicking navigates to a filtered request list showing only requests with unread replies.

### Request Detail Page

The existing request detail page gains an "Emails" section showing all linked `EmailMessage` records in chronological order:
- Outbound emails (what we sent) — shown with a "sent" indicator
- Inbound emails (broker replies) — shown with a "received" indicator
- Each email shows: from, to, subject, timestamp, body (expandable)

### Activity Log

IMAP events appear in the dashboard activity feed:
- "Reply detected from {broker_name}" with timestamp
- "IMAP connection error: {error}" (if polling fails)

## New Dependency

```toml
# pyproject.toml — add to core dependencies
"imap-tools>=1.8.0"
```

`imap_tools` is a well-maintained library (1.1k GitHub stars, latest release 2024) that wraps `imaplib` with a clean API for fetching, filtering, and parsing emails. It handles MIME, encoding, multipart, and attachments transparently.

## Migration

One Alembic migration:
- Add `message_id` column to `requests` table (nullable String)
- Add `reply_read_at` column to `requests` table (nullable DateTime)
- Create `email_messages` table with all columns defined above

## File Structure

```
backend/
  core/
    imap.py           # ImapPoller class, reply matching logic
  api/
    imap.py           # API routes for IMAP settings and status (new router)
  senders/
    email.py          # Modified: set Message-ID, store outbound EmailMessage
  db/
    models.py         # Modified: add message_id to Request, new EmailMessage model
frontend/src/
  pages/
    Settings.tsx       # Modified: add IMAP config section
    RequestDetail.tsx  # Modified: add email thread view
  components/
    EmailThread.tsx    # New: email thread display component
```

## Testing Strategy

### Unit Tests
- Reply matching: test all three tiers with various email header combinations
- Auto-transitions: test each status × reply scenario from the transition table
- Email parsing: test multipart, HTML-only, encoded subjects, non-Latin characters
- Poller lifecycle: test start/stop/restart on config changes

### Integration Tests
- IMAP connection with mock IMAP server (use `aiosmtpd` test fixtures pattern)
- End-to-end: send email → poll IMAP → match → transition → verify state
- Settings API: CRUD operations, test connection, poller state

### What Not to Test
- `imap_tools` internals (library handles MIME parsing)
- Actual SMTP/IMAP server behavior (that's provider testing, not unit testing)

## Out of Scope

- **Reply classification** (auto-detecting "confirmed deletion" vs "requesting more info" vs "refused"). Designed for future addition — the `EmailMessage` table stores the full body, and a classifier can be added as a post-processing step.
- **IMAP IDLE** (persistent connections for instant detection). Polling is sufficient for this use case and dramatically simpler.
- **Plus-addressing** (encoding request ID in reply-to address). Research showed data brokers frequently reply to `From:` not `Reply-To:`, and not all providers support plus-addressing. The three-tier matching strategy is more reliable.
- **Notification emails** (sending the user an email when a reply is detected). Dashboard badge is sufficient for v1.
