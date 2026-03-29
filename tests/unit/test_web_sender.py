"""Tests for the web form sender."""
from datetime import date

import yaml

from backend.core.profile import Address, Profile
from backend.senders.base import SenderStatus
from backend.senders.web import (
    FormDefinition,
    FormRegistry,
    FormStep,
    WebFormSender,
    _resolve_value,
)


def _make_profile():
    return Profile(
        full_name="Test User",
        previous_names=[],
        date_of_birth=date(1990, 1, 15),
        emails=["test@example.com"],
        phones=["+1 555 0100"],
        addresses=[
            Address(street="123 Test St", city="Berlin", postal_code="10115", country="DE")
        ],
    )


def test_resolve_value_full_name():
    profile = _make_profile()
    assert _resolve_value("{profile.full_name}", profile) == "Test User"


def test_resolve_value_email():
    profile = _make_profile()
    assert _resolve_value("{profile.email}", profile) == "test@example.com"


def test_resolve_value_address():
    profile = _make_profile()
    assert _resolve_value("{profile.city}", profile) == "Berlin"
    assert _resolve_value("{profile.postal_code}", profile) == "10115"


def test_resolve_value_dob():
    profile = _make_profile()
    assert _resolve_value("{profile.dob}", profile) == "1990-01-15"


def test_resolve_value_combined():
    profile = _make_profile()
    result = _resolve_value(
        "Name: {profile.full_name}, Email: {profile.email}", profile,
    )
    assert result == "Name: Test User, Email: test@example.com"


def test_resolve_value_no_template():
    profile = _make_profile()
    assert _resolve_value("plain text", profile) == "plain text"


def test_form_registry_load(tmp_path):
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir()

    form_data = {
        "broker_domain": "example.com",
        "url": "https://example.com/optout",
        "verify_selector": ".success",
        "steps": [
            {"action": "fill", "selector": "#name", "value": "{profile.full_name}"},
            {"action": "click", "selector": "button[type=submit]"},
        ],
    }
    (forms_dir / "example-com.yaml").write_text(yaml.dump(form_data))

    registry = FormRegistry(forms_dir)
    assert "example.com" in registry.domains

    form = registry.get("example.com")
    assert form is not None
    assert form.url == "https://example.com/optout"
    assert len(form.steps) == 2
    assert form.steps[0].action == "fill"
    assert form.steps[0].value == "{profile.full_name}"


def test_form_registry_empty_dir(tmp_path):
    registry = FormRegistry(tmp_path / "nonexistent")
    assert len(registry.domains) == 0


def test_form_registry_skips_invalid(tmp_path):
    forms_dir = tmp_path / "forms"
    forms_dir.mkdir()
    (forms_dir / "bad.yaml").write_text("not: a: valid: form")
    registry = FormRegistry(forms_dir)
    assert len(registry.domains) == 0


async def test_web_sender_no_definition():
    """Without a form definition, returns MANUAL_NEEDED."""
    profile = _make_profile()
    sender = WebFormSender(profile)
    result = await sender.send("unknown.com", "https://unknown.com/optout")
    assert result.status == SenderStatus.MANUAL_NEEDED
    assert "No form automation" in result.message


async def test_web_sender_no_playwright():
    """Without playwright installed, returns MANUAL_NEEDED."""
    from unittest.mock import patch

    profile = _make_profile()

    form_def = FormDefinition(
        broker_domain="test.com",
        url="https://test.com/optout",
        steps=[FormStep(action="click", selector="button")],
    )

    sender = WebFormSender(profile)
    sender._registry._forms["test.com"] = form_def

    with patch("importlib.util.find_spec", return_value=None):
        result = await sender.send("test.com", "https://test.com/optout")

    assert result.status == SenderStatus.MANUAL_NEEDED
    assert "Playwright not installed" in result.message


def test_form_step_defaults():
    step = FormStep(action="fill", selector="#name")
    assert step.value == ""
    assert step.timeout == 10000
