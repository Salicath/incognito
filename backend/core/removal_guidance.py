"""Source-specific removal guidance for exposures with no registry broker.

Web-search hits that map to a known broker get the one-click Art. 17 path.
Everything else — a leaked identifier in code, an archived profile, an
account on some service — needs a different, per-source removal route.
This module turns each such hit into concrete steps + reference links.

Processes verified against the providers' own docs (see links in each entry).
"""

from __future__ import annotations


def _github(data: dict) -> dict:
    repo = data.get("repository") or data.get("broker_name") or "the repository"
    return {
        "title": f"Get your data removed from {repo}",
        "steps": [
            "If it's your own repo: rewrite history with git-filter-repo to purge the "
            "data, force-push, and delete/rebuild any forks that still carry the commit.",
            "If it's someone else's repo: open an issue or contact the owner asking them "
            "to remove it. If the leaked value is a live credential, rotate it now — "
            "removal never undoes exposure.",
            "Ask GitHub Support to purge cached views and PR references. GitHub only "
            "force-removes data that poses a security risk (credentials, tokens), not "
            "arbitrary personal data — so pair this with a request to the repo owner.",
        ],
        "links": [
            {
                "label": "Removing sensitive data (GitHub Docs)",
                "url": "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository",
            },
            {
                "label": "GitHub Private Information Removal Policy",
                "url": "https://docs.github.com/en/site-policy/content-removal-policies/github-private-information-removal-policy",
            },
        ],
    }


def _wayback(data: dict) -> dict:
    return {
        "title": "Request exclusion from the Wayback Machine",
        "steps": [
            "Email info@archive.org and clearly ask for the URL(s) to be excluded from "
            "the Wayback Machine.",
            "Include proof you own or are responsible for the domain (e.g. a host "
            "invoice) — archive.org won't act without it.",
            "To stop future archiving of a site you control, add "
            "'User-agent: ia_archiver / Disallow: /' to its robots.txt.",
        ],
        "links": [
            {
                "label": "How to request removal (archive.org Help)",
                "url": "https://help.archive.org/help/how-do-i-request-to-remove-something-from-archive-org/",
            },
        ],
    }


def _account(data: dict) -> dict:
    from backend.core.account_registry import lookup_deletion

    service = data.get("service") or data.get("broker_name") or "this service"
    url = data.get("url") or ""
    entry = lookup_deletion(
        url=url or None,
        name=service if service != "this service" else None,
    )

    if entry and entry.url.startswith("http"):
        links = [{"label": f"{entry.name} deletion page", "url": entry.url}]
        if entry.impossible:
            return {
                "title": f"You cannot delete your {entry.name} account",
                "steps": [
                    entry.notes or f"{entry.name} does not permit account deletion.",
                    "There is no erasure route at source — mark this exposure as "
                    "'Can't delete'. You can still ask their DPO to restrict processing "
                    "(Art. 18) even where deletion is refused.",
                ],
                "links": links,
                "difficulty": entry.difficulty,
            }
        steps = []
        if entry.notes:
            steps.append(entry.notes)
        steps.append(f"Open the deletion page and follow it through: {entry.url}")
        if entry.email:
            steps.append(
                f"If self-service fails, send an Art. 17 erasure request to {entry.email}."
            )
        else:
            steps.append(
                f"If you can't self-delete, send an Art. 17 erasure request to "
                f"{entry.name}'s privacy/DPO contact (mandatory for EU residents)."
            )
        return {
            "title": f"Delete your {entry.name} account (difficulty: {entry.difficulty})",
            "steps": steps,
            "links": links,
            "difficulty": entry.difficulty,
        }

    # No JustDelete.me match — generic account-closure guidance.
    return {
        "title": f"Close or erase your {service} account",
        "steps": [
            f"Log in to {service} and delete the account directly if you still have "
            "access — that's the fastest route.",
            f"If you can't log in, send an Art. 17 erasure request to {service}'s "
            "privacy/DPO contact (they must honour it for EU residents).",
            "Check JustDelete.me for the exact deletion URL and difficulty rating.",
        ],
        "links": [
            {"label": "JustDelete.me", "url": "https://justdeleteme.xyz/"},
        ],
    }


def _websearch(data: dict) -> dict:
    return {
        "title": "Remove or delist this search result",
        "steps": [
            "Open the page and confirm it actually contains your personal data before "
            "acting.",
            "Contact the site's owner or privacy contact and ask them to remove it — "
            "send an Art. 17 erasure request if they're an EU controller.",
            "If the page won't come down, request delisting from Google/Bing so it no "
            "longer surfaces for searches of your name (right to be forgotten).",
        ],
        "links": [
            {
                "label": "Google results removal (RTBF)",
                "url": "https://support.google.com/websearch/answer/2744324",
            },
        ],
    }


_HANDLERS = {
    "github": _github,
    "wayback": _wayback,
    "userscan": _account,
    "maigret": _account,
    "holehe": _account,  # legacy rows
    "duckduckgo": _websearch,
}


def guidance_for(source: str, data: dict | None) -> dict | None:
    """Return {title, steps, links} for a source, or None if unknown.

    `source` may carry a suffix (e.g. "holehe:me@x.com"); only the prefix matters.
    """
    base = source.split(":", 1)[0]
    handler = _HANDLERS.get(base)
    if handler is None:
        return None
    return handler(data if isinstance(data, dict) else {})
