from __future__ import annotations

import enum
from dataclasses import dataclass


class SenderStatus(enum.StrEnum):
    SUCCESS = "success"
    FAILURE = "failure"
    MANUAL_NEEDED = "manual_needed"


@dataclass(frozen=True)
class SenderResult:
    status: SenderStatus
    message: str
