from __future__ import annotations

from dataclasses import dataclass, field

import httpx


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


async def check_email_accounts(email: str, on_progress=None) -> AccountReport:
    """Check which services have an account registered with this email."""
    report = AccountReport(email=email)

    try:
        import holehe.modules
        from holehe.core import get_functions, import_submodules

        modules = import_submodules(holehe.modules)
        websites = get_functions(modules)

        total = len(websites)
        checked = 0

        async with httpx.AsyncClient(timeout=10.0) as client:
            out = []

            for website in websites:
                try:
                    await website(email, client, out)
                except Exception:
                    pass

                checked += 1
                report.checked = checked
                if on_progress:
                    on_progress(checked, total)

            for result in out:
                if result.get("exists") is True:
                    report.hits.append(AccountHit(
                        service=result.get("name", "Unknown"),
                        url=result.get("domain", ""),
                        exists=True,
                        email_recovery=result.get("emailrecovery"),
                        phone_recovery=result.get("phoneNumber"),
                    ))

            report.checked = total
    except ImportError:
        report.errors.append("holehe not installed — pip install holehe")
    except Exception as e:
        report.errors.append(str(e))

    return report
