from datetime import date

import pytest
import yaml

from backend.core.config import AppConfig
from backend.core.profile import Address, ImapConfig, Profile, ProfileVault, SmtpConfig


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Create a temporary data directory."""
    return tmp_path


@pytest.fixture
def sample_profile():
    """A standard test profile."""
    return Profile(
        full_name="Test User",
        previous_names=[],
        date_of_birth=date(1990, 1, 1),
        emails=["test@example.com"],
        phones=["+49 170 0000000"],
        addresses=[
            Address(street="Teststraße 1", city="Berlin", postal_code="10115", country="DE")
        ],
    )


@pytest.fixture
def sample_smtp():
    """A standard test SMTP config."""
    return SmtpConfig(
        host="smtp.test.com",
        port=587,
        username="test@test.com",
        password="test_password",
    )


@pytest.fixture
def sample_imap():
    return ImapConfig(host="imap.test.com", port=993, username="test@test.com", password="test_password")


@pytest.fixture
def config(tmp_data_dir):
    """AppConfig pointing to a temp directory."""
    return AppConfig(data_dir=tmp_data_dir)


@pytest.fixture
def config_with_brokers(tmp_data_dir):
    """AppConfig with a brokers directory containing test brokers."""
    brokers_dir = tmp_data_dir / "brokers"
    brokers_dir.mkdir()
    for i in range(3):
        broker = {
            "name": f"Test Broker {i}",
            "domain": f"broker{i}.com",
            "category": "data_broker",
            "dpo_email": f"dpo@broker{i}.com",
            "removal_method": "email",
            "country": "DE",
            "gdpr_applies": True,
            "verification_required": False,
            "language": "en",
            "last_verified": "2026-03-01",
        }
        (brokers_dir / f"broker{i}.yaml").write_text(yaml.dump(broker))
    return AppConfig(data_dir=tmp_data_dir)


@pytest.fixture
def seeded_vault(config, sample_profile, sample_smtp):
    """A vault pre-populated with test profile and SMTP."""
    vault = ProfileVault(config.vault_path)
    vault.save(sample_profile, sample_smtp, "test_password")
    return vault


@pytest.fixture
def authenticated_client(config, seeded_vault):
    """A TestClient that is already authenticated."""
    from fastapi.testclient import TestClient

    from backend.main import create_app

    app = create_app(config)
    client = TestClient(app)
    client.post("/api/auth/unlock", json={"password": "test_password"})
    return client
