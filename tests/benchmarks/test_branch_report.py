# tests/benchmarks/test_branch_report.py
"""Tests for branch benchmark report helpers and Markdown rendering."""

from pathlib import Path

from scripts.profile.branch_report import (
    BenchmarkSuite,
    RefMetadata,
    _branch_summary_payload,
    _comparison_summary_payload,
    _render_markdown_report,
    _retarget_cli_case,
    _suite_collection_name,
)
from scripts.profile.perf_suite import PerfCase
from sec_nlp.core.types import as_json_dict


def test_suite_collection_name_is_stable_and_sanitized() -> None:
    """Build stable collection names for branch comparison suites."""
    assert (
        _suite_collection_name(
            suite_name="flow rems candidates",
            ref_label="Feature/Branch",
            repeat_index=2,
        )
        == "branch_report_feature_branch_flow_rems_candidates_r2"
    )


def test_retarget_cli_case_rewrites_collection_arguments() -> None:
    """Clone one chat case with suite-specific vector settings."""
    case = PerfCase(
        name="chat_rems_thematic",
        pipeline="chat",
        args=[
            "chat",
            "MP",
            "--vdb.collection-name",
            "old_collection",
            "--vdb.qdrant-location",
            ".qdrant/old",
            "--collections",
            "old_collection",
        ],
        tags=["chat", "rems", "thematic"],
    )

    updated = _retarget_cli_case(
        case,
        collection_name="branch_report_feature_thematic_r1",
        qdrant_location=Path("/tmp/qdrant"),
    )

    assert updated.args == [
        "chat",
        "MP",
        "--vdb.collection-name",
        "branch_report_feature_thematic_r1",
        "--vdb.qdrant-location",
        "/tmp/qdrant",
        "--collections",
        "branch_report_feature_thematic_r1",
    ]


def test_branch_summary_and_comparison_payloads_render_markdown() -> None:
    """Build summary payloads and render a comparison report."""
    suite = BenchmarkSuite(
        name="thematic_retrieve_chat",
        include_tags=["thematic", "benchmark"],
        repeats=2,
        description="Directional thematic retrieve/chat comparisons.",
    )
    feature_meta = RefMetadata(
        label="feature",
        ref="HEAD",
        branch="feature-branch",
        commit="feature123",
        workdir=Path("/tmp/feature"),
    )
    baseline_meta = RefMetadata(
        label="main",
        ref="main",
        branch="main",
        commit="main456",
        workdir=Path("/tmp/main"),
    )
    feature_summary = _branch_summary_payload(
        ref_meta=feature_meta,
        suites=[suite],
        suite_summaries={
            "thematic_retrieve_chat": {
                "summary": {
                    "chat_rems_thematic": {
                        "pipeline": "chat",
                        "iterations": 2,
                        "success_count": 2,
                        "mean_seconds": 12.0,
                        "p95_seconds": 13.0,
                        "stage_mean_seconds": {"llm_generate": 6.0},
                        "output_mean_counts": {"hits_retrieved": 9.0},
                    }
                }
            }
        },
    )
    baseline_summary = _branch_summary_payload(
        ref_meta=baseline_meta,
        suites=[suite],
        suite_summaries={
            "thematic_retrieve_chat": {
                "summary": {
                    "chat_rems_thematic": {
                        "pipeline": "chat",
                        "iterations": 2,
                        "success_count": 2,
                        "mean_seconds": 10.0,
                        "p95_seconds": 11.0,
                        "stage_mean_seconds": {"llm_generate": 5.0},
                        "output_mean_counts": {"hits_retrieved": 8.0},
                    }
                }
            }
        },
    )

    comparison = _comparison_summary_payload(
        feature_summary=feature_summary,
        baseline_summary=baseline_summary,
        suites=[suite],
    )
    suites_raw = comparison.get("suites")
    assert suites_raw is not None
    suites_payload = as_json_dict(suites_raw)
    assert suites_payload is not None
    suite_payload_raw = suites_payload.get("thematic_retrieve_chat")
    assert suite_payload_raw is not None
    suite_payload = as_json_dict(suite_payload_raw)
    assert suite_payload is not None
    cases_raw = suite_payload.get("cases")
    assert cases_raw is not None
    cases_payload = as_json_dict(cases_raw)
    assert cases_payload is not None
    case_payload_raw = cases_payload.get("chat_rems_thematic")
    assert case_payload_raw is not None
    case_payload = as_json_dict(case_payload_raw)
    assert case_payload is not None
    assert case_payload.get("delta_p95_seconds") == 2.0
    assert case_payload.get("delta_p95_pct") == 18.181818

    markdown = _render_markdown_report(
        feature_summary=feature_summary,
        baseline_summary=baseline_summary,
        comparison_summary=comparison,
        suites=[suite],
    )

    assert "Conflict/Monopoly Benchmark Report" in markdown
    assert "`feature-branch` at `feature123`" in markdown
    assert "`main` at `main456`" in markdown
    assert (
        "| chat_rems_thematic | 2/2 | 2/2 | 13.0 | 11.0 | 2.0 | 18.181818 |"
        in markdown
    )
