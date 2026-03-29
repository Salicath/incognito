from collections import Counter

from fastapi import APIRouter, Cookie, HTTPException

from backend.api.deps import SessionStore
from backend.core.broker import BrokerRegistry


def create_brokers_router(registry: BrokerRegistry, session_store: SessionStore) -> APIRouter:
    r = APIRouter(prefix="/api/brokers", tags=["brokers"])

    @r.get("")
    def list_brokers(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        return [b.model_dump() for b in registry.brokers]

    @r.get("/stats")
    def broker_stats(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        brokers = registry.brokers
        countries = Counter(b.country for b in brokers)
        methods = Counter(b.removal_method.value for b in brokers)
        return {
            "total": len(brokers),
            "by_country": dict(countries.most_common()),
            "by_method": dict(methods.most_common()),
            "gdpr_applicable": sum(1 for b in brokers if b.gdpr_applies),
            "email_capable": sum(
                1 for b in brokers if b.removal_method.value == "email"
            ),
        }

    @r.get("/{broker_id}")
    def get_broker(broker_id: str, session: str | None = Cookie(default=None)):
        session_store.validate(session)
        broker = registry.get(broker_id)
        if broker is None:
            raise HTTPException(status_code=404, detail="Broker not found")
        return broker.model_dump()

    return r
