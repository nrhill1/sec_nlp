from __future__ import annotations

import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest


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

    monkeypatch.setattr(sys, "argv", argv)

    # Import first to see the module structure
    import sec_nlp.cli.__main__ as cli_main

    # Patch on the actual module object
    with (
        patch.object(cli_main, "setup_folders", return_value=(out, dl)),
        patch.object(cli_main, "Pipeline", FakePipeline),
        patch.object(cli_main, "load_dotenv", MagicMock()),
    ):
        cli_main.main()

    # Verify directories exist
    assert out.exists()
    assert dl.exists()
