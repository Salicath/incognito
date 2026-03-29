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
    lower = result.lower()
    assert "supervisory authority" in lower or "data protection authority" in lower


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


def test_render_german_erasure_request(renderer, profile):
    result = renderer.render_localized(
        "erasure_request",
        "de",
        profile=profile,
        reference_id="REQ-003",
        broker_name="SCHUFA",
    )
    assert "Art. 17" in result or "Artikel 17" in result
    assert "DSGVO" in result
    assert "Malte Example" in result
    assert "SCHUFA" in result
    assert "REQ-003" in result


def test_render_german_access_request(renderer, profile):
    result = renderer.render_localized(
        "access_request",
        "de",
        profile=profile,
        reference_id="REQ-004",
        broker_name="Deutsche Post",
    )
    assert "Art. 15" in result or "Artikel 15" in result
    assert "DSGVO" in result
    assert "Deutsche Post" in result


def test_render_french_erasure_request(renderer, profile):
    result = renderer.render_localized(
        "erasure_request",
        "fr",
        profile=profile,
        reference_id="REQ-005",
        broker_name="Criteo",
    )
    assert "article 17" in result.lower()
    assert "RGPD" in result
    assert "Criteo" in result


def test_render_localized_fallback_to_english(renderer, profile):
    result = renderer.render_localized(
        "erasure_request",
        "xx",  # nonexistent locale
        profile=profile,
        reference_id="REQ-006",
        broker_name="Test",
    )
    assert "Article 17" in result  # English fallback
