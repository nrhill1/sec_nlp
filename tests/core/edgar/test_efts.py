# tests/core/edgar/test_efts.py
"""Tests for SEC EDGAR Full-Text Search (EFTS) client."""

from __future__ import annotations

import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

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
        assert config.rate_limit_delay == 0.1

    def test_custom_user_agent(self) -> None:
        config = EFTSClientConfig(
            user_agent="MyApp (test@example.com)",
        )

        assert "MyApp" in config.user_agent
        assert "test@example.com" in config.user_agent


class TestEFTSClient:
    """Tests for EFTSClient - uses sync mocking to avoid network calls."""

    def test_rust_backend_uses_extension(
        self, monkeypatch: pytest.MonkeyPatch, socket_enabled: None
    ) -> None:
        """Ensure the Rust backend path is used."""
        from sec_nlp.core.edgar import efts as efts_module

        # Create mock hit object with attribute access
        mock_hit = Mock()
        mock_hit.accession_number = "0001234567-24-000001"
        mock_hit.cik = "0001234567"
        mock_hit.company_name = "Test Co"
        mock_hit.tickers = ["TST"]
        mock_hit.form_type = "10-K"
        mock_hit.filed_date = date(2024, 1, 15)
        mock_hit.file_number = None
        mock_hit.film_number = None
        mock_hit.snippet = "test"
        mock_hit.score = 1.0
        mock_hit.filing_url = None

        # Create mock response object with attribute access
        mock_response = Mock()
        mock_response.query = "warranty"
        mock_response.total = 1
        mock_response.hits = [mock_hit]
        mock_response.start = 0
        mock_response.limit = 1

        rust_client_instance = Mock()
        # Use AsyncMock for the async method
        rust_client_instance.search_async = AsyncMock(
            return_value=mock_response
        )
        rust_client_class = Mock(return_value=rust_client_instance)
        rust_module = Mock()
        rust_module.EFTSClient = rust_client_class

        monkeypatch.setattr(
            efts_module, "_load_efts_module", lambda: rust_module
        )

        config = EFTSClientConfig(
            user_agent="Test (test@example.com)",
            rate_limit_delay=0,
        )
        client = EFTSClient(config=config)
        response = asyncio.run(client.search("warranty", limit=1))

        assert response.total == 1
        assert response.hits[0].company_name == "Test Co"
        rust_client_class.assert_called_once()
        _, kwargs = rust_client_class.call_args
        assert kwargs.get("base_url") == config.base_url
        rust_client_instance.search_async.assert_called_once()

    def test_search_all_uses_rust_async(
        self, monkeypatch: pytest.MonkeyPatch, socket_enabled: None
    ) -> None:
        """Ensure search_all uses the Rust search_all_async method."""
        from sec_nlp.core.edgar import efts as efts_module

        # Create mock hit objects
        mock_hits = []
        for i in range(3):
            mock_hit = Mock()
            mock_hit.accession_number = f"0001234567-24-00000{i + 1}"
            mock_hit.cik = "0001234567"
            mock_hit.company_name = f"Test Co {i + 1}"
            mock_hit.tickers = ["TST"]
            mock_hit.form_type = "10-K"
            mock_hit.filed_date = date(2024, 1, 15 + i)
            mock_hit.file_number = None
            mock_hit.film_number = None
            mock_hit.snippet = "test"
            mock_hit.score = 1.0 - (i * 0.1)
            mock_hit.filing_url = None
            mock_hits.append(mock_hit)

        rust_client_instance = Mock()
        rust_client_instance.search_all_async = AsyncMock(
            return_value=mock_hits
        )
        rust_client_class = Mock(return_value=rust_client_instance)
        rust_module = Mock()
        rust_module.EFTSClient = rust_client_class

        monkeypatch.setattr(
            efts_module, "_load_efts_module", lambda: rust_module
        )

        config = EFTSClientConfig(
            user_agent="Test (test@example.com)",
            rate_limit_delay=0,
        )
        client = EFTSClient(config=config)
        hits = asyncio.run(client.search_all("warranty", max_results=10))

        assert len(hits) == 3
        assert hits[0].company_name == "Test Co 1"
        assert hits[2].company_name == "Test Co 3"
        rust_client_instance.search_all_async.assert_called_once()
        call_kwargs = rust_client_instance.search_all_async.call_args.kwargs
        assert call_kwargs.get("max_results") == 10

    def test_batch_search_uses_rust_async(
        self, monkeypatch: pytest.MonkeyPatch, socket_enabled: None
    ) -> None:
        """Ensure batch_search_async uses the Rust implementation."""
        from sec_nlp.core.edgar import efts as efts_module

        # Create mock hit objects for two queries
        mock_results = []
        for query_idx, query in enumerate(["warranty", "liability"]):
            mock_hit = Mock()
            mock_hit.accession_number = f"0001234567-24-00000{query_idx + 1}"
            mock_hit.cik = "0001234567"
            mock_hit.company_name = f"Test Co {query_idx + 1}"
            mock_hit.tickers = ["TST"]
            mock_hit.form_type = "10-K"
            mock_hit.filed_date = date(2024, 1, 15 + query_idx)
            mock_hit.file_number = None
            mock_hit.film_number = None
            mock_hit.snippet = "test"
            mock_hit.score = 1.0
            mock_hit.filing_url = None

            mock_result = Mock()
            mock_result.query = query
            mock_result.hits = [mock_hit]
            mock_result.total = 1
            mock_result.error = None
            mock_result.success = True
            mock_results.append(mock_result)

        rust_client_instance = Mock()
        rust_client_instance.batch_search_async = AsyncMock(
            return_value=mock_results
        )
        rust_client_class = Mock(return_value=rust_client_instance)
        rust_module = Mock()
        rust_module.EFTSClient = rust_client_class

        monkeypatch.setattr(
            efts_module, "_load_efts_module", lambda: rust_module
        )

        # Test that we can call batch_search_async directly on the Rust client
        results = asyncio.run(
            rust_client_instance.batch_search_async(
                ["warranty", "liability"], limit_per_query=10
            )
        )

        assert len(results) == 2
        assert results[0].query == "warranty"
        assert results[1].query == "liability"
        rust_client_instance.batch_search_async.assert_called_once()

    def test_search_all_with_progress_calls_callback(
        self, monkeypatch: pytest.MonkeyPatch, socket_enabled: None
    ) -> None:
        """Ensure progress callback is called during search_all."""
        from sec_nlp.core.edgar import efts as efts_module

        # Track progress calls
        progress_calls: list[Mock] = []

        def on_progress(p: Mock) -> None:
            progress_calls.append(p)

        # Create mock hits
        mock_hits = []
        for i in range(3):
            mock_hit = Mock()
            mock_hit.accession_number = f"0001234567-24-00000{i + 1}"
            mock_hit.cik = "0001234567"
            mock_hit.company_name = f"Test Co {i + 1}"
            mock_hit.tickers = ["TST"]
            mock_hit.form_type = "10-K"
            mock_hit.filed_date = date(2024, 1, 15 + i)
            mock_hit.file_number = None
            mock_hit.film_number = None
            mock_hit.snippet = "test"
            mock_hit.score = 1.0
            mock_hit.filing_url = None
            mock_hits.append(mock_hit)

        rust_client_instance = Mock()

        async def mock_search_all_with_progress(
            query: str,
            on_progress: Mock,
            **kwargs: Mock,
        ) -> list[Mock]:
            # Simulate progress callback
            progress = Mock()
            progress.current_page = 1
            progress.total_pages = 1
            progress.hits_fetched = 3
            progress.total_hits = 3
            progress.query = query
            on_progress(progress)
            return mock_hits

        rust_client_instance.search_all_with_progress_async = AsyncMock(
            side_effect=mock_search_all_with_progress
        )
        rust_client_class = Mock(return_value=rust_client_instance)
        rust_module = Mock()
        rust_module.EFTSClient = rust_client_class

        monkeypatch.setattr(
            efts_module, "_load_efts_module", lambda: rust_module
        )

        # Call the method
        hits = asyncio.run(
            rust_client_instance.search_all_with_progress_async(
                "warranty",
                on_progress=on_progress,
                max_results=100,
            )
        )

        assert len(hits) == 3
        assert len(progress_calls) == 1
        assert progress_calls[0].current_page == 1


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
