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
    usernames: list[str] = []  # handles/aliases for account + archive scanners


class SmtpConfig(BaseModel):
    host: str
    port: int
    username: str
    password: str


class ImapConfig(BaseModel):
    host: str
    port: int = 993
    username: str
    password: str
    folder: str = "INBOX"
    poll_interval_minutes: int = 5
    # True for Proton Bridge (port 1143), False for standard IMAPS (port 993)
    starttls: bool = False


class _VaultData(BaseModel):
    profile: Profile
    smtp: SmtpConfig | None = None
    imap: ImapConfig | None = None
    # API keys/tokens (HIBP, GitHub) — encrypted at rest alongside the profile
    secrets: dict[str, str] = {}


class ProfileVault:
    def __init__(self, path: Path):
        self._path = path

    def exists(self) -> bool:
        return self._path.exists()

    def save(
        self, profile: Profile, smtp: SmtpConfig | None = None,
        password: str = "", *, imap: ImapConfig | None = None,
    ) -> None:
        if not password:
            raise ValueError("Password must not be empty")
        key, salt = derive_key(password, return_salt=True)
        self.save_with_key(profile, smtp, imap, key, salt)

    def create_initial(
        self, profile: Profile, smtp: SmtpConfig | None, password: str,
        imap: ImapConfig | None = None,
    ) -> None:
        """Atomically create the vault. Raises FileExistsError if it already exists."""
        import os

        if not password:
            raise ValueError("Password must not be empty")
        key, salt = derive_key(password, return_salt=True)
        vault_data = _VaultData(profile=profile, smtp=smtp, imap=imap)
        plaintext = vault_data.model_dump_json().encode("utf-8")
        payload = encrypt(plaintext, key)
        data = salt + payload.to_bytes()

        self._path.parent.mkdir(parents=True, exist_ok=True)
        # O_CREAT | O_EXCL: fails atomically if file already exists (portable)
        fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.write(fd, data)
        except BaseException:
            os.close(fd)
            # Clean up partial write so retry is possible
            self._path.unlink(missing_ok=True)
            raise
        os.close(fd)

    def save_with_key(
        self,
        profile: Profile,
        smtp: SmtpConfig | None,
        imap: ImapConfig | None,
        key: bytes,
        salt: bytes,
    ) -> None:
        # Preserve any stored secrets across an ordinary profile/smtp/imap save,
        # since callers don't pass them in.
        secrets: dict[str, str] = {}
        if self._path.exists():
            try:
                secrets = self._load_all(key)[3]
            except Exception:
                secrets = {}
        self._write(profile, smtp, imap, secrets, key, salt)

    def _write(
        self,
        profile: Profile,
        smtp: SmtpConfig | None,
        imap: ImapConfig | None,
        secrets: dict[str, str],
        key: bytes,
        salt: bytes,
    ) -> None:
        import os

        vault_data = _VaultData(profile=profile, smtp=smtp, imap=imap, secrets=secrets)
        plaintext = vault_data.model_dump_json().encode("utf-8")
        payload = encrypt(plaintext, key)

        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to temp file then rename (prevents corruption on crash)
        tmp_path = self._path.with_suffix(".tmp")
        fd = os.open(str(tmp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, salt + payload.to_bytes())
        finally:
            os.close(fd)
        os.replace(tmp_path, self._path)

    def load(self, password: str) -> tuple[Profile, SmtpConfig | None, ImapConfig | None]:
        key, salt = self.derive_key_from_file(password)
        return self.load_with_key(key)

    def derive_key_from_file(self, password: str) -> tuple[bytes, bytes]:
        """Derive the encryption key from password and stored salt."""
        raw = self._path.read_bytes()
        salt = raw[:16]
        key = derive_key(password, salt=salt)
        return key, salt

    def _load_all(
        self, key: bytes
    ) -> tuple[Profile, SmtpConfig | None, ImapConfig | None, dict[str, str]]:
        raw = self._path.read_bytes()
        payload = EncryptedPayload.from_bytes(raw[16:])
        plaintext = decrypt(payload, key)
        vault_data = _VaultData.model_validate_json(plaintext)
        return vault_data.profile, vault_data.smtp, vault_data.imap, dict(vault_data.secrets)

    def load_with_key(self, key: bytes) -> tuple[Profile, SmtpConfig | None, ImapConfig | None]:
        """Load vault using a pre-derived key (avoids re-deriving from password)."""
        profile, smtp, imap, _ = self._load_all(key)
        return profile, smtp, imap

    def get_secret(self, name: str, key: bytes) -> str | None:
        """Read an encrypted secret (API key/token) by name, or None."""
        return self._load_all(key)[3].get(name) or None

    def set_secret(self, name: str, value: str, key: bytes, salt: bytes) -> None:
        profile, smtp, imap, secrets = self._load_all(key)
        secrets[name] = value
        self._write(profile, smtp, imap, secrets, key, salt)

    def delete_secret(self, name: str, key: bytes, salt: bytes) -> bool:
        profile, smtp, imap, secrets = self._load_all(key)
        existed = secrets.pop(name, None) is not None
        if existed:
            self._write(profile, smtp, imap, secrets, key, salt)
        return existed
