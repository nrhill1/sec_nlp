# sec_nlp/tests/utils/test_downloader.py
from datetime import date


def test_sec_downloader_calls_client(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def get(self, **k):
            calls.append(k)

    monkeypatch.setattr("sec_nlp.utils.downloader.Downloader", FakeClient)

    from sec_nlp.utils.downloader import SECFilingDownloader
    from sec_nlp.types import FilingMode

    d = SECFilingDownloader(email="x@y.com", downloads_folder=tmp_path)
    d.add_symbols(["AAPL", "MSFT"])
    res = d.download_filings(
        mode=FilingMode.quarterly,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
    )
    assert res == {"AAPL": True, "MSFT": True}
    assert {c["filing_type"] for c in calls} == {"10-Q"}
    assert {c["symbol"] for c in calls} == {"AAPL", "MSFT"}
