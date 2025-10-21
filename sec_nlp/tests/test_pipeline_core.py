from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Protocol, TypedDict, cast
from unittest.mock import MagicMock, patch

import pytest

from sec_nlp.core.enums import FilingMode
from sec_nlp.core.pipeline import Pipeline


class HasPageContent(Protocol):
    page_content: str


class ChainSummary(TypedDict):
    summary: str
    points: list[str]
    confidence: float


class ChainOutput(TypedDict):
    status: str
    summary: ChainSummary


class BatchingGraph(Protocol):
    def batch(self, batch_inputs: list[dict[str, Any]]) -> list[ChainOutput]: ...


def make_fake_doc(text: str) -> HasPageContent:
    d = cast(HasPageContent, MagicMock())
    d.page_content = text
    return d


def test_pipeline_instantiation_validates_and_loads_prompt(tmp_path: Path) -> None:
    p = Pipeline(
        mode=FilingMode.annual,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        keyword="revenue",
        out_path=tmp_path / "out",
        dl_path=tmp_path / "dl",
        dry_run=True,
    )
    assert p.keyword_lower == "revenue"
    assert p.out_path.exists()
    assert p.dl_path.exists()


@patch("sec_nlp.core.pipeline.SECFilingDownloader")
@patch("sec_nlp.core.pipeline.Preprocessor")
@patch("sec_nlp.core.pipeline.build_summarization_runnable")
def test_pipeline_run_writes_summary(
    mock_build_chain: MagicMock,
    MockPre: MagicMock,
    MockDL: MagicMock,
    tmp_path: Path,
) -> None:
    out_path = tmp_path / "out"
    out_path.mkdir(parents=True, exist_ok=True)
    dl_path = tmp_path / "dl"
    dl_path.mkdir(parents=True, exist_ok=True)

    dl_inst = cast(MagicMock, MockDL.return_value)
    dl_inst.add_symbol.return_value = None
    dl_inst.download_filings.return_value = {"AAPL": True}

    pre_inst = cast(MagicMock, MockPre.return_value)
    fake_html = dl_path / "sec-edgar-filings" / "AAPL" / "10-K" / "0001" / "primary-document.html"
    fake_html.parent.mkdir(parents=True, exist_ok=True)
    fake_html.write_text("<html>Revenue is up</html>", encoding="utf-8")
    pre_inst.html_paths_for_symbol.return_value = [fake_html]
    pre_inst.transform_html.return_value = [make_fake_doc("Revenue increased due to X")]

    class FakeGraph:
        def batch(self, batch_inputs: list[dict[str, Any]]) -> list[ChainOutput]:
            return [
                cast(
                    ChainOutput,
                    {
                        "status": "ok",
                        "summary": cast(
                            ChainSummary,
                            {
                                "summary": "Revenue up",
                                "points": ["X"],
                                "confidence": 0.9,
                            },
                        ),
                    },
                )
                for _ in batch_inputs
            ]

    mock_build_chain.return_value = cast(BatchingGraph, FakeGraph())

    pipe = Pipeline(
        mode=FilingMode.annual,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        keyword="revenue",
        out_path=out_path,
        dl_path=dl_path,
        dry_run=True,
    )

    written = pipe.run("AAPL")

    assert len(written) == 1
    out_file = written[0]
    assert out_file.exists()
    payload: dict[str, Any] = json.loads(out_file.read_text())
    assert payload["symbol"] == "AAPL"
    assert payload["summaries"][0]["summary"] == "Revenue up"


def test_pipeline_date_validators_and_errors(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Pipeline(
            mode=FilingMode.annual,
            start_date=date(2025, 1, 2),
            end_date=date(2025, 1, 1),
            keyword="rev",
            out_path=tmp_path / "o",
            dl_path=tmp_path / "d",
            dry_run=True,
        )
