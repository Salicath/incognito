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
