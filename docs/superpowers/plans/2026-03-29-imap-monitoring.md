# IMAP Reply Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically detect broker email replies via IMAP polling, completing the GDPR enforcement pipeline (send → detect reply → track deadline → escalate via DPA complaint).

**Architecture:** Background asyncio task polls IMAP inbox on a configurable interval using the `imap_tools` library. Incoming emails are matched to existing requests via Message-ID threading, subject line reference codes, or sender domain. Matched replies auto-transition requests to ACKNOWLEDGED and are displayed in the UI.

**Tech Stack:** Python `imap_tools` for IMAP access, SQLAlchemy for new models, Alembic for migration, React/TypeScript for frontend UI.

**Spec:** `docs/superpowers/specs/2026-03-29-imap-monitoring-design.md`

---

## File Structure

### New files
- `backend/core/imap.py` — IMAP poller, reply matching logic
- `backend/api/imap.py` — API routes for IMAP settings and status
- `frontend/src/components/EmailThread.tsx` — Email thread display component
- `backend/db/migrations/versions/xxxx_add_imap_monitoring.py` — Alembic migration
- `tests/unit/test_imap.py` — Unit tests for IMAP matching and poller logic
- `tests/unit/test_imap_api.py` — Integration tests for IMAP API routes

### Modified files
- `backend/db/models.py` — Add `message_id`, `reply_read_at` to Request; new `EmailMessage` model
- `backend/core/profile.py` — Add `ImapConfig` model and vault support
- `backend/senders/email.py` — Set `Message-ID` header, embed `[REF-...]` in subject
- `backend/main.py` — Register IMAP router, start/stop poller via lifespan
- `backend/api/requests.py` — Return `email_messages` in request detail, mark `reply_read_at`
- `backend/api/settings.py` — Add IMAP endpoints to existing settings router (or use new router)
- `frontend/src/api/client.ts` — Add IMAP API methods
- `frontend/src/pages/Settings.tsx` — Add IMAP configuration section
- `frontend/src/pages/RequestDetail.tsx` — Add email thread view
- `frontend/src/pages/Dashboard.tsx` — Add unread replies badge
- `pyproject.toml` — Add `imap-tools` dependency
- `tests/conftest.py` — Add `sample_imap` fixture

---

### Task 1: Add `imap-tools` dependency and `ImapConfig` model

**Files:**
- Modify: `pyproject.toml:12-22`
- Modify: `backend/core/profile.py:29-38`
- Test: `tests/unit/test_imap.py` (new)

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_imap.py
from backend.core.profile import ImapConfig


def test_imap_config_defaults():
    cfg = ImapConfig(host="imap.example.com", username="user@example.com", password="secret")
    assert cfg.port == 993
    assert cfg.folder == "INBOX"
    assert cfg.poll_interval_minutes == 5
    assert cfg.tls is True


def test_imap_config_custom():
    cfg = ImapConfig(
        host="127.0.0.1",
        port=1143,
        username="user@proton.me",
        password="bridge-password",
        folder="All Mail",
        poll_interval_minutes=10,
        tls=False,
    )
    assert cfg.port == 1143
    assert cfg.folder == "All Mail"
    assert cfg.tls is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_imap.py::test_imap_config_defaults -v`
Expected: FAIL with `ImportError: cannot import name 'ImapConfig'`

- [ ] **Step 3: Add `imap-tools` to dependencies**

In `pyproject.toml`, add `"imap-tools>=1.8.0"` to the `dependencies` list (after `"aiosmtplib>=3.0.0"`).

- [ ] **Step 4: Add `ImapConfig` to profile module**

In `backend/core/profile.py`, add after the `SmtpConfig` class:

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

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_imap.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml backend/core/profile.py tests/unit/test_imap.py
git commit -m "feat(imap): add imap-tools dependency and ImapConfig model"
```

---

### Task 2: Add IMAP to encrypted vault

**Files:**
- Modify: `backend/core/profile.py:36-109`
- Test: `tests/unit/test_imap.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_imap.py`:

```python
from backend.core.profile import ImapConfig, Profile, ProfileVault, SmtpConfig


def test_vault_roundtrip_with_imap(tmp_path):
    vault = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(full_name="Test", emails=["t@example.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="u", password="p")
    imap = ImapConfig(host="imap.test.com", username="u", password="p")

    vault.save(profile, smtp=smtp, imap=imap, password="pw")
    loaded_profile, loaded_smtp, loaded_imap = vault.load("pw")

    assert loaded_profile.full_name == "Test"
    assert loaded_smtp is not None
    assert loaded_smtp.host == "smtp.test.com"
    assert loaded_imap is not None
    assert loaded_imap.host == "imap.test.com"
    assert loaded_imap.port == 993


def test_vault_roundtrip_without_imap(tmp_path):
    vault = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(full_name="Test", emails=["t@example.com"])
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="u", password="p")

    vault.save(profile, smtp=smtp, password="pw")
    loaded_profile, loaded_smtp, loaded_imap = vault.load("pw")

    assert loaded_profile.full_name == "Test"
    assert loaded_smtp is not None
    assert loaded_imap is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_imap.py::test_vault_roundtrip_with_imap -v`
Expected: FAIL — `save()` doesn't accept `imap` param, `load()` returns 2-tuple not 3-tuple.

- [ ] **Step 3: Update `_VaultData`, `ProfileVault.save`, `ProfileVault.load`, and related methods**

In `backend/core/profile.py`, update `_VaultData`:

```python
class _VaultData(BaseModel):
    profile: Profile
    smtp: SmtpConfig | None = None
    imap: ImapConfig | None = None
```

Update `ProfileVault.save`:

```python
def save(self, profile: Profile, smtp: SmtpConfig | None = None, imap: ImapConfig | None = None, password: str = "") -> None:
    key, salt = derive_key(password, return_salt=True)
    self.save_with_key(profile, smtp, imap, key, salt)
```

Update `ProfileVault.create_initial`:

```python
def create_initial(
    self, profile: Profile, smtp: SmtpConfig | None, password: str,
    imap: ImapConfig | None = None,
) -> None:
    """Atomically create the vault. Raises FileExistsError if it already exists."""
    import os

    key, salt = derive_key(password, return_salt=True)
    vault_data = _VaultData(profile=profile, smtp=smtp, imap=imap)
    plaintext = vault_data.model_dump_json().encode("utf-8")
    payload = encrypt(plaintext, key)
    data = salt + payload.to_bytes()

    self._path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
```

Update `ProfileVault.save_with_key`:

```python
def save_with_key(
    self,
    profile: Profile,
    smtp: SmtpConfig | None,
    imap: ImapConfig | None,
    key: bytes,
    salt: bytes,
) -> None:
    import os

    vault_data = _VaultData(profile=profile, smtp=smtp, imap=imap)
    plaintext = vault_data.model_dump_json().encode("utf-8")

    payload = encrypt(plaintext, key)

    self._path.parent.mkdir(parents=True, exist_ok=True)
    self._path.write_bytes(salt + payload.to_bytes())

    os.chmod(self._path, 0o600)
```

Update `ProfileVault.load` to return 3-tuple:

```python
def load(self, password: str) -> tuple[Profile, SmtpConfig | None, ImapConfig | None]:
    key, salt = self.derive_key_from_file(password)
    return self.load_with_key(key)
```

Update `ProfileVault.load_with_key` to return 3-tuple:

```python
def load_with_key(self, key: bytes) -> tuple[Profile, SmtpConfig | None, ImapConfig | None]:
    """Load vault using a pre-derived key (avoids re-deriving from password)."""
    raw = self._path.read_bytes()
    payload = EncryptedPayload.from_bytes(raw[16:])
    plaintext = decrypt(payload, key)
    vault_data = _VaultData.model_validate_json(plaintext)
    return vault_data.profile, vault_data.smtp, vault_data.imap
```

- [ ] **Step 4: Fix all callers of vault.load/load_with_key/save_with_key**

Every call site that unpacks the vault return value needs updating from 2-tuple to 3-tuple. Search the codebase for all `vault.load`, `vault.load_with_key`, and `vault.save_with_key` calls and update them:

In `backend/main.py:107`:
```python
profile, _ = vault.load_with_key(key)
```
→
```python
profile, _, _ = vault.load_with_key(key)
```

In `backend/api/settings.py:39-40`:
```python
_, smtp = vault.load_with_key(key)
```
→
```python
_, smtp, _ = vault.load_with_key(key)
```

In `backend/api/settings.py:54`:
```python
profile, _ = vault.load_with_key(key)
vault.save_with_key(profile, body.smtp, key, salt)
```
→
```python
profile, _, imap = vault.load_with_key(key)
vault.save_with_key(profile, body.smtp, imap, key, salt)
```

In `backend/api/settings.py:60`:
```python
_, smtp = vault.load_with_key(key)
vault.save_with_key(body.profile, smtp, key, salt)
```
→
```python
_, smtp, imap = vault.load_with_key(key)
vault.save_with_key(body.profile, smtp, imap, key, salt)
```

In `backend/api/settings.py:98-99`:
```python
_, smtp = vault.load_with_key(key)
```
→
```python
_, smtp, _ = vault.load_with_key(key)
```

Search for all other callers in `backend/api/` files (auth.py, setup.py, blast.py, scan.py) and update the tuple unpacking the same way. Every `_, smtp = vault.load_with_key(key)` becomes `_, smtp, _ = vault.load_with_key(key)`. Every `profile, _ = vault.load_with_key(key)` becomes `profile, _, _ = vault.load_with_key(key)`. Every `profile, smtp = vault.load(password)` becomes `profile, smtp, _ = vault.load(password)`. Every `vault.save_with_key(profile, smtp, key, salt)` becomes `vault.save_with_key(profile, smtp, imap, key, salt)` where `imap` was loaded from the vault in the same function.

- [ ] **Step 5: Run the full test suite**

Run: `python -m pytest tests/ -v`
Expected: All 129+ tests pass (existing tests use `vault.load`/`vault.save` which now return 3-tuples — the tests in conftest.py that call `vault.save(profile, smtp, "pw")` need to still work because `imap` has a default of `None` in the new signature).

- [ ] **Step 6: Commit**

```bash
git add backend/core/profile.py backend/main.py backend/api/ tests/unit/test_imap.py
git commit -m "feat(imap): add IMAP config to encrypted vault"
```

---

### Task 3: Database models and migration

**Files:**
- Modify: `backend/db/models.py`
- Create: `backend/db/migrations/versions/xxxx_add_imap_monitoring.py`
- Test: `tests/unit/test_imap.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_imap.py`:

```python
from backend.db.models import EmailDirection, EmailMessage, Request, RequestStatus, RequestType
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from backend.db.models import Base


def test_email_message_model():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    req = Request(
        id="test-req-001",
        broker_id="example-com",
        request_type=RequestType.ERASURE,
        status=RequestStatus.SENT,
        message_id="<test-req-001@incognito.local>",
    )
    db.add(req)
    db.commit()

    email = EmailMessage(
        request_id="test-req-001",
        message_id="<reply-001@broker.com>",
        in_reply_to="<test-req-001@incognito.local>",
        direction=EmailDirection.INBOUND,
        from_address="dpo@broker.com",
        to_address="user@proton.me",
        subject="Re: Data Erasure Request [REF-TEST0001]",
        body_text="Your data has been deleted.",
    )
    db.add(email)
    db.commit()

    loaded = db.query(EmailMessage).filter_by(request_id="test-req-001").first()
    assert loaded is not None
    assert loaded.direction == EmailDirection.INBOUND
    assert loaded.from_address == "dpo@broker.com"
    assert loaded.in_reply_to == "<test-req-001@incognito.local>"

    loaded_req = db.get(Request, "test-req-001")
    assert loaded_req.message_id == "<test-req-001@incognito.local>"
    assert loaded_req.reply_read_at is None

    db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_imap.py::test_email_message_model -v`
Expected: FAIL with `ImportError: cannot import name 'EmailDirection'`

- [ ] **Step 3: Add models to `backend/db/models.py`**

Add the `EmailDirection` enum after `RequestType`:

```python
class EmailDirection(enum.StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
```

Add `message_id` and `reply_read_at` to the `Request` model (after `response_body`):

```python
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reply_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Add the `EmailMessage` model after `RequestEvent`:

```python
class EmailMessage(Base):
    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String, ForeignKey("requests.id"), nullable=False, index=True
    )
    message_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    in_reply_to: Mapped[str | None] = mapped_column(String, nullable=True)
    direction: Mapped[EmailDirection] = mapped_column(Enum(EmailDirection), nullable=False)
    from_address: Mapped[str] = mapped_column(String, nullable=False)
    to_address: Mapped[str] = mapped_column(String, nullable=False)
    subject: Mapped[str] = mapped_column(String, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_imap.py::test_email_message_model -v`
Expected: PASS

- [ ] **Step 5: Generate Alembic migration**

Run: `cd /home/malte/incognito && python -m alembic revision -m "add imap monitoring"`

Then edit the generated migration file to contain:

```python
def upgrade() -> None:
    op.add_column("requests", sa.Column("message_id", sa.String(), nullable=True))
    op.add_column("requests", sa.Column("reply_read_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "email_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("message_id", sa.String(), nullable=False),
        sa.Column("in_reply_to", sa.String(), nullable=True),
        sa.Column(
            "direction",
            sa.Enum("inbound", "outbound", name="emaildirection"),
            nullable=False,
        ),
        sa.Column("from_address", sa.String(), nullable=False),
        sa.Column("to_address", sa.String(), nullable=False),
        sa.Column("subject", sa.String(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["requests.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_messages_request_id", "email_messages", ["request_id"])
    op.create_index("ix_email_messages_message_id", "email_messages", ["message_id"])


def downgrade() -> None:
    op.drop_table("email_messages")
    op.drop_column("requests", "reply_read_at")
    op.drop_column("requests", "message_id")
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/db/models.py backend/db/migrations/versions/
git commit -m "feat(imap): add EmailMessage model and migration"
```

---

### Task 4: Modify email sender to set Message-ID and reference code

**Files:**
- Modify: `backend/senders/email.py`
- Test: `tests/unit/test_imap.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_imap.py`:

```python
from backend.senders.email import EmailSender


def test_email_sender_sets_message_id_and_ref():
    """Verify the EmailMessage object has Message-ID and [REF-...] in subject."""
    from backend.core.profile import SmtpConfig

    smtp_config = SmtpConfig(host="smtp.test.com", port=587, username="user@test.com", password="pw")
    sender = EmailSender(smtp_config)

    request_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    rendered = "Subject: Data Erasure Request pursuant to Article 17 GDPR\n\nPlease delete my data."

    msg = sender.build_message(
        to_email="dpo@broker.com",
        rendered_text=rendered,
        request_id=request_id,
    )

    assert msg["Message-ID"] == f"<{request_id}@incognito.local>"
    assert "[REF-A1B2C3D4]" in msg["Subject"]
    assert msg["To"] == "dpo@broker.com"
    assert msg["From"] == "user@test.com"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_imap.py::test_email_sender_sets_message_id_and_ref -v`
Expected: FAIL — `EmailSender` has no `build_message` method.

- [ ] **Step 3: Refactor EmailSender to extract `build_message`**

In `backend/senders/email.py`, refactor the `send` method to extract message building:

```python
class EmailSender:
    def __init__(self, smtp_config: SmtpConfig):
        self._config = smtp_config

    @staticmethod
    def _parse_rendered(text: str) -> tuple[str, str]:
        lines = text.strip().split("\n")
        if lines and lines[0].startswith("Subject:"):
            subject = lines[0][len("Subject:"):].strip()
            body = "\n".join(lines[1:]).strip()
            return subject, body
        return "GDPR Request", text.strip()

    def build_message(
        self, to_email: str, rendered_text: str, request_id: str | None = None,
    ) -> EmailMessage:
        subject, body = self._parse_rendered(rendered_text)

        if request_id:
            ref_code = request_id.split("-")[0].upper()[:8]
            subject = f"{subject} [REF-{ref_code}]"

        msg = EmailMessage()
        msg["From"] = self._config.username
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        if request_id:
            msg["Message-ID"] = f"<{request_id}@incognito.local>"

        return msg

    async def send(
        self, to_email: str, rendered_text: str, request_id: str | None = None,
    ) -> SenderResult:
        msg = self.build_message(to_email, rendered_text, request_id)

        try:
            async with SMTP(
                hostname=self._config.host,
                port=self._config.port,
                start_tls=True,
            ) as smtp:
                await smtp.login(self._config.username, self._config.password)
                await smtp.send_message(msg)

            return SenderResult(status=SenderStatus.SUCCESS, message=f"Sent to {to_email}")
        except Exception as exc:
            log.error("SMTP send to %s failed: %s", to_email, exc)
            return SenderResult(
                status=SenderStatus.FAILURE,
                message=f"Failed to send to {to_email}. Check SMTP settings.",
            )
```

- [ ] **Step 4: Update callers that pass `request_id` to `send()`**

Search for all calls to `sender.send(` in `backend/` — they are in `backend/api/blast.py` and `backend/core/scheduler.py`. Update them to pass `request_id` where available. The existing `send(to_email, rendered_text)` signature still works (request_id defaults to None), so existing callers in `backend/api/settings.py` (test-smtp) don't need changes.

In the blast/scheduler code where a request object is available, update to:
```python
result = await sender.send(broker.dpo_email, rendered, request_id=req.id)
```

Also update the request's `message_id` field and store the outbound email after sending:
```python
if result.status == SenderStatus.SUCCESS:
    req.message_id = f"<{req.id}@incognito.local>"

    # Store outbound email in EmailMessage table
    from backend.db.models import EmailDirection, EmailMessage
    outbound_record = EmailMessage(
        request_id=req.id,
        message_id=req.message_id,
        direction=EmailDirection.OUTBOUND,
        from_address=smtp.username,
        to_address=broker.dpo_email,
        subject=subject,  # from the rendered template
        body_text=rendered,
    )
    db.add(outbound_record)
    db.commit()
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/senders/email.py backend/api/blast.py backend/core/scheduler.py tests/unit/test_imap.py
git commit -m "feat(imap): set Message-ID and [REF-...] on outgoing emails"
```

---

### Task 5: IMAP reply matching logic

**Files:**
- Create: `backend/core/imap.py`
- Test: `tests/unit/test_imap.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_imap.py`:

```python
from backend.core.imap import match_reply, MatchResult, MatchTier


def test_match_by_message_id_threading():
    """Tier 1: In-Reply-To matches a stored outbound Message-ID."""
    outbound_ids = {"<req-001@incognito.local>": "req-001"}

    result = match_reply(
        in_reply_to="<req-001@incognito.local>",
        references="",
        subject="Re: Data Erasure Request [REF-REQ00001]",
        from_address="dpo@broker.com",
        outbound_message_ids=outbound_ids,
        broker_domains={"broker.com"},
    )

    assert result is not None
    assert result.request_id == "req-001"
    assert result.tier == MatchTier.MESSAGE_ID


def test_match_by_references_header():
    """Tier 1: References header contains a stored outbound Message-ID."""
    outbound_ids = {"<req-002@incognito.local>": "req-002"}

    result = match_reply(
        in_reply_to="<some-other-id@broker.com>",
        references="<some-other-id@broker.com> <req-002@incognito.local>",
        subject="Re: Something",
        from_address="dpo@broker.com",
        outbound_message_ids=outbound_ids,
        broker_domains={"broker.com"},
    )

    assert result is not None
    assert result.request_id == "req-002"
    assert result.tier == MatchTier.MESSAGE_ID


def test_match_by_subject_ref_code():
    """Tier 2: Subject contains [REF-XXXXXXXX] and sender domain matches a broker."""
    outbound_ids = {}
    ref_code_map = {"A1B2C3D4": "req-003"}

    result = match_reply(
        in_reply_to="",
        references="",
        subject="Re: Data Erasure Request [REF-A1B2C3D4]",
        from_address="privacy@databroker.eu",
        outbound_message_ids=outbound_ids,
        broker_domains={"databroker.eu"},
        ref_code_map=ref_code_map,
    )

    assert result is not None
    assert result.request_id == "req-003"
    assert result.tier == MatchTier.REFERENCE_CODE


def test_match_by_subject_ref_code_wrong_domain():
    """Tier 2: Subject matches but sender domain is not a known broker — no match."""
    ref_code_map = {"A1B2C3D4": "req-003"}

    result = match_reply(
        in_reply_to="",
        references="",
        subject="Re: Data Erasure Request [REF-A1B2C3D4]",
        from_address="random@unknown.com",
        outbound_message_ids={},
        broker_domains={"databroker.eu"},
        ref_code_map=ref_code_map,
    )

    assert result is None


def test_match_by_sender_domain():
    """Tier 3: Sender domain matches a broker with active request — low confidence."""
    domain_request_map = {"broker.com": "req-004"}

    result = match_reply(
        in_reply_to="",
        references="",
        subject="Your privacy request",
        from_address="noreply@broker.com",
        outbound_message_ids={},
        broker_domains={"broker.com"},
        domain_request_map=domain_request_map,
    )

    assert result is not None
    assert result.request_id == "req-004"
    assert result.tier == MatchTier.DOMAIN_ONLY


def test_no_match():
    """No matching strategy succeeds — returns None."""
    result = match_reply(
        in_reply_to="",
        references="",
        subject="Unrelated email",
        from_address="someone@random.com",
        outbound_message_ids={},
        broker_domains=set(),
    )

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_imap.py::test_match_by_message_id_threading -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.core.imap'`

- [ ] **Step 3: Implement the matching logic**

Create `backend/core/imap.py`:

```python
from __future__ import annotations

import enum
import logging
import re
from dataclasses import dataclass

log = logging.getLogger("incognito.imap")

_REF_PATTERN = re.compile(r"\[REF-([A-Z0-9]{8})\]")


class MatchTier(enum.StrEnum):
    MESSAGE_ID = "message_id"
    REFERENCE_CODE = "reference_code"
    DOMAIN_ONLY = "domain_only"


@dataclass(frozen=True)
class MatchResult:
    request_id: str
    tier: MatchTier


def _extract_domain(email_address: str) -> str:
    """Extract domain from an email address."""
    return email_address.rsplit("@", 1)[-1].lower()


def match_reply(
    in_reply_to: str,
    references: str,
    subject: str,
    from_address: str,
    outbound_message_ids: dict[str, str],
    broker_domains: set[str],
    ref_code_map: dict[str, str] | None = None,
    domain_request_map: dict[str, str] | None = None,
) -> MatchResult | None:
    """Match an inbound email to an existing request.

    Args:
        in_reply_to: In-Reply-To header value.
        references: References header value (space-separated Message-IDs).
        subject: Email subject line.
        from_address: Sender email address.
        outbound_message_ids: Map of outbound Message-ID -> request_id.
        broker_domains: Set of all known broker domains.
        ref_code_map: Map of 8-char reference code -> request_id.
        domain_request_map: Map of broker domain -> request_id (active requests only).

    Returns:
        MatchResult if matched, None otherwise.
    """
    # Tier 1: Message-ID threading
    if in_reply_to and in_reply_to.strip() in outbound_message_ids:
        return MatchResult(
            request_id=outbound_message_ids[in_reply_to.strip()],
            tier=MatchTier.MESSAGE_ID,
        )

    if references:
        for ref_id in references.split():
            ref_id = ref_id.strip()
            if ref_id in outbound_message_ids:
                return MatchResult(
                    request_id=outbound_message_ids[ref_id],
                    tier=MatchTier.MESSAGE_ID,
                )

    # Tier 2: Subject reference code + domain validation
    if ref_code_map:
        match = _REF_PATTERN.search(subject)
        if match:
            code = match.group(1)
            if code in ref_code_map:
                sender_domain = _extract_domain(from_address)
                if sender_domain in broker_domains:
                    return MatchResult(
                        request_id=ref_code_map[code],
                        tier=MatchTier.REFERENCE_CODE,
                    )

    # Tier 3: Sender domain match (low confidence)
    if domain_request_map:
        sender_domain = _extract_domain(from_address)
        if sender_domain in domain_request_map:
            return MatchResult(
                request_id=domain_request_map[sender_domain],
                tier=MatchTier.DOMAIN_ONLY,
            )

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_imap.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/core/imap.py tests/unit/test_imap.py
git commit -m "feat(imap): reply matching logic with 3-tier strategy"
```

---

### Task 6: IMAP poller background task

**Files:**
- Modify: `backend/core/imap.py`
- Test: `tests/unit/test_imap.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_imap.py`:

```python
import asyncio
from unittest.mock import MagicMock, patch
from datetime import datetime, UTC

from backend.core.imap import ImapPoller
from backend.core.profile import ImapConfig
from backend.db.models import Base, Request, RequestStatus, RequestType, EmailMessage, EmailDirection, RequestEvent
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _make_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def test_poller_processes_matched_reply():
    """Poller stores email and transitions request to ACKNOWLEDGED."""
    db_factory = _make_db()
    db = db_factory()

    req = Request(
        id="req-poll-001",
        broker_id="broker-com",
        request_type=RequestType.ERASURE,
        status=RequestStatus.SENT,
        message_id="<req-poll-001@incognito.local>",
        sent_at=datetime.now(UTC),
        deadline_at=datetime.now(UTC),
    )
    db.add(req)
    db.commit()

    broker_domains = {"broker.com"}
    imap_config = ImapConfig(host="localhost", username="u", password="p")

    poller = ImapPoller(
        imap_config=imap_config,
        db_session_factory=db_factory,
        broker_domains=broker_domains,
    )

    # Simulate a fetched email
    mock_msg = MagicMock()
    mock_msg.headers = {
        "in-reply-to": ("<req-poll-001@incognito.local>",),
        "references": ("",),
    }
    mock_msg.subject = "Re: Data Erasure Request [REF-REQPOLL0]"
    mock_msg.from_ = "dpo@broker.com"
    mock_msg.to = ("user@proton.me",)
    mock_msg.text = "Your data has been deleted."
    mock_msg.date = datetime.now(UTC)
    mock_msg.uid = "123"

    poller.process_message(mock_msg)

    db2 = db_factory()
    updated_req = db2.get(Request, "req-poll-001")
    assert updated_req.status == RequestStatus.ACKNOWLEDGED
    assert updated_req.response_at is not None
    assert "deleted" in updated_req.response_body

    emails = db2.query(EmailMessage).filter_by(request_id="req-poll-001").all()
    assert len(emails) == 1
    assert emails[0].direction == EmailDirection.INBOUND

    events = db2.query(RequestEvent).filter_by(request_id="req-poll-001").all()
    response_events = [e for e in events if e.event_type == "response_detected"]
    assert len(response_events) == 1

    db.close()
    db2.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_imap.py::test_poller_processes_matched_reply -v`
Expected: FAIL — `ImportError: cannot import name 'ImapPoller'`

- [ ] **Step 3: Implement `ImapPoller`**

Add to `backend/core/imap.py`:

```python
import asyncio
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker

from backend.core.profile import ImapConfig
from backend.db.models import (
    EmailDirection,
    EmailMessage,
    Request,
    RequestEvent,
    RequestStatus,
)


class ImapPoller:
    def __init__(
        self,
        imap_config: ImapConfig,
        db_session_factory: sessionmaker,
        broker_domains: set[str],
    ):
        self._config = imap_config
        self._db_factory = db_session_factory
        self._broker_domains = broker_domains
        self._running = False
        self._task: asyncio.Task | None = None
        self.last_check: datetime | None = None
        self.matched_count = 0
        self.unmatched_count = 0

    def _build_lookup_maps(self, db: Session):
        """Build lookup maps from active requests."""
        active_statuses = {RequestStatus.SENT, RequestStatus.OVERDUE, RequestStatus.ESCALATED}
        requests = (
            db.query(Request)
            .filter(Request.status.in_(active_statuses))
            .all()
        )

        outbound_ids: dict[str, str] = {}
        ref_code_map: dict[str, str] = {}
        domain_request_map: dict[str, str] = {}

        for req in requests:
            if req.message_id:
                outbound_ids[req.message_id] = req.id
            ref_code = req.id.split("-")[0].upper()[:8]
            ref_code_map[ref_code] = req.id
            domain_request_map[req.broker_id.replace("-", ".")] = req.id

        return outbound_ids, ref_code_map, domain_request_map

    def process_message(self, msg) -> MatchResult | None:
        """Process a single IMAP message. Used by poll loop and tests."""
        db = self._db_factory()
        try:
            outbound_ids, ref_code_map, domain_request_map = self._build_lookup_maps(db)

            in_reply_to = ""
            references = ""
            if hasattr(msg, "headers"):
                in_reply_to_vals = msg.headers.get("in-reply-to", ("",))
                in_reply_to = in_reply_to_vals[0] if in_reply_to_vals else ""
                ref_vals = msg.headers.get("references", ("",))
                references = ref_vals[0] if ref_vals else ""

            from_addr = msg.from_ if isinstance(msg.from_, str) else str(msg.from_)
            to_addr = msg.to[0] if isinstance(msg.to, (list, tuple)) and msg.to else str(msg.to)

            result = match_reply(
                in_reply_to=in_reply_to,
                references=references,
                subject=msg.subject or "",
                from_address=from_addr,
                outbound_message_ids=outbound_ids,
                broker_domains=self._broker_domains,
                ref_code_map=ref_code_map,
                domain_request_map=domain_request_map,
            )

            if result is None:
                self.unmatched_count += 1
                return None

            # Store the email
            body_text = msg.text or ""
            email_record = EmailMessage(
                request_id=result.request_id,
                message_id=in_reply_to or f"<unknown-{msg.uid}@imap>",
                in_reply_to=in_reply_to or None,
                direction=EmailDirection.INBOUND,
                from_address=from_addr,
                to_address=to_addr,
                subject=msg.subject or "",
                body_text=body_text,
                received_at=msg.date if msg.date else datetime.now(UTC),
            )
            db.add(email_record)

            # Auto-transition for high-confidence matches
            if result.tier in (MatchTier.MESSAGE_ID, MatchTier.REFERENCE_CODE):
                req = db.get(Request, result.request_id)
                if req and req.status in (
                    RequestStatus.SENT,
                    RequestStatus.OVERDUE,
                    RequestStatus.ESCALATED,
                ):
                    req.status = RequestStatus.ACKNOWLEDGED
                    req.response_at = datetime.now(UTC)
                    req.response_body = body_text[:2000] if body_text else ""
                    req.updated_at = datetime.now(UTC)

                    event = RequestEvent(
                        request_id=result.request_id,
                        event_type="response_detected",
                        details=f"Reply detected via {result.tier.value} from {from_addr}",
                    )
                    db.add(event)

            self.matched_count += 1
            db.commit()
            return result
        finally:
            db.close()

    async def poll_once(self) -> int:
        """Connect to IMAP, fetch unseen messages, process them. Returns count processed."""
        from imap_tools import MailBox, AND

        processed = 0
        try:
            with MailBox(
                host=self._config.host,
                port=self._config.port,
                ssl=self._config.tls,
            ).login(self._config.username, self._config.password, self._config.folder) as mailbox:
                for msg in mailbox.fetch(AND(seen=False), mark_seen=False):
                    result = self.process_message(msg)
                    if result is not None:
                        mailbox.seen(msg, True)
                    processed += 1
        except Exception as exc:
            log.error("IMAP poll failed: %s", exc)

        self.last_check = datetime.now(UTC)
        return processed

    async def _run_loop(self):
        """Main polling loop."""
        self._running = True
        log.info("IMAP poller started (interval=%dm, folder=%s)",
                 self._config.poll_interval_minutes, self._config.folder)
        while self._running:
            await self.poll_once()
            await asyncio.sleep(self._config.poll_interval_minutes * 60)

    def start(self):
        """Start the polling loop as a background task."""
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_loop())

    def stop(self):
        """Stop the polling loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_imap.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/core/imap.py tests/unit/test_imap.py
git commit -m "feat(imap): ImapPoller with background polling loop"
```

---

### Task 7: Wire poller into FastAPI lifespan

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add lifespan context manager to `backend/main.py`**

Add imports at the top:

```python
from contextlib import asynccontextmanager
from backend.core.imap import ImapPoller
```

Add a lifespan function before `create_app`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start IMAP poller if configured
    poller = getattr(app.state, "imap_poller", None)
    if poller:
        poller.start()
    yield
    # Stop IMAP poller on shutdown
    if poller:
        poller.stop()
```

In `create_app`, pass `lifespan=lifespan` to the `FastAPI()` constructor:

```python
app = FastAPI(title="Incognito", version="0.1.0", docs_url=None, redoc_url=None, lifespan=lifespan)
```

After `broker_registry` is created and before the router registrations, add:

```python
# Initialize IMAP poller (started in lifespan if IMAP is configured)
app.state.imap_poller = None
broker_domain_set = {b.domain.lower() for b in broker_registry.brokers}
app.state.broker_domains = broker_domain_set
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass (poller is None by default, so lifespan is a no-op)

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat(imap): wire poller into FastAPI lifespan"
```

---

### Task 8: IMAP settings API

**Files:**
- Modify: `backend/api/settings.py`
- Test: `tests/unit/test_imap_api.py` (new)
- Modify: `tests/conftest.py`

- [ ] **Step 1: Add `sample_imap` fixture to conftest**

In `tests/conftest.py`, add:

```python
from backend.core.profile import ImapConfig

@pytest.fixture
def sample_imap():
    """A standard test IMAP config."""
    return ImapConfig(
        host="imap.test.com",
        port=993,
        username="test@test.com",
        password="test_password",
    )
```

- [ ] **Step 2: Write failing test**

Create `tests/unit/test_imap_api.py`:

```python
import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import ProfileVault, ImapConfig
from backend.main import create_app


@pytest.fixture
def client(config, seeded_vault):
    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})
    return client


def test_get_imap_not_configured(client):
    res = client.get("/api/settings/imap")
    assert res.status_code == 200
    assert res.json()["configured"] is False


def test_save_and_get_imap(client):
    res = client.post("/api/settings/imap", json={
        "imap": {
            "host": "imap.proton.me",
            "port": 993,
            "username": "user@proton.me",
            "password": "bridge-pw",
        }
    })
    assert res.status_code == 200

    res = client.get("/api/settings/imap")
    assert res.status_code == 200
    data = res.json()
    assert data["configured"] is True
    assert data["host"] == "imap.proton.me"
    assert "password" not in data


def test_delete_imap(client):
    # First save
    client.post("/api/settings/imap", json={
        "imap": {
            "host": "imap.proton.me",
            "port": 993,
            "username": "user@proton.me",
            "password": "bridge-pw",
        }
    })
    # Then delete
    res = client.delete("/api/settings/imap")
    assert res.status_code == 200

    res = client.get("/api/settings/imap")
    assert res.json()["configured"] is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_imap_api.py -v`
Expected: FAIL — 404 on `/api/settings/imap`

- [ ] **Step 4: Add IMAP endpoints to settings router**

In `backend/api/settings.py`, add after the `UpdateSmtpRequest` class:

```python
class UpdateImapRequest(BaseModel):
    imap: ImapConfig
```

Add the import at the top:

```python
from backend.core.profile import Profile, ProfileVault, SmtpConfig, ImapConfig
```

Add these endpoints inside the `create_settings_router` function, after the SMTP endpoints:

```python
@r.get("/imap")
def get_imap_status(session: str | None = Cookie(default=None)):
    key, _salt = session_store.validate(session)
    _, _, imap = vault.load_with_key(key)
    if imap is None:
        return {"configured": False}
    return {
        "configured": True,
        "host": imap.host,
        "port": imap.port,
        "username": imap.username,
        "folder": imap.folder,
        "poll_interval_minutes": imap.poll_interval_minutes,
        "tls": imap.tls,
    }

@r.post("/imap")
def update_imap(body: UpdateImapRequest, request: FastAPIRequest, session: str | None = Cookie(default=None)):
    key, salt = session_store.validate(session)
    profile, smtp, _ = vault.load_with_key(key)
    vault.save_with_key(profile, smtp, body.imap, key, salt)

    # Restart poller with new config
    from backend.core.imap import ImapPoller
    old_poller = getattr(request.app.state, "imap_poller", None)
    if old_poller:
        old_poller.stop()
    broker_domains = getattr(request.app.state, "broker_domains", set())
    poller = ImapPoller(
        imap_config=body.imap,
        db_session_factory=request.app.state.db_session_factory,
        broker_domains=broker_domains,
    )
    poller.start()
    request.app.state.imap_poller = poller
    return {"status": "updated"}

@r.delete("/imap")
def delete_imap(request: FastAPIRequest, session: str | None = Cookie(default=None)):
    key, salt = session_store.validate(session)
    profile, smtp, _ = vault.load_with_key(key)
    vault.save_with_key(profile, smtp, None, key, salt)

    # Stop poller
    old_poller = getattr(request.app.state, "imap_poller", None)
    if old_poller:
        old_poller.stop()
    request.app.state.imap_poller = None
    return {"status": "deleted"}
```

Note: Add `from fastapi import Request as FastAPIRequest` to the imports at the top of `create_settings_router`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_imap_api.py -v`
Expected: 3 passed

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/api/settings.py tests/unit/test_imap_api.py tests/conftest.py
git commit -m "feat(imap): IMAP settings API (get/save/delete)"
```

---

### Task 9: IMAP test-connection and status endpoints

**Files:**
- Modify: `backend/api/settings.py`
- Test: `tests/unit/test_imap_api.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_imap_api.py`:

```python
def test_imap_status_not_configured(client):
    res = client.get("/api/imap/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is False


def test_test_imap_not_configured(client):
    res = client.post("/api/settings/imap/test")
    assert res.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_imap_api.py::test_imap_status_not_configured -v`
Expected: FAIL — 404

- [ ] **Step 3: Add test-connection and status endpoints**

In `backend/api/settings.py`, add to the router:

```python
@r.post("/imap/test")
def test_imap(session: str | None = Cookie(default=None)):
    key, _salt = session_store.validate(session)
    _, _, imap = vault.load_with_key(key)
    if imap is None:
        raise HTTPException(status_code=400, detail="IMAP not configured")

    try:
        from imap_tools import MailBox
        with MailBox(host=imap.host, port=imap.port, ssl=imap.tls).login(
            imap.username, imap.password, imap.folder
        ) as mailbox:
            folders = [f.name for f in mailbox.folder.list()]
        return {"status": "success", "folders": folders}
    except Exception as exc:
        log.error("IMAP test failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="IMAP connection failed. Check your server, port, and credentials.",
        ) from None
```

Add a separate status endpoint. This can go on the same settings router using the `/imap/status` path:

```python
@r.get("/imap/status")
def imap_status(session: str | None = Cookie(default=None)):
    session_store.validate(session)
    from fastapi import Request as FastAPIRequest
    # Access the poller from app state — need to access via the settings router's state
    # This requires passing app state or the poller reference into the router
    # For now, return basic status based on whether IMAP is configured
    key, _salt = session_store.validate(session)
    _, _, imap = vault.load_with_key(key)
    return {
        "enabled": imap is not None,
        "poll_interval_minutes": imap.poll_interval_minutes if imap else None,
    }
```

Note: The full poller status (last_check, matched_count, etc.) requires passing the poller instance into the router. Update the `create_settings_router` function signature to accept an optional poller reference, or access it via `app.state` using the request object. The simplest approach — update the endpoint to accept a `request` parameter:

```python
from fastapi import Request as FastAPIRequest

@r.get("/imap/status")
def imap_status(request: FastAPIRequest, session: str | None = Cookie(default=None)):
    session_store.validate(session)
    poller = getattr(request.app.state, "imap_poller", None)
    key, _salt = session_store.validate(session)
    _, _, imap = vault.load_with_key(key)
    return {
        "enabled": imap is not None,
        "last_check": poller.last_check.isoformat() if poller and poller.last_check else None,
        "matched_count": poller.matched_count if poller else 0,
        "unmatched_count": poller.unmatched_count if poller else 0,
        "poll_interval_minutes": imap.poll_interval_minutes if imap else None,
    }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_imap_api.py -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/api/settings.py tests/unit/test_imap_api.py
git commit -m "feat(imap): test-connection and status API endpoints"
```

---

### Task 10: Request detail API — include emails and mark read

**Files:**
- Modify: `backend/api/requests.py`
- Test: `tests/unit/test_imap_api.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_imap_api.py`:

```python
def test_request_detail_includes_emails(client):
    """Request detail should include email_messages list."""
    # Create a request
    res = client.post("/api/requests", json={"broker_id": "broker0-com", "request_type": "erasure"})
    req_id = res.json()["id"]

    # Fetch detail
    res = client.get(f"/api/requests/{req_id}")
    assert res.status_code == 200
    data = res.json()
    assert "email_messages" in data
    assert data["email_messages"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_imap_api.py::test_request_detail_includes_emails -v`
Expected: FAIL — `email_messages` not in response

- [ ] **Step 3: Update request detail endpoint**

In `backend/api/requests.py`, add import:

```python
from backend.db.models import Request, RequestEvent, RequestStatus, RequestType, EmailMessage
```

In the `get_request` endpoint (the `@r.get("/{request_id}")` handler), add after building the `result` dict:

```python
# Include email messages
emails = (
    db.query(EmailMessage)
    .filter_by(request_id=request_id)
    .order_by(EmailMessage.received_at)
    .all()
)
result["email_messages"] = [
    {
        "id": e.id,
        "direction": e.direction.value,
        "from_address": e.from_address,
        "to_address": e.to_address,
        "subject": e.subject,
        "body_text": e.body_text,
        "received_at": e.received_at.isoformat() if e.received_at else None,
    }
    for e in emails
]

# Mark replies as read
if emails and req.reply_read_at is None:
    has_inbound = any(e.direction.value == "inbound" for e in emails)
    if has_inbound:
        req.reply_read_at = datetime.now(UTC)
        db.commit()
```

Add the datetime import at the top:

```python
from datetime import UTC, datetime
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/unit/test_imap_api.py -v`
Expected: All pass

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/api/requests.py tests/unit/test_imap_api.py
git commit -m "feat(imap): include emails in request detail, mark as read"
```

---

### Task 11: Unread replies count in stats

**Files:**
- Modify: `backend/api/requests.py`
- Test: `tests/unit/test_imap_api.py`

- [ ] **Step 1: Write failing test**

Append to `tests/unit/test_imap_api.py`:

```python
def test_stats_include_unread_replies(client):
    res = client.get("/api/requests/stats")
    assert res.status_code == 200
    data = res.json()
    assert "unread_replies" in data
    assert data["unread_replies"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_imap_api.py::test_stats_include_unread_replies -v`
Expected: FAIL — `unread_replies` not in response

- [ ] **Step 3: Add unread count to stats endpoint**

In `backend/api/requests.py`, in the `stats` endpoint, add after `counts["broker_count"]`:

```python
counts["unread_replies"] = (
    db.query(Request)
    .filter(
        Request.status == RequestStatus.ACKNOWLEDGED,
        Request.response_at.isnot(None),
        Request.reply_read_at.is_(None),
    )
    .count()
)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add backend/api/requests.py tests/unit/test_imap_api.py
git commit -m "feat(imap): unread replies count in dashboard stats"
```

---

### Task 12: Frontend — IMAP settings section

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add IMAP API methods to client**

In `frontend/src/api/client.ts`, add to the `api` object:

```typescript
getImapStatus: () => request<{ configured: boolean; host?: string; port?: number; username?: string; folder?: string; poll_interval_minutes?: number; tls?: boolean }>("/settings/imap"),
saveImap: (imap: { host: string; port: number; username: string; password: string; folder?: string; poll_interval_minutes?: number; tls?: boolean }) =>
  request("/settings/imap", { method: "POST", body: JSON.stringify({ imap }) }),
deleteImap: () => request("/settings/imap", { method: "DELETE" }),
testImap: () => request<{ status: string; folders: string[] }>("/settings/imap/test", { method: "POST" }),
getImapPollerStatus: () => request<{ enabled: boolean; last_check: string | null; matched_count: number; unmatched_count: number; poll_interval_minutes: number | null }>("/imap/status"),
```

- [ ] **Step 2: Add IMAP section to Settings page**

In `frontend/src/pages/Settings.tsx`, add the `Inbox` icon to the lucide imports:

```typescript
import { Mail, User, Info, CheckCircle, Loader2, ShieldAlert, Download, Upload, Inbox } from "lucide-react";
```

Add IMAP state variables after the SMTP state:

```typescript
// IMAP state
const [imapStatus, setImapStatus] = useState<{ configured: boolean; host?: string; port?: number; username?: string; folder?: string; poll_interval_minutes?: number; tls?: boolean } | null>(null);
const [imapForm, setImapForm] = useState({ host: "", port: 993, username: "", password: "", folder: "INBOX", poll_interval_minutes: 5, tls: true });
const [showImapForm, setShowImapForm] = useState(false);
const [imapSaving, setImapSaving] = useState(false);
const [imapTesting, setImapTesting] = useState(false);
const [imapMessage, setImapMessage] = useState({ type: "", text: "" });
```

Add `api.getImapStatus()` to the `loadData` Promise.all call, and set it:

```typescript
const [smtp, info, prof, hibp, imap] = await Promise.all([
  settingsRequest<SmtpStatus>("/settings/smtp"),
  settingsRequest<AppInfo>("/settings/info"),
  api.getProfile(),
  api.getHibpStatus(),
  api.getImapStatus(),
]);
// ...existing setters...
setImapStatus(imap);
if (imap.configured) {
  setImapForm({ host: imap.host || "", port: imap.port || 993, username: imap.username || "", password: "", folder: imap.folder || "INBOX", poll_interval_minutes: imap.poll_interval_minutes || 5, tls: imap.tls ?? true });
}
```

Add IMAP handler functions:

```typescript
async function handleSaveImap() {
  setImapSaving(true);
  setImapMessage({ type: "", text: "" });
  try {
    await api.saveImap(imapForm);
    setImapMessage({ type: "success", text: "IMAP settings saved." });
    setShowImapForm(false);
    loadData();
  } catch (e) {
    setImapMessage({ type: "error", text: e instanceof Error ? e.message : "Failed to save" });
  } finally {
    setImapSaving(false);
  }
}

async function handleTestImap() {
  setImapTesting(true);
  setImapMessage({ type: "", text: "" });
  try {
    const result = await api.testImap();
    setImapMessage({ type: "success", text: `Connected. Folders: ${result.folders.join(", ")}` });
  } catch (e) {
    setImapMessage({ type: "error", text: e instanceof Error ? e.message : "Test failed" });
  } finally {
    setImapTesting(false);
  }
}

async function handleDeleteImap() {
  setImapSaving(true);
  setImapMessage({ type: "", text: "" });
  try {
    await api.deleteImap();
    setImapMessage({ type: "success", text: "IMAP monitoring disabled." });
    loadData();
  } catch (e) {
    setImapMessage({ type: "error", text: e instanceof Error ? e.message : "Failed to delete" });
  } finally {
    setImapSaving(false);
  }
}
```

Add the IMAP settings card JSX after the SMTP card (before the HIBP card). Follow the exact same pattern as the SMTP card but with IMAP fields: host, port, username, password, folder (text input), poll interval (select with options 1/2/5/10/15), TLS toggle (checkbox), test connection button, and a "Remove" button when configured.

- [ ] **Step 3: Build frontend**

Run: `cd /home/malte/incognito/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/Settings.tsx
git commit -m "feat(imap): IMAP settings UI section"
```

---

### Task 13: Frontend — email thread in request detail

**Files:**
- Create: `frontend/src/components/EmailThread.tsx`
- Modify: `frontend/src/pages/RequestDetail.tsx`

- [ ] **Step 1: Create `EmailThread` component**

Create `frontend/src/components/EmailThread.tsx`:

```tsx
import { Mail, ArrowUpRight, ArrowDownLeft } from "lucide-react";

interface EmailItem {
  id: number;
  direction: "inbound" | "outbound";
  from_address: string;
  to_address: string;
  subject: string;
  body_text: string;
  received_at: string | null;
}

export default function EmailThread({ emails }: { emails: EmailItem[] }) {
  if (emails.length === 0) return null;

  return (
    <div className="space-y-3">
      {emails.map((email) => (
        <div
          key={email.id}
          className={`rounded-lg border p-4 ${
            email.direction === "outbound"
              ? "border-blue-200 bg-blue-50"
              : "border-green-200 bg-green-50"
          }`}
        >
          <div className="flex items-center gap-2 mb-2">
            {email.direction === "outbound" ? (
              <ArrowUpRight className="w-3.5 h-3.5 text-blue-500" />
            ) : (
              <ArrowDownLeft className="w-3.5 h-3.5 text-green-500" />
            )}
            <span className="text-xs font-medium text-gray-700">
              {email.direction === "outbound" ? "Sent" : "Received"}
            </span>
            <span className="text-xs text-gray-400">
              {email.received_at ? new Date(email.received_at).toLocaleString() : ""}
            </span>
          </div>
          <div className="text-xs text-gray-500 space-y-0.5 mb-2">
            <p>From: {email.from_address}</p>
            <p>To: {email.to_address}</p>
            <p>Subject: {email.subject}</p>
          </div>
          <pre className="text-sm whitespace-pre-wrap text-gray-800 max-h-40 overflow-y-auto">
            {email.body_text}
          </pre>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Add email thread to RequestDetail page**

In `frontend/src/pages/RequestDetail.tsx`, add import:

```typescript
import EmailThread from "../components/EmailThread";
```

Add the `email_messages` field to the `RequestDetail` interface:

```typescript
email_messages?: Array<{
  id: number;
  direction: "inbound" | "outbound";
  from_address: string;
  to_address: string;
  subject: string;
  body_text: string;
  received_at: string | null;
}>;
```

Add the email thread section in the JSX, between the Actions card and the DPA Complaint card:

```tsx
{/* Email Thread */}
{request.email_messages && request.email_messages.length > 0 && (
  <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6 mb-6">
    <div className="flex items-center gap-2 mb-4">
      <Mail className="w-4 h-4 text-gray-500" />
      <h2 className="font-semibold">Emails ({request.email_messages.length})</h2>
    </div>
    <EmailThread emails={request.email_messages} />
  </div>
)}
```

- [ ] **Step 3: Build frontend**

Run: `cd /home/malte/incognito/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/EmailThread.tsx frontend/src/pages/RequestDetail.tsx
git commit -m "feat(imap): email thread view in request detail page"
```

---

### Task 14: Frontend — unread replies badge on dashboard

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add unread badge to dashboard**

In `frontend/src/pages/Dashboard.tsx`, add `Mail` to the lucide imports:

```typescript
import { Send, Clock, Zap, Shield, Loader2, Search, Mail } from "lucide-react";
```

Add `unread_replies` to the `Stats` interface:

```typescript
unread_replies: number;
```

In the hero metrics grid (the `grid grid-cols-2 sm:grid-cols-4` div), add a new metric after "Needs attention" and replace "Brokers contacted" row, or add as a conditional 5th item. The simplest approach — show it conditionally in the "Deadline monitoring" section:

Add a new notification banner after the hero metric, before the deadline monitoring section:

```tsx
{stats.unread_replies > 0 && (
  <div
    className="bg-green-50 border border-green-200 rounded-xl px-5 py-4 mb-6 flex items-center justify-between cursor-pointer hover:bg-green-100 transition"
    onClick={() => navigate("/requests?status=acknowledged")}
  >
    <div className="flex items-center gap-3">
      <div className="p-2 bg-green-100 rounded-lg">
        <Mail className="w-5 h-5 text-green-600" />
      </div>
      <div>
        <p className="font-medium text-green-900">
          {stats.unread_replies} new {stats.unread_replies === 1 ? "reply" : "replies"} from brokers
        </p>
        <p className="text-green-700 text-sm">Click to review broker responses</p>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 2: Build frontend**

Run: `cd /home/malte/incognito/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(imap): unread replies notification badge on dashboard"
```

---

### Task 15: Final integration test and cleanup

**Files:**
- Test: `tests/unit/test_imap.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Run linter**

Run: `ruff check .`
Expected: No errors

- [ ] **Step 3: Update test count in CLAUDE.md**

Update the test count in `CLAUDE.md` to reflect the new test count.

- [ ] **Step 4: Build frontend**

Run: `cd /home/malte/incognito/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 5: Final commit**

```bash
git add CLAUDE.md frontend/dist/
git commit -m "docs: update test count, rebuild frontend"
```
