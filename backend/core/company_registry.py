"""GDPR privacy contacts for ordinary companies, from the Datenanfragen.de database.

Vendored CC0 snapshot (data/datenanfragen_companies.json) of datenanfragen/data,
trimmed to what a request needs. Lets an exposure that isn't a registry broker
(a newsletter sender, a found account) get a tracked Art. 17 request through the
normal send / follow-up / complaint machinery. Never blasted: blast iterates the
plain BrokerRegistry. Attribution: Datenanfragen.de e. V.

Refresh the snapshot:
    git clone --depth 1 https://github.com/datenanfragen/data /tmp/datenanfragen
    python -m backend.core.company_registry /tmp/datenanfragen/companies
"""

from __future__ import annotations

import json
import re
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from backend.core.account_registry import _host_from_url
from backend.core.broker import Broker, BrokerRegistry, RemovalMethod

_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "datenanfragen_companies.json"
_LOCALES = {"en", "da", "de", "fr", "es", "it", "nl", "pl"}
# No request-language given: write in the company's home language when we have it.
_COUNTRY_LOCALE = {
    "DK": "da", "DE": "de", "AT": "de", "FR": "fr", "ES": "es", "IT": "it", "NL": "nl", "PL": "pl",
}
CATEGORY = "company"


@lru_cache(maxsize=1)
def company_registry() -> BrokerRegistry:
    try:
        rows = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        rows = []
    brokers: dict[str, Broker] = {}
    for r in rows:
        try:
            b = Broker(
                name=r["name"], domain=r["domain"], category=CATEGORY,
                dpo_email=r["email"], removal_method=RemovalMethod.EMAIL,
                country=r.get("country", ""), gdpr_applies=True,
                verification_required=r.get("needs_id", False),
                language=r.get("lang", "en"), last_verified="", notes="Datenanfragen.de",
            )
        except (KeyError, TypeError, ValidationError):
            continue
        brokers.setdefault(b.id, b)  # first wins on a shared domain
    return BrokerRegistry(list(brokers.values()))


def lookup_company(url_or_domain: str | None, *, exact: bool = False) -> Broker | None:
    """The company owning this URL/domain, stripping subdomains (mail.zalando.de).

    `exact`: no stripping — on a shared host (someone.wordpress.com) the parent
    domain is the platform, not the controller of the page.
    """
    host = _host_from_url(url_or_domain) if url_or_domain else None
    reg = company_registry()
    if exact:
        return reg.get(re.sub(r"[^a-z0-9]+", "-", host).strip("-")) if host else None
    while host and "." in host:
        hit = reg.get(re.sub(r"[^a-z0-9]+", "-", host).strip("-"))
        if hit:
            return hit
        host = host.split(".", 1)[1]
    return None


def _convert(companies_dir: Path) -> list[dict]:
    out = []
    for f in sorted(companies_dir.glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        email = c.get("email")
        # Scraped records are unreviewed — not good enough for legal mail.
        if not email or c.get("quality") == "scraped":
            continue
        domain = _host_from_url(c["web"]) if c.get("web") else email.rsplit("@", 1)[-1].lower()
        countries = [x.upper() for x in c.get("relevant-countries", []) if x != "all"]
        country = countries[0] if countries else ""
        lang = c.get("request-language") or _COUNTRY_LOCALE.get(country, "en")
        out.append({
            "name": c["name"], "domain": domain, "email": email,
            "country": country,
            "lang": lang if lang in _LOCALES else "en",
            "needs_id": bool(c.get("needs-id-document")),
        })
    return out


if __name__ == "__main__":
    rows = _convert(Path(sys.argv[1]))
    _DATA_PATH.write_text(json.dumps(rows, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} companies to {_DATA_PATH}")
