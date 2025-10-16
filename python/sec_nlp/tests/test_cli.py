from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Iterable, Mapping

import importlib
import importlib.util
import pytest
from unittest.mock import patch


def test_cli_main_wires_pipeline_and_cleans(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    out.mkdir()
    dl = tmp_path / "dl"
    dl.mkdir()

    class FakePipeline:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs: Mapping[str, Any] = dict(kwargs)

        def run_all(self, symbols: Iterable[str]) -> dict[str, list[Path]]:
            return {s: [out / f"{s.lower()}_x.json"] for s in symbols}

    argv: list[str] = [
        "python",
        "-m",
        "sec_nlp.cli",
        "AAPL",
        "MSFT",
        "--mode",
        "quarterly",
        "--start_date",
        "2024-01-01",
        "--end_date",
        "2024-12-31",
        "--keyword",
        "revenue",
        "--limit",
        "1",
        "--dry-run",
        "--no-cleanup",
    ]

    with (
        patch("sec_nlp.cli.__main__.setup_folders", return_value=(out, dl)),
        patch("sec_nlp.cli.__main__.Pipeline", FakePipeline),
        patch("sec_nlp.cli.__main__.load_dotenv", lambda: None),
    ):
        monkeypatch.setattr(sys, "argv", argv)

        import sec_nlp.cli.__main__ as entry

        importlib.reload(entry)
        entry.main()

    assert out.exists() and dl.exists()
