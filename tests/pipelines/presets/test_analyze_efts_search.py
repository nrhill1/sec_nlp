# tests/pipelines/presets/test_analyze_efts_search.py
"""Tests for EFTS search helpers."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.pipelines.presets.analyze.config import (
    AnalyzeConfig,
    EFTSConfig,
    SearchConfig,
)
from sec_nlp.pipelines.presets.analyze.steps.search.efts_search import (
    EFTSSearchRunner,
)


def test_filter_hits_by_ticker_keeps_all_hits() -> None:
    hits = [
        EFTSHit(
            accession_number="0000000000-24-000001",
            cik="0000000000",
            company_name="Alpha Inc",
            form_type="10-K",
            filed_date=date(2024, 1, 1),
            tickers=["ALPHA"],
        ),
        EFTSHit(
            accession_number="0000000000-24-000002",
            cik="0000000000",
            company_name="Beta Inc",
            form_type="10-Q",
            filed_date=date(2024, 2, 1),
        ),
    ]

    filtered = EFTSSearchRunner._filter_hits_by_ticker(hits, ["ZZZZ"])

    assert filtered == hits


def test_efts_search_uses_rust_client(
    monkeypatch: pytest.MonkeyPatch, socket_enabled: None
) -> None:
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
    rust_client_instance.search_async = AsyncMock(return_value=mock_response)
    rust_client_class = Mock(return_value=rust_client_instance)
    rust_module = Mock()
    rust_module.EFTSClient = rust_client_class

    monkeypatch.setattr(efts_module, "_load_efts_module", lambda: rust_module)

    config = AnalyzeConfig(
        symbols=["AAPL"],
        search=SearchConfig(queries=["warranty"]),
        efts=EFTSConfig(enabled=True, limit=1),
    )
    runner = EFTSSearchRunner(config=config, email="test@example.com")

    results = asyncio.run(runner.search_queries(["warranty"]))

    assert results
    assert results[0].hits
    rust_client_class.assert_called_once()
    rust_client_instance.search_async.assert_called_once()
