# tests/pipelines/presets/test_holdings_pipeline.py
"""Tests for holdings pipeline and helper steps."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.edgar.holdings_parser import HoldingsParser
from sec_nlp.pipelines.presets.holdings.config import HoldingsSettings
from sec_nlp.pipelines.presets.holdings.models import HoldingPosition
from sec_nlp.pipelines.presets.holdings.pipeline import HoldingsPipeline
from sec_nlp.pipelines.presets.holdings.run_stages import (
    HoldingsRunState,
    build_holdings_stage_chain,
)
from sec_nlp.pipelines.presets.holdings.steps.aggregate import (
    build_ownership_summary,
)
from sec_nlp.pipelines.presets.holdings.steps.diff import build_holdings_diffs
from sec_nlp.pipelines.presets.holdings.steps.download import (
    DownloadedHoldingsFiling,
    download_holdings_filings,
)
from sec_nlp.pipelines.presets.holdings.steps.parse import (
    parse_holding_positions,
)


def _position(
    *,
    accession: str,
    filed_date: str,
    cusip: str,
    shares: int,
    value: int,
    issuer: str,
) -> HoldingPosition:
    return HoldingPosition(
        symbol="ABC",
        accession_number=accession,
        form_type="13F-HR",
        filed_date=filed_date,
        issuer=issuer,
        title_of_class="COM",
        cusip=cusip,
        shares=shares,
        value_thousands=value,
    )


def test_parse_holding_positions_maps_parser_documents() -> None:
    filing = DownloadedHoldingsFiling(
        symbol="ABC",
        form_type="13F-HR",
        accession_number="0000000000-24-000001",
        filing_dir=Path("."),
        filed_date=date(2024, 1, 31),
    )

    doc = Document(
        page_content="holding",
        metadata={
            "accession_number": filing.accession_number,
            "form_type": filing.form_type,
            "filed_date": "2024-01-31",
            "holding_index": 1,
            "issuer": "Acme Corp",
            "title_of_class": "COM",
            "cusip": "000000000",
            "value": 12345,
            "shares": 1000,
            "share_type": "SH",
            "investment_discretion": "SOLE",
            "other_manager": None,
            "voting_authority": {"sole": 1000, "shared": 0, "none": 0},
            "source": "/tmp/infotable.xml",
        },
    )

    class _Parser(HoldingsParser):
        def parse_accession_dir(self, accession_dir: Path) -> list[Document]:
            _ = accession_dir
            return [doc]

    parser = _Parser()

    positions = parse_holding_positions(
        symbol="ABC",
        filing=filing,
        parser=parser,
        cusip_filter="000000000",
    )

    assert len(positions) == 1
    assert positions[0].issuer == "Acme Corp"
    assert positions[0].cusip == "000000000"
    assert positions[0].voting_sole == 1000
    assert positions[0].source_file == "infotable.xml"


def test_build_holdings_diffs_detects_change_types() -> None:
    positions = [
        _position(
            accession="a1",
            filed_date="2024-03-31",
            cusip="CUSIP_A",
            shares=100,
            value=1000,
            issuer="Issuer A",
        ),
        _position(
            accession="a1",
            filed_date="2024-03-31",
            cusip="CUSIP_B",
            shares=50,
            value=500,
            issuer="Issuer B",
        ),
        _position(
            accession="a1",
            filed_date="2024-03-31",
            cusip="CUSIP_D",
            shares=20,
            value=200,
            issuer="Issuer D",
        ),
        _position(
            accession="a2",
            filed_date="2024-06-30",
            cusip="CUSIP_A",
            shares=150,
            value=1200,
            issuer="Issuer A",
        ),
        _position(
            accession="a2",
            filed_date="2024-06-30",
            cusip="CUSIP_C",
            shares=10,
            value=100,
            issuer="Issuer C",
        ),
        _position(
            accession="a2",
            filed_date="2024-06-30",
            cusip="CUSIP_D",
            shares=20,
            value=200,
            issuer="Issuer D",
        ),
    ]

    diffs = build_holdings_diffs(symbol="ABC", positions=positions)
    by_cusip = {diff.cusip: diff for diff in diffs}

    assert by_cusip["CUSIP_A"].status == "increase"
    assert by_cusip["CUSIP_B"].status == "exit"
    assert by_cusip["CUSIP_C"].status == "new"
    assert by_cusip["CUSIP_D"].status == "unchanged"


def test_build_ownership_summary_computes_hhi() -> None:
    positions = [
        _position(
            accession="a1",
            filed_date="2024-03-31",
            cusip="OLD",
            shares=10,
            value=100,
            issuer="Old",
        ),
        _position(
            accession="a2",
            filed_date="2024-06-30",
            cusip="CUSIP_A",
            shares=100,
            value=800,
            issuer="Issuer A",
        ),
        _position(
            accession="a2",
            filed_date="2024-06-30",
            cusip="CUSIP_B",
            shares=50,
            value=200,
            issuer="Issuer B",
        ),
    ]

    summary = build_ownership_summary(
        symbol="ABC",
        positions=positions,
        top_holders=5,
    )

    assert summary.latest_accession == "a2"
    assert summary.total_value_thousands == 1000
    assert summary.total_positions == 2
    assert summary.concentration_hhi == 6800.0
    assert summary.top_holdings[0].cusip == "CUSIP_A"
    assert summary.top_holdings[0].portfolio_weight == 0.8


def test_pipeline_run_writes_outputs_with_mocked_steps(
    tmp_path: Path, monkeypatch
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    config = HoldingsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=dl_path,
        out_path=out_path,
        output_format="all",
        quarters=4,
    )

    filing = DownloadedHoldingsFiling(
        symbol="ABC",
        form_type="13F-HR",
        accession_number="0000000000-24-000001",
        filing_dir=tmp_path,
        filed_date=date(2024, 6, 30),
    )

    positions = [
        _position(
            accession=filing.accession_number,
            filed_date="2024-06-30",
            cusip="CUSIP_A",
            shares=100,
            value=1000,
            issuer="Issuer A",
        )
    ]

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.holdings.run_stages.download_holdings_filings",
        lambda symbol, settings: [filing],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.holdings.run_stages.parse_holding_positions",
        lambda symbol, filing, parser, cusip_filter=None: positions,
    )

    pipeline = HoldingsPipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert result.symbols_processed == 1
    assert result.positions_processed == 1
    assert result.diffs_generated == 0
    assert len(result.outputs) == 5
    for output_path in result.outputs:
        assert output_path.exists()

    summary_json_path = next(
        path for path in result.outputs if path.name.endswith("_summary.json")
    )
    summary_payload = json.loads(summary_json_path.read_text())
    expected_short_id = config.short_id if config.short_id > 0 else None
    assert summary_payload["run_id"] == str(config.run_id)
    assert summary_payload["run_short_id"] == expected_short_id
    assert isinstance(summary_payload["run_timestamp"], str)

    snapshot_path = next(
        path for path in result.outputs if path.name.endswith("_snapshot.csv")
    )
    lines = snapshot_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
    assert lines[4].startswith("symbol,accession_number")


def test_download_holdings_filings_uses_include_amends_for_13f_amendments(
    tmp_path: Path, monkeypatch
) -> None:
    dl_root = tmp_path / "downloads"
    filing_dir = (
        dl_root
        / "sec-edgar-filings"
        / "ABC"
        / "13F-HR"
        / "0000000000-24-000001"
    )
    filing_dir.mkdir(parents=True)

    type _CallValue = str | int | bool | date | None
    calls: list[dict[str, _CallValue]] = []

    class _FakeDownloader:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get(
            self,
            form: str,
            ticker_or_cik: str,
            *,
            limit: int | None = None,
            after: date | None = None,
            before: date | None = None,
            include_amends: bool = False,
            download_details: bool = False,
            accession_numbers_to_skip: set[str] | None = None,
        ) -> int:
            _ = accession_numbers_to_skip
            calls.append(
                {
                    "form": form,
                    "ticker_or_cik": ticker_or_cik,
                    "limit": limit,
                    "after": after,
                    "before": before,
                    "include_amends": include_amends,
                    "download_details": download_details,
                }
            )
            return 0

    monkeypatch.setattr(
        "sec_nlp.core.ingest.downloader.FilingDownloader", _FakeDownloader
    )

    settings = HoldingsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=dl_root,
        out_path=tmp_path / "out",
        forms=["13F-HR", "13F-HR/A"],
        quarters=4,
    )

    filings = download_holdings_filings(symbol="ABC", settings=settings)

    assert len(calls) == 1
    assert calls[0]["form"] == "13F-HR"
    assert calls[0]["include_amends"] is True
    assert calls[0]["download_details"] is True
    assert len(filings) == 1
    assert filings[0].form_type == "13F-HR"


def test_holdings_stage_chain_preserves_state_identity(
    tmp_path: Path, monkeypatch
) -> None:
    config = HoldingsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="json",
    )
    pipeline = HoldingsPipeline(config=config)
    monkeypatch.setattr(
        HoldingsPipeline,
        "_write_outputs",
        lambda self, **_kwargs: [],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.holdings.run_stages.download_holdings_filings",
        lambda symbol, settings: [],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.holdings.run_stages.parse_holding_positions",
        lambda symbol, filing, parser, cusip_filter=None: [],
    )

    chain = build_holdings_stage_chain(pipeline)
    initial_state = HoldingsRunState(
        runtime=pipeline,
        symbol="ABC",
        progress=None,
        phase_task=None,
    )
    initial_state_id = id(initial_state)
    final_state = pipeline.run_stage_chain(
        initial_state=initial_state,
        stage_chain=chain,
    )

    assert id(final_state) == initial_state_id
