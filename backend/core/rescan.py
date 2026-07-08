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


def _normalize_url(url: str) -> str:
    """Scheme/www/trailing-slash-insensitive form for delisted-URL comparison."""
    u = url.strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix):]
            break
    if u.startswith("www."):
        u = u[4:]
    return u.rstrip("/")


async def verify_delisted_urls(
    session: Session, profile, region: str | None = "dk-da",
) -> list[RescanAlert]:
    """Re-verify granted delistings with bare name queries.

    The broker rescan only issues '"name" site:<broker>' queries, so a
    delisted news article on a non-broker domain never enters its hit list.
    This check searches the name directly (region-scoped — the EU RTBF filter
    is market-scoped, C-507/17) and flags any COMPLETED delisting whose URL
    resurfaces. Delisting is exact-URL: same content at a new URL needs a new
    request, not an alert here.
    """
    import httpx

    from backend.scanner.duckduckgo import _search_ddg

    delisted = (
        session.query(Request)
        .filter(
            Request.status == RequestStatus.COMPLETED,
            Request.broker_id.like("delisting-%"),
            Request.target_url.isnot(None),
        )
        .all()
    )
    if not delisted:
        return []

    targets: dict[str, Request] = {}
    for row in delisted:
        targets[_normalize_url(row.target_url or "")] = row

    names = [profile.full_name, *profile.previous_names] if profile.full_name else list(
        profile.previous_names
    )
    alerts: list[RescanAlert] = []
    flagged: set[str] = set()
    async with httpx.AsyncClient() as client:
        for name in [n for n in names if n]:
            try:
                results = await _search_ddg(f'"{name}"', client, region=region)
            except RuntimeError as exc:
                log.warning("Delisting re-verification query failed: %s", exc)
                continue
            for res in results:
                norm = _normalize_url(res.get("url", ""))
                hit_req = targets.get(norm) or targets.get(norm.split("?")[0])
                if hit_req is None or hit_req.id in flagged:
                    continue
                flagged.add(hit_req.id)
                alerts.append(RescanAlert(
                    broker_domain=norm.split("/")[0] if norm else "",
                    broker_name=f"Delisted URL resurfaced ({hit_req.broker_id})",
                    snippet=res.get("snippet", ""),
                    url=res.get("url", ""),
                    previous_removal_date=(
                        hit_req.updated_at.strftime("%Y-%m-%d")
                        if hit_req.updated_at else None
                    ),
                ))

    if alerts:
        from backend.core.notifier import EventType, notify
        for alert in alerts:
            notify(
                EventType.DATA_REAPPEARED,
                "Delisted URL resurfaced in name search",
                f"{alert.url} is back in name-query results "
                f"(delisted {alert.previous_removal_date}). Re-file citing the "
                "prior grant.",
            )
    return alerts


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
    notify_alerts: bool = True,
) -> RescanReport:
    """Compare current scan hits against completed requests to detect reappearances.

    notify_alerts=False for read-only callers (the web /rescan GET is polled on
    every page view — pushing a DATA_REAPPEARED notification each time is spam).
    """
    report = RescanReport(
        total_checked=len(current_hits),
        scan_date=datetime.now(UTC).isoformat(),
    )

    # Get all completed (deleted) requests — these brokers should no longer have data
    completed = (
        session.query(Request.broker_id, Request.updated_at)
        .filter(Request.status == RequestStatus.COMPLETED)
        .all()
    )
    completed_broker_ids = {r.broker_id for r in completed}
    completed_dates = {
        r.broker_id: r.updated_at.strftime("%Y-%m-%d") if r.updated_at else None
        for r in completed
    }

    # Successfully delisted URLs should not resurface in name-search results.
    # (The broker scan's hits are site:-scoped so this branch rarely fires on
    # its own — verify_delisted_urls below runs the bare name queries.)
    delisted_rows = (
        session.query(Request.broker_id, Request.target_url, Request.updated_at)
        .filter(
            Request.status == RequestStatus.COMPLETED,
            Request.broker_id.like("delisting-%"),
            Request.target_url.isnot(None),
        )
        .all()
    )
    delisted_urls = {
        _normalize_url(r.target_url): (
            r.broker_id,
            r.updated_at.strftime("%Y-%m-%d") if r.updated_at else None,
        )
        for r in delisted_rows
    }

    # Get broker IDs that had previous scan hits (only fetch the column we need)
    previously_seen = {
        r[0] for r in session.query(ScanResult.broker_id).distinct().all()
    }

    for hit in current_hits:
        domain = hit.get("broker_domain", "")
        alert = RescanAlert(
            broker_domain=domain,
            broker_name=hit.get("broker_name", domain),
            snippet=hit.get("snippet", ""),
            url=hit.get("url", ""),
            previous_removal_date=None,
        )

        hit_url = _normalize_url(hit.get("url") or "")
        if hit_url and hit_url in delisted_urls:
            engine_id, removal_date = delisted_urls[hit_url]
            alert.broker_name = f"Delisted URL resurfaced ({engine_id})"
            alert.previous_removal_date = removal_date
            report.reappeared.append(alert)
            log.warning(
                "Delisted URL resurfaced in name search: %s (delisted %s via %s)",
                hit_url, removal_date, engine_id,
            )
        elif domain in completed_broker_ids:
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

    # Send notifications for alerts
    if notify_alerts and (report.reappeared or report.new_exposures):
        from backend.core.notifier import EventType, notify
        for alert in report.reappeared:
            notify(
                EventType.DATA_REAPPEARED,
                f"Data reappeared: {alert.broker_name}",
                f"Your data was found again on {alert.broker_domain} "
                f"(removed {alert.previous_removal_date}).",
            )
        for alert in report.new_exposures:
            notify(
                EventType.NEW_EXPOSURE,
                f"New exposure: {alert.broker_name}",
                f"Your data was found on {alert.broker_domain}: {alert.snippet[:100]}",
            )

    return report
