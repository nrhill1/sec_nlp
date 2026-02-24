# tests/benchmarks/test_chat_retrieve_perf.py
"""Deterministic perf-suite utility tests (no network)."""

from __future__ import annotations

import pytest

from scripts.profile.perf_suite import (
    PerfIteration,
    _build_summary,
    _percentile,
    _safe_output_counts,
    _safe_stage_timings,
)
from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonValue


def test_percentile_linear_interpolation() -> None:
    values = [1.0, 3.0, 5.0, 7.0]
    assert _percentile(values, 95) == pytest.approx(6.7)
    assert _percentile(values, 50) == 4.0


def test_build_summary_aggregates_case_iterations() -> None:
    iterations = [
        PerfIteration(
            case="chat_case",
            pipeline="chat",
            iteration=1,
            run_id="r1",
            success=True,
            return_code=0,
            elapsed_seconds=10.0,
            started_at="2026-02-20T00:00:00+00:00",
            stage_timings={"vector_search": 1.0, "llm_generate": 5.0},
            output_counts={"hits_retrieved": 8, "citations_returned": 4},
            stderr_tail=None,
        ),
        PerfIteration(
            case="chat_case",
            pipeline="chat",
            iteration=2,
            run_id="r2",
            success=True,
            return_code=0,
            elapsed_seconds=14.0,
            started_at="2026-02-20T00:01:00+00:00",
            stage_timings={"vector_search": 1.5, "llm_generate": 7.0},
            output_counts={"hits_retrieved": 9, "citations_returned": 5},
            stderr_tail=None,
        ),
    ]

    summary = _build_summary(iterations)
    case_summary_raw = summary.get("chat_case")
    assert case_summary_raw is not None
    case_summary = as_json_dict(case_summary_raw)
    assert case_summary is not None
    assert case_summary.get("iterations") == 2
    assert case_summary.get("success_count") == 2
    assert case_summary.get("mean_seconds") == 12.0
    assert case_summary.get("p95_seconds") == 13.8
    stage_mean_raw = case_summary.get("stage_mean_seconds")
    assert stage_mean_raw is not None
    stage_mean = as_json_dict(stage_mean_raw)
    assert stage_mean is not None
    assert stage_mean.get("vector_search") == 1.25
    assert stage_mean.get("llm_generate") == 6.0


def test_safe_stage_timings_filters_non_numeric_values() -> None:
    stage = _safe_stage_timings(
        {
            "stage_timings": {
                "vector_search": 1.2,
                "write": "bad",
                "rerank": 0.8,
            }
        }
    )
    assert stage == {"vector_search": 1.2, "rerank": 0.8}


def test_safe_output_counts_handles_chat_and_retrieve() -> None:
    chat_counts = _safe_output_counts(
        "chat",
        {"hits_retrieved": 11, "citations_returned": 3},
    )
    assert chat_counts == {"hits_retrieved": 11, "citations_returned": 3}

    retrieve_counts = _safe_output_counts(
        "retrieve",
        {
            "ABC": {"ranked_hits": 4},
            "XYZ": {"ranked_hits": 6},
            "stage_timings": {"write": 0.1},
        },
    )
    assert retrieve_counts == {"ranked_hits": 10}
