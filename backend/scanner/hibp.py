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


async def check_breaches(email: str, api_key: str | None) -> BreachReport:
    """Check HIBP for breaches containing this email; XposedOrNot without a key."""
    if not api_key:
        return await _check_xposedornot(email)
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

            try:
                data = resp.json()
            except Exception:
                report.error = "Failed to parse HIBP response"
                return report
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


async def _check_xposedornot(email: str) -> BreachReport:
    """Keyless breach lookup via XposedOrNot (free public API, 1 req/s).

    Its corpus overlaps HIBP's public breaches; HIBP stays the opt-in source
    when the user has a paid key.
    """
    report = BreachReport(email=email)
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://api.xposedornot.com/v1/breach-analytics",
                params={"email": email},
                headers={"User-Agent": "Incognito-GDPR-Tool"},
            )
        if resp.status_code == 429:
            report.error = "XposedOrNot rate limit exceeded. Try again in a minute."
            return report
        if resp.status_code == 404:
            return report
        if resp.status_code != 200:
            report.error = f"XposedOrNot returned status {resp.status_code}"
            return report
        exposed = (resp.json() or {}).get("ExposedBreaches") or {}
        for b in exposed.get("breaches_details") or []:
            report.breaches.append(BreachInfo(
                name=b.get("breach", ""),
                title=b.get("breach", ""),
                domain=b.get("domain", ""),
                breach_date=str(b.get("xposed_date", "")),
                pwn_count=int(b.get("xposed_records") or 0),
                data_classes=[c for c in (b.get("xposed_data") or "").split(";") if c],
                description=b.get("details", ""),
            ))
        report.total_breaches = len(report.breaches)
    except Exception as e:
        report.error = f"XposedOrNot lookup failed: {type(e).__name__}"
    return report
