# tests/core/test_downloader.py
"""Tests for download helpers."""

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.ingest import downloader as downloader_module


def test_download_filings_insider_requests_both_forms(
    tmp_path, monkeypatch
) -> None:
    calls = []

    class FakeDownloader:
        def __init__(self, company_name, email, work_folder) -> None:
            self.company_name = company_name
            self.email = email
            self.work_folder = work_folder

        def get(
            self,
            form_type,
            symbol,
            after=None,
            before=None,
            limit=None,
            download_details=True,
        ):
            calls.append(
                {
                    "form_type": form_type,
                    "symbol": symbol,
                    "after": after,
                    "before": before,
                    "limit": limit,
                    "download_details": download_details,
                }
            )
            return 2

    monkeypatch.setattr(downloader_module, "Downloader", FakeDownloader)

    results = downloader_module.download_filings(
        symbols=["ACME"],
        mode=FilingMode.insider,
        work_folder=tmp_path,
        company_name="Test Co",
        email="test@example.com",
        after_date=None,
        before_date=None,
        limit_per_symbol=None,
    )

    assert len(calls) == 2
    forms = {call.get("form_type") for call in calls}
    assert forms == {"3", "4"}

    result = results.get("ACME")
    assert isinstance(result, dict)
    assert result.get("downloaded") == 4
    assert result.get("form_type") == "3, 4"
