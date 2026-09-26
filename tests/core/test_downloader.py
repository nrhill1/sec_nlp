# tests/core/test_downloader.py
"""Tests for refreshed source selection and shared SEC document downloads."""

from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pytest

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.ingest import downloader
from sec_nlp.types import JsonDict

NEW = "0001234567-26-000002"
OLD = "0001234567-26-000001"


def _metadata() -> JsonDict:
    """Return latest-first submissions with two independently selectable forms."""
    return {
        "filings": {
            "recent": {
                "accessionNumber": [NEW, OLD],
                "filingDate": ["2026-09-25", "2026-09-24"],
                "primaryDocument": ["new.xml", "old.xml"],
                "form": ["4", "3"],
            },
            "files": [],
        }
    }


def _patch_sources(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Replace every HTTP entry point with deterministic local fixtures."""
    monkeypatch.setattr(
        downloader, "get_cik_for_ticker", lambda **_: "0001234567"
    )
    fetch = Mock(return_value=_metadata())
    monkeypatch.setattr(downloader, "_fetch_submissions_payload", fetch)
    monkeypatch.setattr(
        downloader, "fetch_sec_bytes", lambda *_: b"source document"
    )
    return fetch


def test_latest_limit_refreshes_metadata_when_old_cache_is_full(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    metadata = _patch_sources(monkeypatch)
    existing = tmp_path / "sec-edgar-filings" / "ACME" / "3" / OLD
    existing.mkdir(parents=True)
    (existing / "full-submission.txt").write_text("old")
    (existing / "primary-document.xml").write_text("old")
    result = downloader.download_filings(
        symbols=["ACME"],
        mode=FilingMode.insider,
        work_folder=tmp_path,
        company_name="Test",
        email="test@example.com",
        limit_per_symbol=1,
    )
    assert result["ACME"]["downloaded"] == 1
    assert (
        tmp_path
        / "sec-edgar-filings"
        / "ACME"
        / "4"
        / NEW
        / "primary-document.xml"
    ).exists()
    metadata.assert_called_once()
    second = downloader.download_filings(
        symbols=["ACME"],
        mode=FilingMode.insider,
        work_folder=tmp_path,
        company_name="Test",
        email="test@example.com",
        limit_per_symbol=1,
    )
    assert second["ACME"]["downloaded"] == 0
    assert second["ACME"]["skipped_existing"] == 1
    assert metadata.call_count == 2


def test_insider_forms_and_source_dates_filter_before_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_sources(monkeypatch)
    result = downloader.download_filings(
        symbols=["ACME"],
        mode=FilingMode.insider,
        work_folder=tmp_path,
        company_name="Test",
        email="test@example.com",
        before_date=date(2026, 9, 24),
        limit_per_symbol=1,
    )
    assert result["ACME"]["downloaded"] == 1
    assert (tmp_path / "sec-edgar-filings" / "ACME" / "3" / OLD).exists()
    assert not (tmp_path / "sec-edgar-filings" / "ACME" / "4" / NEW).exists()


def test_specialist_adapter_filters_exact_forms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_sources(monkeypatch)
    client = downloader.FilingDownloader("Test", "test@example.com", tmp_path)
    assert client.get("3", "ACME", limit=1) == 1
    assert (tmp_path / "sec-edgar-filings" / "ACME" / "3" / OLD).exists()
    assert not (tmp_path / "sec-edgar-filings" / "ACME" / "4").exists()


def test_download_errors_are_independent_by_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_sources(monkeypatch)
    monkeypatch.setattr(
        downloader,
        "_fetch_submissions_payload",
        Mock(side_effect=[ValueError("invalid response"), _metadata()]),
    )
    result = downloader.download_filings(
        symbols=["BAD", "GOOD"],
        mode=FilingMode.insider,
        work_folder=tmp_path,
        company_name="Test",
        email="test@example.com",
        limit_per_symbol=1,
    )
    assert result["BAD"]["success"] is False
    assert result["GOOD"]["success"] is True
