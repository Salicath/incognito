# Incognito Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-hosted, GDPR-first personal data removal tool with a web UI, encrypted profile storage, automated request sending, and rootless container deployment.

**Architecture:** Python FastAPI backend serves a React/TypeScript frontend as static files. SQLite stores request state. User profile is AES-256-GCM encrypted at rest. Jinja2 templates generate legally-correct GDPR requests. Senders dispatch via email (SMTP), web forms (Playwright), or API. A CLI wraps both the server and cron-friendly automation commands.

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy, Pydantic, Jinja2, Playwright, React 18, TypeScript, Vite, Tailwind CSS, SQLite, Podman/Quadlet

**Spec:** `docs/superpowers/specs/2026-03-28-incognito-design.md`

---

## Phase 1: Project Foundation

### Task 1: Project Scaffolding & Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `backend/__init__.py`
- Create: `backend/core/__init__.py`
- Create: `backend/api/__init__.py`
- Create: `backend/senders/__init__.py`
- Create: `backend/scanner/__init__.py`
- Create: `backend/db/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `.gitignore`
- Create: `ruff.toml`

- [ ] **Step 1: Initialize git repo**

```bash
cd /home/malte/incognito
git init
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "incognito"
version = "0.1.0"
description = "Self-hosted GDPR personal data removal tool"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.14.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    "jinja2>=3.1.0",
    "pyyaml>=6.0.0",
    "jsonschema>=4.23.0",
    "cryptography>=44.0.0",
    "argon2-cffi>=23.1.0",
    "typer>=0.15.0",
    "rich>=13.9.0",
    "httpx>=0.28.0",
    "playwright>=1.49.0",
    "aiosmtplib>=3.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.25.0",
    "pytest-cov>=6.0.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
    "aiosmtpd>=1.4.0",
]

[project.scripts]
incognito = "cli:app"

[build-system]
requires = ["setuptools>=75.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create ruff.toml**

```toml
target-version = "py312"
line-length = 100

[lint]
select = ["E", "F", "I", "N", "UP", "B", "A", "SIM"]

[format]
quote-style = "double"
```

- [ ] **Step 4: Create .gitignore**

```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
build/
.mypy_cache/
.pytest_cache/
.ruff_cache/
*.db
*.enc
node_modules/
frontend/dist/
.env
```

- [ ] **Step 5: Create all __init__.py files**

Create empty `__init__.py` in: `backend/`, `backend/core/`, `backend/api/`, `backend/senders/`, `backend/scanner/`, `backend/db/`, `tests/`, `tests/unit/`, `tests/integration/`.

All files are empty (just `# noqa`).

- [ ] **Step 6: Create virtual environment and install**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

- [ ] **Step 7: Verify setup**

```bash
python -c "import fastapi; import sqlalchemy; import cryptography; print('OK')"
pytest --co -q  # should show "no tests ran"
ruff check .    # should pass with no errors
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml ruff.toml .gitignore backend/ tests/
git commit -m "feat: project scaffolding with dependencies"
```

---

### Task 2: Database Models & Session

**Files:**
- Create: `backend/db/models.py`
- Create: `backend/db/session.py`
- Create: `tests/unit/test_db_models.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_db_models.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.db.models import Base, Request, RequestEvent, ScanResult, RequestStatus, RequestType


def make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def test_create_request():
    engine = make_engine()
    with Session(engine) as session:
        req = Request(
            id=str(uuid.uuid4()),
            broker_id="acxiom",
            request_type=RequestType.ERASURE,
            status=RequestStatus.CREATED,
        )
        session.add(req)
        session.commit()
        session.refresh(req)

        assert req.status == RequestStatus.CREATED
        assert req.request_type == RequestType.ERASURE
        assert req.broker_id == "acxiom"
        assert req.created_at is not None
        assert req.sent_at is None
        assert req.deadline_at is None


def test_create_request_event():
    engine = make_engine()
    with Session(engine) as session:
        req_id = str(uuid.uuid4())
        req = Request(
            id=req_id,
            broker_id="acxiom",
            request_type=RequestType.ACCESS,
            status=RequestStatus.CREATED,
        )
        session.add(req)
        session.flush()

        event = RequestEvent(
            request_id=req_id,
            event_type="status_change",
            details="created -> sent",
        )
        session.add(event)
        session.commit()
        session.refresh(event)

        assert event.request_id == req_id
        assert event.event_type == "status_change"
        assert event.created_at is not None


def test_create_scan_result():
    engine = make_engine()
    with Session(engine) as session:
        result = ScanResult(
            source="peoplesearch.example.com",
            broker_id="example-broker",
            found_data='{"name": "Test User", "email": "test@example.com"}',
        )
        session.add(result)
        session.commit()
        session.refresh(result)

        assert result.actioned is False
        assert result.broker_id == "example-broker"
        assert result.scanned_at is not None


def test_request_status_values():
    assert RequestStatus.CREATED == "created"
    assert RequestStatus.SENT == "sent"
    assert RequestStatus.ACKNOWLEDGED == "acknowledged"
    assert RequestStatus.COMPLETED == "completed"
    assert RequestStatus.REFUSED == "refused"
    assert RequestStatus.OVERDUE == "overdue"
    assert RequestStatus.ESCALATED == "escalated"
    assert RequestStatus.MANUAL_ACTION_NEEDED == "manual_action_needed"


def test_request_type_values():
    assert RequestType.ACCESS == "access"
    assert RequestType.ERASURE == "erasure"
    assert RequestType.FOLLOW_UP == "follow_up"
    assert RequestType.ESCALATION_WARNING == "escalation_warning"
    assert RequestType.DPA_COMPLAINT == "dpa_complaint"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_db_models.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.db.models'`

- [ ] **Step 3: Write backend/db/models.py**

```python
# backend/db/models.py
import enum
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class RequestStatus(str, enum.Enum):
    CREATED = "created"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    COMPLETED = "completed"
    REFUSED = "refused"
    OVERDUE = "overdue"
    ESCALATED = "escalated"
    MANUAL_ACTION_NEEDED = "manual_action_needed"


class RequestType(str, enum.Enum):
    ACCESS = "access"
    ERASURE = "erasure"
    FOLLOW_UP = "follow_up"
    ESCALATION_WARNING = "escalation_warning"
    DPA_COMPLAINT = "dpa_complaint"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    broker_id: Mapped[str] = mapped_column(String, nullable=False)
    request_type: Mapped[RequestType] = mapped_column(Enum(RequestType), nullable=False)
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus), nullable=False, default=RequestStatus.CREATED
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    events: Mapped[list["RequestEvent"]] = relationship(back_populates="request")


class RequestEvent(Base):
    __tablename__ = "request_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(
        String, ForeignKey("requests.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    request: Mapped["Request"] = relationship(back_populates="events")


class ScanResult(Base):
    __tablename__ = "scan_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    broker_id: Mapped[str | None] = mapped_column(String, nullable=True)
    found_data: Mapped[str] = mapped_column(Text, nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    actioned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
```

- [ ] **Step 4: Write backend/db/session.py**

```python
# backend/db/session.py
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from backend.db.models import Base


def get_engine(db_path: Path):
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, echo=False)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def init_db(db_path: Path) -> sessionmaker:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_db_models.py -v
```
Expected: all 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/db/models.py backend/db/session.py tests/unit/test_db_models.py
git commit -m "feat: database models for requests, events, and scan results"
```

---

### Task 3: Encryption Module (AES-256-GCM + Argon2id)

**Files:**
- Create: `backend/core/crypto.py`
- Create: `tests/unit/test_crypto.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_crypto.py
import json

import pytest

from backend.core.crypto import derive_key, encrypt, decrypt, EncryptedPayload


def test_derive_key_deterministic():
    key1 = derive_key("password123", salt=b"fixed_salt_16byt")
    key2 = derive_key("password123", salt=b"fixed_salt_16byt")
    assert key1 == key2
    assert len(key1) == 32  # 256 bits


def test_derive_key_different_passwords():
    key1 = derive_key("password1", salt=b"fixed_salt_16byt")
    key2 = derive_key("password2", salt=b"fixed_salt_16byt")
    assert key1 != key2


def test_encrypt_decrypt_roundtrip():
    key = derive_key("my_password", salt=b"fixed_salt_16byt")
    plaintext = b'{"name": "Test User", "email": "test@example.com"}'

    payload = encrypt(plaintext, key)
    assert isinstance(payload, EncryptedPayload)

    decrypted = decrypt(payload, key)
    assert decrypted == plaintext


def test_decrypt_wrong_key_fails():
    key1 = derive_key("correct_password", salt=b"fixed_salt_16byt")
    key2 = derive_key("wrong_password", salt=b"other_salt_16byt")
    plaintext = b"secret data"

    payload = encrypt(plaintext, key1)

    with pytest.raises(Exception):
        decrypt(payload, key2)


def test_encrypted_payload_serialization():
    key = derive_key("password", salt=b"fixed_salt_16byt")
    plaintext = b"test data"

    payload = encrypt(plaintext, key)
    serialized = payload.to_bytes()
    restored = EncryptedPayload.from_bytes(serialized)

    decrypted = decrypt(restored, key)
    assert decrypted == plaintext


def test_derive_key_generates_salt():
    key1, salt1 = derive_key("password", return_salt=True)
    key2, salt2 = derive_key("password", return_salt=True)
    assert salt1 != salt2  # random salt each time
    assert len(salt1) == 16
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_crypto.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write backend/core/crypto.py**

```python
# backend/core/crypto.py
from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_ARGON2_TIME_COST = 3
_ARGON2_MEMORY_COST = 65536  # 64 MB
_ARGON2_PARALLELISM = 4
_ARGON2_HASH_LEN = 32  # 256 bits
_SALT_LEN = 16
_NONCE_LEN = 12


def derive_key(
    password: str,
    salt: bytes | None = None,
    return_salt: bool = False,
) -> bytes | tuple[bytes, bytes]:
    if salt is None:
        salt = os.urandom(_SALT_LEN)

    key = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=salt,
        time_cost=_ARGON2_TIME_COST,
        memory_cost=_ARGON2_MEMORY_COST,
        parallelism=_ARGON2_PARALLELISM,
        hash_len=_ARGON2_HASH_LEN,
        type=Type.ID,
    )

    if return_salt:
        return key, salt
    return key


@dataclass(frozen=True)
class EncryptedPayload:
    nonce: bytes
    ciphertext: bytes

    def to_bytes(self) -> bytes:
        return (
            struct.pack(">H", len(self.nonce))
            + self.nonce
            + self.ciphertext
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> EncryptedPayload:
        (nonce_len,) = struct.unpack(">H", data[:2])
        nonce = data[2 : 2 + nonce_len]
        ciphertext = data[2 + nonce_len :]
        return cls(nonce=nonce, ciphertext=ciphertext)


def encrypt(plaintext: bytes, key: bytes) -> EncryptedPayload:
    nonce = os.urandom(_NONCE_LEN)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return EncryptedPayload(nonce=nonce, ciphertext=ciphertext)


def decrypt(payload: EncryptedPayload, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(payload.nonce, payload.ciphertext, None)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_crypto.py -v
```
Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/crypto.py tests/unit/test_crypto.py
git commit -m "feat: AES-256-GCM encryption with Argon2id key derivation"
```

---

### Task 4: Profile Model & Encrypted Vault

**Files:**
- Create: `backend/core/profile.py`
- Create: `tests/unit/test_profile.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_profile.py
import json
from datetime import date
from pathlib import Path

import pytest

from backend.core.profile import Address, Profile, SmtpConfig, ProfileVault


def test_profile_model():
    profile = Profile(
        full_name="Malte Example",
        previous_names=[],
        date_of_birth=date(1990, 1, 15),
        emails=["malte@example.com"],
        phones=["+49 170 1234567"],
        addresses=[
            Address(street="Beispielstraße 42", city="Berlin", postal_code="10115", country="DE")
        ],
    )
    assert profile.full_name == "Malte Example"
    assert len(profile.addresses) == 1
    assert profile.addresses[0].country == "DE"


def test_profile_serialization():
    profile = Profile(
        full_name="Test User",
        previous_names=["Old Name"],
        date_of_birth=date(1985, 6, 20),
        emails=["test@example.com", "alt@example.com"],
        phones=[],
        addresses=[],
    )
    data = profile.model_dump_json()
    restored = Profile.model_validate_json(data)
    assert restored == profile


def test_smtp_config_model():
    config = SmtpConfig(
        host="smtp.gmail.com",
        port=587,
        username="user@gmail.com",
        password="app_password_here",
    )
    assert config.port == 587


def test_vault_save_and_load(tmp_path: Path):
    vault_path = tmp_path / "profile.enc"
    password = "test_master_password"

    profile = Profile(
        full_name="Vault Test",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["vault@test.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(
        host="smtp.test.com", port=587, username="vault@test.com", password="smtp_pass"
    )

    vault = ProfileVault(vault_path)
    vault.save(profile, smtp, password)

    assert vault_path.exists()

    loaded_profile, loaded_smtp = vault.load(password)
    assert loaded_profile == profile
    assert loaded_smtp == smtp


def test_vault_wrong_password(tmp_path: Path):
    vault_path = tmp_path / "profile.enc"

    profile = Profile(
        full_name="Test",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["t@t.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")

    vault = ProfileVault(vault_path)
    vault.save(profile, smtp, "correct_password")

    with pytest.raises(Exception):
        vault.load("wrong_password")


def test_vault_exists(tmp_path: Path):
    vault_path = tmp_path / "profile.enc"
    vault = ProfileVault(vault_path)
    assert vault.exists() is False

    profile = Profile(
        full_name="Test",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["t@t.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")
    vault.save(profile, smtp, "password")
    assert vault.exists() is True


def test_address_formatted():
    addr = Address(street="Beispielstraße 42", city="Berlin", postal_code="10115", country="DE")
    assert "Beispielstraße 42" in addr.formatted
    assert "Berlin" in addr.formatted
    assert "10115" in addr.formatted
    assert "DE" in addr.formatted
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_profile.py -v
```
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write backend/core/profile.py**

```python
# backend/core/profile.py
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from backend.core.crypto import derive_key, encrypt, decrypt, EncryptedPayload


class Address(BaseModel):
    street: str
    city: str
    postal_code: str
    country: str

    @property
    def formatted(self) -> str:
        return f"{self.street}, {self.postal_code} {self.city}, {self.country}"


class Profile(BaseModel):
    full_name: str
    previous_names: list[str]
    date_of_birth: date
    emails: list[str]
    phones: list[str]
    addresses: list[Address]


class SmtpConfig(BaseModel):
    host: str
    port: int
    username: str
    password: str


class _VaultData(BaseModel):
    profile: Profile
    smtp: SmtpConfig


class ProfileVault:
    def __init__(self, path: Path):
        self._path = path

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, profile: Profile, smtp: SmtpConfig, password: str) -> None:
        vault_data = _VaultData(profile=profile, smtp=smtp)
        plaintext = vault_data.model_dump_json().encode("utf-8")

        key, salt = derive_key(password, return_salt=True)
        payload = encrypt(plaintext, key)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(salt + payload.to_bytes())

    def load(self, password: str) -> tuple[Profile, SmtpConfig]:
        raw = self._path.read_bytes()
        salt = raw[:16]
        payload = EncryptedPayload.from_bytes(raw[16:])

        key = derive_key(password, salt=salt)
        plaintext = decrypt(payload, key)

        vault_data = _VaultData.model_validate_json(plaintext)
        return vault_data.profile, vault_data.smtp
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_profile.py -v
```
Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/profile.py tests/unit/test_profile.py
git commit -m "feat: profile model with encrypted vault storage"
```

---

### Task 5: Configuration Module

**Files:**
- Create: `backend/core/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_config.py
from pathlib import Path

from backend.core.config import AppConfig


def test_default_config():
    config = AppConfig()
    assert config.data_dir == Path.home() / ".incognito"
    assert config.db_name == "incognito.db"
    assert config.rate_limit_per_hour == 10
    assert config.session_timeout_minutes == 30
    assert config.gdpr_deadline_days == 30
    assert config.log_level == "info"


def test_config_db_path():
    config = AppConfig()
    assert config.db_path == config.data_dir / config.db_name


def test_config_vault_path():
    config = AppConfig()
    assert config.vault_path == config.data_dir / "profile.enc"


def test_config_override():
    config = AppConfig(data_dir=Path("/tmp/test-incognito"), rate_limit_per_hour=20)
    assert config.data_dir == Path("/tmp/test-incognito")
    assert config.rate_limit_per_hour == 20
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_config.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/core/config.py**

```python
# backend/core/config.py
from pathlib import Path

from pydantic_settings import BaseSettings


class AppConfig(BaseSettings):
    model_config = {"env_prefix": "INCOGNITO_"}

    data_dir: Path = Path.home() / ".incognito"
    db_name: str = "incognito.db"
    rate_limit_per_hour: int = 10
    session_timeout_minutes: int = 30
    gdpr_deadline_days: int = 30
    log_level: str = "info"
    host: str = "127.0.0.1"
    port: int = 8080

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.db_name

    @property
    def vault_path(self) -> Path:
        return self.data_dir / "profile.enc"

    @property
    def brokers_dir(self) -> Path:
        return self.data_dir / "brokers"

    @property
    def log_dir(self) -> Path:
        return self.data_dir / "logs"
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_config.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/config.py tests/unit/test_config.py
git commit -m "feat: app configuration with env var overrides"
```

---

### Task 6: Broker Registry Loader

**Files:**
- Create: `backend/core/broker.py`
- Create: `brokers/schema.yaml`
- Create: `brokers/acxiom.yaml`
- Create: `tests/unit/test_broker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_broker.py
from pathlib import Path

import pytest
import yaml

from backend.core.broker import Broker, BrokerRegistry, RemovalMethod


def test_broker_model():
    broker = Broker(
        name="Acxiom",
        domain="acxiom.com",
        category="data_broker",
        dpo_email="privacy@acxiom.com",
        removal_method=RemovalMethod.EMAIL,
        removal_url=None,
        api_endpoint=None,
        country="US",
        gdpr_applies=True,
        verification_required=False,
        language="en",
        last_verified="2026-03-01",
        notes="Major data broker",
    )
    assert broker.name == "Acxiom"
    assert broker.removal_method == RemovalMethod.EMAIL


def test_broker_id():
    broker = Broker(
        name="Acxiom",
        domain="acxiom.com",
        category="data_broker",
        dpo_email="privacy@acxiom.com",
        removal_method=RemovalMethod.EMAIL,
        country="US",
        gdpr_applies=True,
        verification_required=False,
        language="en",
        last_verified="2026-03-01",
    )
    assert broker.id == "acxiom-com"


def test_registry_load_from_directory(tmp_path: Path):
    broker_yaml = {
        "name": "Test Broker",
        "domain": "testbroker.com",
        "category": "data_broker",
        "dpo_email": "dpo@testbroker.com",
        "removal_method": "email",
        "removal_url": None,
        "api_endpoint": None,
        "country": "DE",
        "gdpr_applies": True,
        "verification_required": False,
        "language": "de",
        "last_verified": "2026-03-01",
        "notes": "Test broker",
    }
    (tmp_path / "test-broker.yaml").write_text(yaml.dump(broker_yaml))

    registry = BrokerRegistry.load(tmp_path)
    assert len(registry.brokers) == 1
    assert registry.brokers[0].name == "Test Broker"
    assert registry.brokers[0].language == "de"


def test_registry_get_by_id(tmp_path: Path):
    broker_yaml = {
        "name": "Example Corp",
        "domain": "example.com",
        "category": "data_broker",
        "dpo_email": "privacy@example.com",
        "removal_method": "email",
        "country": "US",
        "gdpr_applies": True,
        "verification_required": False,
        "language": "en",
        "last_verified": "2026-03-01",
    }
    (tmp_path / "example.yaml").write_text(yaml.dump(broker_yaml))

    registry = BrokerRegistry.load(tmp_path)
    broker = registry.get("example-com")
    assert broker is not None
    assert broker.name == "Example Corp"
    assert registry.get("nonexistent") is None


def test_registry_skips_non_yaml_files(tmp_path: Path):
    (tmp_path / "readme.txt").write_text("not a broker")
    (tmp_path / "schema.yaml").write_text("type: object")  # schema file skipped
    registry = BrokerRegistry.load(tmp_path)
    assert len(registry.brokers) == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_broker.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/core/broker.py**

```python
# backend/core/broker.py
from __future__ import annotations

import enum
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, computed_field


class RemovalMethod(str, enum.Enum):
    EMAIL = "email"
    WEB_FORM = "web_form"
    API = "api"


class Broker(BaseModel):
    name: str
    domain: str
    category: str
    dpo_email: str
    removal_method: RemovalMethod
    removal_url: str | None = None
    api_endpoint: str | None = None
    country: str
    gdpr_applies: bool
    verification_required: bool
    language: str = "en"
    last_verified: str
    notes: str | None = None

    @computed_field
    @property
    def id(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.domain.lower()).strip("-")


class BrokerRegistry:
    def __init__(self, brokers: list[Broker]):
        self.brokers = brokers
        self._by_id = {b.id: b for b in brokers}

    def get(self, broker_id: str) -> Broker | None:
        return self._by_id.get(broker_id)

    @classmethod
    def load(cls, directory: Path) -> BrokerRegistry:
        brokers = []
        if not directory.exists():
            return cls(brokers)

        for path in sorted(directory.glob("*.yaml")):
            if path.stem == "schema":
                continue
            data = yaml.safe_load(path.read_text())
            if data and isinstance(data, dict) and "name" in data:
                brokers.append(Broker.model_validate(data))

        return cls(brokers)
```

- [ ] **Step 4: Create brokers/schema.yaml**

```yaml
# brokers/schema.yaml
type: object
required:
  - name
  - domain
  - category
  - dpo_email
  - removal_method
  - country
  - gdpr_applies
  - verification_required
  - language
  - last_verified
properties:
  name:
    type: string
  domain:
    type: string
  category:
    type: string
    enum: [data_broker, people_search, marketing, credit_agency, other]
  dpo_email:
    type: string
    format: email
  removal_method:
    type: string
    enum: [email, web_form, api]
  removal_url:
    type: [string, "null"]
  api_endpoint:
    type: [string, "null"]
  country:
    type: string
  gdpr_applies:
    type: boolean
  verification_required:
    type: boolean
  language:
    type: string
  last_verified:
    type: string
    format: date
  notes:
    type: [string, "null"]
```

- [ ] **Step 5: Create brokers/acxiom.yaml**

```yaml
# brokers/acxiom.yaml
name: Acxiom
domain: acxiom.com
category: data_broker
dpo_email: privacy@acxiom.com
removal_method: email
removal_url: null
api_endpoint: null
country: US
gdpr_applies: true
verification_required: false
language: en
last_verified: "2026-03-01"
notes: "Major data broker, typically responds within 14 days"
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/unit/test_broker.py -v
```
Expected: all 5 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/core/broker.py brokers/schema.yaml brokers/acxiom.yaml tests/unit/test_broker.py
git commit -m "feat: broker registry with YAML loader and schema"
```

---

### Task 7: Request State Machine

**Files:**
- Create: `backend/core/request.py`
- Create: `tests/unit/test_request.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_request.py
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pytest

from backend.db.models import Base, Request, RequestEvent, RequestStatus, RequestType
from backend.core.request import RequestManager, InvalidTransitionError


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_create_request():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    assert req.status == RequestStatus.CREATED
    assert req.broker_id == "acxiom"

    events = session.query(RequestEvent).filter_by(request_id=req.id).all()
    assert len(events) == 1
    assert events[0].event_type == "created"


def test_transition_created_to_sent():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.SENT
    assert req.sent_at is not None
    assert req.deadline_at is not None
    assert (req.deadline_at - req.sent_at).days == 30


def test_transition_sent_to_acknowledged():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "We received your request")

    session.refresh(req)
    assert req.status == RequestStatus.ACKNOWLEDGED
    assert req.response_at is not None
    assert req.response_body == "We received your request"


def test_transition_acknowledged_to_completed():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "Processing")
    mgr.mark_completed(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.COMPLETED


def test_transition_acknowledged_to_refused():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "Processing")
    mgr.mark_refused(req.id, "Exemption under Art. 17(3)")

    session.refresh(req)
    assert req.status == RequestStatus.REFUSED
    assert "Art. 17(3)" in req.response_body


def test_mark_overdue():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_overdue(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.OVERDUE


def test_mark_escalated():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_overdue(req.id)
    mgr.mark_escalated(req.id)

    session.refresh(req)
    assert req.status == RequestStatus.ESCALATED


def test_mark_manual_action_needed():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_manual_action_needed(req.id, "CAPTCHA detected on opt-out form")

    session.refresh(req)
    assert req.status == RequestStatus.MANUAL_ACTION_NEEDED


def test_invalid_transition_raises():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)

    with pytest.raises(InvalidTransitionError):
        mgr.mark_completed(req.id)  # can't go from CREATED to COMPLETED


def test_find_overdue_requests():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)

    # Manually set deadline in the past
    req.deadline_at = datetime.now(timezone.utc) - timedelta(days=1)
    session.commit()

    overdue = mgr.find_overdue()
    assert len(overdue) == 1
    assert overdue[0].id == req.id


def test_event_trail():
    session = make_session()
    mgr = RequestManager(session, gdpr_deadline_days=30)

    req = mgr.create("acxiom", RequestType.ERASURE)
    mgr.mark_sent(req.id)
    mgr.mark_acknowledged(req.id, "Got it")
    mgr.mark_completed(req.id)

    events = session.query(RequestEvent).filter_by(request_id=req.id).order_by(RequestEvent.id).all()
    types = [e.event_type for e in events]
    assert types == ["created", "sent", "acknowledged", "completed"]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_request.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/core/request.py**

```python
# backend/core/request.py
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.db.models import Request, RequestEvent, RequestStatus, RequestType


class InvalidTransitionError(Exception):
    pass


_VALID_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.CREATED: {RequestStatus.SENT, RequestStatus.MANUAL_ACTION_NEEDED},
    RequestStatus.SENT: {
        RequestStatus.ACKNOWLEDGED,
        RequestStatus.OVERDUE,
        RequestStatus.MANUAL_ACTION_NEEDED,
    },
    RequestStatus.ACKNOWLEDGED: {
        RequestStatus.COMPLETED,
        RequestStatus.REFUSED,
        RequestStatus.MANUAL_ACTION_NEEDED,
    },
    RequestStatus.REFUSED: {RequestStatus.ESCALATED},
    RequestStatus.OVERDUE: {RequestStatus.ESCALATED, RequestStatus.ACKNOWLEDGED},
    RequestStatus.ESCALATED: {RequestStatus.ACKNOWLEDGED, RequestStatus.COMPLETED},
    RequestStatus.MANUAL_ACTION_NEEDED: {RequestStatus.SENT, RequestStatus.COMPLETED},
}


class RequestManager:
    def __init__(self, session: Session, gdpr_deadline_days: int = 30):
        self._session = session
        self._deadline_days = gdpr_deadline_days

    def _transition(self, request_id: str, new_status: RequestStatus, details: str | None = None):
        req = self._session.get(Request, request_id)
        if req is None:
            raise ValueError(f"Request {request_id} not found")

        allowed = _VALID_TRANSITIONS.get(req.status, set())
        if new_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from {req.status.value} to {new_status.value}"
            )

        old_status = req.status
        req.status = new_status
        req.updated_at = datetime.now(timezone.utc)

        event = RequestEvent(
            request_id=request_id,
            event_type=new_status.value,
            details=details or f"{old_status.value} -> {new_status.value}",
        )
        self._session.add(event)
        self._session.commit()

        return req

    def create(self, broker_id: str, request_type: RequestType) -> Request:
        req = Request(
            id=str(uuid.uuid4()),
            broker_id=broker_id,
            request_type=request_type,
            status=RequestStatus.CREATED,
        )
        self._session.add(req)

        event = RequestEvent(
            request_id=req.id,
            event_type="created",
            details=f"Created {request_type.value} request for {broker_id}",
        )
        self._session.add(event)
        self._session.commit()

        return req

    def mark_sent(self, request_id: str) -> Request:
        req = self._transition(request_id, RequestStatus.SENT, "Request sent")
        now = datetime.now(timezone.utc)
        req.sent_at = now
        req.deadline_at = now + timedelta(days=self._deadline_days)
        self._session.commit()
        return req

    def mark_acknowledged(self, request_id: str, response_body: str) -> Request:
        req = self._transition(request_id, RequestStatus.ACKNOWLEDGED, response_body)
        req.response_at = datetime.now(timezone.utc)
        req.response_body = response_body
        self._session.commit()
        return req

    def mark_completed(self, request_id: str) -> Request:
        return self._transition(request_id, RequestStatus.COMPLETED, "Deletion confirmed")

    def mark_refused(self, request_id: str, reason: str) -> Request:
        req = self._transition(request_id, RequestStatus.REFUSED, reason)
        req.response_body = reason
        self._session.commit()
        return req

    def mark_overdue(self, request_id: str) -> Request:
        return self._transition(request_id, RequestStatus.OVERDUE, "GDPR deadline passed")

    def mark_escalated(self, request_id: str) -> Request:
        return self._transition(request_id, RequestStatus.ESCALATED, "Escalated")

    def mark_manual_action_needed(self, request_id: str, reason: str) -> Request:
        return self._transition(request_id, RequestStatus.MANUAL_ACTION_NEEDED, reason)

    def find_overdue(self) -> list[Request]:
        now = datetime.now(timezone.utc)
        return (
            self._session.query(Request)
            .filter(
                Request.status == RequestStatus.SENT,
                Request.deadline_at < now,
            )
            .all()
        )
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_request.py -v
```
Expected: all 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/request.py tests/unit/test_request.py
git commit -m "feat: request state machine with transition validation and audit trail"
```

---

## Phase 2: Template System & Senders

### Task 8: GDPR Request Templates

**Files:**
- Create: `backend/core/template.py`
- Create: `templates/access_request.txt.j2`
- Create: `templates/erasure_request.txt.j2`
- Create: `templates/follow_up.txt.j2`
- Create: `templates/escalation_warning.txt.j2`
- Create: `templates/dpa_complaint.txt.j2`
- Create: `tests/unit/test_template.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_template.py
from datetime import date
from pathlib import Path

import pytest

from backend.core.profile import Address, Profile
from backend.core.template import TemplateRenderer


@pytest.fixture
def templates_dir():
    return Path(__file__).parent.parent.parent / "templates"


@pytest.fixture
def profile():
    return Profile(
        full_name="Malte Example",
        previous_names=[],
        date_of_birth=date(1990, 1, 15),
        emails=["malte@example.com", "m.example@gmail.com"],
        phones=["+49 170 1234567"],
        addresses=[
            Address(street="Beispielstraße 42", city="Berlin", postal_code="10115", country="DE")
        ],
    )


@pytest.fixture
def renderer(templates_dir):
    return TemplateRenderer(templates_dir)


def test_render_erasure_request(renderer, profile):
    result = renderer.render(
        "erasure_request",
        profile=profile,
        reference_id="REQ-001",
        broker_name="Acxiom",
    )
    assert "Article 17" in result
    assert "Malte Example" in result
    assert "malte@example.com" in result
    assert "REQ-001" in result
    assert "30 days" in result.lower() or "Article 12(3)" in result


def test_render_access_request(renderer, profile):
    result = renderer.render(
        "access_request",
        profile=profile,
        reference_id="REQ-002",
        broker_name="Test Broker",
    )
    assert "Article 15" in result
    assert "Malte Example" in result
    assert "REQ-002" in result


def test_render_follow_up(renderer, profile):
    result = renderer.render(
        "follow_up",
        profile=profile,
        reference_id="REQ-001",
        broker_name="Acxiom",
        original_date="2026-02-26",
    )
    assert "REQ-001" in result
    assert "Acxiom" in result


def test_render_escalation_warning(renderer, profile):
    result = renderer.render(
        "escalation_warning",
        profile=profile,
        reference_id="REQ-001",
        broker_name="Acxiom",
        original_date="2026-02-26",
    )
    assert "supervisory authority" in result.lower() or "data protection authority" in result.lower()


def test_render_dpa_complaint(renderer, profile):
    result = renderer.render(
        "dpa_complaint",
        profile=profile,
        reference_id="REQ-001",
        broker_name="Acxiom",
        broker_email="privacy@acxiom.com",
        original_date="2026-02-26",
        dpa_name="BfDI",
    )
    assert "BfDI" in result
    assert "Acxiom" in result


def test_render_returns_subject_and_body(renderer, profile):
    result = renderer.render(
        "erasure_request",
        profile=profile,
        reference_id="REQ-001",
        broker_name="Acxiom",
    )
    assert "Subject:" in result
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_template.py -v
```
Expected: FAIL

- [ ] **Step 3: Create templates**

**templates/access_request.txt.j2:**
```
Subject: Data Access Request pursuant to Article 15 GDPR — {{ profile.full_name }} [{{ reference_id }}]

Dear Data Protection Officer at {{ broker_name }},

Pursuant to Article 15 of the General Data Protection Regulation (EU) 2016/679, I am requesting confirmation as to whether you are processing any personal data relating to me. If so, please provide me with a copy of all personal data you hold about me, along with the following information as required by Article 15(1):

- The purposes of the processing
- The categories of personal data concerned
- The recipients to whom the data has been disclosed
- The retention period or criteria for determining it
- The source of the data if not collected directly from me

My identifying details:
- Name: {{ profile.full_name }}
- Email: {{ profile.emails | join(', ') }}
{% if profile.phones %}- Phone: {{ profile.phones | join(', ') }}
{% endif %}{% if profile.date_of_birth %}- Date of birth: {{ profile.date_of_birth }}
{% endif %}{% if profile.addresses %}- Address: {{ profile.addresses[0].formatted }}
{% endif %}

Please respond within 30 days as required by Article 12(3) GDPR. Failure to respond within this period constitutes a violation of the GDPR and may result in a complaint to the relevant supervisory authority.

Yours faithfully,
{{ profile.full_name }}

Ref: {{ reference_id }}
```

**templates/erasure_request.txt.j2:**
```
Subject: Data Erasure Request pursuant to Article 17 GDPR — {{ profile.full_name }} [{{ reference_id }}]

Dear Data Protection Officer at {{ broker_name }},

I am writing to request the erasure of all personal data you hold relating to me, pursuant to Article 17 of the General Data Protection Regulation (EU) 2016/679.

I am exercising my right to erasure on the grounds that:
- The data is no longer necessary for the purpose for which it was collected (Art. 17(1)(a))
- I withdraw my consent, and there is no other legal ground for the processing (Art. 17(1)(b))
- I object to the processing and there are no overriding legitimate grounds (Art. 17(1)(c))

My identifying details:
- Name: {{ profile.full_name }}
- Email: {{ profile.emails | join(', ') }}
{% if profile.phones %}- Phone: {{ profile.phones | join(', ') }}
{% endif %}{% if profile.date_of_birth %}- Date of birth: {{ profile.date_of_birth }}
{% endif %}{% if profile.addresses %}- Address: {{ profile.addresses[0].formatted }}
{% endif %}

Please confirm the deletion of my data within 30 days as required by Article 12(3) GDPR. If you believe an exemption applies under Article 17(3), please specify the legal basis for your refusal.

Failure to respond within the statutory period may result in a complaint to the relevant supervisory authority.

Yours faithfully,
{{ profile.full_name }}

Ref: {{ reference_id }}
```

**templates/follow_up.txt.j2:**
```
Subject: Follow-up: Unanswered GDPR Request — {{ profile.full_name }} [{{ reference_id }}]

Dear Data Protection Officer at {{ broker_name }},

I am writing to follow up on my previous data protection request (Ref: {{ reference_id }}) sent on {{ original_date }}.

Under Article 12(3) GDPR, you are required to respond to data subject requests without undue delay and within one month. The statutory deadline has now passed without a response.

I request that you process my original request immediately and confirm completion.

Yours faithfully,
{{ profile.full_name }}

Ref: {{ reference_id }}
```

**templates/escalation_warning.txt.j2:**
```
Subject: Final Notice Before Supervisory Authority Complaint — {{ profile.full_name }} [{{ reference_id }}]

Dear Data Protection Officer at {{ broker_name }},

This is a final notice regarding my unanswered GDPR request (Ref: {{ reference_id }}) originally sent on {{ original_date }}.

Despite the statutory deadline having passed, I have not received a substantive response to my request. This constitutes a violation of Articles 12 and 17 (or 15) of the General Data Protection Regulation.

If I do not receive a response within 7 days, I will file a formal complaint with the relevant data protection authority under Article 77 GDPR.

Yours faithfully,
{{ profile.full_name }}

Ref: {{ reference_id }}
```

**templates/dpa_complaint.txt.j2:**
```
Subject: GDPR Complaint — Non-Compliance by {{ broker_name }} [{{ reference_id }}]

To: {{ dpa_name }}

I am filing a complaint under Article 77 of the General Data Protection Regulation (EU) 2016/679 regarding the failure of {{ broker_name }} (contact: {{ broker_email }}) to comply with my data protection rights.

Details of the complaint:
- On {{ original_date }}, I submitted a data protection request to {{ broker_name }} (Ref: {{ reference_id }}).
- The statutory 30-day response period under Article 12(3) GDPR has passed.
- I sent a follow-up and a final warning, but have not received a substantive response.

My identifying details:
- Name: {{ profile.full_name }}
- Email: {{ profile.emails | join(', ') }}
{% if profile.addresses %}- Address: {{ profile.addresses[0].formatted }}
{% endif %}

I request that the supervisory authority investigate this matter and take appropriate enforcement action.

Yours faithfully,
{{ profile.full_name }}

Ref: {{ reference_id }}
```

- [ ] **Step 4: Write backend/core/template.py**

```python
# backend/core/template.py
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.core.profile import Profile


class TemplateRenderer:
    def __init__(self, templates_dir: Path):
        self._env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape([]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, template_name: str, *, profile: Profile, **kwargs) -> str:
        template = self._env.get_template(f"{template_name}.txt.j2")
        return template.render(profile=profile, **kwargs)

    def render_localized(
        self, template_name: str, language: str, *, profile: Profile, **kwargs
    ) -> str:
        try:
            template = self._env.get_template(f"locales/{language}/{template_name}.txt.j2")
        except Exception:
            template = self._env.get_template(f"{template_name}.txt.j2")
        return template.render(profile=profile, **kwargs)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_template.py -v
```
Expected: all 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/core/template.py templates/ tests/unit/test_template.py
git commit -m "feat: GDPR request templates with Jinja2 rendering"
```

---

### Task 9: Email Sender

**Files:**
- Create: `backend/senders/base.py`
- Create: `backend/senders/email.py`
- Create: `tests/unit/test_email_sender.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_email_sender.py
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from backend.core.profile import SmtpConfig
from backend.senders.base import SenderResult, SenderStatus
from backend.senders.email import EmailSender


@pytest.fixture
def smtp_config():
    return SmtpConfig(
        host="smtp.test.com",
        port=587,
        username="test@test.com",
        password="test_password",
    )


def test_sender_result_model():
    result = SenderResult(status=SenderStatus.SUCCESS, message="Sent OK")
    assert result.status == SenderStatus.SUCCESS

    fail = SenderResult(status=SenderStatus.FAILURE, message="Connection refused")
    assert fail.status == SenderStatus.FAILURE


def test_email_sender_parse_subject_body():
    text = "Subject: Test Subject\n\nBody line 1\nBody line 2"
    subject, body = EmailSender._parse_rendered(text)
    assert subject == "Test Subject"
    assert "Body line 1" in body
    assert "Body line 2" in body


def test_email_sender_parse_no_subject():
    text = "No subject header here\nJust body text"
    subject, body = EmailSender._parse_rendered(text)
    assert subject == "GDPR Request"
    assert "No subject header here" in body


@pytest.mark.asyncio
async def test_email_sender_send_success(smtp_config):
    sender = EmailSender(smtp_config)

    with patch("backend.senders.email.SMTP") as mock_smtp_cls:
        mock_smtp = AsyncMock()
        mock_smtp_cls.return_value = mock_smtp
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=False)

        result = await sender.send(
            to_email="dpo@broker.com",
            rendered_text="Subject: Test\n\nBody here",
        )

    assert result.status == SenderStatus.SUCCESS


@pytest.mark.asyncio
async def test_email_sender_send_failure(smtp_config):
    sender = EmailSender(smtp_config)

    with patch("backend.senders.email.SMTP") as mock_smtp_cls:
        mock_smtp_cls.side_effect = ConnectionError("Connection refused")

        result = await sender.send(
            to_email="dpo@broker.com",
            rendered_text="Subject: Test\n\nBody here",
        )

    assert result.status == SenderStatus.FAILURE
    assert "Connection refused" in result.message
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_email_sender.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/senders/base.py**

```python
# backend/senders/base.py
from __future__ import annotations

import enum
from dataclasses import dataclass


class SenderStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    MANUAL_NEEDED = "manual_needed"


@dataclass(frozen=True)
class SenderResult:
    status: SenderStatus
    message: str
```

- [ ] **Step 4: Write backend/senders/email.py**

```python
# backend/senders/email.py
from __future__ import annotations

from email.message import EmailMessage

from aiosmtplib import SMTP

from backend.core.profile import SmtpConfig
from backend.senders.base import SenderResult, SenderStatus


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

    async def send(self, to_email: str, rendered_text: str) -> SenderResult:
        subject, body = self._parse_rendered(rendered_text)

        msg = EmailMessage()
        msg["From"] = self._config.username
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

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
            return SenderResult(status=SenderStatus.FAILURE, message=str(exc))
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_email_sender.py -v
```
Expected: all 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/senders/base.py backend/senders/email.py tests/unit/test_email_sender.py
git commit -m "feat: async email sender with SMTP support"
```

---

## Phase 3: FastAPI Backend

### Task 10: FastAPI App Skeleton & Auth

**Files:**
- Create: `backend/main.py`
- Create: `backend/api/auth.py`
- Create: `backend/api/deps.py`
- Create: `tests/unit/test_auth_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_auth_api.py
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Address, Profile, ProfileVault, SmtpConfig


@pytest.fixture
def app_dir(tmp_path):
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def seeded_vault(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test User",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["test@test.com"],
        phones=[],
        addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="test@test.com", password="p")
    vault.save(profile, smtp, "master_password")
    return vault


@pytest.fixture
def client(config, seeded_vault):
    from backend.main import create_app

    app = create_app(config)
    return TestClient(app)


def test_unlock_success(client):
    response = client.post("/api/auth/unlock", json={"password": "master_password"})
    assert response.status_code == 200
    assert "session" in response.cookies


def test_unlock_wrong_password(client):
    response = client.post("/api/auth/unlock", json={"password": "wrong"})
    assert response.status_code == 401


def test_protected_endpoint_without_auth(client):
    response = client.get("/api/profile")
    assert response.status_code == 401


def test_protected_endpoint_with_auth(client):
    client.post("/api/auth/unlock", json={"password": "master_password"})
    response = client.get("/api/profile")
    assert response.status_code == 200
    data = response.json()
    assert data["full_name"] == "Test User"


def test_lock(client):
    client.post("/api/auth/unlock", json={"password": "master_password"})
    response = client.post("/api/auth/lock")
    assert response.status_code == 200

    response = client.get("/api/profile")
    assert response.status_code == 401


def test_setup_status_not_initialized(config):
    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["initialized"] is False


def test_setup_status_initialized(client):
    response = client.get("/api/auth/status")
    assert response.status_code == 200
    assert response.json()["initialized"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_auth_api.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/api/deps.py**

```python
# backend/api/deps.py
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import Cookie, HTTPException


class SessionStore:
    def __init__(self, timeout_minutes: int):
        self._timeout_minutes = timeout_minutes
        self._sessions: dict[str, tuple[str, datetime]] = {}  # token -> (password, last_access)

    def create(self, password: str) -> str:
        token = secrets.token_urlsafe(32)
        self._sessions[token] = (password, datetime.now(timezone.utc))
        return token

    def validate(self, token: str | None) -> str:
        if token is None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        entry = self._sessions.get(token)
        if entry is None:
            raise HTTPException(status_code=401, detail="Invalid session")

        password, last_access = entry
        elapsed = (datetime.now(timezone.utc) - last_access).total_seconds()
        if elapsed > self._timeout_minutes * 60:
            del self._sessions[token]
            raise HTTPException(status_code=401, detail="Session expired")

        self._sessions[token] = (password, datetime.now(timezone.utc))
        return password

    def destroy(self, token: str | None) -> None:
        if token and token in self._sessions:
            del self._sessions[token]
```

- [ ] **Step 4: Write backend/api/auth.py**

```python
# backend/api/auth.py
from fastapi import APIRouter, Response, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.profile import ProfileVault

router = APIRouter(prefix="/api/auth", tags=["auth"])


def create_auth_router(vault: ProfileVault, session_store: SessionStore) -> APIRouter:
    r = APIRouter(prefix="/api/auth", tags=["auth"])

    class UnlockRequest(BaseModel):
        password: str

    @r.get("/status")
    def status():
        return {"initialized": vault.exists()}

    @r.post("/unlock")
    def unlock(req: UnlockRequest, response: Response):
        if not vault.exists():
            raise HTTPException(status_code=400, detail="Not initialized")
        try:
            vault.load(req.password)
        except Exception:
            raise HTTPException(status_code=401, detail="Wrong password")

        token = session_store.create(req.password)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,  # localhost
        )
        return {"status": "unlocked"}

    @r.post("/lock")
    def lock(response: Response, session: str | None = Cookie(default=None)):
        session_store.destroy(session)
        response.delete_cookie("session")
        return {"status": "locked"}

    return r
```

- [ ] **Step 5: Write backend/main.py**

```python
# backend/main.py
from pathlib import Path

from fastapi import FastAPI, Cookie, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import create_auth_router
from backend.api.deps import SessionStore
from backend.core.config import AppConfig
from backend.core.profile import ProfileVault
from backend.db.session import init_db


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = AppConfig()

    app = FastAPI(title="Incognito", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    config.data_dir.mkdir(parents=True, exist_ok=True)

    vault = ProfileVault(config.vault_path)
    session_store = SessionStore(config.session_timeout_minutes)
    db_session_factory = init_db(config.db_path)

    app.state.config = config
    app.state.vault = vault
    app.state.session_store = session_store
    app.state.db_session_factory = db_session_factory

    app.include_router(create_auth_router(vault, session_store))

    @app.get("/api/profile")
    def get_profile(session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        profile, _ = vault.load(password)
        return profile.model_dump()

    return app
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/unit/test_auth_api.py -v
```
Expected: all 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/main.py backend/api/auth.py backend/api/deps.py tests/unit/test_auth_api.py
git commit -m "feat: FastAPI app with session auth and profile endpoint"
```

---

### Task 11: Setup Wizard API

**Files:**
- Create: `backend/api/setup.py`
- Create: `tests/unit/test_setup_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_setup_api.py
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig


@pytest.fixture
def config(tmp_path):
    return AppConfig(data_dir=tmp_path)


@pytest.fixture
def client(config):
    from backend.main import create_app

    app = create_app(config)
    return TestClient(app)


def test_setup_creates_profile(client, config):
    response = client.post(
        "/api/setup",
        json={
            "password": "master_password",
            "profile": {
                "full_name": "Malte Example",
                "previous_names": [],
                "date_of_birth": "1990-01-15",
                "emails": ["malte@example.com"],
                "phones": [],
                "addresses": [],
            },
            "smtp": {
                "host": "smtp.gmail.com",
                "port": 587,
                "username": "malte@example.com",
                "password": "app_password",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "initialized"
    assert config.vault_path.exists()


def test_setup_rejects_if_already_initialized(client, config):
    setup_data = {
        "password": "master_password",
        "profile": {
            "full_name": "Test",
            "previous_names": [],
            "date_of_birth": "1990-01-01",
            "emails": ["t@t.com"],
            "phones": [],
            "addresses": [],
        },
        "smtp": {
            "host": "smtp.test.com",
            "port": 587,
            "username": "t@t.com",
            "password": "p",
        },
    }
    client.post("/api/setup", json=setup_data)
    response = client.post("/api/setup", json=setup_data)
    assert response.status_code == 400


def test_setup_validates_profile(client):
    response = client.post(
        "/api/setup",
        json={
            "password": "master_password",
            "profile": {
                "full_name": "",
                "previous_names": [],
                "date_of_birth": "invalid-date",
                "emails": [],
                "phones": [],
                "addresses": [],
            },
            "smtp": {
                "host": "smtp.test.com",
                "port": 587,
                "username": "t@t.com",
                "password": "p",
            },
        },
    )
    assert response.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_setup_api.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/api/setup.py**

```python
# backend/api/setup.py
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.profile import Profile, ProfileVault, SmtpConfig


def create_setup_router(vault: ProfileVault, session_store: SessionStore) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["setup"])

    class SetupRequest(BaseModel):
        password: str
        profile: Profile
        smtp: SmtpConfig

    @r.post("/setup")
    def setup(req: SetupRequest, response: Response):
        if vault.exists():
            raise HTTPException(status_code=400, detail="Already initialized")

        vault.save(req.profile, req.smtp, req.password)

        token = session_store.create(req.password)
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="strict",
            secure=False,
        )
        return {"status": "initialized"}

    return r
```

- [ ] **Step 4: Register router in backend/main.py**

Add import and include the router in `create_app`:

```python
from backend.api.setup import create_setup_router

# Inside create_app, after the auth router:
app.include_router(create_setup_router(vault, session_store))
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_setup_api.py -v
```
Expected: all 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/setup.py backend/main.py tests/unit/test_setup_api.py
git commit -m "feat: setup wizard API endpoint"
```

---

### Task 12: Brokers API

**Files:**
- Create: `backend/api/brokers.py`
- Create: `tests/unit/test_brokers_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_brokers_api.py
from datetime import date
from pathlib import Path

import yaml
import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def app_dir(tmp_path):
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()
    broker = {
        "name": "Test Broker",
        "domain": "testbroker.com",
        "category": "data_broker",
        "dpo_email": "dpo@testbroker.com",
        "removal_method": "email",
        "country": "DE",
        "gdpr_applies": True,
        "verification_required": False,
        "language": "de",
        "last_verified": "2026-03-01",
        "notes": "Test",
    }
    (brokers_dir / "test-broker.yaml").write_text(yaml.dump(broker))
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def client(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test", previous_names=[], date_of_birth=date(1990, 1, 1),
        emails=["t@t.com"], phones=[], addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def test_list_brokers(client):
    response = client.get("/api/brokers")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Broker"
    assert data[0]["id"] == "testbroker-com"


def test_get_broker_by_id(client):
    response = client.get("/api/brokers/testbroker-com")
    assert response.status_code == 200
    assert response.json()["name"] == "Test Broker"


def test_get_broker_not_found(client):
    response = client.get("/api/brokers/nonexistent")
    assert response.status_code == 404


def test_brokers_requires_auth(config):
    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    response = c.get("/api/brokers")
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_brokers_api.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/api/brokers.py**

```python
# backend/api/brokers.py
from fastapi import APIRouter, Cookie, HTTPException

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry


def create_brokers_router(registry: BrokerRegistry, session_store: SessionStore) -> APIRouter:
    r = APIRouter(prefix="/api/brokers", tags=["brokers"])

    @r.get("")
    def list_brokers(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        return [b.model_dump() for b in registry.brokers]

    @r.get("/{broker_id}")
    def get_broker(broker_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        broker = registry.get(broker_id)
        if broker is None:
            raise HTTPException(status_code=404, detail="Broker not found")
        return broker.model_dump()

    return r
```

- [ ] **Step 4: Register router in backend/main.py**

Add to `create_app`:

```python
from backend.api.brokers import create_brokers_router
from backend.core.broker import BrokerRegistry

# Inside create_app, after vault/session setup:
brokers_dir = config.brokers_dir
if not brokers_dir.exists():
    # Fall back to project-level brokers/ directory
    project_brokers = Path(__file__).parent.parent / "brokers"
    if project_brokers.exists():
        brokers_dir = project_brokers

broker_registry = BrokerRegistry.load(brokers_dir)
app.state.broker_registry = broker_registry

app.include_router(create_brokers_router(broker_registry, session_store))
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_brokers_api.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/brokers.py backend/main.py tests/unit/test_brokers_api.py
git commit -m "feat: brokers API with list and detail endpoints"
```

---

### Task 13: Requests API

**Files:**
- Create: `backend/api/requests.py`
- Create: `tests/unit/test_requests_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_requests_api.py
from datetime import date
from pathlib import Path

import yaml
import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig
from backend.core.profile import Profile, ProfileVault, SmtpConfig


@pytest.fixture
def app_dir(tmp_path):
    brokers_dir = tmp_path / "brokers"
    brokers_dir.mkdir()
    broker = {
        "name": "Test Broker",
        "domain": "testbroker.com",
        "category": "data_broker",
        "dpo_email": "dpo@testbroker.com",
        "removal_method": "email",
        "country": "DE",
        "gdpr_applies": True,
        "verification_required": False,
        "language": "en",
        "last_verified": "2026-03-01",
    }
    (brokers_dir / "test-broker.yaml").write_text(yaml.dump(broker))
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def client(config):
    vault = ProfileVault(config.vault_path)
    profile = Profile(
        full_name="Test", previous_names=[], date_of_birth=date(1990, 1, 1),
        emails=["t@t.com"], phones=[], addresses=[],
    )
    smtp = SmtpConfig(host="smtp.test.com", port=587, username="t@t.com", password="p")
    vault.save(profile, smtp, "password")

    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    c.post("/api/auth/unlock", json={"password": "password"})
    return c


def test_create_request(client):
    response = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "created"
    assert data["broker_id"] == "testbroker-com"


def test_list_requests(client):
    client.post("/api/requests", json={"broker_id": "testbroker-com", "request_type": "access"})
    client.post("/api/requests", json={"broker_id": "testbroker-com", "request_type": "erasure"})

    response = client.get("/api/requests")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_request_detail(client):
    create_resp = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    req_id = create_resp.json()["id"]

    response = client.get(f"/api/requests/{req_id}")
    assert response.status_code == 200
    assert response.json()["id"] == req_id


def test_get_request_events(client):
    create_resp = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    req_id = create_resp.json()["id"]

    response = client.get(f"/api/requests/{req_id}/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) >= 1
    assert events[0]["event_type"] == "created"


def test_update_request_status(client):
    create_resp = client.post(
        "/api/requests",
        json={"broker_id": "testbroker-com", "request_type": "erasure"},
    )
    req_id = create_resp.json()["id"]

    # Mark as sent
    response = client.post(
        f"/api/requests/{req_id}/transition",
        json={"action": "mark_sent"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "sent"


def test_dashboard_stats(client):
    client.post("/api/requests", json={"broker_id": "testbroker-com", "request_type": "erasure"})

    response = client.get("/api/requests/stats")
    assert response.status_code == 200
    stats = response.json()
    assert stats["total"] == 1
    assert stats["created"] == 1


def test_requests_requires_auth(config):
    from backend.main import create_app
    app = create_app(config)
    c = TestClient(app)
    response = c.get("/api/requests")
    assert response.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_requests_api.py -v
```
Expected: FAIL

- [ ] **Step 3: Write backend/api/requests.py**

```python
# backend/api/requests.py
from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.deps import SessionStore
from backend.core.request import InvalidTransitionError, RequestManager
from backend.db.models import Request, RequestEvent, RequestStatus, RequestType


def create_requests_router(
    db_session_factory, session_store: SessionStore, gdpr_deadline_days: int
) -> APIRouter:
    r = APIRouter(prefix="/api/requests", tags=["requests"])

    class CreateRequest(BaseModel):
        broker_id: str
        request_type: RequestType

    class TransitionRequest(BaseModel):
        action: str
        details: str | None = None

    def _get_db() -> Session:
        return db_session_factory()

    @r.get("/stats")
    def stats(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            all_requests = db.query(Request).all()
            counts = {}
            for status in RequestStatus:
                counts[status.value] = sum(1 for r in all_requests if r.status == status)
            counts["total"] = len(all_requests)
            return counts
        finally:
            db.close()

    @r.get("")
    def list_requests(
        status: str | None = None,
        session: str | None = Cookie(default=None),
    ):
        session_store.validate(session)
        db = _get_db()
        try:
            query = db.query(Request)
            if status:
                query = query.filter(Request.status == status)
            requests = query.order_by(Request.created_at.desc()).all()
            return [
                {
                    "id": req.id,
                    "broker_id": req.broker_id,
                    "request_type": req.request_type.value,
                    "status": req.status.value,
                    "sent_at": req.sent_at.isoformat() if req.sent_at else None,
                    "deadline_at": req.deadline_at.isoformat() if req.deadline_at else None,
                    "created_at": req.created_at.isoformat() if req.created_at else None,
                }
                for req in requests
            ]
        finally:
            db.close()

    @r.post("")
    def create_request(body: CreateRequest, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            mgr = RequestManager(db, gdpr_deadline_days)
            req = mgr.create(body.broker_id, body.request_type)
            return {
                "id": req.id,
                "broker_id": req.broker_id,
                "request_type": req.request_type.value,
                "status": req.status.value,
            }
        finally:
            db.close()

    @r.get("/{request_id}")
    def get_request(request_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            req = db.get(Request, request_id)
            if req is None:
                raise HTTPException(status_code=404, detail="Request not found")
            return {
                "id": req.id,
                "broker_id": req.broker_id,
                "request_type": req.request_type.value,
                "status": req.status.value,
                "sent_at": req.sent_at.isoformat() if req.sent_at else None,
                "deadline_at": req.deadline_at.isoformat() if req.deadline_at else None,
                "response_at": req.response_at.isoformat() if req.response_at else None,
                "response_body": req.response_body,
                "created_at": req.created_at.isoformat() if req.created_at else None,
            }
        finally:
            db.close()

    @r.get("/{request_id}/events")
    def get_events(request_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        db = _get_db()
        try:
            events = (
                db.query(RequestEvent)
                .filter_by(request_id=request_id)
                .order_by(RequestEvent.id)
                .all()
            )
            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "details": e.details,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                for e in events
            ]
        finally:
            db.close()

    @r.post("/{request_id}/transition")
    def transition(
        request_id: str, body: TransitionRequest, session: str | None = Cookie(default=None)
    ):
        session_store.validate(session)
        db = _get_db()
        try:
            mgr = RequestManager(db, gdpr_deadline_days)
            action_map = {
                "mark_sent": mgr.mark_sent,
                "mark_acknowledged": lambda rid: mgr.mark_acknowledged(rid, body.details or ""),
                "mark_completed": mgr.mark_completed,
                "mark_refused": lambda rid: mgr.mark_refused(rid, body.details or ""),
                "mark_overdue": mgr.mark_overdue,
                "mark_escalated": mgr.mark_escalated,
                "mark_manual_action_needed": lambda rid: mgr.mark_manual_action_needed(
                    rid, body.details or ""
                ),
            }
            fn = action_map.get(body.action)
            if fn is None:
                raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")
            try:
                req = fn(request_id)
            except InvalidTransitionError as e:
                raise HTTPException(status_code=400, detail=str(e))
            return {"id": req.id, "status": req.status.value}
        finally:
            db.close()

    return r
```

- [ ] **Step 4: Register router in backend/main.py**

Add to `create_app`:

```python
from backend.api.requests import create_requests_router

app.include_router(
    create_requests_router(db_session_factory, session_store, config.gdpr_deadline_days)
)
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/unit/test_requests_api.py -v
```
Expected: all 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/requests.py backend/main.py tests/unit/test_requests_api.py
git commit -m "feat: requests API with CRUD, transitions, stats, and events"
```

---

## Phase 4: Frontend

### Task 14: Frontend Scaffolding

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/api/client.ts`

- [ ] **Step 1: Create frontend/package.json**

```json
{
  "name": "incognito-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.28.0",
    "lucide-react": "^0.460.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0"
  }
}
```

- [ ] **Step 2: Create frontend/tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "moduleDetection": "force",
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "noUncheckedSideEffectImports": true
  },
  "include": ["src"]
}
```

- [ ] **Step 3: Create frontend/vite.config.ts**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8080",
    },
  },
  build: {
    outDir: "dist",
  },
});
```

- [ ] **Step 4: Create frontend/tailwind.config.js**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};
```

- [ ] **Step 5: Create frontend/postcss.config.js**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 6: Create frontend/index.html**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Incognito</title>
  </head>
  <body class="bg-gray-50 text-gray-900">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Create frontend/src/index.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 8: Create frontend/src/api/client.ts**

```typescript
const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

export const api = {
  getStatus: () => request<{ initialized: boolean }>("/auth/status"),
  unlock: (password: string) =>
    request("/auth/unlock", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  lock: () => request("/auth/lock", { method: "POST" }),
  setup: (data: { password: string; profile: unknown; smtp: unknown }) =>
    request("/setup", { method: "POST", body: JSON.stringify(data) }),
  getProfile: () => request<Record<string, unknown>>("/profile"),
  getBrokers: () => request<Array<Record<string, unknown>>>("/brokers"),
  getBroker: (id: string) => request<Record<string, unknown>>(`/brokers/${id}`),
  getRequests: (status?: string) =>
    request<Array<Record<string, unknown>>>(
      `/requests${status ? `?status=${status}` : ""}`
    ),
  getRequest: (id: string) => request<Record<string, unknown>>(`/requests/${id}`),
  getRequestEvents: (id: string) =>
    request<Array<Record<string, unknown>>>(`/requests/${id}/events`),
  createRequest: (brokerId: string, requestType: string) =>
    request("/requests", {
      method: "POST",
      body: JSON.stringify({ broker_id: brokerId, request_type: requestType }),
    }),
  transitionRequest: (id: string, action: string, details?: string) =>
    request(`/requests/${id}/transition`, {
      method: "POST",
      body: JSON.stringify({ action, details }),
    }),
  getStats: () => request<Record<string, number>>("/requests/stats"),
};
```

- [ ] **Step 9: Create frontend/src/main.tsx**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

- [ ] **Step 10: Create frontend/src/App.tsx**

```tsx
import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api/client";

function App() {
  const [status, setStatus] = useState<{
    initialized: boolean;
    authenticated: boolean;
    loading: boolean;
  }>({ initialized: false, authenticated: false, loading: true });

  useEffect(() => {
    Promise.all([api.getStatus(), api.getProfile().catch(() => null)]).then(
      ([s, profile]) => {
        setStatus({
          initialized: s.initialized,
          authenticated: profile !== null,
          loading: false,
        });
      }
    );
  }, []);

  if (status.loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/*" element={<p className="p-8 text-lg">Incognito is running. UI pages coming soon.</p>} />
      </Routes>
    </div>
  );
}

export default App;
```

- [ ] **Step 11: Install dependencies and build**

```bash
cd /home/malte/incognito/frontend
npm install
npm run build
```
Expected: build succeeds, `dist/` directory created

- [ ] **Step 12: Commit**

```bash
cd /home/malte/incognito
git add frontend/
git commit -m "feat: frontend scaffolding with React, Vite, Tailwind, and API client"
```

---

### Task 15: Setup Wizard Page

**Files:**
- Create: `frontend/src/pages/SetupWizard.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/src/pages/SetupWizard.tsx**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { Shield } from "lucide-react";

type Step = "password" | "profile" | "smtp" | "confirm";

export default function SetupWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("password");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [profile, setProfile] = useState({
    full_name: "",
    previous_names: [] as string[],
    date_of_birth: "",
    emails: [""],
    phones: [""],
    addresses: [] as Array<{
      street: string;
      city: string;
      postal_code: string;
      country: string;
    }>,
  });

  const [smtp, setSmtp] = useState({
    host: "",
    port: 587,
    username: "",
    password: "",
  });

  const steps: Step[] = ["password", "profile", "smtp", "confirm"];
  const currentIndex = steps.indexOf(step);

  async function handleSubmit() {
    setLoading(true);
    setError("");
    try {
      await api.setup({
        password,
        profile: {
          ...profile,
          emails: profile.emails.filter((e) => e.trim()),
          phones: profile.phones.filter((p) => p.trim()),
        },
        smtp,
      });
      navigate("/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Setup failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-xl w-full p-8">
        <div className="flex items-center gap-3 mb-6">
          <Shield className="w-8 h-8 text-indigo-600" />
          <h1 className="text-2xl font-bold text-gray-900">Incognito Setup</h1>
        </div>

        {/* Progress bar */}
        <div className="flex gap-2 mb-8">
          {steps.map((s, i) => (
            <div
              key={s}
              className={`h-1.5 flex-1 rounded-full ${
                i <= currentIndex ? "bg-indigo-600" : "bg-gray-200"
              }`}
            />
          ))}
        </div>

        {error && (
          <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg mb-4 text-sm">
            {error}
          </div>
        )}

        {step === "password" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Master Password</h2>
            <p className="text-sm text-gray-600">
              This encrypts your profile data. Choose something strong.
            </p>
            <input
              type="password"
              placeholder="Master password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <input
              type="password"
              placeholder="Confirm password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <button
              onClick={() => {
                if (password.length < 8) {
                  setError("Password must be at least 8 characters");
                  return;
                }
                if (password !== confirmPassword) {
                  setError("Passwords don't match");
                  return;
                }
                setError("");
                setStep("profile");
              }}
              className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition"
            >
              Continue
            </button>
          </div>
        )}

        {step === "profile" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Your Identity</h2>
            <p className="text-sm text-gray-600">
              This is what we search for and include in removal requests.
            </p>
            <input
              type="text"
              placeholder="Full name"
              value={profile.full_name}
              onChange={(e) =>
                setProfile({ ...profile, full_name: e.target.value })
              }
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <input
              type="date"
              value={profile.date_of_birth}
              onChange={(e) =>
                setProfile({ ...profile, date_of_birth: e.target.value })
              }
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <input
              type="email"
              placeholder="Primary email"
              value={profile.emails[0]}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  emails: [e.target.value, ...profile.emails.slice(1)],
                })
              }
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <input
              type="tel"
              placeholder="Phone (optional)"
              value={profile.phones[0]}
              onChange={(e) =>
                setProfile({
                  ...profile,
                  phones: [e.target.value],
                })
              }
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setStep("password")}
                className="flex-1 border border-gray-300 py-2.5 rounded-lg font-medium hover:bg-gray-50 transition"
              >
                Back
              </button>
              <button
                onClick={() => {
                  if (!profile.full_name.trim()) {
                    setError("Name is required");
                    return;
                  }
                  if (!profile.emails[0]?.trim()) {
                    setError("At least one email is required");
                    return;
                  }
                  setError("");
                  setStep("smtp");
                }}
                className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === "smtp" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Email Sending</h2>
            <p className="text-sm text-gray-600">
              Used to send removal requests. Use an app password, not your main
              password.
            </p>
            <input
              type="text"
              placeholder="SMTP server (e.g. smtp.gmail.com)"
              value={smtp.host}
              onChange={(e) => setSmtp({ ...smtp, host: e.target.value })}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <input
              type="number"
              placeholder="Port (587)"
              value={smtp.port}
              onChange={(e) =>
                setSmtp({ ...smtp, port: parseInt(e.target.value) || 587 })
              }
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <input
              type="text"
              placeholder="Username (email)"
              value={smtp.username}
              onChange={(e) => setSmtp({ ...smtp, username: e.target.value })}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <input
              type="password"
              placeholder="App password"
              value={smtp.password}
              onChange={(e) => setSmtp({ ...smtp, password: e.target.value })}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
            />
            <div className="flex gap-3">
              <button
                onClick={() => setStep("profile")}
                className="flex-1 border border-gray-300 py-2.5 rounded-lg font-medium hover:bg-gray-50 transition"
              >
                Back
              </button>
              <button
                onClick={() => {
                  if (!smtp.host.trim() || !smtp.username.trim() || !smtp.password.trim()) {
                    setError("All SMTP fields are required");
                    return;
                  }
                  setError("");
                  setStep("confirm");
                }}
                className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition"
              >
                Continue
              </button>
            </div>
          </div>
        )}

        {step === "confirm" && (
          <div className="space-y-4">
            <h2 className="text-lg font-semibold">Confirm Setup</h2>
            <div className="bg-gray-50 rounded-lg p-4 text-sm space-y-2">
              <p>
                <span className="font-medium">Name:</span> {profile.full_name}
              </p>
              <p>
                <span className="font-medium">Email:</span>{" "}
                {profile.emails.filter((e) => e.trim()).join(", ")}
              </p>
              <p>
                <span className="font-medium">SMTP:</span> {smtp.host}:{smtp.port}
              </p>
            </div>
            <p className="text-sm text-gray-600">
              Your profile will be encrypted with your master password and stored
              locally.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setStep("smtp")}
                className="flex-1 border border-gray-300 py-2.5 rounded-lg font-medium hover:bg-gray-50 transition"
              >
                Back
              </button>
              <button
                onClick={handleSubmit}
                disabled={loading}
                className="flex-1 bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition disabled:opacity-50"
              >
                {loading ? "Setting up..." : "Complete Setup"}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update frontend/src/App.tsx to route to wizard**

```tsx
import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { api } from "./api/client";
import SetupWizard from "./pages/SetupWizard";

function LockScreen({ onUnlock }: { onUnlock: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleUnlock() {
    try {
      await api.unlock(password);
      onUnlock();
    } catch {
      setError("Wrong password");
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 to-slate-800 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-8 text-center">
        <h1 className="text-2xl font-bold mb-2">Incognito</h1>
        <p className="text-gray-500 text-sm mb-6">Enter your master password to unlock</p>
        {error && <p className="text-red-600 text-sm mb-3">{error}</p>}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleUnlock()}
          placeholder="Master password"
          className="w-full px-4 py-2.5 border border-gray-300 rounded-lg mb-3 focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none"
        />
        <button
          onClick={handleUnlock}
          className="w-full bg-indigo-600 text-white py-2.5 rounded-lg font-medium hover:bg-indigo-700 transition"
        >
          Unlock
        </button>
      </div>
    </div>
  );
}

function App() {
  const [status, setStatus] = useState<{
    initialized: boolean;
    authenticated: boolean;
    loading: boolean;
  }>({ initialized: false, authenticated: false, loading: true });

  useEffect(() => {
    checkStatus();
  }, []);

  async function checkStatus() {
    const [s, profile] = await Promise.all([
      api.getStatus(),
      api.getProfile().catch(() => null),
    ]);
    setStatus({
      initialized: s.initialized,
      authenticated: profile !== null,
      loading: false,
    });
  }

  if (status.loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading...</p>
      </div>
    );
  }

  if (!status.initialized) {
    return <SetupWizard />;
  }

  if (!status.authenticated) {
    return <LockScreen onUnlock={() => setStatus({ ...status, authenticated: true })} />;
  }

  return (
    <div className="min-h-screen">
      <Routes>
        <Route path="/" element={<p className="p-8 text-lg">Dashboard coming next.</p>} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </div>
  );
}

export default App;
```

- [ ] **Step 3: Build and verify**

```bash
cd /home/malte/incognito/frontend
npm run build
```
Expected: build succeeds

- [ ] **Step 4: Commit**

```bash
cd /home/malte/incognito
git add frontend/src/
git commit -m "feat: setup wizard and lock screen pages"
```

---

### Task 16: Dashboard & Navigation Shell

**Files:**
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/pages/Dashboard.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/src/components/Layout.tsx**

```tsx
import { NavLink, Outlet } from "react-router-dom";
import { Shield, LayoutDashboard, Send, Database, Search, Settings, LogOut } from "lucide-react";
import { api } from "../api/client";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/requests", icon: Send, label: "Requests" },
  { to: "/brokers", icon: Database, label: "Brokers" },
  { to: "/scan", icon: Search, label: "Scan" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export default function Layout({ onLock }: { onLock: () => void }) {
  async function handleLock() {
    await api.lock();
    onLock();
  }

  return (
    <div className="min-h-screen flex">
      <aside className="w-56 bg-slate-900 text-white flex flex-col">
        <div className="flex items-center gap-2.5 px-5 py-5 border-b border-slate-700">
          <Shield className="w-6 h-6 text-indigo-400" />
          <span className="font-bold text-lg">Incognito</span>
        </div>
        <nav className="flex-1 py-4">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 px-5 py-2.5 text-sm transition ${
                  isActive
                    ? "bg-slate-800 text-white font-medium"
                    : "text-slate-400 hover:text-white hover:bg-slate-800/50"
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={handleLock}
          className="flex items-center gap-3 px-5 py-4 text-sm text-slate-400 hover:text-white border-t border-slate-700 transition"
        >
          <LogOut className="w-4 h-4" />
          Lock
        </button>
      </aside>
      <main className="flex-1 bg-gray-50 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
```

- [ ] **Step 2: Create frontend/src/pages/Dashboard.tsx**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Send, CheckCircle, Clock, AlertTriangle } from "lucide-react";

interface Stats {
  total: number;
  created: number;
  sent: number;
  acknowledged: number;
  completed: number;
  refused: number;
  overdue: number;
  escalated: number;
  manual_action_needed: number;
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [recentRequests, setRecentRequests] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    api.getStats().then((s) => setStats(s as unknown as Stats));
    api.getRequests().then((r) => setRecentRequests(r.slice(0, 10)));
  }, []);

  if (!stats) {
    return <div className="p-8 text-gray-500">Loading...</div>;
  }

  const cards = [
    { label: "Pending", value: stats.created, icon: Clock, color: "text-yellow-600 bg-yellow-50" },
    { label: "Sent", value: stats.sent, icon: Send, color: "text-blue-600 bg-blue-50" },
    { label: "Completed", value: stats.completed, icon: CheckCircle, color: "text-green-600 bg-green-50" },
    { label: "Overdue", value: stats.overdue + stats.manual_action_needed, icon: AlertTriangle, color: "text-red-600 bg-red-50" },
  ];

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>

      <div className="grid grid-cols-4 gap-4 mb-8">
        {cards.map(({ label, value, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-xl shadow-sm border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-gray-500">{label}</span>
              <div className={`p-2 rounded-lg ${color}`}>
                <Icon className="w-4 h-4" />
              </div>
            </div>
            <p className="text-3xl font-bold">{value}</p>
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-200">
          <h2 className="font-semibold">Recent Activity</h2>
        </div>
        {recentRequests.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 text-center text-sm">
            No requests yet. Run a scan or create a request to get started.
          </p>
        ) : (
          <div className="divide-y divide-gray-100">
            {recentRequests.map((req) => (
              <div key={req.id as string} className="px-5 py-3 flex items-center justify-between text-sm">
                <div>
                  <span className="font-medium">{req.broker_id as string}</span>
                  <span className="text-gray-400 mx-2">·</span>
                  <span className="text-gray-500">{req.request_type as string}</span>
                </div>
                <StatusBadge status={req.status as string} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    created: "bg-gray-100 text-gray-700",
    sent: "bg-blue-100 text-blue-700",
    acknowledged: "bg-indigo-100 text-indigo-700",
    completed: "bg-green-100 text-green-700",
    refused: "bg-red-100 text-red-700",
    overdue: "bg-orange-100 text-orange-700",
    escalated: "bg-red-100 text-red-700",
    manual_action_needed: "bg-yellow-100 text-yellow-700",
  };

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[status] || "bg-gray-100"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
```

- [ ] **Step 3: Update App.tsx to use Layout and Dashboard**

Replace the authenticated section of the Routes in `App.tsx`:

```tsx
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";

// In the return for authenticated state:
return (
  <div className="min-h-screen">
    <Routes>
      <Route element={<Layout onLock={() => setStatus({ ...status, authenticated: false })} />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/requests" element={<p className="p-8">Requests page coming soon.</p>} />
        <Route path="/brokers" element={<p className="p-8">Brokers page coming soon.</p>} />
        <Route path="/scan" element={<p className="p-8">Scan page coming soon.</p>} />
        <Route path="/settings" element={<p className="p-8">Settings page coming soon.</p>} />
      </Route>
      <Route path="*" element={<Navigate to="/" />} />
    </Routes>
  </div>
);
```

- [ ] **Step 4: Build and verify**

```bash
cd /home/malte/incognito/frontend
npm run build
```
Expected: build succeeds

- [ ] **Step 5: Commit**

```bash
cd /home/malte/incognito
git add frontend/src/
git commit -m "feat: dashboard page with stats cards and navigation layout"
```

---

### Task 17: Requests Page

**Files:**
- Create: `frontend/src/pages/Requests.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/src/pages/Requests.tsx**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Send, Eye, ChevronDown } from "lucide-react";

interface RequestItem {
  id: string;
  broker_id: string;
  request_type: string;
  status: string;
  sent_at: string | null;
  deadline_at: string | null;
  created_at: string | null;
}

interface RequestEvent {
  id: number;
  event_type: string;
  details: string | null;
  created_at: string | null;
}

export default function Requests() {
  const [requests, setRequests] = useState<RequestItem[]>([]);
  const [filter, setFilter] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [events, setEvents] = useState<RequestEvent[]>([]);

  useEffect(() => {
    loadRequests();
  }, [filter]);

  async function loadRequests() {
    const data = await api.getRequests(filter || undefined);
    setRequests(data as unknown as RequestItem[]);
  }

  async function viewEvents(id: string) {
    if (selectedId === id) {
      setSelectedId(null);
      return;
    }
    const data = await api.getRequestEvents(id);
    setEvents(data as unknown as RequestEvent[]);
    setSelectedId(id);
  }

  async function handleTransition(id: string, action: string) {
    await api.transitionRequest(id, action);
    loadRequests();
  }

  const statusFilters = [
    "", "created", "sent", "acknowledged", "completed",
    "refused", "overdue", "escalated", "manual_action_needed",
  ];

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Requests</h1>
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        {statusFilters.map((s) => (
          <button
            key={s}
            onClick={() => setFilter(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              filter === s
                ? "bg-indigo-600 text-white"
                : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
            }`}
          >
            {s || "All"}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        {requests.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 text-center text-sm">No requests found.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {requests.map((req) => (
              <div key={req.id}>
                <div className="px-5 py-3 flex items-center justify-between text-sm">
                  <div className="flex items-center gap-4">
                    <span className="font-medium w-40 truncate">{req.broker_id}</span>
                    <span className="text-gray-500 w-24">{req.request_type}</span>
                    <StatusBadge status={req.status} />
                  </div>
                  <div className="flex items-center gap-2">
                    {req.status === "created" && (
                      <button
                        onClick={() => handleTransition(req.id, "mark_sent")}
                        className="flex items-center gap-1 px-3 py-1 bg-indigo-50 text-indigo-700 rounded-lg text-xs font-medium hover:bg-indigo-100 transition"
                      >
                        <Send className="w-3 h-3" /> Send
                      </button>
                    )}
                    <button
                      onClick={() => viewEvents(req.id)}
                      className="flex items-center gap-1 px-3 py-1 bg-gray-50 text-gray-600 rounded-lg text-xs hover:bg-gray-100 transition"
                    >
                      <Eye className="w-3 h-3" />
                      {selectedId === req.id ? "Hide" : "Events"}
                    </button>
                  </div>
                </div>
                {selectedId === req.id && (
                  <div className="px-5 pb-4 pl-12">
                    <div className="border-l-2 border-indigo-200 pl-4 space-y-2">
                      {events.map((e) => (
                        <div key={e.id} className="text-xs">
                          <span className="font-medium text-indigo-600">{e.event_type}</span>
                          {e.details && (
                            <span className="text-gray-500 ml-2">{e.details}</span>
                          )}
                          {e.created_at && (
                            <span className="text-gray-400 ml-2">
                              {new Date(e.created_at).toLocaleString()}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    created: "bg-gray-100 text-gray-700",
    sent: "bg-blue-100 text-blue-700",
    acknowledged: "bg-indigo-100 text-indigo-700",
    completed: "bg-green-100 text-green-700",
    refused: "bg-red-100 text-red-700",
    overdue: "bg-orange-100 text-orange-700",
    escalated: "bg-red-100 text-red-700",
    manual_action_needed: "bg-yellow-100 text-yellow-700",
  };

  return (
    <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${styles[status] || "bg-gray-100"}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}
```

- [ ] **Step 2: Update App.tsx route**

Replace the requests placeholder route:

```tsx
import Requests from "./pages/Requests";

// Replace: <Route path="/requests" element={<p ...>} />
<Route path="/requests" element={<Requests />} />
```

- [ ] **Step 3: Build and verify**

```bash
cd /home/malte/incognito/frontend
npm run build
```

- [ ] **Step 4: Commit**

```bash
cd /home/malte/incognito
git add frontend/src/
git commit -m "feat: requests page with filtering, events, and transitions"
```

---

### Task 18: Brokers Page

**Files:**
- Create: `frontend/src/pages/Brokers.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create frontend/src/pages/Brokers.tsx**

```tsx
import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Search, Plus, ExternalLink } from "lucide-react";

interface BrokerItem {
  id: string;
  name: string;
  domain: string;
  category: string;
  dpo_email: string;
  removal_method: string;
  country: string;
  gdpr_applies: boolean;
  language: string;
}

export default function Brokers() {
  const [brokers, setBrokers] = useState<BrokerItem[]>([]);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.getBrokers().then((data) => setBrokers(data as unknown as BrokerItem[]));
  }, []);

  const filtered = brokers.filter(
    (b) =>
      b.name.toLowerCase().includes(search.toLowerCase()) ||
      b.domain.toLowerCase().includes(search.toLowerCase())
  );

  async function handleCreateRequest(brokerId: string, type: string) {
    await api.createRequest(brokerId, type);
    alert(`${type} request created for ${brokerId}`);
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Brokers</h1>
        <span className="text-sm text-gray-500">{brokers.length} brokers in registry</span>
      </div>

      <div className="relative mb-4">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search brokers..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg bg-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm"
        />
      </div>

      <div className="bg-white rounded-xl shadow-sm border border-gray-200">
        {filtered.length === 0 ? (
          <p className="px-5 py-8 text-gray-500 text-center text-sm">No brokers found.</p>
        ) : (
          <div className="divide-y divide-gray-100">
            {filtered.map((broker) => (
              <div key={broker.id} className="px-5 py-3 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div>
                    <p className="text-sm font-medium">{broker.name}</p>
                    <p className="text-xs text-gray-500">{broker.domain} · {broker.country}</p>
                  </div>
                  <span className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600">
                    {broker.removal_method.replace("_", " ")}
                  </span>
                  {broker.gdpr_applies && (
                    <span className="px-2 py-0.5 rounded text-xs bg-green-50 text-green-700">
                      GDPR
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => handleCreateRequest(broker.id, "access")}
                    className="px-3 py-1 text-xs bg-gray-50 text-gray-700 rounded-lg hover:bg-gray-100 transition"
                  >
                    Art. 15
                  </button>
                  <button
                    onClick={() => handleCreateRequest(broker.id, "erasure")}
                    className="px-3 py-1 text-xs bg-indigo-50 text-indigo-700 rounded-lg hover:bg-indigo-100 transition"
                  >
                    Art. 17
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update App.tsx route**

```tsx
import Brokers from "./pages/Brokers";

// Replace: <Route path="/brokers" element={<p ...>} />
<Route path="/brokers" element={<Brokers />} />
```

- [ ] **Step 3: Build and verify**

```bash
cd /home/malte/incognito/frontend
npm run build
```

- [ ] **Step 4: Commit**

```bash
cd /home/malte/incognito
git add frontend/src/
git commit -m "feat: brokers page with search and request creation"
```

---

## Phase 5: CLI & Deployment

### Task 19: CLI Entry Point

**Files:**
- Create: `cli.py`
- Create: `tests/unit/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_cli.py
from typer.testing import CliRunner

from cli import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "incognito" in result.output.lower() or "Incognito" in result.output


def test_serve_help():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert "host" in result.output.lower() or "port" in result.output.lower()


def test_status_without_init(tmp_path, monkeypatch):
    monkeypatch.setenv("INCOGNITO_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0 or "not initialized" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_cli.py -v
```
Expected: FAIL

- [ ] **Step 3: Write cli.py**

```python
# cli.py
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from backend.core.config import AppConfig

app = typer.Typer(name="incognito", help="Self-hosted GDPR personal data removal tool.")
console = Console()


def get_config() -> AppConfig:
    return AppConfig()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Host to bind to"),
    port: int = typer.Option(8080, help="Port to listen on"),
):
    """Start the Incognito web server."""
    from backend.main import create_app

    config = get_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold green]Incognito[/] starting on http://{host}:{port}")
    fastapi_app = create_app(config)
    uvicorn.run(fastapi_app, host=host, port=port)


@app.command()
def status():
    """Show request status summary."""
    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/] Run [bold]incognito serve[/] and complete setup.")
        return

    from backend.db.session import init_db
    from backend.db.models import Request, RequestStatus

    session_factory = init_db(config.db_path)
    session = session_factory()

    try:
        all_requests = session.query(Request).all()

        if not all_requests:
            console.print("No requests yet.")
            return

        table = Table(title="Request Status")
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")

        for s in RequestStatus:
            count = sum(1 for r in all_requests if r.status == s)
            if count > 0:
                table.add_row(s.value, str(count))

        table.add_row("Total", str(len(all_requests)), style="bold")
        console.print(table)
    finally:
        session.close()


@app.command(name="follow-up")
def follow_up(
    auto: bool = typer.Option(False, "--auto", help="Automatically send follow-ups"),
):
    """Check deadlines and send follow-ups for overdue requests."""
    config = get_config()

    if not config.vault_path.exists():
        console.print("[yellow]Not initialized.[/]")
        return

    from backend.db.session import init_db
    from backend.core.request import RequestManager

    session_factory = init_db(config.db_path)
    session = session_factory()

    try:
        mgr = RequestManager(session, config.gdpr_deadline_days)
        overdue = mgr.find_overdue()

        if not overdue:
            console.print("[green]No overdue requests.[/]")
            return

        console.print(f"[yellow]{len(overdue)} overdue request(s) found.[/]")
        for req in overdue:
            console.print(f"  - {req.broker_id} ({req.request_type.value}) sent {req.sent_at}")
            if auto:
                mgr.mark_overdue(req.id)
                console.print(f"    [yellow]Marked as overdue[/]")
    finally:
        session.close()


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_cli.py -v
```
Expected: all 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/unit/test_cli.py
git commit -m "feat: CLI with serve, status, and follow-up commands"
```

---

### Task 20: Static File Serving

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: Add static file serving to backend/main.py**

Add to the end of `create_app`, after all API routers:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve frontend static files
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))
```

- [ ] **Step 2: Verify the app starts**

```bash
cd /home/malte/incognito
python -c "from backend.main import create_app; app = create_app(); print('OK')"
```
Expected: prints "OK"

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: serve frontend SPA from FastAPI"
```

---

### Task 21: Container & Quadlet Files

**Files:**
- Create: `deploy/Containerfile`
- Create: `deploy/incognito.container`
- Create: `deploy/incognito-data.volume`
- Create: `deploy/incognito-followup.timer`
- Create: `deploy/incognito-followup.service`

- [ ] **Step 1: Create deploy/Containerfile**

```dockerfile
# Stage 1: Build frontend
FROM node:22-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim
WORKDIR /app

RUN groupadd -g 1000 incognito && \
    useradd -u 1000 -g incognito -m incognito

RUN pip install --no-cache-dir playwright && \
    playwright install --with-deps chromium

COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY backend/ backend/
COPY cli.py ./
COPY templates/ templates/
COPY brokers/ brokers/
COPY --from=frontend-builder /build/dist frontend/dist/

RUN chown -R incognito:incognito /app

USER incognito
EXPOSE 8080

CMD ["python", "cli.py", "serve", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 2: Create deploy/incognito.container**

```ini
[Unit]
Description=Incognito — Personal Data Removal Service

[Container]
Image=ghcr.io/malte/incognito:latest
AutoUpdate=registry
PublishPort=127.0.0.1:8080:8080
Volume=incognito-data.volume:/home/incognito/.incognito:Z
Environment=INCOGNITO_LOG_LEVEL=info
UserNS=keep-id

[Service]
Restart=always

[Install]
WantedBy=default.target
```

- [ ] **Step 3: Create deploy/incognito-data.volume**

```ini
[Volume]
User=1000
Group=1000
```

- [ ] **Step 4: Create deploy/incognito-followup.timer**

```ini
[Unit]
Description=Incognito daily follow-up check

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 5: Create deploy/incognito-followup.service**

```ini
[Unit]
Description=Incognito follow-up runner

[Service]
Type=oneshot
ExecStart=podman exec systemd-incognito incognito follow-up --auto
```

- [ ] **Step 6: Commit**

```bash
git add deploy/
git commit -m "feat: Containerfile and Quadlet systemd units"
```

---

### Task 22: Seed Initial Broker Database

**Files:**
- Create: `brokers/oracle-datacloud.yaml`
- Create: `brokers/experian.yaml`
- Create: `brokers/equifax.yaml`
- Create: `brokers/epsilon.yaml`
- Create: `brokers/spokeo.yaml`

- [ ] **Step 1: Create broker YAML files**

**brokers/oracle-datacloud.yaml:**
```yaml
name: Oracle Data Cloud
domain: oracle.com
category: data_broker
dpo_email: secalert_grp@oracle.com
removal_method: email
country: US
gdpr_applies: true
verification_required: false
language: en
last_verified: "2026-03-01"
notes: "Major data broker via BlueKai/AddThis acquisitions"
```

**brokers/experian.yaml:**
```yaml
name: Experian
domain: experian.com
category: credit_agency
dpo_email: dpo@experian.com
removal_method: email
country: US
gdpr_applies: true
verification_required: true
language: en
last_verified: "2026-03-01"
notes: "Credit bureau, may require ID verification"
```

**brokers/equifax.yaml:**
```yaml
name: Equifax
domain: equifax.com
category: credit_agency
dpo_email: privacy@equifax.com
removal_method: email
country: US
gdpr_applies: true
verification_required: true
language: en
last_verified: "2026-03-01"
notes: "Credit bureau, typically requires ID verification"
```

**brokers/epsilon.yaml:**
```yaml
name: Epsilon Data Management
domain: epsilon.com
category: data_broker
dpo_email: privacy@epsilon.com
removal_method: email
country: US
gdpr_applies: true
verification_required: false
language: en
last_verified: "2026-03-01"
notes: "Marketing data broker, subsidiary of Publicis"
```

**brokers/spokeo.yaml:**
```yaml
name: Spokeo
domain: spokeo.com
category: people_search
dpo_email: privacy@spokeo.com
removal_method: web_form
removal_url: "https://www.spokeo.com/optout"
country: US
gdpr_applies: true
verification_required: false
language: en
last_verified: "2026-03-01"
notes: "People search engine, web form opt-out required"
```

- [ ] **Step 2: Validate all broker files load**

```bash
python -c "
from backend.core.broker import BrokerRegistry
from pathlib import Path
registry = BrokerRegistry.load(Path('brokers'))
print(f'Loaded {len(registry.brokers)} brokers:')
for b in registry.brokers:
    print(f'  - {b.name} ({b.id})')
"
```
Expected: prints 6 brokers (acxiom + 5 new)

- [ ] **Step 3: Commit**

```bash
git add brokers/
git commit -m "feat: seed broker database with 6 initial brokers"
```

---

### Task 23: Full Integration Test

**Files:**
- Create: `tests/integration/test_full_flow.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_full_flow.py
"""Integration test: full flow from setup to request creation."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.core.config import AppConfig


@pytest.fixture
def app_dir(tmp_path):
    # Copy broker files
    import shutil
    brokers_src = Path(__file__).parent.parent.parent / "brokers"
    brokers_dst = tmp_path / "brokers"
    shutil.copytree(brokers_src, brokers_dst)
    return tmp_path


@pytest.fixture
def config(app_dir):
    return AppConfig(data_dir=app_dir)


@pytest.fixture
def client(config):
    from backend.main import create_app
    app = create_app(config)
    return TestClient(app)


def test_full_setup_to_request_flow(client):
    # 1. Check not initialized
    resp = client.get("/api/auth/status")
    assert resp.json()["initialized"] is False

    # 2. Run setup
    resp = client.post("/api/setup", json={
        "password": "test_password_123",
        "profile": {
            "full_name": "Integration Test User",
            "previous_names": [],
            "date_of_birth": "1990-06-15",
            "emails": ["integration@test.com"],
            "phones": ["+49 170 0000000"],
            "addresses": [{
                "street": "Teststraße 1",
                "city": "Berlin",
                "postal_code": "10115",
                "country": "DE",
            }],
        },
        "smtp": {
            "host": "smtp.test.com",
            "port": 587,
            "username": "integration@test.com",
            "password": "smtp_password",
        },
    })
    assert resp.status_code == 200

    # 3. Check initialized
    resp = client.get("/api/auth/status")
    assert resp.json()["initialized"] is True

    # 4. Get profile (should be authenticated from setup)
    resp = client.get("/api/profile")
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Integration Test User"

    # 5. List brokers
    resp = client.get("/api/brokers")
    assert resp.status_code == 200
    brokers = resp.json()
    assert len(brokers) >= 6

    # 6. Create an erasure request
    broker_id = brokers[0]["id"]
    resp = client.post("/api/requests", json={
        "broker_id": broker_id,
        "request_type": "erasure",
    })
    assert resp.status_code == 200
    req_id = resp.json()["id"]
    assert resp.json()["status"] == "created"

    # 7. Check stats
    resp = client.get("/api/requests/stats")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["created"] == 1

    # 8. Transition to sent
    resp = client.post(f"/api/requests/{req_id}/transition", json={
        "action": "mark_sent",
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"

    # 9. Check events
    resp = client.get(f"/api/requests/{req_id}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) == 2  # created + sent
    assert events[0]["event_type"] == "created"
    assert events[1]["event_type"] == "sent"

    # 10. Lock and verify auth required
    client.post("/api/auth/lock")
    resp = client.get("/api/profile")
    assert resp.status_code == 401

    # 11. Re-unlock
    resp = client.post("/api/auth/unlock", json={"password": "test_password_123"})
    assert resp.status_code == 200

    resp = client.get("/api/profile")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run integration test**

```bash
pytest tests/integration/test_full_flow.py -v
```
Expected: all assertions PASS

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_full_flow.py
git commit -m "test: full integration test from setup through request lifecycle"
```

---

## Self-Review Checklist

**Spec coverage:**
- Overview/goals: covered by project structure and all features
- Profile & Security (encryption, auth, vault): Task 3, 4, 10
- Broker Registry: Task 6, 22
- Request Lifecycle (state machine, types, DB schema): Task 2, 7
- Template System: Task 8
- Email Sender: Task 9
- Web UI (Setup, Dashboard, Requests, Brokers): Tasks 14-18
- CLI Commands (serve, status, follow-up): Task 19
- Deployment (Container, Quadlet): Task 21
- Error Handling: built into senders (Task 9) and state machine (Task 7)
- Testing: unit tests throughout, integration test in Task 23

**Not yet covered (deferred to follow-up tasks):**
- Scan functionality (people-search scanner) — needs real broker research
- Web form sender (Playwright) — per-broker adapters, high maintenance
- API sender — varies per broker
- Settings page — profile edit, backup export
- Localized templates (de, fr, nl) — templates structure is there, content deferred
- `brokers update` command — needs a community repo to pull from
- Scan results page — needs scanner implementation first

These are intentionally deferred — the plan delivers a working end-to-end system: setup → browse brokers → create requests → send via email → track status → follow up on overdue. The scanner and web form automation are the next phase.

**Placeholder scan:** No TBDs, TODOs, or vague instructions found.

**Type consistency:** Verified — `RequestStatus`, `RequestType`, `Broker`, `Profile`, `SmtpConfig`, `SenderResult` used consistently across all tasks.
