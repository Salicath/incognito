"""Account-existence scanner (email axis) backed by user-scanner.

Drop-in replacement for the retired holehe scanner. user-scanner exposes no
stable public API, so the internal `user_scanner.core.engine` import is
isolated to this module — if that internal shape changes, this is the only
file to fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AccountHit:
    service: str
    url: str
    exists: bool
    email_recovery: str | None = None
    phone_recovery: str | None = None


@dataclass
class AccountReport:
    email: str
    hits: list[AccountHit] = field(default_factory=list)
    checked: int = 0
    errors: list[str] = field(default_factory=list)


def _is_found(result) -> bool:
    # user-scanner Result exposes is_found(); Status.TAKEN -> "Found".
    is_found = getattr(result, "is_found", None)
    if callable(is_found):
        try:
            return bool(is_found())
        except Exception:
            pass
    status = getattr(result, "status", None)
    value = getattr(status, "value", status)
    return str(value).lower() in {"found", "taken", "claimed", "exists", "true"}


async def check_email_accounts(email: str, on_progress=None) -> AccountReport:
    """Check which services have an account registered with this email."""
    report = AccountReport(email=email)
    try:
        from user_scanner.core import engine
    except Exception as e:  # ImportError or partial-install failure
        report.errors.append(f"user-scanner is not installed: {e}")
        return report

    try:
        results = await engine.check_all(email, is_email=True)
    except Exception as e:
        report.errors.append(str(e))
        return report

    results = list(results or [])
    total = len(results)
    for i, result in enumerate(results, start=1):
        if _is_found(result):
            report.hits.append(
                AccountHit(
                    service=getattr(result, "site_name", None) or "Unknown",
                    url=getattr(result, "url", "") or "",
                    exists=True,
                )
            )
        report.checked = i
        if on_progress:
            on_progress(i, total)
    report.checked = total
    return report
