from __future__ import annotations

import asyncio

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry
from backend.core.profile import ProfileVault
from backend.scanner.duckduckgo import scan_profile, ScanReport


def create_scan_router(
    vault: ProfileVault,
    session_store: SessionStore,
    broker_registry: BrokerRegistry,
) -> APIRouter:
    r = APIRouter(prefix="/api/scan", tags=["scan"])

    # Store latest scan results in memory
    _latest_report: dict[str, ScanReport | None] = {"report": None, "running": False}

    @r.post("/start")
    async def start_scan(session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        profile, _ = vault.load(password)

        if _latest_report.get("running"):
            raise HTTPException(status_code=409, detail="Scan already running")

        _latest_report["running"] = True

        broker_domains = [(b.domain, b.name) for b in broker_registry.brokers]

        try:
            report = await scan_profile(profile, broker_domains)
            _latest_report["report"] = report
        finally:
            _latest_report["running"] = False

        return {
            "status": "completed",
            "hits": len(report.hits),
            "checked": report.checked,
        }

    @r.get("/results")
    def get_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)

        report = _latest_report.get("report")
        if report is None:
            return {"hits": [], "checked": 0, "has_results": False}

        return {
            "has_results": True,
            "checked": report.checked,
            "hits": [
                {
                    "broker_domain": hit.broker_domain,
                    "broker_name": hit.broker_name,
                    "snippet": hit.snippet,
                    "url": hit.url,
                }
                for hit in report.hits
            ],
        }

    @r.get("/status")
    def scan_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        return {"running": _latest_report.get("running", False)}

    return r
