# tests/pipelines/presets/test_analyze_enhancements.py
"""Tests for analysis enhancement summaries."""

from sec_nlp.core.types import is_json_mapping
from sec_nlp.pipelines.presets.analyze.io.enhancements import (
    build_peer_comparison,
    build_symbol_summary,
)
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord


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

    summary = build_symbol_summary(
        symbol="ACME",
        run_id=123,
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
        assert is_json_mapping(row)
        accession = row.get("accession")
        assert isinstance(accession, str)
        accessions.append(accession)
    assert accessions == ["0001", "0002"]

    comparisons = summary.get("filing_comparisons")
    assert isinstance(comparisons, list)
    assert len(comparisons) == 1
    comparison = comparisons[0]
    assert is_json_mapping(comparison)
    tags_added = comparison.get("tags_added")
    tags_removed = comparison.get("tags_removed")
    assert isinstance(tags_added, list)
    assert isinstance(tags_removed, list)
    added_values = [tag for tag in tags_added if isinstance(tag, str)]
    removed_values = [tag for tag in tags_removed if isinstance(tag, str)]
    assert "liquidity" in added_values
    assert "pricing" in removed_values

    rollup = summary.get("entity_rollup")
    assert is_json_mapping(rollup)
    company_rollup = rollup.get("company")
    assert is_json_mapping(company_rollup)
    assert company_rollup.get("unique") == 1
    top_values = company_rollup.get("top")
    assert isinstance(top_values, list)
    assert top_values
    top_entry = top_values[0]
    assert is_json_mapping(top_entry)
    assert top_entry.get("count") == 2


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

    summary = build_peer_comparison(profiles)

    symbols = summary.get("symbols")
    common_tags = summary.get("common_tags")
    sentiment_rank = summary.get("sentiment_rank")
    assert symbols == ["AAA", "BBB"]
    assert common_tags == ["pricing"]
    assert isinstance(sentiment_rank, list)
    assert sentiment_rank
    first_rank = sentiment_rank[0]
    assert is_json_mapping(first_rank)
    assert first_rank.get("symbol") == "AAA"
