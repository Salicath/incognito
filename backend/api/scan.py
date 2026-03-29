from __future__ import annotations

import logging
import time

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry
from backend.core.profile import ProfileVault
from backend.scanner.duckduckgo import scan_profile

log = logging.getLogger("incognito.scan")


def create_scan_router(
    vault: ProfileVault,
    session_store: SessionStore,
    broker_registry: BrokerRegistry,
    config=None,  # Add this
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
    stuck_timeout = 600

    def _is_stuck() -> bool:
        if not _state["running"]:
            return False
        return (time.time() - _state["started_at"]) > stuck_timeout

    async def _run_scan(profile, broker_domains):
        try:
            def on_progress(checked, total):
                _state["progress"] = checked
                _state["total"] = total

            report = await scan_profile(profile, broker_domains, on_progress=on_progress)
            _state["report"] = report
            _state["error"] = None
        except Exception as e:
            log.error("DuckDuckGo scan failed: %s", e)
            _state["error"] = "Scan failed. Check logs for details."
        finally:
            _state["running"] = False

    @r.post("/start")
    async def start_scan(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
    ):
        key, _salt = session_store.validate(session)
        profile, _ = vault.load_with_key(key)

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

    # Account scan state (Holehe)
    _account_state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "progress": 0,
        "total": 0,
        "error": None,
    }

    async def _run_account_scan(email: str):
        try:
            from backend.scanner.holehe_scanner import check_email_accounts

            def on_progress(checked, total):
                _account_state["progress"] = checked
                _account_state["total"] = total

            report = await check_email_accounts(email, on_progress=on_progress)
            _account_state["report"] = report
            _account_state["error"] = None
        except Exception as e:
            log.error("Account scan failed: %s", e)
            _account_state["error"] = "Account scan failed. Check logs for details."
        finally:
            _account_state["running"] = False

    @r.post("/accounts/start")
    async def start_account_scan(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
        email: str | None = None,
    ):
        key, _salt = session_store.validate(session)
        profile, _ = vault.load_with_key(key)

        elapsed = time.time() - _account_state["started_at"]
        if _account_state["running"] and not (elapsed > stuck_timeout):
            raise HTTPException(status_code=409, detail="Account scan already running")

        target_email = email
        if not target_email:
            if not profile.emails:
                raise HTTPException(status_code=400, detail="No email addresses provided")
            target_email = profile.emails[0]

        _account_state["running"] = True
        _account_state["started_at"] = time.time()
        _account_state["progress"] = 0
        _account_state["error"] = None

        background_tasks.add_task(_run_account_scan, target_email)

        return {"status": "started", "email": target_email}

    @r.get("/accounts/results")
    def get_account_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)

        report = _account_state.get("report")
        if report is None:
            return {"hits": [], "checked": 0, "has_results": False, "email": ""}

        return {
            "has_results": True,
            "email": report.email,
            "checked": report.checked,
            "hits": [
                {
                    "service": hit.service,
                    "url": hit.url,
                }
                for hit in report.hits
            ],
            "errors": report.errors,
        }

    @r.get("/accounts/status")
    def account_scan_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        elapsed = time.time() - _account_state["started_at"]
        running = _account_state["running"] and not (elapsed > stuck_timeout)
        return {
            "running": running,
            "progress": _account_state["progress"],
            "total": _account_state["total"],
            "error": _account_state.get("error"),
        }

    # HIBP breach check state
    _breach_state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "error": None,
    }

    async def _run_breach_check(email: str, api_key: str):
        try:
            from backend.scanner.hibp import check_breaches
            report = await check_breaches(email, api_key)
            _breach_state["report"] = report
            _breach_state["error"] = report.error
        except Exception as e:
            log.error("Breach check failed: %s", e)
            _breach_state["error"] = "Breach check failed. Check logs for details."
        finally:
            _breach_state["running"] = False

    @r.post("/breaches/start")
    async def start_breach_check(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
        email: str | None = None,
    ):
        key, _salt = session_store.validate(session)
        profile, _ = vault.load_with_key(key)

        # Read HIBP key from file
        from backend.core.config import AppConfig
        effective_config = config if config is not None else AppConfig()
        key_path = effective_config.data_dir / "hibp_key.txt"
        if not key_path.exists():
            raise HTTPException(
                status_code=400,
                detail="HIBP API key not configured. Add it in Settings.",
            )
        api_key = key_path.read_text().strip()

        elapsed = time.time() - _breach_state["started_at"]
        if _breach_state["running"] and not (elapsed > stuck_timeout):
            raise HTTPException(status_code=409, detail="Breach check already running")

        target_email = email or (profile.emails[0] if profile.emails else None)
        if not target_email:
            raise HTTPException(status_code=400, detail="No email provided")

        _breach_state["running"] = True
        _breach_state["started_at"] = time.time()
        _breach_state["error"] = None

        background_tasks.add_task(_run_breach_check, target_email, api_key)

        return {"status": "started", "email": target_email}

    @r.get("/breaches/results")
    def get_breach_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        report = _breach_state.get("report")
        if report is None:
            return {"has_results": False, "breaches": [], "email": "", "error": None}
        return {
            "has_results": True,
            "email": report.email,
            "total_breaches": report.total_breaches,
            "breaches": [
                {
                    "name": b.name,
                    "title": b.title,
                    "domain": b.domain,
                    "breach_date": b.breach_date,
                    "pwn_count": b.pwn_count,
                    "data_classes": b.data_classes,
                }
                for b in report.breaches
            ],
            "error": report.error,
        }

    @r.get("/breaches/status")
    def breach_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        elapsed = time.time() - _breach_state["started_at"]
        running = _breach_state["running"] and not (elapsed > stuck_timeout)
        return {"running": running, "error": _breach_state.get("error")}

    return r
