"""Account-deletion instructions from the JustDelete.me dataset.

Maps a discovered account (a scanner hit's profile URL or service name) to its
concrete deletion URL, difficulty, and notes. Data is a vendored MIT-licensed
snapshot of jdm-contrib/jdm (_data/sites.json); attribution: JustDelete.me.

Matching is by registrable domain first (robust against subdomain/www noise),
falling back to a punctuation-normalized service name.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

_DATA_PATH = Path(__file__).resolve().parents[2] / "data" / "justdeleteme_sites.json"
IMPOSSIBLE = "impossible"


@dataclass(frozen=True)
class AccountDeletion:
    name: str
    url: str
    difficulty: str
    notes: str
    email: str | None = None

    @property
    def impossible(self) -> bool:
        return self.difficulty == IMPOSSIBLE


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _norm_host(host: str) -> str:
    host = host.strip().lower()
    return host[4:] if host.startswith("www.") else host


def _host_from_url(url: str) -> str | None:
    if "//" not in url:
        url = "//" + url
    host = urlparse(url).hostname
    return _norm_host(host) if host else None


class AccountRegistry:
    def __init__(self, entries: list[dict]):
        self._by_domain: dict[str, AccountDeletion] = {}
        self._by_name: dict[str, AccountDeletion] = {}
        for e in entries:
            if not isinstance(e, dict) or not e.get("name"):
                continue
            deletion = AccountDeletion(
                name=e["name"],
                url=e.get("url") or "",
                difficulty=(e.get("difficulty") or "").lower(),
                notes=e.get("notes") or "",
                email=e.get("email"),
            )
            for host in e.get("domains") or []:
                self._by_domain.setdefault(_norm_host(host), deletion)
            self._by_name.setdefault(_norm_name(e["name"]), deletion)

    def lookup(self, url: str | None = None, name: str | None = None) -> AccountDeletion | None:
        if url:
            host = _host_from_url(url)
            # Strip subdomains left-to-right, matching against the known domain
            # set — only a real dataset domain can match, so this can't overreach.
            while host:
                hit = self._by_domain.get(host)
                if hit:
                    return hit
                if "." not in host:
                    break
                host = host.split(".", 1)[1]
        if name:
            return self._by_name.get(_norm_name(name))
        return None

    @classmethod
    def load(cls, path: str | Path | None = None) -> AccountRegistry:
        p = Path(path) if path else _DATA_PATH
        if not p.exists():
            return cls([])
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return cls([])
        return cls(data if isinstance(data, list) else [])


@lru_cache(maxsize=1)
def _registry() -> AccountRegistry:
    return AccountRegistry.load()


def lookup_deletion(url: str | None = None, name: str | None = None) -> AccountDeletion | None:
    return _registry().lookup(url=url, name=name)
