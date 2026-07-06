"""restriction_only track — sources where GDPR erasure is legally impossible.

Pure information: each entry says honestly why erasure cannot happen
(Art. 17(3) grounds + the Danish statute) and what restriction or mitigation
the user CAN do instead. No state machine. See docs/tracks/restriction_only.md.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel

log = logging.getLogger("incognito.restriction_only")


class RestrictionEntry(BaseModel):
    id: str
    name: str
    what_it_is: str
    why_undeletable: str
    mitigation: str
    mitigation_url: str = ""
    requires_mitid: bool = False
    notes: str | None = None


class RestrictionRegistry:
    def __init__(self, entries: list[RestrictionEntry]):
        self.entries = entries
        self._by_id = {e.id: e for e in entries}

    def get(self, entry_id: str) -> RestrictionEntry | None:
        return self._by_id.get(entry_id)

    @classmethod
    def load(cls, path: Path) -> RestrictionRegistry:
        if not path.exists():
            return cls([])
        try:
            data = yaml.safe_load(path.read_text())
            entries = [
                RestrictionEntry.model_validate(e) for e in data.get("entries", [])
            ]
        except Exception as e:
            log.warning("Failed to load restriction entries from %s: %s", path, e)
            return cls([])
        return cls(entries)
