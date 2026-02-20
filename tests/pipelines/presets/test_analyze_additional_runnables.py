"""Tests for additional analyze runnables."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document

from sec_nlp.core.market import MarketQuote
from sec_nlp.core.stats.sector import SectorCorrelation
from sec_nlp.pipelines.presets.analyze.runnables.earnings_surprise import (
    EarningsSurpriseInput,
    EarningsSurpriseRunnable,
)
from sec_nlp.pipelines.presets.analyze.runnables.filing_sentiment_diff import (
    FilingSentimentDiffInput,
    FilingSentimentDiffRunnable,
)
from sec_nlp.pipelines.presets.analyze.runnables.regulatory_exposure import (
    RegulatoryExposureInput,
    RegulatoryExposureRunnable,
)
from sec_nlp.pipelines.presets.analyze.runnables.sector_correlation import (
    SectorCorrelationInput,
    SectorCorrelationRunnable,
)
from sec_nlp.pipelines.presets.analyze.runnables.supply_chain_map import (
    SupplyChainMapInput,
    SupplyChainMapRunnable,
)
from sec_nlp.pipelines.types import AnalysisResultDict


def test_sector_correlation_runnable_identifies_strongest_pair(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Strongest pair should use absolute correlation magnitude."""
    from sec_nlp.pipelines.presets.analyze.runnables import (
        sector_correlation as runnable_module,
    )

    def _mock_sector_correlation(*args, **kwargs) -> list[SectorCorrelation]:
        _ = args
        _ = kwargs
        return [
            SectorCorrelation(
                sic_code="SECTOR",
                symbols=["AAA", "BBB", "CCC"],
                correlation_matrix={
                    "AAA": {"AAA": 1.0, "BBB": 0.42, "CCC": -0.91},
                    "BBB": {"AAA": 0.42, "BBB": 1.0, "CCC": 0.35},
                    "CCC": {"AAA": -0.91, "BBB": 0.35, "CCC": 1.0},
                },
            )
        ]

    monkeypatch.setattr(
        runnable_module,
        "sector_correlation",
        _mock_sector_correlation,
    )

    runner = SectorCorrelationRunnable()
    output = runner.invoke(
        SectorCorrelationInput(symbols=["aaa", "BBB", "CCC"], days=120)
    )

    assert output.symbols == ["AAA", "BBB", "CCC"]
    assert output.strongest_pair == ("AAA", "CCC")
    assert output.strongest_correlation == pytest.approx(-0.91)


def test_sector_correlation_runnable_handles_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No sector data should still return normalized symbols."""
    from sec_nlp.pipelines.presets.analyze.runnables import (
        sector_correlation as runnable_module,
    )

    monkeypatch.setattr(
        runnable_module, "sector_correlation", lambda *_, **__: []
    )

    runner = SectorCorrelationRunnable()
    output = runner.invoke(SectorCorrelationInput(symbols=["bbb", "AAA"]))

    assert output.symbols == ["AAA", "BBB"]
    assert output.correlation_matrix == {}
    assert output.strongest_pair is None
    assert output.strongest_correlation is None


def test_filing_sentiment_diff_runnable_computes_deltas() -> None:
    """Runnable should compute topic deltas and risk-factor changes."""
    previous_results: list[AnalysisResultDict] = [
        {
            "sentiment": "negative",
            "tags": ["supply_chain", "risk_management"],
            "key_points": ["Supplier risk elevated"],
            "source_metadata": {"topic_hits": ["operational risk"]},
        },
        {
            "sentiment": "neutral",
            "tags": ["liquidity"],
            "key_points": ["Cash position unchanged"],
            "source_metadata": {},
        },
    ]
    current_results: list[AnalysisResultDict] = [
        {
            "sentiment": "positive",
            "tags": ["supply_chain"],
            "key_points": ["Supplier risk easing"],
            "source_metadata": {},
        },
        {
            "sentiment": "negative",
            "tags": ["liquidity"],
            "key_points": ["Liquidity risk remains high"],
            "source_metadata": {},
        },
        {
            "sentiment": "positive",
            "tags": ["new_product"],
            "key_points": ["New product launch momentum"],
            "source_metadata": {},
        },
    ]

    runner = FilingSentimentDiffRunnable()
    output = runner.invoke(
        FilingSentimentDiffInput(
            current_results=current_results,
            previous_results=previous_results,
        )
    )

    assert output.per_topic_delta["supply_chain"] == pytest.approx(2.0)
    assert output.per_topic_delta["liquidity"] == pytest.approx(-1.0)
    assert output.per_topic_delta["risk_management"] == pytest.approx(1.0)
    assert output.per_topic_delta["new_product"] == pytest.approx(1.0)
    assert output.overall_sentiment_change == pytest.approx(5 / 6)
    assert output.direction == "improving"
    assert "liquidity risk remains high" in output.new_risk_factors
    assert "operational risk" in output.removed_risk_factors


def test_filing_sentiment_diff_runnable_defaults_for_empty_inputs() -> None:
    """Empty inputs should return a stable no-op diff."""
    runner = FilingSentimentDiffRunnable()
    output = runner.invoke(FilingSentimentDiffInput())

    assert output.per_topic_delta == {}
    assert output.new_risk_factors == []
    assert output.removed_risk_factors == []
    assert output.overall_sentiment_change == 0.0
    assert output.direction == "stable"


def _quote(timestamp: int, close: float) -> MarketQuote:
    return MarketQuote(
        timestamp=timestamp,
        open_price=close,
        high=close,
        low=close,
        close=close,
        volume=1_000_000,
        adjclose=close,
    )


def test_earnings_surprise_runnable_computes_surprise_and_post_event_car(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Runnable should compute surprise % and CAR windows deterministically."""
    from sec_nlp.pipelines.presets.analyze.runnables import (
        earnings_surprise as runnable_module,
    )

    class _FakeRetriever:
        def retrieve_range(
            self,
            ticker: str,
            date_range: tuple[date, date],
        ) -> list[MarketQuote]:
            _ = date_range
            if ticker == "AAA":
                return [
                    _quote(1, 100.0),
                    _quote(2, 104.0),
                    _quote(3, 105.0),
                    _quote(4, 106.0),
                    _quote(5, 107.0),
                    _quote(6, 108.0),
                ]
            return [
                _quote(1, 200.0),
                _quote(2, 202.0),
                _quote(3, 203.0),
                _quote(4, 204.0),
                _quote(5, 205.0),
                _quote(6, 206.0),
            ]

    def _fallback_car(
        symbol_closes: list[float], benchmark_closes: list[float]
    ) -> float:
        symbol_return = (symbol_closes[-1] / symbol_closes[0]) - 1.0
        benchmark_return = (benchmark_closes[-1] / benchmark_closes[0]) - 1.0
        return symbol_return - benchmark_return

    monkeypatch.setattr(runnable_module, "corr_car", _fallback_car)

    runner = EarningsSurpriseRunnable(
        retriever=_FakeRetriever(),
        eps_provider=lambda _symbol, _period: (2.5, date(2024, 1, 2)),
    )
    output = runner.invoke(
        EarningsSurpriseInput(symbol="aaa", period="2024-Q4", expected_eps=2.0)
    )

    assert output.symbol == "AAA"
    assert output.period == "2024-Q4"
    assert output.reported_eps == pytest.approx(2.5)
    assert output.expected_eps == pytest.approx(2.0)
    assert output.surprise_pct == pytest.approx(25.0)
    assert output.post_earnings_car_1d == pytest.approx(0.03)
    assert output.post_earnings_car_5d == pytest.approx(0.05)


def test_earnings_surprise_runnable_uses_explicit_reported_eps_and_event_date() -> (
    None
):
    """Callable provider is optional if input includes reported EPS + event date."""

    class _FakeRetriever:
        def retrieve_range(
            self,
            ticker: str,
            date_range: tuple[date, date],
        ) -> list[MarketQuote]:
            _ = ticker
            _ = date_range
            return [
                _quote(1, 100.0),
                _quote(2, 101.0),
                _quote(3, 102.0),
                _quote(4, 103.0),
                _quote(5, 104.0),
                _quote(6, 105.0),
            ]

    runner = EarningsSurpriseRunnable(retriever=_FakeRetriever())
    output = runner.invoke(
        EarningsSurpriseInput(
            symbol="AAA",
            period="2024-Q4",
            expected_eps=1.0,
            reported_eps=0.8,
            event_date="2024-01-02",
        )
    )

    assert output.surprise_pct == pytest.approx(-20.0)


def test_supply_chain_map_runnable_extracts_relationships() -> None:
    """Runnable should classify subsidiary/supplier/customer relationships."""
    exhibit_doc = Document(
        page_content=(
            "Alpha Manufacturing LLC is a wholly owned subsidiary of the company."
        ),
        metadata={
            "accession_number": "0000000000-24-000001",
            "section": "Exhibit 21",
        },
    )
    risk_doc = Document(
        page_content=(
            "We rely on Beta Components Inc as a key supplier and "
            "Gamma Retail Corp as a major customer."
        ),
        metadata={
            "accession_number": "0000000000-24-000001",
            "section": "Item 1A",
        },
    )

    runner = SupplyChainMapRunnable(
        exhibit_provider=lambda _symbol: [exhibit_doc],
        risk_factor_provider=lambda _symbol: [risk_doc],
        entity_extractor=lambda text: (
            ["Alpha Manufacturing LLC"]
            if "wholly owned subsidiary" in text
            else ["Beta Components Inc", "Gamma Retail Corp"]
        ),
    )
    output = runner.invoke(SupplyChainMapInput(symbol="abc"))

    assert output.symbol == "ABC"
    assert output.entity_count == 3
    by_name = {entity.name: entity for entity in output.entities}
    assert by_name["Alpha Manufacturing LLC"].relationship == "subsidiary"
    assert by_name["Beta Components Inc"].relationship == "supplier"
    assert by_name["Gamma Retail Corp"].relationship == "customer"


def test_supply_chain_map_runnable_deduplicates_entities() -> None:
    """Duplicate entity mentions should collapse to one relationship row."""
    risk_doc_a = Document(
        page_content="Beta Components Inc is a major supplier.",
        metadata={
            "accession_number": "0000000000-24-000009",
            "section": "Item 1A",
        },
    )
    risk_doc_b = Document(
        page_content="Our supplier, Beta Components Inc, is critical.",
        metadata={
            "accession_number": "0000000000-24-000009",
            "section": "Item 1A",
        },
    )

    runner = SupplyChainMapRunnable(
        risk_factor_provider=lambda _symbol: [risk_doc_a, risk_doc_b],
        entity_extractor=lambda _text: ["Beta Components Inc"],
    )
    output = runner.invoke(
        SupplyChainMapInput(symbol="ABC", include_exhibits=False)
    )

    assert output.entity_count == 1
    assert output.entities[0].name == "Beta Components Inc"
    assert output.entities[0].relationship == "supplier"


def test_supply_chain_map_runnable_uses_entity_extension_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When available, extension-tagged ORG entities should drive extraction."""
    from sec_nlp.pipelines.presets.analyze.runnables import (
        supply_chain_map as runnable_module,
    )

    risk_doc = Document(
        page_content="Delta Metals Co is one of our key suppliers.",
        metadata={
            "accession_number": "0000000000-24-000010",
            "section": "Item 1A",
        },
    )

    monkeypatch.setattr(
        runnable_module,
        "extract_entities",
        lambda _text: [
            SimpleNamespace(
                entity_type="ORG",
                text="Delta Metals Co",
                normalized="",
            ),
            SimpleNamespace(
                entity_type="DATE",
                text="2024",
                normalized="",
            ),
        ],
    )

    runner = SupplyChainMapRunnable(
        risk_factor_provider=lambda _symbol: [risk_doc],
    )
    output = runner.invoke(
        SupplyChainMapInput(symbol="ABC", include_exhibits=False)
    )

    assert output.entity_count == 1
    assert output.entities[0].name == "Delta Metals Co"
    assert output.entities[0].relationship == "supplier"


def test_regulatory_exposure_runnable_aggregates_references_and_trend() -> None:
    """Runnable should aggregate mentions and compute compare-window trend."""
    current_documents = [
        Document(
            page_content=(
                "Rule 10b-5 and Section 13(a) apply. "
                "Rule 10b-5 remains relevant."
            ),
            metadata={"section": "Item 1A"},
        ),
        Document(
            page_content="Dodd-Frank and Clean Air Act compliance.",
            metadata={"section": "Item 1A"},
        ),
    ]
    previous_documents = [
        Document(
            page_content="Rule 10b-5 was discussed. GDPR obligations were noted.",
            metadata={"section": "Item 1A"},
        )
    ]

    runner = RegulatoryExposureRunnable()
    output = runner.invoke(
        RegulatoryExposureInput(
            documents=current_documents,
            compare_with=previous_documents,
        )
    )

    by_regulation = {
        reference.regulation: reference for reference in output.references
    }
    assert output.total_mentions == 5
    assert output.top_regulators[:2] == ["SEC", "EPA"]
    assert by_regulation["Rule 10b-5"].mention_count == 2
    assert by_regulation["Section 13(a)"].mention_count == 1
    assert by_regulation["Dodd-Frank"].mention_count == 1
    assert by_regulation["Clean Air Act"].mention_count == 1

    assert output.trend is not None
    assert output.trend["Rule 10b-5"] == 1
    assert output.trend["Section 13(a)"] == 1
    assert output.trend["Dodd-Frank"] == 1
    assert output.trend["Clean Air Act"] == 1
    assert output.trend["GDPR"] == -1


def test_regulatory_exposure_runnable_uses_entity_extension_when_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When available, extension REGULATION entities should be consumed."""
    from sec_nlp.pipelines.presets.analyze.runnables import (
        regulatory_exposure as runnable_module,
    )

    documents = [
        Document(
            page_content="Regulatory discussion text.",
            metadata={"section": "Risk Factors"},
        )
    ]
    monkeypatch.setattr(
        runnable_module,
        "extract_entities",
        lambda _text: [
            SimpleNamespace(
                entity_type="REGULATION",
                text="Rule 10b-5",
                normalized="Rule 10b-5",
            ),
            SimpleNamespace(
                entity_type="REGULATION",
                text="Rule 10b-5",
                normalized="Rule 10b-5",
            ),
            SimpleNamespace(
                entity_type="REGULATION",
                text="State Privacy Rule",
                normalized="",
            ),
            SimpleNamespace(
                entity_type="ORG",
                text="Example Corp",
                normalized="",
            ),
        ],
    )

    runner = RegulatoryExposureRunnable()
    output = runner.invoke(RegulatoryExposureInput(documents=documents))

    by_regulation = {
        reference.regulation: reference for reference in output.references
    }
    assert output.total_mentions == 3
    assert by_regulation["Rule 10b-5"].mention_count == 2
    assert by_regulation["Rule 10b-5"].regulatory_body == "SEC"
    assert by_regulation["State Privacy Rule"].mention_count == 1
    assert by_regulation["State Privacy Rule"].regulatory_body == "Unknown"


def test_regulatory_exposure_runnable_supports_custom_extractor() -> None:
    """Custom extractor should be used when configured on the runnable."""
    documents = [
        Document(
            page_content="custom text",
            metadata={"section": "Legal Proceedings"},
        )
    ]
    runner = RegulatoryExposureRunnable(
        regulation_extractor=lambda _text: [
            "Rule 10b-5",
            "Rule 10b-5",
            "State Privacy Rule",
        ]
    )
    output = runner.invoke(RegulatoryExposureInput(documents=documents))

    assert output.total_mentions == 3
    by_regulation = {
        reference.regulation: reference for reference in output.references
    }
    assert by_regulation["Rule 10b-5"].mention_count == 2
    assert by_regulation["Rule 10b-5"].regulatory_body == "SEC"
    assert by_regulation["State Privacy Rule"].regulatory_body == "Unknown"
    assert output.trend is None
