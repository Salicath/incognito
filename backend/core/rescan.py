"""Re-scan monitoring — detect data reappearing after confirmed removal."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.db.models import Request, RequestStatus, ScanResult

log = logging.getLogger("incognito.rescan")


@dataclass
class RescanAlert:
    broker_domain: str
    broker_name: str
    snippet: str
    url: str
    previous_removal_date: str | None


@dataclass
class RescanReport:
    new_exposures: list[RescanAlert] = field(default_factory=list)
    reappeared: list[RescanAlert] = field(default_factory=list)
    total_checked: int = 0
    scan_date: str = ""


def save_scan_results(
    session: Session,
    hits: list[dict],
    source: str = "duckduckgo",
) -> int:
    """Persist scan results to the database. Returns number saved."""
    saved = 0
    for hit in hits:
        result = ScanResult(
            source=source,
            broker_id=hit.get("broker_domain", ""),
            found_data=json.dumps(hit),
            scanned_at=datetime.now(UTC),
        )
        session.add(result)
        saved += 1
    session.commit()
    return saved


def check_for_reappearances(
    session: Session,
    current_hits: list[dict],
) -> RescanReport:
    """Compare current scan hits against completed requests to detect reappearances."""
    report = RescanReport(
        total_checked=len(current_hits),
        scan_date=datetime.now(UTC).isoformat(),
    )

    # Get all completed (deleted) requests — these brokers should no longer have data
    completed = (
        session.query(Request)
        .filter(Request.status == RequestStatus.COMPLETED)
        .all()
    )
    completed_broker_ids = {r.broker_id for r in completed}
    completed_dates = {
        r.broker_id: r.updated_at.strftime("%Y-%m-%d") if r.updated_at else None
        for r in completed
    }

    # Get broker IDs that had previous scan hits
    previous_results = session.query(ScanResult).all()
    previously_seen = {r.broker_id for r in previous_results}

    for hit in current_hits:
        domain = hit.get("broker_domain", "")
        alert = RescanAlert(
            broker_domain=domain,
            broker_name=hit.get("broker_name", domain),
            snippet=hit.get("snippet", ""),
            url=hit.get("url", ""),
            previous_removal_date=None,
        )

        if domain in completed_broker_ids:
            # Data reappeared after confirmed deletion
            alert.previous_removal_date = completed_dates.get(domain)
            report.reappeared.append(alert)
            log.warning(
                "Data reappeared on %s after removal on %s",
                domain, alert.previous_removal_date,
            )
        elif domain not in previously_seen:
            # New exposure not seen in previous scans
            report.new_exposures.append(alert)

    return report
