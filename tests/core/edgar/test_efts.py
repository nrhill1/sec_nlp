# tests/core/edgar/test_efts.py
"""Tests for SEC EDGAR Full-Text Search (EFTS) client."""

from __future__ import annotations

import asyncio
import json
from datetime import date
from unittest.mock import MagicMock, patch

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

# Sample EFTS API response for mocking
SAMPLE_EFTS_RESPONSE = {
    "query": {"from": 0, "size": 10, "q": "warranty accrual"},
    "hits": {
        "total": {"value": 42},
        "hits": [
            {
                "_score": 15.5,
                "_source": {
                    "adsh": "0001234567-24-000001",
                    "cik": "1234567",
                    "display_names": ["Apple Inc."],
                    "form": "10-K",
                    "file_date": "2024-01-15",
                },
                "highlight": {"text": ["warranty <em>accrual</em> provisions"]},
            },
            {
                "_score": 12.3,
                "_source": {
                    "adsh": "0009876543-24-000002",
                    "cik": "9876543",
                    "display_names": ["Microsoft Corporation"],
                    "form": "10-Q",
                    "file_date": "2024-02-20",
                },
                "highlight": {"text": ["product <em>warranty</em> reserves"]},
            },
        ],
    },
}

EMPTY_EFTS_RESPONSE = {
    "query": {"from": 0, "size": 10, "q": "nonexistent term"},
    "hits": {"total": {"value": 0}, "hits": []},
}


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
        assert config.rate_limit_delay == 0.1

    def test_custom_user_agent(self) -> None:
        config = EFTSClientConfig(
            user_agent="MyApp (test@example.com)",
        )

        assert "MyApp" in config.user_agent
        assert "test@example.com" in config.user_agent


class TestEFTSClient:
    """Tests for EFTSClient - uses sync mocking to avoid network calls."""

    def test_parse_response(self) -> None:
        """Test response parsing without network."""
        config = EFTSClientConfig(
            user_agent="Test (test@example.com)",
            rate_limit_delay=0,
        )
        client = EFTSClient(config=config)

        response = client._parse_response(
            SAMPLE_EFTS_RESPONSE, "warranty accrual"
        )

        assert response.total == 42
        assert len(response.hits) == 2
        assert response.hits[0].company_name == "Apple Inc."
        assert response.hits[0].form_type == "10-K"
        assert response.hits[0].score == 15.5

    def test_parse_empty_response(self) -> None:
        """Test parsing empty results."""
        config = EFTSClientConfig(
            user_agent="Test (test@example.com)",
        )
        client = EFTSClient(config=config)

        response = client._parse_response(EMPTY_EFTS_RESPONSE, "test")

        assert response.total == 0
        assert len(response.hits) == 0

    def test_parse_hit(self) -> None:
        """Test individual hit parsing."""
        config = EFTSClientConfig(user_agent="Test")
        client = EFTSClient(config=config)

        raw_hit = {
            "_score": 15.5,
            "_source": {
                "adsh": "0001234567-24-000001",
                "cik": "1234567",
                "display_names": ["Apple Inc."],
                "form": "10-K",
                "file_date": "2024-01-15",
            },
            "highlight": {"text": ["warranty <em>accrual</em>"]},
        }

        hit = client._parse_hit(raw_hit)

        assert hit.accession_number == "0001234567-24-000001"
        assert hit.company_name == "Apple Inc."
        assert hit.form_type == "10-K"
        assert hit.score == 15.5
        assert "warranty" in hit.snippet

    def test_build_url(self) -> None:
        """Test URL building."""
        config = EFTSClientConfig(user_agent="Test")
        client = EFTSClient(config=config)

        url = client._build_url({"q": "test", "size": 10})

        assert "q=test" in url
        assert "size=10" in url
        assert url.startswith("https://efts.sec.gov")


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
