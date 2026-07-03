import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


def _fake_modules(check_all):
    """Build a user_scanner.core.engine module chain so `from user_scanner.core
    import engine` resolves to our fake regardless of whether the real package
    is installed."""
    engine = types.ModuleType("user_scanner.core.engine")
    engine.check_all = check_all
    core = types.ModuleType("user_scanner.core")
    core.engine = engine
    pkg = types.ModuleType("user_scanner")
    pkg.core = core
    return {
        "user_scanner": pkg,
        "user_scanner.core": core,
        "user_scanner.core.engine": engine,
    }


@pytest.fixture
def patch_modules(monkeypatch):
    def apply(mapping):
        for name, mod in mapping.items():
            monkeypatch.setitem(sys.modules, name, mod)

    return apply


@pytest.mark.asyncio
async def test_check_email_maps_found_accounts(patch_modules):
    check_all = AsyncMock(
        return_value=[
            _result("Twitter", "https://twitter.com/x", True),
            _result("Ghost", "https://ghost.example", False),
        ]
    )
    patch_modules(_fake_modules(check_all))

    report = await check_email_accounts("me@example.com")

    assert isinstance(report, AccountReport)
    assert report.email == "me@example.com"
    assert [h.service for h in report.hits] == ["Twitter"]
    assert report.hits[0].url == "https://twitter.com/x"
    assert report.errors == []


@pytest.mark.asyncio
async def test_check_email_records_import_error(patch_modules):
    # Force `import user_scanner` to raise ImportError.
    patch_modules({"user_scanner": None})
    report = await check_email_accounts("me@example.com")
    assert report.hits == []
    assert report.errors and "user-scanner" in report.errors[0]


@pytest.mark.asyncio
async def test_check_email_survives_engine_exception(patch_modules):
    check_all = AsyncMock(side_effect=RuntimeError("boom"))
    patch_modules(_fake_modules(check_all))
    report = await check_email_accounts("me@example.com")
    assert report.hits == []
    assert report.errors


def test_account_hit_model():
    hit = AccountHit(service="Twitter", url="twitter.com", exists=True)
    assert hit.service == "Twitter"
    assert hit.exists is True
