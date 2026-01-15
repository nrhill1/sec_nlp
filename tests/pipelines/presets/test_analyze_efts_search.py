# tests/pipelines/presets/test_analyze_efts_search.py
"""Tests for EFTS search helpers."""

from datetime import date

from sec_nlp.core.edgar.efts_models import EFTSHit
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
