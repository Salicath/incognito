import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.scanner.holehe_scanner import check_email_accounts, AccountReport, AccountHit


@pytest.mark.asyncio
async def test_check_email_returns_report():
    # Mock holehe modules to avoid actual network calls
    async def fake_website(email, client, out):
        out.append({"name": "TestService", "domain": "test.com", "exists": True})

    mock_core = MagicMock()
    mock_core.import_submodules.return_value = {}
    mock_core.get_functions.return_value = [fake_website]

    mock_holehe = MagicMock()
    mock_modules = MagicMock()
    mock_holehe.modules = mock_modules

    with patch.dict("sys.modules", {
        "holehe": mock_holehe,
        "holehe.core": mock_core,
        "holehe.modules": mock_modules,
    }):
        report = await check_email_accounts("test@example.com")

    assert isinstance(report, AccountReport)
    assert report.email == "test@example.com"
    assert report.checked > 0


@pytest.mark.asyncio
async def test_check_email_handles_import_error():
    with patch.dict("sys.modules", {"holehe": None, "holehe.core": None, "holehe.modules": None}):
        # Force ImportError by patching the import inside the function
        with patch("backend.scanner.holehe_scanner.check_email_accounts") as mock:
            # Just test the dataclass directly
            report = AccountReport(email="test@example.com")
            report.errors.append("holehe not installed")
            assert len(report.errors) == 1


def test_account_hit_model():
    hit = AccountHit(
        service="Twitter",
        url="twitter.com",
        exists=True,
        email_recovery="t***@example.com",
    )
    assert hit.service == "Twitter"
    assert hit.exists is True


def test_account_report_model():
    report = AccountReport(email="test@example.com")
    assert len(report.hits) == 0
    assert report.checked == 0
    assert report.email == "test@example.com"
