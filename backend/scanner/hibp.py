from __future__ import annotations

from dataclasses import dataclass, field

import httpx


@dataclass
class BreachInfo:
    name: str
    title: str
    domain: str
    breach_date: str
    pwn_count: int
    data_classes: list[str]
    description: str


@dataclass
class BreachReport:
    email: str
    breaches: list[BreachInfo] = field(default_factory=list)
    total_breaches: int = 0
    error: str | None = None


async def check_breaches(email: str, api_key: str) -> BreachReport:
    """Check HIBP for breaches containing this email."""
    report = BreachReport(email=email)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"https://haveibeenpwned.com/api/v3/breachedaccount/{email}",
                params={"truncateResponse": "false"},
                headers={
                    "hibp-api-key": api_key,
                    "User-Agent": "Incognito-GDPR-Tool",
                },
            )

            if resp.status_code == 404:
                # No breaches found — good news
                return report
            elif resp.status_code == 401:
                report.error = "Invalid HIBP API key"
                return report
            elif resp.status_code == 429:
                report.error = "HIBP rate limit exceeded. Try again in a minute."
                return report
            elif resp.status_code != 200:
                report.error = f"HIBP API returned status {resp.status_code}"
                return report

            data = resp.json()
            for breach in data:
                report.breaches.append(BreachInfo(
                    name=breach.get("Name", ""),
                    title=breach.get("Title", ""),
                    domain=breach.get("Domain", ""),
                    breach_date=breach.get("BreachDate", ""),
                    pwn_count=breach.get("PwnCount", 0),
                    data_classes=breach.get("DataClasses", []),
                    description=breach.get("Description", ""),
                ))
            report.total_breaches = len(report.breaches)
    except Exception as e:
        report.error = str(e)

    return report
