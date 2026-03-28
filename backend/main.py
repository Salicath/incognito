from pathlib import Path

from fastapi import FastAPI, Cookie, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import create_auth_router
from backend.api.setup import create_setup_router
from backend.api.brokers import create_brokers_router
from backend.api.deps import SessionStore
from backend.core.config import AppConfig
from backend.core.profile import ProfileVault
from backend.core.broker import BrokerRegistry
from backend.db.session import init_db


def create_app(config: AppConfig | None = None) -> FastAPI:
    if config is None:
        config = AppConfig()

    app = FastAPI(title="Incognito", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
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

    @app.get("/api/profile")
    def get_profile(session: str | None = Cookie(default=None)):
        password = session_store.validate(session)
        profile, _ = vault.load(password)
        return profile.model_dump()

    return app
