"""Playwright-based web form sender for brokers that require form submissions.

Form definitions are YAML files that describe the steps to fill and submit
an opt-out form. Each definition maps to a broker by domain.

Usage:
    sender = WebFormSender(profile)
    result = await sender.send(broker, request_id)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from backend.core.profile import Profile
from backend.senders.base import SenderResult, SenderStatus

log = logging.getLogger("incognito.web")


@dataclass
class FormStep:
    """A single step in a form automation script."""

    action: str  # fill, click, select, check, wait, screenshot
    selector: str = ""
    value: str = ""  # Can use {profile.full_name}, {profile.emails[0]}, etc.
    timeout: int = 10000  # ms


@dataclass
class FormDefinition:
    """Automation script for a broker's opt-out form."""

    broker_domain: str
    url: str
    steps: list[FormStep] = field(default_factory=list)
    verify_selector: str = ""  # Selector that appears on success
    notes: str = ""


class FormRegistry:
    """Loads form definitions from a directory of YAML files."""

    def __init__(self, forms_dir: Path):
        self._forms: dict[str, FormDefinition] = {}
        if forms_dir.exists():
            for path in forms_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(path.read_text())
                    if not data or not isinstance(data, dict):
                        continue
                    domain = data.get("broker_domain", "")
                    steps = [
                        FormStep(**s) for s in data.get("steps", [])
                    ]
                    self._forms[domain] = FormDefinition(
                        broker_domain=domain,
                        url=data.get("url", ""),
                        steps=steps,
                        verify_selector=data.get("verify_selector", ""),
                        notes=data.get("notes", ""),
                    )
                except Exception as e:
                    log.warning("Failed to load form definition %s: %s", path.name, e)
            log.info("Loaded %d form definitions", len(self._forms))

    def get(self, domain: str) -> FormDefinition | None:
        return self._forms.get(domain)

    @property
    def domains(self) -> set[str]:
        return set(self._forms.keys())


def _resolve_value(template: str, profile: Profile) -> str:
    """Resolve template placeholders like {profile.full_name} with actual values."""
    replacements = {
        "{profile.full_name}": profile.full_name,
        "{profile.email}": profile.emails[0] if profile.emails else "",
        "{profile.phone}": profile.phones[0] if profile.phones else "",
    }
    if profile.addresses:
        addr = profile.addresses[0]
        replacements.update({
            "{profile.street}": addr.street,
            "{profile.city}": addr.city,
            "{profile.postal_code}": addr.postal_code,
            "{profile.country}": addr.country,
        })
    if profile.date_of_birth:
        replacements["{profile.dob}"] = profile.date_of_birth.isoformat()

    result = template
    for key, val in replacements.items():
        result = result.replace(key, val)
    return result


class WebFormSender:
    """Submits opt-out forms using Playwright browser automation."""

    def __init__(self, profile: Profile, forms_dir: Path | None = None):
        self._profile = profile
        self._registry = FormRegistry(forms_dir) if forms_dir else FormRegistry(Path())

    async def send(
        self, broker_domain: str, removal_url: str, request_id: str | None = None,
    ) -> SenderResult:
        form_def = self._registry.get(broker_domain)

        if form_def is None:
            return SenderResult(
                status=SenderStatus.MANUAL_NEEDED,
                message=f"No form automation defined for {broker_domain}. "
                f"Visit {removal_url} to submit manually.",
            )

        try:
            import importlib.util
            if importlib.util.find_spec("playwright") is None:
                raise ImportError("playwright not installed")
        except ImportError:
            return SenderResult(
                status=SenderStatus.MANUAL_NEEDED,
                message="Playwright not installed. "
                "Install with: pip install -e '.[automation]'",
            )

        try:
            return await self._execute_form(form_def)
        except Exception as exc:
            log.error(
                "Form submission failed for %s: %s", broker_domain, exc,
            )
            return SenderResult(
                status=SenderStatus.FAILURE,
                message=f"Form submission failed: {exc}",
            )

    async def _execute_form(self, form_def: FormDefinition) -> SenderResult:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            try:
                await page.goto(
                    form_def.url, wait_until="domcontentloaded", timeout=30000,
                )

                for step in form_def.steps:
                    await self._execute_step(page, step)

                # Verify success if selector is defined
                if form_def.verify_selector:
                    try:
                        await page.wait_for_selector(
                            form_def.verify_selector, timeout=10000,
                        )
                    except Exception:
                        return SenderResult(
                            status=SenderStatus.FAILURE,
                            message="Form submitted but success verification failed. "
                            "Check the broker's site manually.",
                        )

                return SenderResult(
                    status=SenderStatus.SUCCESS,
                    message=f"Form submitted on {form_def.broker_domain}",
                )
            finally:
                await browser.close()

    async def _execute_step(self, page, step: FormStep) -> None:
        value = _resolve_value(step.value, self._profile) if step.value else ""

        if step.action == "fill":
            await page.fill(step.selector, value, timeout=step.timeout)
        elif step.action == "click":
            await page.click(step.selector, timeout=step.timeout)
        elif step.action == "select":
            await page.select_option(step.selector, value, timeout=step.timeout)
        elif step.action == "check":
            await page.check(step.selector, timeout=step.timeout)
        elif step.action == "wait":
            timeout = int(step.value) if step.value.isdigit() else step.timeout
            await page.wait_for_timeout(timeout)
        elif step.action == "type":
            # Slower typing for fields that validate on keypress
            await page.type(step.selector, value, delay=50, timeout=step.timeout)
        else:
            log.warning("Unknown form step action: %s", step.action)
