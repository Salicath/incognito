from datetime import date
from pathlib import Path

from pydantic import BaseModel

from backend.core.crypto import EncryptedPayload, decrypt, derive_key, encrypt


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
    previous_names: list[str] = []
    date_of_birth: date | None = None
    emails: list[str]
    phones: list[str] = []
    addresses: list[Address] = []


class SmtpConfig(BaseModel):
    host: str
    port: int
    username: str
    password: str


class _VaultData(BaseModel):
    profile: Profile
    smtp: SmtpConfig | None = None


class ProfileVault:
    def __init__(self, path: Path):
        self._path = path

    def exists(self) -> bool:
        return self._path.exists()

    def save(self, profile: Profile, smtp: SmtpConfig | None = None, password: str = "") -> None:
        key, salt = derive_key(password, return_salt=True)
        self.save_with_key(profile, smtp, key, salt)

    def create_initial(
        self, profile: Profile, smtp: SmtpConfig | None, password: str,
    ) -> None:
        """Atomically create the vault. Raises FileExistsError if it already exists."""
        import os

        key, salt = derive_key(password, return_salt=True)
        vault_data = _VaultData(profile=profile, smtp=smtp)
        plaintext = vault_data.model_dump_json().encode("utf-8")
        payload = encrypt(plaintext, key)
        data = salt + payload.to_bytes()

        self._path.parent.mkdir(parents=True, exist_ok=True)
        # O_CREAT | O_EXCL: fails atomically if file already exists
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)

    def save_with_key(
        self,
        profile: Profile,
        smtp: SmtpConfig | None,
        key: bytes,
        salt: bytes,
    ) -> None:
        import os

        vault_data = _VaultData(profile=profile, smtp=smtp)
        plaintext = vault_data.model_dump_json().encode("utf-8")

        payload = encrypt(plaintext, key)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_bytes(salt + payload.to_bytes())

        # Restrict vault file permissions (owner-only read/write)
        os.chmod(self._path, 0o600)

    def load(self, password: str) -> tuple[Profile, SmtpConfig | None]:
        key, salt = self.derive_key_from_file(password)
        return self.load_with_key(key)

    def derive_key_from_file(self, password: str) -> tuple[bytes, bytes]:
        """Derive the encryption key from password and stored salt."""
        raw = self._path.read_bytes()
        salt = raw[:16]
        key = derive_key(password, salt=salt)
        return key, salt

    def load_with_key(self, key: bytes) -> tuple[Profile, SmtpConfig | None]:
        """Load vault using a pre-derived key (avoids re-deriving from password)."""
        raw = self._path.read_bytes()
        payload = EncryptedPayload.from_bytes(raw[16:])
        plaintext = decrypt(payload, key)
        vault_data = _VaultData.model_validate_json(plaintext)
        return vault_data.profile, vault_data.smtp
