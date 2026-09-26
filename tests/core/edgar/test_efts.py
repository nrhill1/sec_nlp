# tests/core/edgar/test_efts.py
"""Tests for SEC EDGAR Full-Text Search (EFTS) client."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import httpx
import pytest

from sec_nlp.core.edgar.efts import (
    EFTSAPIError,
    EFTSClient,
    EFTSClientConfig,
    create_efts_client,
)
from sec_nlp.core.edgar.efts_models import (
    EFTSHit,
    EFTSSearchParams,
    EFTSSearchResponse,
    EFTSSortField,
    EFTSSortOrder,
)


class TestEFTSSearchParams:
    """Tests for EFTSSearchParams model."""

    def test_basic_params(self) -> None:
        params = EFTSSearchParams(query="warranty")
        api_params = params.to_api_params()

        assert api_params["q"] == "warranty"
        assert api_params["from"] == 0
        assert api_params["size"] == 10
        assert "sort" in api_params

    def test_with_forms_filter(self) -> None:
        params = EFTSSearchParams(
            query="warranty",
            forms=["10-K", "10-Q"],
        )
        api_params = params.to_api_params()

        assert api_params["forms"] == "10-K,10-Q"

    def test_with_date_range(self) -> None:
        params = EFTSSearchParams(
            query="warranty",
            start_date=date(2023, 1, 1),
            end_date=date(2024, 12, 31),
        )
        api_params = params.to_api_params()

        assert api_params["startdt"] == "2023-01-01"
        assert api_params["enddt"] == "2024-12-31"

    def test_with_tickers(self) -> None:
        params = EFTSSearchParams(
            query="warranty",
            tickers=["AAPL", "MSFT"],
        )
        api_params = params.to_api_params()

        assert api_params["tickers"] == "AAPL,MSFT"

    def test_pagination(self) -> None:
        params = EFTSSearchParams(
            query="warranty",
            start=20,
            limit=50,
        )
        api_params = params.to_api_params()

        assert api_params["from"] == 20
        assert api_params["size"] == 50

    def test_sort_options(self) -> None:
        params = EFTSSearchParams(
            query="warranty",
            sort_field=EFTSSortField.filed,
            sort_order=EFTSSortOrder.asc,
        )
        api_params = params.to_api_params()

        assert api_params["sort"] == "filed:asc"


class TestEFTSHit:
    """Tests for EFTSHit model."""

    def test_edgar_url_generation(self) -> None:
        hit = EFTSHit(
            accession_number="0001234567-24-000001",
            cik="0001234567",
            company_name="Apple Inc.",
            form_type="10-K",
            filed_date=date(2024, 1, 15),
            score=15.5,
        )

        assert "1234567" in hit.edgar_url
        assert "000123456724000001" in hit.edgar_url

    def test_ticker_property_returns_none(self) -> None:
        hit = EFTSHit(
            accession_number="0001234567-24-000001",
            cik="0001234567",
            company_name="Apple Inc.",
            form_type="10-K",
            filed_date=date(2024, 1, 15),
        )

        assert hit.ticker is None


class TestEFTSSearchResponse:
    """Tests for EFTSSearchResponse model."""

    def test_has_more_true(self) -> None:
        response = EFTSSearchResponse(
            query="test",
            total=100,
            hits=[
                EFTSHit(
                    accession_number="0001234567-24-000001",
                    cik="0001234567",
                    company_name="Test Co",
                    form_type="10-K",
                    filed_date=date(2024, 1, 1),
                )
            ],
            start=0,
            limit=10,
        )

        assert response.has_more is True
        assert response.next_offset == 1

    def test_has_more_false(self) -> None:
        response = EFTSSearchResponse(
            query="test",
            total=1,
            hits=[
                EFTSHit(
                    accession_number="0001234567-24-000001",
                    cik="0001234567",
                    company_name="Test Co",
                    form_type="10-K",
                    filed_date=date(2024, 1, 1),
                )
            ],
            start=0,
            limit=10,
        )

        assert response.has_more is False


class TestEFTSClientConfig:
    """Tests for EFTSClientConfig model."""

    def test_defaults(self) -> None:
        config = EFTSClientConfig()

        assert config.timeout == 30.0
        assert config.max_retries == 3
        assert config.rate_limit_delay == 0.2

    def test_custom_user_agent(self) -> None:
        config = EFTSClientConfig(
            user_agent="MyApp (test@example.com)",
        )

        assert "MyApp" in config.user_agent
        assert "test@example.com" in config.user_agent


class TestEFTSClient:
    """Verify HTTPX transport use and native parsing of offline payloads."""

    def test_search_uses_shared_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sec_nlp.core.edgar.transport import SecTransport

        fetch = AsyncMock(
            return_value=b'{"hits":{"total":{"value":1},"hits":[{"_score":1.0,"_source":{"adsh":"0001234567-24-000001","cik":"1234567","display_names":["Test Co"],"form":"10-K","file_date":"2024-01-15"}}]}}'
        )
        monkeypatch.setattr(SecTransport, "get_bytes", fetch)
        result = asyncio.run(EFTSClient().search("warranty", limit=1, start=2))
        assert result.hits[0].company_name == "Test Co"
        assert result.start == 2 and result.limit == 1
        assert fetch.call_args.kwargs["params"]["q"] == "warranty"

    def test_batch_preserves_independent_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch = AsyncMock(
            side_effect=[
                EFTSAPIError(429, "limited"),
                EFTSSearchResponse(query="second", total=0),
            ]
        )
        monkeypatch.setattr(EFTSClient, "search", fetch)
        results = asyncio.run(EFTSClient().batch_search(["first", "second"]))
        assert results[0].error and results[1].success

    def test_search_all_stops_on_empty_page(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetch = AsyncMock(
            return_value=EFTSSearchResponse(query="test", total=100, hits=[])
        )
        monkeypatch.setattr(EFTSClient, "search", fetch)
        assert asyncio.run(EFTSClient().search_all("test")) == []
        fetch.assert_awaited_once()

    def test_transport_errors_keep_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from sec_nlp.core.edgar.transport import SecTransport

        response = httpx.Response(
            403, request=httpx.Request("GET", "https://efts.sec.gov/test")
        )
        fetch = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "forbidden", request=response.request, response=response
            )
        )
        monkeypatch.setattr(SecTransport, "get_bytes", fetch)
        with pytest.raises(EFTSAPIError) as failure:
            asyncio.run(EFTSClient().search("warranty"))
        assert failure.value.status_code == 403


class TestCreateEFTSClient:
    """Tests for create_efts_client factory function."""

    def test_creates_client_with_user_agent(self) -> None:
        client = create_efts_client(
            email="test@example.com",
            company_name="TestApp",
        )

        assert "TestApp" in client.config.user_agent
        assert "test@example.com" in client.config.user_agent

    def test_custom_timeout(self) -> None:
        client = create_efts_client(
            email="test@example.com",
            timeout=60.0,
        )

        assert client.config.timeout == 60.0


class TestEFTSAPIError:
    """Tests for EFTSAPIError exception."""

    def test_error_message(self) -> None:
        error = EFTSAPIError(
            status_code=429,
            message="Rate limited",
            detail="Too many requests",
        )

        assert "429" in str(error)
        assert "Rate limited" in str(error)

    def test_to_model(self) -> None:
        error = EFTSAPIError(
            status_code=500,
            message="Server error",
        )

        model = error.to_model()
        assert model.status == 500
        assert model.message == "Server error"
