from __future__ import annotations

import enum
import re
from pathlib import Path

import yaml
from pydantic import BaseModel, computed_field


class RemovalMethod(str, enum.Enum):
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
        self.brokers = brokers
        self._by_id = {b.id: b for b in brokers}

    def get(self, broker_id: str) -> Broker | None:
        return self._by_id.get(broker_id)

    @classmethod
    def load(cls, directory: Path) -> BrokerRegistry:
        brokers = []
        if not directory.exists():
            return cls(brokers)

        for path in sorted(directory.glob("*.yaml")):
            if path.stem == "schema":
                continue
            data = yaml.safe_load(path.read_text())
            if data and isinstance(data, dict) and "name" in data:
                brokers.append(Broker.model_validate(data))

        return cls(brokers)
