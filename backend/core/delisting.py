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


ENGINES: list[DelistingEngine] = [
    DelistingEngine(
        key="google",
        name="Google",
        action="form",
        target="https://reportcontent.google.com/forms/rtbf?product=websearch",
        id_required=True,
        note="Covers Startpage (resells Google). Requires an ID upload; submit in your browser.",
    ),
    DelistingEngine(
        key="bing",
        name="Bing",
        action="form",
        target="https://www.bing.com/webmaster/tools/eu-privacy-request",
        id_required=True,
        note="Covers DuckDuckGo, Ecosia and Yahoo (they resell Bing). "
        "Requires an ID upload and a signed declaration; submit in your browser.",
    ),
    DelistingEngine(
        key="brave",
        name="Brave Search",
        action="email",
        target="privacy@brave.com",
        id_required=False,
        note="Independent index — not covered by Google/Bing. Email with subject "
        "'RTBF request'; send ID only if Brave asks.",
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
    reason_key = reason if reason in REASONS else _DEFAULT_REASON
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
    }
