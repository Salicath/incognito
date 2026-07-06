from __future__ import annotations

import enum
import logging
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, computed_field

log = logging.getLogger("incognito.broker")


class RemovalMethod(enum.StrEnum):
    EMAIL = "email"
    WEB_FORM = "web_form"
    API = "api"


class Broker(BaseModel):
    name: str
    domain: str
    category: str
    dpo_email: str
    removal_method: RemovalMethod
    removal_url: str | None = None
    api_endpoint: str | None = None
    country: str
    gdpr_applies: bool
    verification_required: bool
    language: str = "en"
    last_verified: str
    notes: str | None = None

    @computed_field
    @property
    def id(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.domain.lower()).strip("-")


class BrokerRegistry:
    def __init__(self, brokers: list[Broker]):
        self.brokers: list[Broker] = brokers
        self._by_id = {b.id: b for b in brokers}

    def get(self, broker_id: str) -> Broker | None:
        return self._by_id.get(broker_id)

    def get_by_domain(self, domain: str | None) -> Broker | None:
        """Resolve a broker from a raw domain (as stored on scan hits).

        Matches on exact domain first, then on the slugified id, so a hit
        recorded as "spokeo.com" finds the broker whose id is "spokeo-com".
        """
        if not domain:
            return None
        d = domain.strip().lower()
        for b in self.brokers:
            if b.domain.lower() == d:
                return b
        slug = re.sub(r"[^a-z0-9]+", "-", d).strip("-")
        return self._by_id.get(slug)

    @classmethod
    def load(cls, directory: Path) -> BrokerRegistry:
        brokers = []
        if not directory.exists():
            return cls(brokers)

        for path in sorted(directory.glob("*.yaml")):
            if path.stem in (
                "schema", "cpr_levers", "controllers", "time_locked",
                "restriction_only",
            ):
                continue
            try:
                data = yaml.safe_load(path.read_text())
                if data and isinstance(data, dict) and "name" in data:
                    brokers.append(Broker.model_validate(data))
            except Exception as e:
                log.warning("Failed to load broker %s: %s", path.name, e)

        return cls(brokers)
