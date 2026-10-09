from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.scanner.hibp import BreachInfo, BreachReport, check_breaches


@pytest.mark.asyncio
async def test_check_breaches_success():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "Name": "Adobe",
            "Title": "Adobe",
            "Domain": "adobe.com",
            "BreachDate": "2013-10-04",
            "PwnCount": 152445165,
            "DataClasses": ["Email addresses", "Passwords"],
            "Description": "Adobe breach",
        }
    ]

    with patch("backend.scanner.hibp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        report = await check_breaches("test@example.com", "fake-api-key")

    assert isinstance(report, BreachReport)
    assert report.total_breaches == 1
    assert report.breaches[0].name == "Adobe"
    assert report.error is None


@pytest.mark.asyncio
async def test_check_breaches_no_results():
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("backend.scanner.hibp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        report = await check_breaches("clean@example.com", "fake-api-key")

    assert report.total_breaches == 0
    assert report.error is None


@pytest.mark.asyncio
async def test_check_breaches_invalid_key():
    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("backend.scanner.hibp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        report = await check_breaches("test@example.com", "bad-key")

    assert report.error == "Invalid HIBP API key"


def test_breach_info_model():
    info = BreachInfo(
        name="Adobe", title="Adobe", domain="adobe.com",
        breach_date="2013-10-04", pwn_count=152445165,
        data_classes=["Email addresses"], description="test",
    )
    assert info.name == "Adobe"
    assert info.pwn_count == 152445165


@pytest.mark.asyncio
async def test_no_key_uses_xposedornot():
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ExposedBreaches": {"breaches_details": [{
        "breach": "McKesson", "domain": "mckesson.com", "xposed_date": "2026",
        "xposed_records": 6800000, "xposed_data": "Email addresses;Names",
        "details": "desc",
    }]}}

    with patch("backend.scanner.hibp.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client_cls.return_value = mock_client
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        report = await check_breaches("test@example.com", None)

    assert "xposedornot" in mock_client.get.call_args.args[0]
    assert report.total_breaches == 1
    assert report.breaches[0].data_classes == ["Email addresses", "Names"]
    assert report.error is None
