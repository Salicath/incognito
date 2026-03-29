import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.core.rescan import check_for_reappearances, save_scan_results
from backend.db.models import Base, Request, RequestStatus, RequestType


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_save_scan_results():
    session = make_session()
    hits = [
        {"broker_domain": "spokeo.com", "broker_name": "Spokeo", "snippet": "found", "url": "https://spokeo.com/x"},
        {"broker_domain": "acxiom.com", "broker_name": "Acxiom", "snippet": "profile", "url": "https://acxiom.com/y"},
    ]
    saved = save_scan_results(session, hits, source="duckduckgo")
    assert saved == 2
    session.close()


def test_detect_reappearance():
    session = make_session()

    # Create a completed (deleted) request for spokeo
    req = Request(
        id=str(uuid.uuid4()),
        broker_id="spokeo-com",
        request_type=RequestType.ERASURE,
        status=RequestStatus.COMPLETED,
        updated_at=datetime(2026, 2, 15, tzinfo=UTC),
    )
    session.add(req)
    session.commit()

    # Save a previous scan that found spokeo
    save_scan_results(session, [
        {"broker_domain": "spokeo-com", "broker_name": "Spokeo"},
    ])

    # New scan also finds spokeo — it reappeared!
    current_hits = [
        {"broker_domain": "spokeo-com", "broker_name": "Spokeo", "snippet": "back again", "url": "https://spokeo.com"},
    ]
    report = check_for_reappearances(session, current_hits)

    assert len(report.reappeared) == 1
    assert report.reappeared[0].broker_domain == "spokeo-com"
    assert report.reappeared[0].previous_removal_date == "2026-02-15"
    assert len(report.new_exposures) == 0
    session.close()


def test_detect_new_exposure():
    session = make_session()

    # No previous scan results, no requests
    current_hits = [
        {"broker_domain": "newbroker.com", "broker_name": "New Broker", "snippet": "found", "url": "https://new.com"},
    ]
    report = check_for_reappearances(session, current_hits)

    assert len(report.new_exposures) == 1
    assert report.new_exposures[0].broker_domain == "newbroker.com"
    assert len(report.reappeared) == 0
    session.close()


def test_no_alert_for_known_exposure():
    session = make_session()

    # Save a previous scan result for this broker
    save_scan_results(session, [
        {"broker_domain": "known.com", "broker_name": "Known"},
    ])

    # Same broker appears again — not new, not reappeared (no completed request)
    current_hits = [
        {"broker_domain": "known.com", "broker_name": "Known", "snippet": "still there", "url": "https://known.com"},
    ]
    report = check_for_reappearances(session, current_hits)

    assert len(report.new_exposures) == 0
    assert len(report.reappeared) == 0
    session.close()
