"""Search-engine delisting (RTBF) assist kit.

Every delisting channel is a manual web form (Google, Bing) or email (Brave) with
an ID-upload step and no API, so this module only *assists*: it builds the per-engine
deep-link and a drafted Article 17 justification the user pastes into the form. It
never auto-submits.

Legal basis: Art. 17 GDPR as applied to search engines (CJEU C-131/12, Google Spain);
delisting is name-query-scoped and EU-scoped (C-507/17), and does not delete the source.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Shared Google/Bing reason vocabulary → human phrasing per locale.
REASONS: dict[str, dict[str, str]] = {
    "inaccurate": {"en": "inaccurate or false", "da": "unøjagtigt eller forkert"},
    "inadequate": {"en": "inadequate or incomplete", "da": "utilstrækkeligt eller ufuldstændigt"},
    "outdated": {
        "en": "out of date and no longer relevant",
        "da": "forældet og ikke længere relevant",
    },
    "excessive": {
        "en": "excessive or inappropriate for the purposes it was published",
        "da": "for vidtgående eller upassende i forhold til de formål, det blev offentliggjort til",
    },
}
_DEFAULT_REASON = "outdated"


@dataclass(frozen=True)
class DelistingEngine:
    key: str
    name: str
    action: str  # "form" | "email"
    target: str  # form URL or email address
    id_required: bool
    note: str
    domain: str = ""  # reply-sender domain, for IMAP matching


@dataclass(frozen=True)
class DelistingTarget:
    """Broker-compatible surface for one engine, so tracked delisting requests
    flow through the shared machinery (requests API, scheduler, complaints).

    dpo_email is empty for form-only engines: the scheduler then skips email
    chasing and auto-escalates after the window (same path as form-only
    controllers). Brave keeps its email so overdue requests get chased.
    """

    id: str
    name: str
    domain: str
    dpo_email: str
    erasure_form_url: str = ""  # complaint contact fallback for form engines
    eu_entity: str = ""
    entity_country: str = "US"
    lead_dpa: str = ""
    no_eu_establishment: bool = False
    art27_rep: str | None = None
    country: str = "US"
    language: str = "en"
    category: str = "delisting"
    notes: str | None = None

    @property
    def removal_method(self):
        from backend.core.broker import RemovalMethod

        return RemovalMethod.EMAIL if self.dpo_email else RemovalMethod.WEB_FORM


# Controller facts per engine, verified July 2026. Google Search RTBF is
# processed by Google LLC (US) — no EU main establishment for that processing,
# so no one-stop-shop: the residence SA decides itself under Art. 55 (IMY
# DI-2018-9274 fined Google LLC; Brussels Market Court 2021 annulled an APD
# fine precisely because Google Belgium wasn't the controller). Bing is
# Microsoft Ireland Operations Ltd -> lead SA IE DPC via Arts. 56/60.
_TARGET_FACTS: dict[str, dict] = {
    "google": {
        "eu_entity": "Google LLC, 1600 Amphitheatre Parkway, Mountain View, CA 94043, USA",
        "entity_country": "US",
        "no_eu_establishment": True,
    },
    "bing": {
        "eu_entity": "Microsoft Ireland Operations Limited, One Microsoft Place, Dublin 18",
        "entity_country": "IE",
        "lead_dpa": "IE DPC",
    },
    "brave": {
        "eu_entity": "Brave Software Inc. (US)",
        "entity_country": "US",
        "no_eu_establishment": True,
        "art27_rep": "brave@gdprnomrep.eu",
    },
}

# Decision emails are form-triggered, not replies: Message-ID/REF matching can
# never fire for Google/Bing. Exact sender addresses only — matching on the
# whole google.com domain would let Google Alerts / "Results about you"
# notifications that quote the tracked URL auto-acknowledge the request and
# silently disarm the Art. 12(3) chase. Precision over recall: an unknown
# decision sender just means the user confirms manually. Bing has no reliable
# sender or body signal at all, so Bing decisions are always user-confirmed.
DECISION_SENDER_ADDRESSES: dict[str, set[str]] = {
    "delisting-google": {
        "removals@google.com",
        "google-legal-support@google.com",
        "reportcontent-noreply@google.com",
        "noreply-reportcontent@google.com",
    },
    "delisting-brave": {"privacy@brave.com"},
}


class DelistingRegistry:
    def __init__(self) -> None:
        self.targets = [
            DelistingTarget(
                id=f"delisting-{e.key}",
                name=f"{e.name} delisting (RTBF)",
                domain=e.domain or e.key + ".com",
                dpo_email=e.target if e.action == "email" else "",
                erasure_form_url=e.target if e.action == "form" else "",
                **_TARGET_FACTS.get(e.key, {}),
            )
            for e in ENGINES
        ]
        self._by_id = {t.id: t for t in self.targets}

    def get(self, target_id: str) -> DelistingTarget | None:
        return self._by_id.get(target_id)

    def get_by_domain(self, domain: str | None) -> DelistingTarget | None:
        if not domain:
            return None
        d = domain.strip().lower()
        for t in self.targets:
            if t.domain == d:
                return t
        return None


ENGINES: list[DelistingEngine] = [
    DelistingEngine(
        key="google",
        name="Google",
        action="form",
        target="https://reportcontent.google.com/forms/rtbf?product=websearch",
        id_required=True,
        note="Covers Startpage (resells Google). Requires an ID upload; submit in your browser.",
        domain="google.com",
    ),
    DelistingEngine(
        key="bing",
        name="Bing",
        action="form",
        target="https://www.bing.com/webmaster/tools/eu-privacy-request",
        id_required=True,
        note="Covers DuckDuckGo, Ecosia and Yahoo (they resell Bing). "
        "Requires an ID upload and a signed declaration; submit in your browser.",
        domain="bing.com",
    ),
    DelistingEngine(
        key="brave",
        name="Brave Search",
        action="email",
        target="privacy@brave.com",
        id_required=False,
        note="Independent index — not covered by Google/Bing. Email with subject "
        "'RTBF request'; send ID only if Brave asks.",
        domain="brave.com",
    ),
]

_TEMPLATES = {
    "en": (
        "I request that the URL(s) below be delisted from results for searches of my "
        "name{name_clause}, under Article 17 GDPR (right to erasure) as applied to search "
        "engines (CJEU C-131/12, Google Spain). The content is {reason}. It relates to me "
        "directly and appears when my name is searched. I am a private individual with no "
        "role in public life, and its continued surfacing is no longer justified by any "
        "overriding public interest."
    ),
    "da": (
        "Jeg anmoder om, at nedenstående URL(er) fjernes fra søgeresultater for søgninger "
        "på mit navn{name_clause}, i henhold til artikel 17 i GDPR (retten til sletning) som "
        "anvendt på søgemaskiner (EU-Domstolen C-131/12, Google Spain). Indholdet er "
        "{reason}. Det vedrører mig direkte og fremkommer, når der søges på mit navn. Jeg er "
        "en privatperson uden offentlig rolle, og den fortsatte visning er ikke længere "
        "begrundet i nogen tungtvejende offentlig interesse."
    ),
}


def _justification(name_queries: list[str], reason_key: str, locale: str) -> str:
    loc = locale if locale in _TEMPLATES else "en"
    reason_text = REASONS[reason_key][loc]
    name = name_queries[0] if name_queries else ""
    name_clause = f", '{name}'" if name else ""
    return _TEMPLATES[loc].format(name_clause=name_clause, reason=reason_text)


def build_delisting_kit(
    url: str,
    name_queries: list[str],
    reason: str = _DEFAULT_REASON,
    locale: str = "en",
) -> dict:
    """Build the per-engine delisting assist kit for one exposed URL."""
    from urllib.parse import quote

    reason_key = reason if reason in REASONS else _DEFAULT_REASON
    name = name_queries[0] if name_queries else ""
    q = quote(f'"{name}"') if name else ""
    return {
        "url": url,
        "name_queries": list(name_queries),
        "reason": reason_key,
        "reasons_available": list(REASONS.keys()),
        "justification": _justification(name_queries, reason_key, locale),
        "engines": [asdict(e) for e in ENGINES],
        "coverage_note": (
            "For a Danish user the practical surface is Google + Bing. DuckDuckGo, "
            "Ecosia, Yahoo and Startpage resell those indexes, so delisting the upstream "
            "covers them. Delisting hides the page for searches of your name across EU "
            "domains — it does not delete the source page or apply worldwide."
        ),
        # Manual re-verification: no ToS-safe programmatic check exists for the
        # Google surface. Signed-out name queries from a DK connection are what
        # matters (delisting is EU/geo-scoped, C-507/17); the vantage IP decides.
        "verify": {
            "google": f"https://www.google.com/search?q={q}&pws=0&num=50" if q else "",
            "bing": f"https://www.bing.com/search?q={q}&mkt=da-DK" if q else "",
            "results_about_you": "https://myactivity.google.com/results-about-you",
            "note": (
                "Open signed-out from your normal Danish connection. Google's "
                "'Results about you' monitors name hits ambiently — enroll it as "
                "a complement; it is a policy track, separate from the Art. 17 "
                "form. The rescan command/timer re-runs name queries and alerts "
                "if a granted delisting resurfaces (Bing surface via DuckDuckGo; "
                "check the Google link manually)."
            ),
        },
    }
