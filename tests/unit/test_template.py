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
