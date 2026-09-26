# tests/core/edgar/test_transport.py
"""Tests for shared SEC pacing, bounded retries, and rejected URLs."""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from sec_nlp.core.edgar import transport

URL = "https://www.sec.gov/test"


def test_shared_sync_and_async_reservations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transport, "_next_request", 0.0)
    monkeypatch.setattr(transport.time, "monotonic", lambda: 100.0)
    assert transport._reserve_delay() == 0.0
    assert transport._reserve_delay() == pytest.approx(0.2)
    assert transport._reserve_delay() == pytest.approx(0.4)


def test_retry_keeps_global_pacing_and_honors_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("GET", URL)
    fetch = AsyncMock(
        side_effect=[
            httpx.Response(429, request=request, headers={"Retry-After": "2"}),
            httpx.Response(200, request=request, content=b"done"),
        ]
    )
    reserve = Mock(return_value=0.2)
    sleep = AsyncMock()
    monkeypatch.setattr(transport, "_reserve_delay", reserve)
    monkeypatch.setattr(transport.asyncio, "sleep", sleep)
    monkeypatch.setattr(httpx.AsyncClient, "get", fetch)

    async def run():
        async with transport.SecTransport("Test test@example.com") as client:
            return await client.get_bytes(URL)

    assert asyncio.run(run()) == b"done"
    assert reserve.call_count == 2
    assert [call.args[0] for call in sleep.call_args_list] == [0.2, 2.0, 0.2]


@pytest.mark.parametrize(
    "url",
    [
        "http://www.sec.gov/test",
        "https://sec.gov.example.com/test",
        "https://user:pass@www.sec.gov/test",
    ],
)
def test_rejects_untrusted_endpoints_before_requests(url: str) -> None:
    with pytest.raises(ValueError):
        transport.fetch_sec_bytes(url, "Test test@example.com")


def test_sync_download_uses_same_gate_and_never_retries_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reserve = Mock(return_value=0)
    fetch = Mock(
        return_value=httpx.Response(404, request=httpx.Request("GET", URL))
    )
    monkeypatch.setattr(transport, "_reserve_delay", reserve)
    monkeypatch.setattr(transport.time, "sleep", lambda _: None)
    monkeypatch.setattr(httpx.Client, "get", fetch)
    with pytest.raises(httpx.HTTPStatusError):
        transport.fetch_sec_bytes(URL, "Test test@example.com")
    assert reserve.call_count == fetch.call_count == 1
