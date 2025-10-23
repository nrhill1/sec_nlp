# sec_nlp/tests/utils/test_downloader.py
from datetime import date

import pytest


@pytest.mark.skip(reason="Network blocked during initial testing")
def test_sec_downloader_calls_client(monkeypatch, tmp_path):
    calls = []

    from sec_nlp.core.downloader import FilingManager
    from sec_nlp.core.enums import FilingMode

    d = FilingManager(email="x@y.com", downloads_folder=tmp_path)
    d.add_symbols(["AAPL", "MSFT"])

    res = d.download_filings(
        mode=FilingMode.quarterly,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    assert res == {"AAPL": True, "MSFT": True}
    assert {c["filing_type"] for c in calls} == {"10-Q"}
    assert {c["symbol"] for c in calls} == {"AAPL", "MSFT"}
