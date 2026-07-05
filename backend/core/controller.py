"""Controller track — tech-giant erasure targets (Meta, Google, Reddit, ...).

Unlike brokers, controllers are services the user may have a live account with:
erasure means account deletion plus a formal Art. 17 for what survives it, so
every request is a per-platform opt-in — never part of the blast. 8 of 16
platforms are form-only (no verifiable Art. 17 email exists); those ride the
MANUAL_ACTION_NEEDED -> SENT lifecycle with a generated assist kit the user
pastes into the platform's rights form. See docs/tracks/controller.md.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, computed_field

from backend.core.broker import BrokerRegistry, RemovalMethod
from backend.core.profile import Profile, SmtpConfig
from backend.core.template import TemplateRenderer

log = logging.getLogger("incognito.controller")


class Controller(BaseModel):
    name: str
    domain: str
    eu_entity: str
    entity_country: str
    lead_dpa: str = ""
    no_eu_establishment: bool = False
    art27_rep: str | None = None
    contact_kind: Literal["privacy_email", "dpo_email", "form_only"]
    privacy_email: str = ""
    cc_emails: list[str] = []
    extra_domains: list[str] = []  # reply-sender domains besides `domain` (Snap: snap.com)
    email_viable: bool
    selfservice_url: str
    erasure_form_url: str = ""
    access_url: str = ""
    postal_address: str = ""
    retention_note: str
    art17_value: str
    demand_content_erasure: bool = False
    special_category: bool = False
    send_from_account_email: bool = False
    prerequisites: list[str] = []
    form_instructions: str = ""
    language: str = "en"
    last_verified: str
    datenanfragen_slug: str = ""
    notes: str | None = None

    @computed_field
    @property
    def id(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.domain.lower()).strip("-")

    # Broker-compatible surface so controllers flow through the shared request
    # machinery (scheduler follow-ups, requests API, complaint generator).
    @property
    def dpo_email(self) -> str:
        return self.privacy_email

    @property
    def country(self) -> str:
        return self.entity_country

    @property
    def category(self) -> str:
        return "controller"

    @property
    def removal_method(self) -> RemovalMethod:
        return RemovalMethod.EMAIL if self.email_viable else RemovalMethod.WEB_FORM

    @property
    def removal_url(self) -> str | None:
        return self.erasure_form_url or self.selfservice_url


class ControllerRegistry:
    def __init__(self, controllers: list[Controller]):
        self.controllers = controllers
        self._by_id = {c.id: c for c in controllers}

    def get(self, controller_id: str) -> Controller | None:
        return self._by_id.get(controller_id)

    def get_by_domain(self, domain: str | None) -> Controller | None:
        if not domain:
            return None
        d = domain.strip().lower()
        for c in self.controllers:
            if c.domain.lower() == d:
                return c
        return None

    @classmethod
    def load(cls, path: Path) -> ControllerRegistry:
        if not path.exists():
            return cls([])
        try:
            data = yaml.safe_load(path.read_text())
            controllers = [
                Controller.model_validate(c) for c in data.get("controllers", [])
            ]
        except Exception as e:
            log.warning("Failed to load controllers from %s: %s", path, e)
            return cls([])
        return cls(controllers)


class RegistryUnion:
    """Broker + controller lookup for machinery shared by both tracks.

    Blast never sees this — it iterates the plain BrokerRegistry, which is what
    keeps controllers structurally excluded from bulk sends.
    """

    def __init__(self, brokers: BrokerRegistry, controllers: ControllerRegistry):
        self._brokers = brokers
        self._controllers = controllers

    def get(self, entry_id: str):
        return self._brokers.get(entry_id) or self._controllers.get(entry_id)

    def get_by_domain(self, domain: str | None):
        return self._brokers.get_by_domain(domain) or self._controllers.get_by_domain(
            domain
        )

    @property
    def brokers(self) -> list:
        return [*self._brokers.brokers, *self._controllers.controllers]


def account_email_ok(controller: Controller, profile: Profile, smtp: SmtpConfig) -> bool:
    """Whether an automated send would come from an address the platform accepts.

    Platforms with send_from_account_email (Reddit) reject requests from
    addresses other than the one verified on the account; if the SMTP identity
    is not one of the user's known addresses, fall back to the manual kit.
    """
    if not controller.send_from_account_email:
        return True
    sender = smtp.username.strip().lower()
    return any(sender == e.strip().lower() for e in profile.emails)


def build_kit(
    controller: Controller,
    profile: Profile,
    reference_id: str,
    renderer: TemplateRenderer,
) -> dict:
    """Assemble everything the user needs to file the Art. 17 themselves.

    For email-viable controllers the request_text is what actually gets sent;
    for form-only ones it is pasted into the platform's rights form.
    """
    request_text = renderer.render_localized(
        "controller_erasure_request",
        controller.language,
        profile=profile,
        reference_id=reference_id,
        controller=controller,
    )
    return {
        "request_text": request_text,
        "form_url": controller.erasure_form_url or None,
        "form_instructions": controller.form_instructions,
        "prerequisites": controller.prerequisites,
        "selfservice_url": controller.selfservice_url,
        "postal_address": controller.postal_address,
        "send_from_account_email": controller.send_from_account_email,
    }
