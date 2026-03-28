from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException

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

    _state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "progress": 0,
        "total": 0,
        "error": None,
    }

    # Auto-clear stuck scans after 10 minutes
    STUCK_TIMEOUT = 600

    def _is_stuck() -> bool:
        if not _state["running"]:
            return False
        return (time.time() - _state["started_at"]) > STUCK_TIMEOUT

    async def _run_scan(profile, broker_domains):
        try:
            def on_progress(checked, total):
                _state["progress"] = checked
                _state["total"] = total

            report = await scan_profile(profile, broker_domains, on_progress=on_progress)
            _state["report"] = report
            _state["error"] = None
        except Exception as e:
            _state["error"] = str(e)
        finally:
            _state["running"] = False

    @r.post("/start")
    async def start_scan(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
    ):
        password = session_store.validate(session)
        profile, _ = vault.load(password)

        if _state["running"] and not _is_stuck():
            raise HTTPException(status_code=409, detail="Scan already running")

        _state["running"] = True
        _state["started_at"] = time.time()
        _state["progress"] = 0
        _state["error"] = None

        broker_domains = [(b.domain, b.name) for b in broker_registry.brokers]
        _state["total"] = len(broker_domains) + len(profile.emails)

        # Run in background so the request returns immediately
        background_tasks.add_task(_run_scan, profile, broker_domains)

        return {
            "status": "started",
            "total": _state["total"],
        }

    @r.get("/results")
    def get_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)

        report = _state.get("report")
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
        running = _state["running"] and not _is_stuck()
        return {
            "running": running,
            "progress": _state["progress"],
            "total": _state["total"],
            "error": _state.get("error"),
        }

    return r
