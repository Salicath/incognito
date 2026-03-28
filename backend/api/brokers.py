from fastapi import APIRouter, Cookie, HTTPException

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry


def create_brokers_router(registry: BrokerRegistry, session_store: SessionStore) -> APIRouter:
    r = APIRouter(prefix="/api/brokers", tags=["brokers"])

    @r.get("")
    def list_brokers(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        return [b.model_dump() for b in registry.brokers]

    @r.get("/{broker_id}")
    def get_broker(broker_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        broker = registry.get(broker_id)
        if broker is None:
            raise HTTPException(status_code=404, detail="Broker not found")
        return broker.model_dump()

    return r
