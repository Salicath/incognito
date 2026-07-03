"""Deep username-enumeration scanner backed by Maigret.

Maigret drags in a heavy dependency tree (flask/lxml/curl-cffi/reportlab/...),
so it is NEVER imported into the app process — it is invoked as a subprocess
against its own venv. The binary path is configurable via INCOGNITO_MAIGRET_BIN
(default: `maigret` on PATH).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TIMEOUT = 30
# Hard ceiling on wall-clock for the whole subprocess (top-sites * per-site timeout
# can run long); scanner must never hang the background task forever.
_SUBPROCESS_TIMEOUT = 900


@dataclass
class MaigretHit:
    service: str
    url: str
    username: str
    tags: list[str] = field(default_factory=list)


@dataclass
class MaigretReport:
    username: str
    hits: list[MaigretHit] = field(default_factory=list)
    checked: int = 0
    errors: list[str] = field(default_factory=list)


def _resolve_binary(binary: str | None) -> str | None:
    candidate = binary or os.environ.get("INCOGNITO_MAIGRET_BIN") or "maigret"
    if os.path.isabs(candidate):
        return candidate if os.path.exists(candidate) else None
    return shutil.which(candidate)


def _is_found(entry: dict) -> bool:
    status = entry.get("status")
    if isinstance(status, dict):
        status = status.get("status")
    return str(status).lower() in {"claimed", "found", "true"}


def _parse_report(data: dict, username: str) -> list[MaigretHit]:
    hits: list[MaigretHit] = []
    for site_name, entry in (data or {}).items():
        if not isinstance(entry, dict):
            continue
        if not _is_found(entry):
            continue
        status = entry.get("status")
        url = entry.get("url_user") or entry.get("url") or ""
        tags: list = []
        if isinstance(status, dict):
            url = url or status.get("url") or ""
            raw_tags = status.get("tags")
            if isinstance(raw_tags, list):
                tags = raw_tags
        hits.append(
            MaigretHit(service=site_name, url=url, username=username, tags=list(tags))
        )
    return hits


async def _run_maigret(username, top_sites, timeout, binary, folder):
    """Run the maigret CLI; return (returncode, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        binary,
        username,
        "--json", "simple",
        "--top-sites", str(top_sites),
        "--timeout", str(timeout),
        "--no-recursion",
        "--no-color",
        "--folder", folder,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_SUBPROCESS_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        raise
    return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")


async def check_maigret(
    username: str,
    top_sites: int = 500,
    timeout: int = DEFAULT_TIMEOUT,
    binary: str | None = None,
    on_progress=None,
) -> MaigretReport:
    report = MaigretReport(username=username)
    resolved = _resolve_binary(binary)
    if not resolved:
        report.errors.append("maigret is not installed (set INCOGNITO_MAIGRET_BIN)")
        return report

    with tempfile.TemporaryDirectory() as folder:
        try:
            rc, _out, err = await _run_maigret(username, top_sites, timeout, resolved, folder)
        except asyncio.TimeoutError:
            report.errors.append("maigret scan timed out")
            return report
        except Exception as e:
            report.errors.append(str(e))
            return report

        if rc not in (0, None):
            report.errors.append(f"maigret exited with code {rc}: {err[:200]}")
            return report

        report_path = Path(folder) / f"report_{username}_simple.json"
        if not report_path.exists():
            candidates = list(Path(folder).glob("*simple*.json"))
            if not candidates:
                report.errors.append("maigret produced no JSON report")
                return report
            report_path = candidates[0]

        try:
            data = json.loads(report_path.read_text())
        except Exception as e:
            report.errors.append(f"could not parse maigret report: {e}")
            return report

    report.hits = _parse_report(data, username)
    report.checked = top_sites
    if on_progress:
        on_progress(top_sites, top_sites)
    return report
