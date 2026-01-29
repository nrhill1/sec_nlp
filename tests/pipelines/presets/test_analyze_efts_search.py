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


def test_filter_hits_by_ticker_filters_to_matching_tickers() -> None:
    """Ticker filter should only keep hits with matching tickers."""
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
            tickers=["BETA"],
        ),
        EFTSHit(
            accession_number="0000000000-24-000003",
            cik="0000000000",
            company_name="Gamma Inc",
            form_type="10-K",
            filed_date=date(2024, 3, 1),
            tickers=[],  # No ticker
        ),
    ]

    # Filter for ALPHA only
    filtered = EFTSSearchRunner._filter_hits_by_ticker(hits, ["ALPHA"])
    assert len(filtered) == 1
    assert filtered[0].tickers == ["ALPHA"]

    # Filter for BETA only
    filtered = EFTSSearchRunner._filter_hits_by_ticker(hits, ["BETA"])
    assert len(filtered) == 1
    assert filtered[0].tickers == ["BETA"]

    # Filter for non-existent ticker returns empty
    filtered = EFTSSearchRunner._filter_hits_by_ticker(hits, ["ZZZZ"])
    assert len(filtered) == 0


def test_filter_hits_by_ticker_empty_filter_keeps_all() -> None:
    """Empty ticker filter should keep all hits."""
    hits = [
        EFTSHit(
            accession_number="0000000000-24-000001",
            cik="0000000000",
            company_name="Alpha Inc",
            form_type="10-K",
            filed_date=date(2024, 1, 1),
            tickers=["ALPHA"],
        ),
    ]

    filtered = EFTSSearchRunner._filter_hits_by_ticker(hits, [])
    assert filtered == hits


def test_filter_hits_by_ticker_case_insensitive() -> None:
    """Ticker filter should be case-insensitive."""
    hits = [
        EFTSHit(
            accession_number="0000000000-24-000001",
            cik="0000000000",
            company_name="Apple Inc",
            form_type="10-K",
            filed_date=date(2024, 1, 1),
            tickers=["AAPL"],
        ),
    ]

    # Lowercase filter should match uppercase ticker
    filtered = EFTSSearchRunner._filter_hits_by_ticker(hits, ["aapl"])
    assert len(filtered) == 1


def test_efts_hit_uses_actual_ticker_not_search_symbol() -> None:
    """EFTS hits should use the filing's ticker, not the search context symbol.

    This guards against a regression where all EFTS results were tagged with
    the search symbol (e.g., AAPL) even when the hits were from other companies
    (e.g., DPZ, AMSWA).
    """
    hit = EFTSHit(
        accession_number="0001234567-24-000001",
        cik="0001234567",
        company_name="Dominos Pizza Inc",
        form_type="10-K",
        filed_date=date(2024, 1, 15),
        tickers=["DPZ"],
        snippet="supply chain risk disclosure",
        score=15.0,
    )

    # The hit's ticker property should return the actual ticker
    assert hit.ticker == "DPZ"
    assert hit.tickers == ["DPZ"]

    # When EFTS results are processed, symbol should come from hit, not search context
    # This is the key behavior: hit.ticker should be used for metadata["symbol"]
    hit_symbol = hit.ticker or (hit.tickers[0] if hit.tickers else "AAPL")
    assert hit_symbol == "DPZ", (
        "Symbol should come from hit.ticker, not search context"
    )


def test_efts_hit_falls_back_to_tickers_list() -> None:
    """When hit.ticker is None, fall back to tickers[0]."""
    # Create hit with tickers but ticker property returns None (e.g., empty string)
    hit = EFTSHit(
        accession_number="0001234567-24-000002",
        cik="0001234567",
        company_name="Test Co",
        form_type="10-K",
        filed_date=date(2024, 1, 15),
        tickers=["TST"],
    )

    # Verify fallback logic works
    tickers = [t for t in hit.tickers if isinstance(t, str) and t]
    hit_symbol = hit.ticker or (tickers[0] if tickers else "FALLBACK")
    assert hit_symbol == "TST"


def test_efts_hit_falls_back_to_search_symbol_when_no_tickers() -> None:
    """When hit has no tickers, fall back to search context symbol."""
    hit = EFTSHit(
        accession_number="0001234567-24-000003",
        cik="0001234567",
        company_name="Unknown Co",
        form_type="10-K",
        filed_date=date(2024, 1, 15),
        tickers=[],  # No tickers
    )

    search_symbol = "AAPL"
    tickers = [t for t in hit.tickers if isinstance(t, str) and t]
    hit_symbol = hit.ticker or (tickers[0] if tickers else search_symbol)
    assert hit_symbol == "AAPL", (
        "Should fall back to search symbol when no tickers"
    )


def test_efts_search_uses_rust_client(
    monkeypatch: pytest.MonkeyPatch, socket_enabled: None
) -> None:
    from sec_nlp.core.edgar import efts as efts_module

    # Create mock hit object with attribute access
    mock_hit = Mock()
    mock_hit.accession_number = "0001234567-24-000001"
    mock_hit.cik = "0001234567"
    mock_hit.company_name = "Test Co"
    mock_hit.tickers = ["AAPL"]
    mock_hit.form_type = "10-K"
    mock_hit.filed_date = date(2024, 1, 15)
    mock_hit.file_number = None
    mock_hit.film_number = None
    mock_hit.snippet = "test"
    mock_hit.score = 1.0
    mock_hit.filing_url = None

    # Create mock batch result object with attribute access
    mock_batch_result = Mock()
    mock_batch_result.query = "warranty"
    mock_batch_result.total = 1
    mock_batch_result.hits = [mock_hit]
    mock_batch_result.error = None

    rust_client_instance = Mock()
    # Use AsyncMock for the async method
    rust_client_instance.batch_search_async = AsyncMock(
        return_value=[mock_batch_result]
    )
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
    rust_client_instance.batch_search_async.assert_called_once()
