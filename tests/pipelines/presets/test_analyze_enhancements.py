# tests/pipelines/presets/test_analyze_enhancements.py
"""Tests for analysis enhancement summaries."""

from uuid import uuid4

from sec_nlp.core.types import as_json_dict, coerce_json_value
from sec_nlp.pipelines.presets.analyze.io.enhancements import (
    build_executive_comp_summary,
    build_peer_comparison,
    build_symbol_summary,
)
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord
from sec_nlp.types import JsonDict, JsonValue


def _as_json_list(value: JsonValue | None) -> list[JsonValue] | None:
    if value is None:
        return None
    coerced = coerce_json_value(value)
    if not isinstance(coerced, list):
        return None
    return list(coerced)


def _as_json_dict(value: JsonValue | None) -> JsonDict | None:
    if value is None:
        return None
    coerced = coerce_json_value(value)
    if coerced is None:
        return None
    return as_json_dict(coerced)


def test_build_symbol_summary_tracks_trends_and_comparisons() -> None:
    result_one: AnalysisResultDict = {
        "sentiment": "positive",
        "tags": ["pricing"],
        "impact_channels": ["demand"],
        "extracted_entities": {"company": {"details": {"name": "Acme Corp"}}},
        "source_metadata": {
            "accession_number": "0001",
            "filing_date": "2024-01-01",
            "form_type": "10-K",
        },
    }
    result_two: AnalysisResultDict = {
        "sentiment": "negative",
        "tags": ["liquidity"],
        "impact_channels": ["supply"],
        "extracted_entities": {"company": {"name": "Acme Corp"}},
        "source_metadata": {
            "accession_number": "0002",
            "filing_date": "2024-02-01",
            "form_type": "10-Q",
        },
    }
    results: list[AnalysisResultDict] = [result_one, result_two]
    fallback_meta: MetadataRecord = {}

    summary: JsonDict = build_symbol_summary(
        symbol="ACME",
        run_id=uuid4(),
        analysis_results=results,
        relevant_results=results,
        fallback_meta=fallback_meta,
    )

    assert summary["total_chunks"] == 2
    assert summary["relevant_chunks"] == 2

    trends = summary.get("sentiment_trends")
    assert isinstance(trends, list)
    accessions: list[str] = []
    for row in trends:
        assert isinstance(row, dict)
        accession = row.get("accession")
        assert isinstance(accession, str)
        accessions.append(accession)
    assert accessions == ["0001", "0002"]

    comparisons = _as_json_list(summary.get("filing_comparisons"))
    assert comparisons is not None
    assert len(comparisons) == 1
    comparison_dict = _as_json_dict(comparisons[0])
    assert comparison_dict is not None
    tags_added = comparison_dict.get("tags_added")
    tags_removed = comparison_dict.get("tags_removed")
    assert comparison_dict.get("missing_key") is None
    assert isinstance(tags_added, list)
    assert isinstance(tags_removed, list)
    added_values = [tag for tag in tags_added if isinstance(tag, str)]
    removed_values = [tag for tag in tags_removed if isinstance(tag, str)]
    assert "liquidity" in added_values
    assert "pricing" in removed_values

    rollup_dict = _as_json_dict(summary.get("entity_rollup"))
    assert rollup_dict is not None
    company_dict = _as_json_dict(rollup_dict.get("company"))
    assert company_dict is not None
    assert company_dict.get("unique") == 1
    top_values = _as_json_list(company_dict.get("top"))
    assert top_values is not None
    assert top_values
    top_entry_dict = _as_json_dict(top_values[0])
    assert top_entry_dict is not None
    assert top_entry_dict.get("count") == 2
    assert top_entry_dict.get("missing_key") is None


def test_build_peer_comparison_ranks_net_sentiment() -> None:
    profiles = {
        "AAA": {
            "top_tags": ["pricing", "demand"],
            "sentiment_breakdown": {"positive": 3, "negative": 1},
            "relevant_chunks": 4,
        },
        "BBB": {
            "top_tags": ["pricing"],
            "sentiment_breakdown": {"negative": 2},
            "relevant_chunks": 2,
        },
    }

    summary: JsonDict = build_peer_comparison(profiles)

    symbols = summary.get("symbols")
    common_tags = summary.get("common_tags")
    sentiment_rank_value = _as_json_list(summary.get("sentiment_rank"))
    assert symbols == ["AAA", "BBB"]
    assert common_tags == ["pricing"]
    assert sentiment_rank_value is not None
    assert sentiment_rank_value
    first_rank_dict = _as_json_dict(sentiment_rank_value[0])
    assert first_rank_dict is not None
    assert first_rank_dict.get("symbol") == "AAA"
    assert first_rank_dict.get("missing_key") is None


def test_build_executive_comp_summary_tracks_peer_deltas_and_yoy() -> None:
    result_one: AnalysisResultDict = {
        "source_metadata": {
            "accession_number": "0001",
            "filing_date": "2023-03-01",
            "form_type": "DEF 14A",
        },
        "tags": ["executive_compensation"],
        "extracted_entities": {
            "executives": [
                {
                    "name": "Jane Doe",
                    "title": "CEO",
                    "compensation": "2.0 million",
                }
            ]
        },
        "compensation_data": {
            "base_salary": "1.2 million",
            "bonus": "0.3 million",
            "equity": "0.5 million",
        },
        "performance_metrics": ["Adjusted EBITDA", "Revenue growth"],
        "peer_set": ["Peer A", "Peer B"],
        "pay_for_performance_flags": ["Pay-for-performance aligned"],
    }
    result_two: AnalysisResultDict = {
        "source_metadata": {
            "accession_number": "0002",
            "filing_date": "2024-03-01",
            "form_type": "DEF 14A",
        },
        "tags": ["executive_compensation"],
        "extracted_entities": {
            "executives": [
                {
                    "name": "Jane Doe",
                    "title": "CEO",
                    "compensation": "2.5 million",
                }
            ]
        },
        "compensation_data": {
            "base_salary": "1.4 million",
            "bonus": "0.4 million",
            "equity": "0.7 million",
        },
        "performance_metrics": ["Adjusted EBITDA"],
        "peer_set": ["Peer A", "Peer C"],
        "pay_for_performance_flags": ["TSR weighting 50%"],
    }
    results = [result_one, result_two]

    summary: JsonDict = build_executive_comp_summary(
        symbol="ACME",
        run_id=uuid4(),
        analysis_results=results,
        relevant_results=results,
        fallback_meta={},
    )

    filings = summary.get("filings")
    assert isinstance(filings, list)
    assert len(filings) == 2

    yoy_changes_value = _as_json_list(summary.get("yoy_changes"))
    assert yoy_changes_value is not None
    assert yoy_changes_value
    first_change_dict = _as_json_dict(yoy_changes_value[0])
    assert first_change_dict is not None
    assert first_change_dict.get("name") == "Jane Doe"
    delta = first_change_dict.get("delta")
    assert first_change_dict.get("missing_key") is None
    assert isinstance(delta, float)
    assert abs(delta - 500000.0) < 0.01

    peer_deltas_value = _as_json_list(summary.get("peer_deltas"))
    assert peer_deltas_value is not None
    assert peer_deltas_value
    first_delta_dict = _as_json_dict(peer_deltas_value[0])
    assert first_delta_dict is not None
    added = first_delta_dict.get("added")
    removed = first_delta_dict.get("removed")
    assert first_delta_dict.get("missing_key") is None
    assert isinstance(added, list)
    assert isinstance(removed, list)
    added_values = [item for item in added if isinstance(item, str)]
    removed_values = [item for item in removed if isinstance(item, str)]
    assert "Peer C" in added_values
    assert "Peer B" in removed_values
