from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from backend.api.auth import create_auth_router
from backend.api.blast import create_blast_router
from backend.api.brokers import create_brokers_router
from backend.api.deps import LoginRateLimiter, SessionStore
from backend.api.requests import create_requests_router
from backend.api.scan import create_scan_router
from backend.api.settings import create_settings_router
from backend.api.setup import create_setup_router
from backend.core.broker import BrokerRegistry
from backend.core.config import AppConfig
from backend.core.notifier import init_notifier
from backend.core.profile import ProfileVault
from backend.db.session import init_db


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    poller = getattr(app.state, "imap_poller", None)
    if poller:
        poller.start()
    yield
    if poller:
        poller.stop()


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = AppConfig()

    config.setup_logging()

    app = FastAPI(
        title="Incognito", version="0.3.0",
        docs_url=None, redoc_url=None, lifespan=lifespan,
    )

    # CORS: localhost by default, extra origins via config
    origins = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    if config.cors_origins:
        origins.extend(o.strip() for o in config.cors_origins.split(",") if o.strip())

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    import os
    config.data_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config.data_dir, 0o700)

    init_notifier(config.notify_url)

    vault = ProfileVault(config.vault_path)
    session_store = SessionStore(config.session_timeout_minutes)
    rate_limiter = LoginRateLimiter()
    db_session_factory = init_db(config.db_path)

    app.state.config = config
    app.state.vault = vault
    app.state.session_store = session_store
    app.state.db_session_factory = db_session_factory

    brokers_dir = config.brokers_dir
    if not brokers_dir.exists():
        project_brokers = Path(__file__).parent.parent / "brokers"
        if project_brokers.exists():
            brokers_dir = project_brokers

    broker_registry = BrokerRegistry.load(brokers_dir)
    app.state.broker_registry = broker_registry

    app.state.imap_poller = None
    broker_domain_set = {b.domain.lower() for b in broker_registry.brokers}
    app.state.broker_domains = broker_domain_set

    app.include_router(create_auth_router(
        vault, session_store, rate_limiter,
        secure_cookies=config.secure_cookies,
        trusted_proxy_header=config.trusted_proxy_header,
    ))
    app.include_router(create_setup_router(
        vault, session_store,
        secure_cookies=config.secure_cookies,
    ))
    app.include_router(create_brokers_router(broker_registry, session_store))
    app.include_router(create_requests_router(
        db_session_factory, session_store, config.gdpr_deadline_days, broker_registry,
    ))
    app.include_router(create_scan_router(
        vault, session_store, broker_registry, config, db_session_factory,
    ))
    app.include_router(create_blast_router(
        vault, session_store, broker_registry, db_session_factory, config,
    ))
    app.include_router(create_settings_router(vault, session_store, broker_registry, config))

    @app.get("/api/metrics")
    def metrics():
        """Prometheus-compatible metrics endpoint."""
        from backend.db.models import Request, RequestStatus, ScanResult
        db = db_session_factory()
        try:
            all_req = db.query(Request).all()
            scans = db.query(ScanResult).count()
            status_counts = {}
            for s in RequestStatus:
                status_counts[s.value] = sum(
                    1 for r in all_req if r.status == s
                )

            lines = [
                "# HELP incognito_requests_total Total requests by status",
                "# TYPE incognito_requests_total gauge",
            ]
            for s, c in status_counts.items():
                lines.append(f'incognito_requests_total{{status="{s}"}} {c}')
            lines.extend([
                "# HELP incognito_brokers_total Brokers in registry",
                "# TYPE incognito_brokers_total gauge",
                f"incognito_brokers_total {len(broker_registry.brokers)}",
                "# HELP incognito_scan_results_total Scan results stored",
                "# TYPE incognito_scan_results_total gauge",
                f"incognito_scan_results_total {scans}",
            ])
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse("\n".join(lines) + "\n")
        finally:
            db.close()

    @app.get("/api/health")
    def health():
        """Health check endpoint for monitoring and container orchestration."""
        from backend.db.models import Request
        health_status = {"status": "healthy", "version": "0.3.0"}
        try:
            db = db_session_factory()
            db.execute(Request.__table__.select().limit(1))
            db.close()
            health_status["database"] = "ok"
        except Exception:
            health_status["database"] = "error"
            health_status["status"] = "degraded"

        health_status["vault"] = "ok" if vault.exists() else "not_initialized"
        health_status["brokers"] = len(broker_registry.brokers)
        return health_status

    @app.get("/api/profile")
    def get_profile(session: str | None = Cookie(default=None)):
        key, _salt = session_store.validate(session)
        profile, _, _ = vault.load_with_key(key)
        return profile.model_dump()

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # Serve frontend static files
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = (frontend_dist / full_path).resolve()
            # Prevent path traversal — resolved path must stay within dist
            if (
                file_path.is_relative_to(frontend_dist.resolve())
                and file_path.exists()
                and file_path.is_file()
            ):
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_dist / "index.html"))

    return app
