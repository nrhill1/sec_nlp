# tests/pipelines/presets/test_financials_pipeline.py
"""Tests for the financials pipeline and step helpers."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from sec_nlp.core.edgar.xbrl_facts import XbrlFact, XbrlParser
from sec_nlp.pipelines.presets.financials.config import FinancialsSettings
from sec_nlp.pipelines.presets.financials.models import FinancialFact
from sec_nlp.pipelines.presets.financials.pipeline import FinancialsPipeline
from sec_nlp.pipelines.presets.financials.steps.aggregate import (
    aggregate_financials,
    build_delta_report,
)
from sec_nlp.pipelines.presets.financials.steps.download import DownloadedFiling
from sec_nlp.pipelines.presets.financials.steps.extract import (
    extract_financial_facts,
    normalize_concept,
)


def test_normalize_concept_maps_expected_aliases() -> None:
    assert normalize_concept("us-gaap:Revenues", "Revenues") == "revenue"
    assert (
        normalize_concept("ifrs-full:ProfitLoss", "ProfitLoss") == "net_income"
    )
    assert normalize_concept("us-gaap:Assets", "Assets") == "total_assets"
    assert normalize_concept("custom:UnknownMetric", "UnknownMetric") is None


def test_extract_financial_facts_dedupes_and_filters(tmp_path: Path) -> None:
    filing_dir = tmp_path / "filing"
    filing_dir.mkdir()
    xbrl_file = filing_dir / "sample.xml"
    xbrl_file.write_text("<xbrl/>")

    filing = DownloadedFiling(
        symbol="ABC",
        form_type="10-K",
        accession_number="0000000000-24-000001",
        filing_dir=filing_dir,
        filed_date=date(2024, 12, 31),
    )

    duplicate = XbrlFact(
        tag="us-gaap:Revenues",
        namespace="us-gaap",
        local_name="Revenues",
        value=100.0,
        raw_value="100.0",
        scale=0,
        unit="USD",
        decimals=0,
        context_ref="ctx_20241231",
        period_start="2024-01-01",
        period_end="2024-12-31",
        period_instant=None,
        entity_id=None,
        segment=None,
    )

    class _Parser(XbrlParser):
        def __init__(self) -> None:
            pass

        def parse_file(self, path: str | Path) -> list[XbrlFact]:
            _ = path
            return [duplicate, duplicate]

    parser = _Parser()

    facts = extract_financial_facts(
        symbol="ABC",
        filing=filing,
        parser=parser,
    )
    assert len(facts) == 1
    assert facts[0].concept == "revenue"
    assert facts[0].accession_number == filing.accession_number


def test_aggregate_financials_computes_ratios() -> None:
    facts = [
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="revenue",
            raw_tag="us-gaap:Revenues",
            value=200.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="gross_profit",
            raw_tag="us-gaap:GrossProfit",
            value=80.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="operating_income",
            raw_tag="us-gaap:OperatingIncomeLoss",
            value=50.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="net_income",
            raw_tag="us-gaap:NetIncomeLoss",
            value=40.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="total_liabilities",
            raw_tag="us-gaap:Liabilities",
            value=120.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="stockholders_equity",
            raw_tag="us-gaap:StockholdersEquity",
            value=100.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="current_assets",
            raw_tag="us-gaap:AssetsCurrent",
            value=50.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="current_liabilities",
            raw_tag="us-gaap:LiabilitiesCurrent",
            value=25.0,
            period_end="2024-12-31",
        ),
    ]

    statements = aggregate_financials(facts, compute_ratios=True)
    assert len(statements) == 1
    statement = statements[0]
    assert statement.current_ratio == 2.0
    assert statement.debt_to_equity == 1.2
    assert statement.gross_margin == 0.4
    assert statement.operating_margin == 0.25
    assert statement.roe == 0.4


def test_build_delta_report_compares_latest_two_periods() -> None:
    facts = [
        FinancialFact(
            symbol="ABC",
            accession_number="a1",
            form_type="10-K",
            concept="revenue",
            raw_tag="us-gaap:Revenues",
            value=200.0,
            period_end="2024-12-31",
        ),
        FinancialFact(
            symbol="ABC",
            accession_number="a0",
            form_type="10-K",
            concept="revenue",
            raw_tag="us-gaap:Revenues",
            value=150.0,
            period_end="2023-12-31",
        ),
    ]
    statements = aggregate_financials(facts, compute_ratios=False)
    report = build_delta_report(statements)
    revenue_delta = report["revenue"]
    assert revenue_delta.current == 200.0
    assert revenue_delta.previous == 150.0
    assert revenue_delta.absolute_change == 50.0
    assert revenue_delta.percent_change == 50.0 / 150.0


def test_pipeline_run_writes_outputs_with_mocked_steps(
    tmp_path: Path, monkeypatch
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    config = FinancialsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=dl_path,
        out_path=out_path,
        output_format="all",
        include_delta_report=True,
        periods=4,
    )

    filing = DownloadedFiling(
        symbol="ABC",
        form_type="10-K",
        accession_number="0000000000-24-000001",
        filing_dir=tmp_path,
        filed_date=date(2024, 12, 31),
    )

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.financials.run_stages.download_financial_filings",
        lambda symbol, settings: [filing],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.financials.run_stages.extract_financial_facts",
        lambda symbol, filing, parser: [
            FinancialFact(
                symbol=symbol,
                accession_number=filing.accession_number,
                form_type=filing.form_type,
                concept="revenue",
                raw_tag="us-gaap:Revenues",
                value=123.0,
                period_end="2024-12-31",
            )
        ],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.financials.pipeline.create_xbrl_parser",
        lambda: SimpleNamespace(),
    )

    pipeline = FinancialsPipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert result.symbols_processed == 1
    assert result.periods_generated == 1
    assert len(result.outputs) == 3
    for output_path in result.outputs:
        assert output_path.exists()

    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    expected_short_id = config.short_id if config.short_id > 0 else None
    assert payload["run_id"] == str(config.run_id)
    assert payload["run_short_id"] == expected_short_id
    assert isinstance(payload["run_timestamp"], str)

    csv_path = next(path for path in result.outputs if path.suffix == ".csv")
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
