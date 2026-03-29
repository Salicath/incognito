from datetime import date
from pathlib import Path

import cryptography.exceptions
import pytest

from backend.core.profile import Address, Profile, ProfileVault, SmtpConfig


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

    loaded_profile, loaded_smtp, _ = vault.load(password)
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

    with pytest.raises(cryptography.exceptions.InvalidTag):
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


def test_vault_save_without_smtp(tmp_path: Path):
    vault_path = tmp_path / "profile.enc"
    password = "test_master_password"

    profile = Profile(
        full_name="No SMTP User",
        previous_names=[],
        date_of_birth=date(1995, 3, 10),
        emails=["nosmtp@test.com"],
        phones=[],
        addresses=[],
    )

    vault = ProfileVault(vault_path)
    vault.save(profile, smtp=None, password=password)

    assert vault_path.exists()

    loaded_profile, loaded_smtp, _ = vault.load(password)
    assert loaded_profile == profile
    assert loaded_smtp is None


def test_address_formatted():
    addr = Address(street="Beispielstraße 42", city="Berlin", postal_code="10115", country="DE")
    assert "Beispielstraße 42" in addr.formatted
    assert "Berlin" in addr.formatted
    assert "10115" in addr.formatted
    assert "DE" in addr.formatted


def test_vault_rejects_empty_password(tmp_path: Path):
    vault = ProfileVault(tmp_path / "profile.enc")
    profile = Profile(
        full_name="Test", previous_names=[], emails=["t@t.com"],
    )
    with pytest.raises(ValueError, match="Password must not be empty"):
        vault.save(profile, password="")

    with pytest.raises(ValueError, match="Password must not be empty"):
        vault.create_initial(profile, smtp=None, password="")
