from __future__ import annotations

import asyncio
import logging
import re
import time

from fastapi import APIRouter, BackgroundTasks, Cookie, HTTPException

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry
from backend.core.profile import ProfileVault
from backend.db.models import ScanResult
from backend.scanner.duckduckgo import scan_profile

log = logging.getLogger("incognito.scan")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _safe_json(text: str):
    """Parse JSON string safely, returning raw text on failure."""
    import json
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text


def _validate_email(email: str | None) -> str | None:
    """Validate email format if provided. Returns cleaned email or raises."""
    if email is None:
        return None
    email = email.strip()
    if not email:
        return None
    if not _EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(status_code=400, detail="Invalid email format")
    return email


def create_scan_router(
    vault: ProfileVault,
    session_store: SessionStore,
    broker_registry: BrokerRegistry,
    config=None,
    db_session_factory=None,
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
    _scan_lock = asyncio.Lock()

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

            # Persist scan results to DB for re-scan comparison
            if db_session_factory and report.hits:
                from backend.core.rescan import save_scan_results
                db = db_session_factory()
                try:
                    hits = [
                        {
                            "broker_domain": h.broker_domain,
                            "broker_name": h.broker_name,
                            "snippet": h.snippet,
                            "url": h.url,
                        }
                        for h in report.hits
                    ]
                    save_scan_results(db, hits, source="duckduckgo")
                finally:
                    db.close()
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
        profile, _, _ = vault.load_with_key(key)

        async with _scan_lock:
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
        "email": "",
    }
    _account_lock = asyncio.Lock()

    async def _run_account_scan(email: str):
        try:
            from backend.scanner.user_scanner import check_email_accounts

            def on_progress(checked, total):
                _account_state["progress"] = checked
                _account_state["total"] = total

            report = await check_email_accounts(email, on_progress=on_progress)
            _account_state["report"] = report
            _account_state["error"] = None

            # Persist per-email so the history survives the next scan overwriting in-memory state
            if db_session_factory and report.hits:
                from backend.core.rescan import save_scan_results
                db = db_session_factory()
                try:
                    hits = [
                        {
                            "broker_domain": h.url,
                            "broker_name": h.service,
                            "email": report.email,
                            "url": h.url,
                            "email_recovery": h.email_recovery,
                            "phone_recovery": h.phone_recovery,
                        }
                        for h in report.hits
                    ]
                    save_scan_results(db, hits, source=f"userscan:{report.email}")
                finally:
                    db.close()
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
        profile, _, _ = vault.load_with_key(key)

        validated = _validate_email(email)
        target_email = validated
        if not target_email:
            if not profile.emails:
                raise HTTPException(status_code=400, detail="No email addresses provided")
            target_email = profile.emails[0]

        async with _account_lock:
            elapsed = time.time() - _account_state["started_at"]
            if _account_state["running"] and not (elapsed > stuck_timeout):
                raise HTTPException(status_code=409, detail="Account scan already running")

            _account_state["running"] = True
            _account_state["started_at"] = time.time()
            _account_state["progress"] = 0
            _account_state["error"] = None
            _account_state["email"] = target_email

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
            "email": _account_state.get("email", ""),
        }

    # Wayback Machine archived-profile scan state
    _wayback_state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "progress": 0,
        "total": 0,
        "error": None,
        "usernames": [],
    }
    _wayback_lock = asyncio.Lock()

    async def _run_wayback_scan(usernames: list[str]):
        try:
            from backend.scanner.wayback import check_wayback_profiles

            def on_progress(checked, total):
                _wayback_state["progress"] = checked
                _wayback_state["total"] = total

            report = await check_wayback_profiles(usernames, on_progress=on_progress)
            _wayback_state["report"] = report
            _wayback_state["error"] = None

            if db_session_factory and report.hits:
                from backend.core.rescan import save_scan_results
                db = db_session_factory()
                try:
                    hits = [
                        {
                            "broker_domain": h.url,
                            "broker_name": f"Wayback: {h.platform}",
                            "url": h.archive_url,
                            "username": h.username,
                            "snapshots": h.snapshots,
                            "last_snapshot": h.last_snapshot,
                        }
                        for h in report.hits
                    ]
                    save_scan_results(db, hits, source="wayback")
                finally:
                    db.close()
        except Exception as e:
            log.error("Wayback scan failed: %s", e)
            _wayback_state["error"] = "Wayback scan failed. Check logs for details."
        finally:
            _wayback_state["running"] = False

    @r.post("/wayback/start")
    async def start_wayback_scan(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
        usernames: str | None = None,
    ):
        key, _salt = session_store.validate(session)
        profile, _, _ = vault.load_with_key(key)

        from backend.scanner.wayback import usernames_from_profile

        if usernames:
            requested = [u for u in usernames.split(",") if u.strip()]
            targets = usernames_from_profile(requested, [])
        else:
            targets = usernames_from_profile(profile.usernames, profile.emails)
        if not targets:
            raise HTTPException(status_code=400, detail="No usernames to check")
        if len(targets) > 10:
            raise HTTPException(status_code=400, detail="Too many usernames (max 10)")

        async with _wayback_lock:
            elapsed = time.time() - _wayback_state["started_at"]
            if _wayback_state["running"] and not (elapsed > stuck_timeout):
                raise HTTPException(status_code=409, detail="Wayback scan already running")

            _wayback_state["running"] = True
            _wayback_state["started_at"] = time.time()
            _wayback_state["progress"] = 0
            _wayback_state["error"] = None
            _wayback_state["usernames"] = targets

        background_tasks.add_task(_run_wayback_scan, targets)

        return {"status": "started", "usernames": targets}

    @r.get("/wayback/results")
    def get_wayback_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)

        report = _wayback_state.get("report")
        if report is None:
            return {"hits": [], "checked": 0, "has_results": False, "usernames": []}

        return {
            "has_results": True,
            "usernames": report.usernames,
            "checked": report.checked,
            "hits": [
                {
                    "platform": h.platform,
                    "username": h.username,
                    "url": h.url,
                    "snapshots": h.snapshots,
                    "first_snapshot": h.first_snapshot,
                    "last_snapshot": h.last_snapshot,
                    "archive_url": h.archive_url,
                }
                for h in report.hits
            ],
            "errors": report.errors,
        }

    @r.get("/wayback/status")
    def wayback_scan_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        elapsed = time.time() - _wayback_state["started_at"]
        running = _wayback_state["running"] and not (elapsed > stuck_timeout)
        return {
            "running": running,
            "progress": _wayback_state["progress"],
            "total": _wayback_state["total"],
            "error": _wayback_state.get("error"),
            "email": ", ".join(_wayback_state.get("usernames", [])),
        }

    # GitHub Code Search scan state
    _github_state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "progress": 0,
        "total": 0,
        "error": None,
        "identifiers": [],
    }
    _github_lock = asyncio.Lock()

    async def _run_github_scan(identifiers: list[str], token: str):
        try:
            from backend.scanner.github_scanner import check_github_exposure

            def on_progress(checked, total):
                _github_state["progress"] = checked
                _github_state["total"] = total

            report = await check_github_exposure(
                identifiers, token, on_progress=on_progress
            )
            _github_state["report"] = report
            _github_state["error"] = None

            if db_session_factory and report.hits:
                from backend.core.rescan import save_scan_results
                db = db_session_factory()
                try:
                    hits = [
                        {
                            "broker_domain": h.repository,
                            "broker_name": f"GitHub: {h.repository}",
                            "url": h.url,
                            "identifier": h.identifier,
                            "path": h.path,
                        }
                        for h in report.hits
                    ]
                    save_scan_results(db, hits, source="github")
                finally:
                    db.close()
        except Exception as e:
            log.error("GitHub scan failed: %s", e)
            _github_state["error"] = "GitHub scan failed. Check logs for details."
        finally:
            _github_state["running"] = False

    @r.post("/github/start")
    async def start_github_scan(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
    ):
        key, salt = session_store.validate(session)
        profile, _, _ = vault.load_with_key(key)

        from backend.core.config import AppConfig
        from backend.core.secrets import read_secret

        effective_config = config if config is not None else AppConfig()
        token = read_secret(vault, effective_config.data_dir, key, salt, "github")
        if not token:
            raise HTTPException(status_code=400, detail="GitHub token not configured")

        from backend.scanner.github_scanner import identifiers_from_profile

        identifiers = identifiers_from_profile(profile.emails, profile.phones)
        if not identifiers:
            raise HTTPException(status_code=400, detail="No identifiers to search")

        async with _github_lock:
            elapsed = time.time() - _github_state["started_at"]
            if _github_state["running"] and not (elapsed > stuck_timeout):
                raise HTTPException(status_code=409, detail="GitHub scan already running")

            _github_state["running"] = True
            _github_state["started_at"] = time.time()
            _github_state["progress"] = 0
            _github_state["error"] = None
            _github_state["identifiers"] = identifiers

        background_tasks.add_task(_run_github_scan, identifiers, token)

        return {"status": "started", "identifiers": identifiers}

    @r.get("/github/results")
    def get_github_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)

        report = _github_state.get("report")
        if report is None:
            return {"hits": [], "checked": 0, "has_results": False, "identifiers": []}

        return {
            "has_results": True,
            "identifiers": report.identifiers,
            "checked": report.checked,
            "hits": [
                {
                    "identifier": h.identifier,
                    "repository": h.repository,
                    "path": h.path,
                    "url": h.url,
                }
                for h in report.hits
            ],
            "errors": report.errors,
        }

    @r.get("/github/status")
    def github_scan_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        elapsed = time.time() - _github_state["started_at"]
        running = _github_state["running"] and not (elapsed > stuck_timeout)
        return {
            "running": running,
            "progress": _github_state["progress"],
            "total": _github_state["total"],
            "error": _github_state.get("error"),
            "email": ", ".join(_github_state.get("identifiers", [])),
        }

    # Maigret deep username-enumeration scan state
    _deep_state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "progress": 0,
        "total": 0,
        "error": None,
        "usernames": [],
    }
    _deep_lock = asyncio.Lock()

    async def _run_deep_scan(usernames: list[str]):
        try:
            from backend.scanner.maigret_scanner import check_maigret

            for uname in usernames:
                report = await check_maigret(uname)
                _deep_state["report"] = report
                if report.errors:
                    _deep_state["error"] = report.errors[0]
                if db_session_factory and report.hits:
                    from backend.core.rescan import save_scan_results
                    db = db_session_factory()
                    try:
                        hits = [
                            {
                                "broker_domain": h.url,
                                "broker_name": h.service,
                                "url": h.url,
                                "username": h.username,
                                "tags": h.tags,
                            }
                            for h in report.hits
                        ]
                        save_scan_results(db, hits, source=f"maigret:{uname}")
                    finally:
                        db.close()
        except Exception as e:
            log.error("Deep scan failed: %s", e)
            _deep_state["error"] = "Deep scan failed. Check logs for details."
        finally:
            _deep_state["running"] = False

    @r.post("/deep-scan/start")
    async def start_deep_scan(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
        usernames: str | None = None,
    ):
        key, _salt = session_store.validate(session)
        profile, _, _ = vault.load_with_key(key)

        from backend.scanner.wayback import usernames_from_profile

        if usernames:
            requested = [u for u in usernames.split(",") if u.strip()]
            targets = usernames_from_profile(requested, [])
        else:
            targets = usernames_from_profile(profile.usernames, profile.emails)
        if not targets:
            raise HTTPException(status_code=400, detail="No usernames to check")
        if len(targets) > 3:
            raise HTTPException(status_code=400, detail="Too many usernames (max 3 for deep scan)")

        async with _deep_lock:
            elapsed = time.time() - _deep_state["started_at"]
            if _deep_state["running"] and not (elapsed > stuck_timeout):
                raise HTTPException(status_code=409, detail="Deep scan already running")
            _deep_state["running"] = True
            _deep_state["started_at"] = time.time()
            _deep_state["progress"] = 0
            _deep_state["error"] = None
            _deep_state["usernames"] = targets

        background_tasks.add_task(_run_deep_scan, targets)
        return {"status": "started", "usernames": targets}

    @r.get("/deep-scan/results")
    def get_deep_scan_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        report = _deep_state.get("report")
        if report is None:
            return {"hits": [], "checked": 0, "has_results": False, "usernames": []}
        return {
            "has_results": True,
            "usernames": _deep_state.get("usernames", []),
            "checked": report.checked,
            "hits": [
                {"service": h.service, "url": h.url, "username": h.username, "tags": h.tags}
                for h in report.hits
            ],
            "errors": report.errors,
        }

    @r.get("/deep-scan/status")
    def deep_scan_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        elapsed = time.time() - _deep_state["started_at"]
        running = _deep_state["running"] and not (elapsed > stuck_timeout)
        return {
            "running": running,
            "progress": _deep_state["progress"],
            "total": _deep_state["total"],
            "error": _deep_state.get("error"),
            "email": ", ".join(_deep_state.get("usernames", [])),
        }

    # HIBP breach check state
    _breach_state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "error": None,
    }
    _breach_lock = asyncio.Lock()

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
        key, salt = session_store.validate(session)
        profile, _, _ = vault.load_with_key(key)

        # Read HIBP key from the encrypted vault (migrating any legacy file)
        from backend.core.config import AppConfig
        from backend.core.secrets import read_secret
        effective_config = config if config is not None else AppConfig()
        api_key = read_secret(vault, effective_config.data_dir, key, salt, "hibp")
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="HIBP API key not configured. Add it in Settings.",
            )

        validated = _validate_email(email)
        target_email = validated or (profile.emails[0] if profile.emails else None)
        if not target_email:
            raise HTTPException(status_code=400, detail="No email provided")

        async with _breach_lock:
            elapsed = time.time() - _breach_state["started_at"]
            if _breach_state["running"] and not (elapsed > stuck_timeout):
                raise HTTPException(status_code=409, detail="Breach check already running")

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

    @r.get("/rescan")
    def get_rescan_report(session: str | None = Cookie(default=None)):
        """Compare latest scan results against completed requests to detect reappearances."""
        session_store.validate(session)

        if db_session_factory is None:
            raise HTTPException(status_code=500, detail="Database not available")

        report = _state.get("report")
        if report is None or not report.hits:
            return {
                "has_results": False,
                "reappeared": [],
                "new_exposures": [],
                "total_checked": 0,
            }

        from backend.core.rescan import check_for_reappearances

        db = db_session_factory()
        try:
            hits = [
                {
                    "broker_domain": h.broker_domain,
                    "broker_name": h.broker_name,
                    "snippet": h.snippet,
                    "url": h.url,
                }
                for h in report.hits
            ]
            rescan = check_for_reappearances(db, hits)
            return {
                "has_results": True,
                "reappeared": [
                    {
                        "broker_domain": a.broker_domain,
                        "broker_name": a.broker_name,
                        "snippet": a.snippet,
                        "url": a.url,
                        "previous_removal_date": a.previous_removal_date,
                    }
                    for a in rescan.reappeared
                ],
                "new_exposures": [
                    {
                        "broker_domain": a.broker_domain,
                        "broker_name": a.broker_name,
                        "snippet": a.snippet,
                        "url": a.url,
                    }
                    for a in rescan.new_exposures
                ],
                "total_checked": rescan.total_checked,
                "scan_date": rescan.scan_date,
            }
        finally:
            db.close()

    @r.get("/history")
    def scan_history(session: str | None = Cookie(default=None)):
        """Get history of all scan results."""
        session_store.validate(session)

        if db_session_factory is None:
            return {"results": [], "total": 0}

        db = db_session_factory()
        try:
            results = (
                db.query(ScanResult)
                .order_by(ScanResult.scanned_at.desc())
                .limit(100)
                .all()
            )
            return {
                "results": [
                    {
                        "id": r.id,
                        "source": r.source,
                        "broker_id": r.broker_id,
                        "found_data": _safe_json(r.found_data),
                        "scanned_at": r.scanned_at.isoformat()
                        if r.scanned_at else None,
                        "actioned": r.actioned,
                    }
                    for r in results
                ],
                "total": len(results),
            }
        finally:
            db.close()

    # --- Exposure triage inbox ---
    # Aggregates every scan hit across sources into one queue so each can be
    # driven to a terminal disposition (the v1 "route everything" goal).
    valid_dispositions = {"actioned", "dismissed", "legally_impossible"}

    # Human labels per scanner source.
    source_labels = {
        "duckduckgo": "Web search",
        "wayback": "Web archive",
        "github": "Code leak",
    }

    def _source_label(source: str) -> str:
        # userscan:<email> / maigret:<user> / holehe:<email> carry a suffix
        base = source.split(":", 1)[0]
        if base in {"userscan", "maigret", "holehe"}:
            return "Account"
        return source_labels.get(base, base)

    def _exposure_title(source: str, data) -> str:
        if not isinstance(data, dict):
            return source
        return (
            data.get("broker_name")
            or data.get("service")
            or data.get("repository")
            or data.get("broker_domain")
            or source
        )

    def _match_broker(row_broker_id, data):
        """A registry broker this exposure could be actioned against, or None."""
        if broker_registry is None:
            return None
        domain = None
        if isinstance(data, dict):
            domain = data.get("broker_domain")
        return broker_registry.get_by_domain(domain or row_broker_id)

    @r.get("/exposures")
    def list_exposures(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        if db_session_factory is None:
            return {"exposures": [], "summary": {"total": 0, "needs_triage": 0}}

        db = db_session_factory()
        try:
            rows = (
                db.query(ScanResult)
                .order_by(ScanResult.scanned_at.desc())
                .limit(500)
                .all()
            )
            exposures = []
            summary = {
                "total": 0,
                "needs_triage": 0,
                "actioned": 0,
                "dismissed": 0,
                "legally_impossible": 0,
            }
            for r_ in rows:
                data = _safe_json(r_.found_data)
                disposition = r_.disposition
                summary["total"] += 1
                if disposition in summary:
                    summary[disposition] += 1
                if disposition is None:
                    summary["needs_triage"] += 1
                url = data.get("url", "") if isinstance(data, dict) else ""
                broker = _match_broker(r_.broker_id, data)
                # Matched brokers get the one-click Art. 17 path; everything else
                # gets source-specific manual removal guidance instead.
                guidance = None
                if broker is None:
                    from backend.core.removal_guidance import guidance_for
                    guidance = guidance_for(r_.source, data)
                exposures.append(
                    {
                        "id": r_.id,
                        "source": r_.source.split(":", 1)[0],
                        "source_label": _source_label(r_.source),
                        "title": _exposure_title(r_.source, data),
                        "url": url,
                        "data": data if isinstance(data, dict) else {"raw": data},
                        "scanned_at": r_.scanned_at.isoformat() if r_.scanned_at else None,
                        "disposition": disposition,
                        "note": r_.note or "",
                        "matched_broker": (
                            {"broker_id": broker.id, "name": broker.name} if broker else None
                        ),
                        "guidance": guidance,
                    }
                )
            return {"exposures": exposures, "summary": summary}
        finally:
            db.close()

    @r.post("/exposures/{exposure_id}/disposition")
    def set_exposure_disposition(
        exposure_id: int,
        body: dict,
        session: str | None = Cookie(default=None),
    ):
        session_store.validate(session)
        if db_session_factory is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        disposition = body.get("disposition")
        note = (body.get("note") or "").strip()
        if disposition is not None and disposition not in valid_dispositions:
            raise HTTPException(status_code=400, detail="Invalid disposition")
        if len(note) > 2000:
            raise HTTPException(status_code=400, detail="Note too long")

        db = db_session_factory()
        try:
            row = db.get(ScanResult, exposure_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Exposure not found")
            row.disposition = disposition
            row.actioned = disposition is not None
            row.note = note
            db.commit()
            return {
                "id": row.id,
                "disposition": row.disposition,
                "note": row.note,
                "actioned": row.actioned,
            }
        finally:
            db.close()

    @r.post("/exposures/{exposure_id}/create-request")
    def create_request_from_exposure(
        exposure_id: int,
        session: str | None = Cookie(default=None),
    ):
        """Create an erasure request for the exposure's broker, then mark it actioned.

        Reuses an existing request for the same broker instead of duplicating,
        so re-actioning a re-scanned exposure is idempotent.
        """
        session_store.validate(session)
        if db_session_factory is None:
            raise HTTPException(status_code=503, detail="Database unavailable")

        from backend.core.request import RequestManager
        from backend.db.models import Request, RequestType

        db = db_session_factory()
        try:
            row = db.get(ScanResult, exposure_id)
            if row is None:
                raise HTTPException(status_code=404, detail="Exposure not found")

            data = _safe_json(row.found_data)
            broker = _match_broker(row.broker_id, data)
            if broker is None:
                raise HTTPException(
                    status_code=400, detail="No matching broker in the registry"
                )

            existing = (
                db.query(Request).filter(Request.broker_id == broker.id).first()
            )
            if existing is not None:
                request_id = existing.id
                created = False
            else:
                deadline_days = config.gdpr_deadline_days if config else 30
                mgr = RequestManager(db, deadline_days)
                req = mgr.create(broker.id, RequestType.ERASURE)
                request_id = req.id
                created = True

            row.disposition = "actioned"
            row.actioned = True
            verb = "Erasure request created" if created else "Linked to existing request"
            row.note = f"{verb} for {broker.name}"
            db.commit()

            return {
                "request_id": request_id,
                "broker_id": broker.id,
                "created": created,
                "disposition": "actioned",
            }
        finally:
            db.close()

    return r
