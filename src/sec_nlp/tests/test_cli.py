import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import importlib
import importlib.util


def test_cli_main_wires_pipeline_and_cleans(tmp_path, monkeypatch):

    out = tmp_path / "out"
    out.mkdir()
    dl = tmp_path / "dl"
    dl.mkdir()

    class FakePipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run_all(self, symbols):
            return {s: [out / f"{s.lower()}_x.json"] for s in symbols}

    # Simulate CLI argv
    argv = [
        "python", "-m", "sec_nlp.cli", "AAPL", "MSFT",
        "--mode", "quarterly",
        "--start_date", "2024-01-01",
        "--end_date", "2024-12-31",
        "--keyword", "revenue",
        "--limit", "1",
        "--dry-run",  # avoid Pinecone requirement
        "--no-cleanup",
    ]

    with patch("sec_nlp.cli.__main__.setup_folders", return_value=(out, dl)), \
            patch("sec_nlp.cli.__main__.Pipeline", FakePipeline), \
            patch("sec_nlp.cli.__main__.load_dotenv", lambda: None):
        monkeypatch.setattr(sys, "argv", argv)

        # Import and run main()
        import sec_nlp.cli.__main__ as entry
        importlib.reload(entry)

        entry.main()

        p: FakePipeline = entry.Pipeline  # type: ignore[assignment]

        assert out.exists() and dl.exists()
