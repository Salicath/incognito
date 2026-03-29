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


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = AppConfig()

    config.setup_logging()

    app = FastAPI(title="Incognito", version="0.1.0", docs_url=None, redoc_url=None)

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

    app.include_router(create_auth_router(
        vault, session_store, rate_limiter,
        secure_cookies=config.secure_cookies,
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

    @app.get("/api/profile")
    def get_profile(session: str | None = Cookie(default=None)):
        key, _salt = session_store.validate(session)
        profile, _ = vault.load_with_key(key)
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
