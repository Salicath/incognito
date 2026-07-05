# Account-Discovery Scanner Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the dead `holehe` account scanner with `user-scanner` (in-process email axis) and add `Maigret` (isolated subprocess) for deep username enumeration, both feeding the existing Exposures triage inbox.

**Architecture:** Two scanner modules under `backend/scanner/`, each following the established pattern: an async run inside a FastAPI `BackgroundTask` persists hits via `save_scan_results(db, hits, source=<label>)`, which the Exposures inbox aggregates and drives to a disposition. `user-scanner` runs in-process (light, asyncio-native). `Maigret` runs as a subprocess against its own venv so its heavy dep tree never touches the app environment.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, pytest (asyncio_mode=auto), React/TypeScript, ruff, bandit.

## Global Constraints

- Base container image: `python:3.12-slim` (Debian/glibc — compiled wheels install without a toolchain).
- `user-scanner` is imported **only** inside `backend/scanner/user_scanner.py` (via its internal `user_scanner.core.engine`); no other module may import it, so API churn is a one-file fix.
- `maigret` is **never** imported into the app process — it is invoked as a subprocess only.
- Every scanner persists via `save_scan_results(db, hits, source=<label>)`; hit dicts use key `broker_domain` for the domain (drives broker matching) and `broker_name` for display.
- No API keys or paid tiers for either tool.
- Scanners never crash the caller: catch all exceptions, record in `report.errors`, set a sanitized `error` on the scan state.
- Quality gate before merge: `ruff check . && bandit -r backend/ -c pyproject.toml -ll -q && python -m pytest tests/ -x -q` all green.

---

## Part A — user-scanner (email axis, replaces holehe)

### Task 1: `user_scanner.py` scanner module

**Files:**
- Create: `backend/scanner/user_scanner.py`
- Create: `tests/unit/test_user_scanner.py`
- Delete: `backend/scanner/holehe_scanner.py`
- Delete: `tests/unit/test_holehe_scanner.py`
- Modify: `pyproject.toml` (the `[project.optional-dependencies] scanner` list)

**Interfaces:**
- Produces: `AccountHit(service: str, url: str, exists: bool, email_recovery: str | None = None, phone_recovery: str | None = None)`; `AccountReport(email: str, hits: list[AccountHit], checked: int, errors: list[str])`; `async def check_email_accounts(email: str, on_progress=None) -> AccountReport`.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_user_scanner.py`:

```python
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.scanner.user_scanner import (
    AccountHit,
    AccountReport,
    check_email_accounts,
)


def _result(site_name, url, found):
    """Mimic user_scanner.core.result.Result enough for the adapter."""
    return SimpleNamespace(
        site_name=site_name,
        url=url,
        status=SimpleNamespace(value="found" if found else "not_found"),
        found=found,
    )


@pytest.mark.asyncio
async def test_check_email_maps_found_accounts():
    fake_engine = SimpleNamespace(
        check_all=AsyncMock(
            return_value=[
                _result("Twitter", "https://twitter.com/x", True),
                _result("Ghost", "https://ghost.example", False),
            ]
        )
    )
    with patch.dict(
        "sys.modules", {"user_scanner.core.engine": fake_engine}
    ):
        report = await check_email_accounts("me@example.com")

    assert isinstance(report, AccountReport)
    assert report.email == "me@example.com"
    assert [h.service for h in report.hits] == ["Twitter"]
    assert report.hits[0].url == "https://twitter.com/x"
    assert report.errors == []


@pytest.mark.asyncio
async def test_check_email_records_import_error():
    with patch.dict("sys.modules", {"user_scanner.core.engine": None}):
        report = await check_email_accounts("me@example.com")
    assert report.hits == []
    assert report.errors and "user-scanner" in report.errors[0]


@pytest.mark.asyncio
async def test_check_email_survives_engine_exception():
    fake_engine = SimpleNamespace(check_all=AsyncMock(side_effect=RuntimeError("boom")))
    with patch.dict("sys.modules", {"user_scanner.core.engine": fake_engine}):
        report = await check_email_accounts("me@example.com")
    assert report.hits == []
    assert report.errors


def test_account_hit_model():
    hit = AccountHit(service="Twitter", url="twitter.com", exists=True)
    assert hit.service == "Twitter"
    assert hit.exists is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_user_scanner.py -q`
Expected: FAIL with `ModuleNotFoundError: backend.scanner.user_scanner`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/scanner/user_scanner.py`:

```python
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
    if getattr(result, "found", None) is True:
        return True
    status = getattr(result, "status", None)
    value = getattr(status, "value", status)
    return str(value).lower() in {"found", "claimed", "exists", "true"}


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
```

Delete `backend/scanner/holehe_scanner.py` and `tests/unit/test_holehe_scanner.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_user_scanner.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Update pyproject scanner extra**

In `pyproject.toml`, replace the `scanner` extra. Current:

```toml
# Account discovery scanner (holehe probes 120+ services)
scanner = [
    "holehe>=1.61",
]
```

New:

```toml
# Account discovery scanner (email axis; user-scanner is the holehe successor)
scanner = [
    "user-scanner>=1.4",
]
```

- [ ] **Step 6: Verify nothing else imports holehe**

Run: `grep -rn "holehe" backend/ tests/ pyproject.toml`
Expected: no matches (Task 2 handles the `scan.py` and guidance references if any remain — if this grep shows `backend/api/scan.py`, `backend/core/removal_guidance.py`, or `backend/api/scan.py` source labels, leave them for Tasks 2/3; they are addressed there). At end of Part A this grep must return nothing.

- [ ] **Step 7: Commit**

```bash
git add backend/scanner/user_scanner.py tests/unit/test_user_scanner.py pyproject.toml
git rm backend/scanner/holehe_scanner.py tests/unit/test_holehe_scanner.py
git commit -m "feat(scan): user-scanner email-axis account scanner, retire holehe"
```

---

### Task 2: Wire scan.py + removal guidance to user-scanner

**Files:**
- Modify: `backend/api/scan.py` (account scan background task ~L175-210; `source_labels` map + `_source_label` ~L714-724)
- Modify: `backend/core/removal_guidance.py` (`_HANDLERS` map ~L98-103)
- Modify: `tests/unit/test_removal_guidance.py`
- Modify: `tests/unit/test_exposures.py`

**Interfaces:**
- Consumes: `check_email_accounts` from Task 1.
- Produces: source label `userscan:<email>` persisted by the account scan; `_source_label("userscan:…")` → `"Account"`; `guidance_for("userscan:…", data)` → account guidance dict.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_removal_guidance.py`, add:

```python
def test_userscan_guidance():
    from backend.core.removal_guidance import guidance_for

    g = guidance_for("userscan:me@example.com", {"service": "Spotify"})
    assert g is not None
    assert "Spotify" in g["title"]
    assert g["steps"] and g["links"]


def test_maigret_guidance():
    from backend.core.removal_guidance import guidance_for

    g = guidance_for("maigret:johndoe", {"service": "Reddit"})
    assert g is not None
    assert "Reddit" in g["title"]
```

(`test_maigret_guidance` will pass once Task 5 lands; it is co-located here because both share the account-guidance handler. If running Part A in isolation, expect this one test to fail until Task 5 — that is acceptable and noted.)

- [ ] **Step 2: Run to verify the userscan test fails**

Run: `python -m pytest tests/unit/test_removal_guidance.py::test_userscan_guidance -q`
Expected: FAIL (`guidance_for` returns `None` for `userscan`).

- [ ] **Step 3: Update removal_guidance handlers**

In `backend/core/removal_guidance.py`, rename `_holehe` to `_account` and register the new source keys (keep `holehe` for any legacy rows):

```python
def _account(data: dict) -> dict:
    service = data.get("service") or data.get("broker_name") or "this service"
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


_HANDLERS = {
    "github": _github,
    "wayback": _wayback,
    "userscan": _account,
    "maigret": _account,
    "holehe": _account,  # legacy rows
    "duckduckgo": _websearch,
}
```

- [ ] **Step 4: Update scan.py account task to use user-scanner**

In `backend/api/scan.py`, change the account background task import and source label. Replace:

```python
                from backend.scanner.holehe_scanner import check_email_accounts
```
with:
```python
                from backend.scanner.user_scanner import check_email_accounts
```

And replace the persisted source:

```python
                    save_scan_results(db, hits, source=f"holehe:{report.email}")
```
with:
```python
                    save_scan_results(db, hits, source=f"userscan:{report.email}")
```

Update the `_source_label` helper. Replace:

```python
    def _source_label(source: str) -> str:
        # holehe:<email> and similar carry a suffix
        base = source.split(":", 1)[0]
        if base == "holehe":
            return "Account"
        return source_labels.get(base, base)
```
with:
```python
    def _source_label(source: str) -> str:
        # userscan:<email> / maigret:<user> / holehe:<email> carry a suffix
        base = source.split(":", 1)[0]
        if base in {"userscan", "maigret", "holehe"}:
            return "Account"
        return source_labels.get(base, base)
```

- [ ] **Step 5: Update the exposures test for the new source**

In `tests/unit/test_exposures.py`, find any fixture/assertion using `holehe:` as the source and update it to `userscan:`. Run first to locate:

Run: `grep -n "holehe" tests/unit/test_exposures.py`
For each match, change `holehe:` → `userscan:` in the source string and keep the expected `source_label == "Account"` assertion intact.

- [ ] **Step 6: Run the affected tests**

Run: `python -m pytest tests/unit/test_removal_guidance.py::test_userscan_guidance tests/unit/test_exposures.py -q`
Expected: PASS (the `test_maigret_guidance` case also passes because `_account` is already wired for `maigret`).

- [ ] **Step 7: Confirm no holehe references remain**

Run: `grep -rn "holehe" backend/ tests/ pyproject.toml`
Expected: no matches.

- [ ] **Step 8: Commit**

```bash
git add backend/api/scan.py backend/core/removal_guidance.py tests/unit/test_removal_guidance.py tests/unit/test_exposures.py
git commit -m "feat(scan): route account scanner + guidance through userscan source"
```

---

### Task 3: Frontend — account card label + exposures source map

**Files:**
- Modify: `frontend/src/pages/Scan.tsx` (account card comment/heading ~L539-544)
- Modify: `frontend/src/pages/Exposures.tsx` (source-label display map)

**Interfaces:**
- Consumes: existing `api.startAccountScan` / `getAccountStatus` / `getAccountResults` (unchanged shape).

- [ ] **Step 1: Update the account card copy**

In `frontend/src/pages/Scan.tsx`, replace the stale holehe reference:

```tsx
      {/* Account Scanner (Holehe) */}
```
with:
```tsx
      {/* Account Scanner (user-scanner) */}
```

- [ ] **Step 2: Update the Exposures source-label map**

Run: `grep -n "holehe\|source_label\|Account\|Web archive" frontend/src/pages/Exposures.tsx`
If a client-side source→label map exists that keys on `holehe`, add `userscan` and `maigret` → `"Account"`. If the page renders `exposure.source_label` from the API directly (no local map), no change is needed — note that and skip.

- [ ] **Step 3: Type-check the frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Scan.tsx frontend/src/pages/Exposures.tsx
git commit -m "feat(scan): frontend copy + exposure labels for user-scanner"
```

---

### Task 4: Part A verification gate

- [ ] **Step 1: Full backend quality suite**

Run: `ruff check . && bandit -r backend/ -c pyproject.toml -ll -q && python -m pytest tests/ -x -q`
Expected: ruff clean, bandit clean, all tests pass.

- [ ] **Step 2: Manual smoke (optional, requires install)**

Run: `pip install -e ".[scanner]" && python -c "import asyncio; from backend.scanner.user_scanner import check_email_accounts; print(asyncio.run(check_email_accounts('test@example.com')).errors)"`
Expected: prints `[]` (or a network note), not an ImportError.

---

## Part B — Maigret (username axis, isolated subprocess)

### Task 5: `maigret_scanner.py` subprocess module

**Files:**
- Create: `backend/scanner/maigret_scanner.py`
- Create: `tests/unit/test_maigret_scanner.py`
- Create: `tests/fixtures/maigret_simple_report.json` (captured real output)
- Modify: `pyproject.toml` (add `scanner-deep` extra)

**Interfaces:**
- Produces: `MaigretHit(service: str, url: str, username: str, tags: list[str])`; `MaigretReport(username: str, hits: list[MaigretHit], checked: int, errors: list[str])`; `async def check_maigret(username: str, top_sites: int = 500, timeout: int = 30, binary: str | None = None, on_progress=None) -> MaigretReport`.

- [ ] **Step 1: Capture a real Maigret JSON fixture**

Install Maigret in a scratch venv and capture the `--json simple` shape so the parser is written against reality, not a guess:

```bash
python -m venv /tmp/maigret-venv
/tmp/maigret-venv/bin/pip install maigret
/tmp/maigret-venv/bin/maigret soxoj --json simple --top-sites 20 --timeout 20 \
  --no-recursion --no-color --folder /tmp/maigret-out
ls /tmp/maigret-out
```

Copy the produced simple JSON to `tests/fixtures/maigret_simple_report.json`. Inspect its top-level shape (a dict keyed by site name; each value carries a found/claimed status and a profile URL). The parser in Step 3 keys off `status` (string or nested) and `url_user`; adjust the accessors in Step 3 to match the captured keys exactly if they differ.

- [ ] **Step 2: Write the failing test against the fixture**

Create `tests/unit/test_maigret_scanner.py`:

```python
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from backend.scanner.maigret_scanner import (
    MaigretReport,
    check_maigret,
    _parse_report,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "maigret_simple_report.json"


def test_parse_report_extracts_found_sites():
    data = json.loads(FIXTURE.read_text())
    hits = _parse_report(data, username="soxoj")
    assert hits, "fixture should contain at least one found site"
    assert all(h.username == "soxoj" for h in hits)
    assert all(h.url for h in hits)


@pytest.mark.asyncio
async def test_check_maigret_missing_binary():
    report = await check_maigret("soxoj", binary="/nonexistent/maigret")
    assert isinstance(report, MaigretReport)
    assert report.hits == []
    assert report.errors and "not installed" in report.errors[0].lower()


@pytest.mark.asyncio
async def test_check_maigret_parses_subprocess_output(tmp_path):
    fixture = json.loads(FIXTURE.read_text())

    async def fake_run(username, top_sites, timeout, binary, folder):
        (Path(folder) / f"report_{username}_simple.json").write_text(json.dumps(fixture))
        return 0, "", ""

    with patch("backend.scanner.maigret_scanner._run_maigret", new=AsyncMock(side_effect=fake_run)):
        report = await check_maigret("soxoj", top_sites=20)
    assert report.username == "soxoj"
    assert report.hits
    assert report.errors == []


@pytest.mark.asyncio
async def test_check_maigret_handles_nonzero_exit():
    async def fake_run(username, top_sites, timeout, binary, folder):
        return 1, "", "maigret crashed"

    with patch("backend.scanner.maigret_scanner._run_maigret", new=AsyncMock(side_effect=fake_run)):
        report = await check_maigret("soxoj")
    assert report.hits == []
    assert report.errors
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/unit/test_maigret_scanner.py -q`
Expected: FAIL with `ModuleNotFoundError: backend.scanner.maigret_scanner`.

- [ ] **Step 4: Write the implementation**

Create `backend/scanner/maigret_scanner.py` (adjust the two accessors marked `# schema:` if the captured fixture keys differ):

```python
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
        if not _is_found(entry):  # schema: found flag
            continue
        url = entry.get("url_user") or entry.get("url") or ""  # schema: profile url
        tags = entry.get("tags") or []
        hits.append(
            MaigretHit(
                service=site_name,
                url=url,
                username=username,
                tags=list(tags) if isinstance(tags, list) else [],
            )
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_maigret_scanner.py -q`
Expected: PASS (4 passed). If `test_parse_report_extracts_found_sites` fails, the captured fixture keys differ from the `# schema:` accessors — adjust `_is_found` / `url_user` to match the real keys in `tests/fixtures/maigret_simple_report.json`.

- [ ] **Step 6: Add the scanner-deep extra to pyproject**

In `pyproject.toml`, under `[project.optional-dependencies]`, add:

```toml
# Deep username enumeration (isolated subprocess — installed into its own venv,
# never into the app environment; see deploy/Containerfile)
scanner-deep = [
    "maigret>=0.6.2",
]
```

- [ ] **Step 7: Commit**

```bash
git add backend/scanner/maigret_scanner.py tests/unit/test_maigret_scanner.py tests/fixtures/maigret_simple_report.json pyproject.toml
git commit -m "feat(scan): Maigret deep username scanner (isolated subprocess)"
```

---

### Task 6: `/deep-scan/*` API endpoints

**Files:**
- Modify: `backend/api/scan.py` (add a deep-scan state block + three endpoints, mirroring the Wayback trio at ~L278-400)
- Modify: `tests/unit/test_scan_api.py`

**Interfaces:**
- Consumes: `check_maigret` from Task 5; `save_scan_results`; `usernames_from_profile` (already imported in `scan.py`).
- Produces: `POST /api/scan/deep-scan/start?usernames=`, `GET /api/scan/deep-scan/status`, `GET /api/scan/deep-scan/results`; persisted source `maigret:<username>`.

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_scan_api.py`, add (match the existing client/fixture style in that file — it constructs the FastAPI app/test client via the shared fixtures; reuse whatever the Wayback tests use):

```python
def test_deep_scan_status_requires_session(client):
    resp = client.get("/api/scan/deep-scan/status")
    assert resp.status_code in (401, 403)


def test_deep_scan_start_and_status(auth_client, monkeypatch):
    import backend.scanner.maigret_scanner as ms

    async def fake_check(username, **kw):
        return ms.MaigretReport(
            username=username,
            hits=[ms.MaigretHit(service="Reddit", url="https://reddit.com/u/x", username=username)],
            checked=20,
        )

    monkeypatch.setattr(ms, "check_maigret", fake_check)
    resp = auth_client.post("/api/scan/deep-scan/start?usernames=soxoj")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"
```

(If `test_scan_api.py` uses different fixture names than `client` / `auth_client`, use the same names the Wayback tests in that file use.)

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/unit/test_scan_api.py -k deep_scan -q`
Expected: FAIL (404 on the deep-scan routes).

- [ ] **Step 3: Add the deep-scan state + endpoints**

In `backend/api/scan.py`, after the GitHub scan block, add (mirrors the Wayback trio; `stuck_timeout`, `session_store`, `vault`, `db_session_factory`, `usernames_from_profile` are already in scope):

```python
    # Maigret deep username-enumeration scan state
    _deep_state: dict = {
        "report": None,
        "running": False,
        "started_at": 0,
        "progress": 0,
        "total": 0,
        "error": None,
        "usernames": [],
    }
    _deep_lock = asyncio.Lock()

    async def _run_deep_scan(usernames: list[str]):
        try:
            from backend.scanner.maigret_scanner import check_maigret

            all_hits = []
            for uname in usernames:
                report = await check_maigret(uname)
                _deep_state["report"] = report
                if report.errors:
                    _deep_state["error"] = report.errors[0]
                if db_session_factory and report.hits:
                    from backend.core.rescan import save_scan_results
                    db = db_session_factory()
                    try:
                        hits = [
                            {
                                "broker_domain": h.url,
                                "broker_name": h.service,
                                "url": h.url,
                                "username": h.username,
                                "tags": h.tags,
                            }
                            for h in report.hits
                        ]
                        save_scan_results(db, hits, source=f"maigret:{uname}")
                    finally:
                        db.close()
                all_hits.extend(report.hits)
            if not _deep_state.get("error"):
                _deep_state["error"] = None
        except Exception as e:
            log.error("Deep scan failed: %s", e)
            _deep_state["error"] = "Deep scan failed. Check logs for details."
        finally:
            _deep_state["running"] = False

    @r.post("/deep-scan/start")
    async def start_deep_scan(
        background_tasks: BackgroundTasks,
        session: str | None = Cookie(default=None),
        usernames: str | None = None,
    ):
        key, _salt = session_store.validate(session)
        profile, _, _ = vault.load_with_key(key)

        from backend.scanner.wayback import usernames_from_profile

        if usernames:
            requested = [u for u in usernames.split(",") if u.strip()]
            targets = usernames_from_profile(requested, [])
        else:
            targets = usernames_from_profile(profile.usernames, profile.emails)
        if not targets:
            raise HTTPException(status_code=400, detail="No usernames to check")
        if len(targets) > 3:
            raise HTTPException(status_code=400, detail="Too many usernames (max 3 for deep scan)")

        async with _deep_lock:
            elapsed = time.time() - _deep_state["started_at"]
            if _deep_state["running"] and not (elapsed > stuck_timeout):
                raise HTTPException(status_code=409, detail="Deep scan already running")
            _deep_state["running"] = True
            _deep_state["started_at"] = time.time()
            _deep_state["progress"] = 0
            _deep_state["error"] = None
            _deep_state["usernames"] = targets

        background_tasks.add_task(_run_deep_scan, targets)
        return {"status": "started", "usernames": targets}

    @r.get("/deep-scan/results")
    def get_deep_scan_results(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        report = _deep_state.get("report")
        if report is None:
            return {"hits": [], "checked": 0, "has_results": False, "usernames": []}
        return {
            "has_results": True,
            "usernames": _deep_state.get("usernames", []),
            "checked": report.checked,
            "hits": [
                {"service": h.service, "url": h.url, "username": h.username, "tags": h.tags}
                for h in report.hits
            ],
            "errors": report.errors,
        }

    @r.get("/deep-scan/status")
    def deep_scan_status(session: str | None = Cookie(default=None)):
        session_store.validate(session)
        elapsed = time.time() - _deep_state["started_at"]
        running = _deep_state["running"] and not (elapsed > stuck_timeout)
        return {
            "running": running,
            "progress": _deep_state["progress"],
            "total": _deep_state["total"],
            "error": _deep_state.get("error"),
            "email": ", ".join(_deep_state.get("usernames", [])),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_scan_api.py -k deep_scan -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/api/scan.py tests/unit/test_scan_api.py
git commit -m "feat(scan): /deep-scan endpoints for Maigret username enumeration"
```

---

### Task 7: Container venv + frontend deep-scan card

**Files:**
- Modify: `deploy/Containerfile`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/Scan.tsx`

**Interfaces:**
- Consumes: `/deep-scan/*` endpoints from Task 6.
- Produces: `api.startDeepScan` / `getDeepScanStatus` / `getDeepScanResults`; a "Deep username scan" card.

- [ ] **Step 1: Install Maigret into an isolated venv in the container**

In `deploy/Containerfile`, after the `RUN pip install --no-cache-dir .` line, add:

```dockerfile
# Maigret runs isolated in its own venv (heavy deps) — invoked as a subprocess.
RUN python -m venv /opt/maigret && \
    /opt/maigret/bin/pip install --no-cache-dir maigret>=0.6.2
ENV INCOGNITO_MAIGRET_BIN=/opt/maigret/bin/maigret
```

Ensure the venv is owned by the runtime user — the existing `RUN chown -R incognito:incognito /app` does not cover `/opt/maigret`; add it:

```dockerfile
RUN chown -R incognito:incognito /app /opt/maigret
```

(Replace the existing `chown -R incognito:incognito /app` line with the line above.)

- [ ] **Step 2: Add the client methods**

In `frontend/src/api/client.ts`, after the wayback methods (~L69), add:

```ts
  startDeepScan: (usernames?: string) =>
    request<{ status: string; usernames: string[] }>(`/scan/deep-scan/start${usernames ? `?usernames=${encodeURIComponent(usernames)}` : ""}`, { method: "POST" }),
  getDeepScanResults: () =>
    request<{ has_results: boolean; usernames: string[]; checked: number; hits: Array<{ service: string; url: string; username: string; tags: string[] }>; errors: string[] }>("/scan/deep-scan/results"),
  getDeepScanStatus: () => request<{ running: boolean; progress: number; total: number; error: string | null; email: string }>("/scan/deep-scan/status"),
```

- [ ] **Step 3: Add the deep-scan card to Scan.tsx**

In `frontend/src/pages/Scan.tsx`, add the hook near the other `useAsyncTask` declarations (after the `wayback` one ~L102):

```tsx
  const [deepInput, setDeepInput] = useState("");
  const deep = useAsyncTask<WaybackResults>({
    startFn: (usernames?: unknown) => api.startDeepScan(usernames as string | undefined),
    statusFn: api.getDeepScanStatus,
    resultsFn: api.getDeepScanResults,
  });
```

Add a card in the JSX modeled on the Wayback card (username input, run button, results list). Use the deep-scan hook's `deep.start(deepInput.trim() || undefined)`, `deep.running`, `deep.error`, and render `deep.results?.hits` as `service` + `url` links. Heading: "Deep Username Scan"; sub-copy: "Enumerate ~3000 sites for accounts tied to a username (slower; up to 3 usernames)." The `hits` shape (`service`, `url`, `username`, `tags`) differs from `WaybackHit`, so define a local interface:

```tsx
interface DeepHit { service: string; url: string; username: string; tags: string[]; }
interface DeepResults { has_results: boolean; usernames: string[]; checked: number; hits: DeepHit[]; errors: string[]; }
```

and type the hook as `useAsyncTask<DeepResults>`.

- [ ] **Step 4: Type-check the frontend**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add deploy/Containerfile frontend/src/api/client.ts frontend/src/pages/Scan.tsx
git commit -m "feat(scan): container venv for Maigret + deep-scan frontend card"
```

---

### Task 8: Final verification gate

- [ ] **Step 1: Backend quality suite**

Run: `ruff check . && bandit -r backend/ -c pyproject.toml -ll -q && python -m pytest tests/ -x -q`
Expected: all green.

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: builds clean.

- [ ] **Step 3: Update CLAUDE.md scanner list**

In `CLAUDE.md`, update the `scanner/` bullet under Architecture from `Holehe account discovery` to `user-scanner account discovery (email axis)` and add `Maigret deep username enumeration (isolated subprocess)`. Update the Security Model / Dependencies sections if they name holehe. Add the new test files to the Testing list:

```
pytest tests/unit/test_user_scanner.py -v      # Account scanner (email axis)
pytest tests/unit/test_maigret_scanner.py -v   # Maigret deep username scanner
```

- [ ] **Step 4: Update docs/PLAN.md**

Mark the Phase 2 item done and record the Maigret-over-WMN / user-scanner-over-holehe decision:

```
- ✅ Maigret + user-scanner integration (replace Holehe): user-scanner is the
  in-process email-axis holehe successor; Maigret runs as an isolated subprocess
  venv for deep 3000-site username enumeration. WMN dataset dropped (Maigret
  supersets it). Phone-axis account enumeration remains a gap (no maintained tool).
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/PLAN.md
git commit -m "docs: record user-scanner + Maigret scanner layer"
```

---

## Self-Review Notes

- **Spec coverage:** holehe drop (T1,T2), user-scanner in-process email (T1,T2,T3), Maigret isolated subprocess (T5,T6,T7), container venv (T7), source labels + guidance for both new sources (T2,T5), Exposures inbox unchanged (verified — only label maps touched), WMN skip (documented T8), phone-gap documented (T8). All spec sections map to a task.
- **Known live-verification point:** the Maigret `--json simple` schema (Task 5 Step 1) — the parser accessors are written against the documented shape and confirmed against a captured fixture before the parser test is finalized. This is a real capture step, not a placeholder.
- **Type consistency:** `AccountHit`/`AccountReport` (Task 1) reused unchanged from the retired holehe module; `MaigretHit`/`MaigretReport`/`check_maigret` signatures consistent across T5→T6; client method names consistent T7→Scan.tsx.
