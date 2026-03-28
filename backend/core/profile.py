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
