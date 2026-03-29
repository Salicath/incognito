from pathlib import Path

from fastapi import Cookie, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import create_auth_router
from backend.api.blast import create_blast_router
from backend.api.brokers import create_brokers_router
from backend.api.deps import SessionStore
from backend.api.requests import create_requests_router
from backend.api.scan import create_scan_router
from backend.api.settings import create_settings_router
from backend.api.setup import create_setup_router
from backend.core.broker import BrokerRegistry
from backend.core.config import AppConfig
from backend.core.profile import ProfileVault
from backend.db.session import init_db


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = AppConfig()

    app = FastAPI(title="Incognito", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",   # Vite dev server
            "http://127.0.0.1:5173",
            "http://localhost:8080",   # Production (same-origin)
            "http://127.0.0.1:8080",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    config.data_dir.mkdir(parents=True, exist_ok=True)

    vault = ProfileVault(config.vault_path)
    session_store = SessionStore(config.session_timeout_minutes)
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

    app.include_router(create_auth_router(vault, session_store))
    app.include_router(create_setup_router(vault, session_store))
    app.include_router(create_brokers_router(broker_registry, session_store))
    app.include_router(create_requests_router(
        db_session_factory, session_store, config.gdpr_deadline_days, broker_registry,
    ))
    app.include_router(create_scan_router(
        vault, session_store, broker_registry, config,
    ))
    app.include_router(create_blast_router(
        vault, session_store, broker_registry, db_session_factory, config,
    ))
    app.include_router(create_settings_router(vault, session_store, broker_registry, config))

    @app.get("/api/profile")
    def get_profile(session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        profile, _ = vault.load(password)
        return profile.model_dump()

    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # Serve frontend static files
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = frontend_dist / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(str(file_path))
            return FileResponse(str(frontend_dist / "index.html"))

    return app
