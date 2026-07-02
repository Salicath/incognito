"""API secret storage backed by the encrypted vault, with legacy-file migration.

HIBP keys and GitHub tokens used to live as plaintext files in the data dir
(0600). They now live inside the AES-256-GCM vault alongside the profile.
On first access after upgrade, any leftover plaintext file is imported into
the vault and then deleted — so existing installs migrate transparently.
"""

from __future__ import annotations

from pathlib import Path

from backend.core.profile import ProfileVault

# secret name -> the legacy plaintext filename it used to live in
LEGACY_FILES = {
    "hibp": "hibp_key.txt",
    "github": "github_token.txt",
}


def read_secret(
    vault: ProfileVault, data_dir: Path, key: bytes, salt: bytes, name: str
) -> str | None:
    """Return the secret, migrating a legacy plaintext file into the vault if found."""
    value = vault.get_secret(name, key)
    if value:
        return value

    legacy = data_dir / LEGACY_FILES[name]
    if legacy.exists():
        migrated = legacy.read_text().strip()
        if migrated:
            vault.set_secret(name, migrated, key, salt)
        legacy.unlink(missing_ok=True)
        return migrated or None
    return None


def write_secret(vault: ProfileVault, key: bytes, salt: bytes, name: str, value: str) -> None:
    vault.set_secret(name, value, key, salt)


def remove_secret(
    vault: ProfileVault, data_dir: Path, key: bytes, salt: bytes, name: str
) -> None:
    vault.delete_secret(name, key, salt)
    # Also clear any legacy file that predates the vault migration.
    (data_dir / LEGACY_FILES[name]).unlink(missing_ok=True)
