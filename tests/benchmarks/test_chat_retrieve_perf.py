# tests/benchmarks/test_chat_retrieve_perf.py
"""Deterministic perf-suite utility tests (no network)."""

from __future__ import annotations

import pytest

from scripts.profile.perf_suite import (
    PerfIteration,
    _apply_flow_benchmark_overrides,
    _build_summary,
    _default_cases,
    _flow_output_counts,
    _flow_stage_timings,
    _flow_stage_timings_for_iteration,
    _percentile,
    _safe_output_counts,
    _safe_stage_timings,
)
from sec_nlp.app.flows.models import (
    FlowDefaults,
    FlowRunResult,
    FlowSpec,
    FlowStageResult,
    FlowStageSpec,
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


def test_flow_helpers_collect_stage_metrics_and_counts() -> None:
    """Build flow metrics from one synthetic flow result."""
    result = FlowRunResult(
        flow_run_id="flow-1",
        flow_name="synthetic_flow",
        success=False,
        stage_results=[
            FlowStageResult(
                stage_id="retrieve_terms",
                pipeline="retrieve",
                success=True,
                duration_seconds=12.5,
            ),
            FlowStageResult(
                stage_id="chat_answer",
                pipeline="chat",
                success=False,
                duration_seconds=31.75,
                error="timeout",
            ),
        ],
        metadata={
            "answer_output_paths": [
                "/tmp/answer.yaml",
                "/tmp/answer.json",
            ]
        },
    )

    assert _flow_stage_timings(result) == {
        "retrieve_terms": 12.5,
        "chat_answer": 31.75,
    }
    assert _flow_stage_timings_for_iteration(
        result,
        elapsed_seconds=60.0,
    ) == {
        "retrieve_terms": 12.5,
        "chat_answer": 31.75,
        "flow_overhead": 15.75,
    }
    assert _flow_output_counts(result) == {
        "stages_total": 2,
        "stages_successful": 1,
        "stages_skipped": 0,
        "stages_failed": 1,
        "answer_files": 2,
    }


def test_apply_flow_benchmark_overrides_uses_unique_collections() -> None:
    """Clone one flow spec with unique collection names for the run."""
    spec = FlowSpec(
        name="bench_flow",
        defaults=FlowDefaults(email="original@example.com"),
        stages=[
            FlowStageSpec(
                id="retrieve_seed",
                pipeline="retrieve",
                overrides={
                    "vdb": {"collection_name": "industry_rems_high"},
                },
            ),
            FlowStageSpec(
                id="chat_answer",
                pipeline="chat",
                overrides={
                    "collections": ["industry_rems_high"],
                    "vdb": {"collection_name": "industry_rems_high"},
                },
            ),
        ],
    )

    updated = _apply_flow_benchmark_overrides(
        spec,
        email="bench@example.com",
        case_name="flow_rems_large_merged",
        iteration=2,
    )

    assert updated.defaults.email == "bench@example.com"
    retrieve_vdb = as_json_dict(updated.stages[0].overrides.get("vdb"))
    assert retrieve_vdb is not None
    retrieve_collection = retrieve_vdb.get("collection_name")
    assert isinstance(retrieve_collection, str)
    assert retrieve_collection.endswith("_flow_rems_large_merged_r2")

    chat_collections = updated.stages[1].overrides.get("collections")
    assert isinstance(chat_collections, list)
    assert chat_collections == [retrieve_collection]


def test_default_cases_include_thematic_rems_and_quantum_cases() -> None:
    """Build default perf cases and include thematic REM and quantum runs."""
    cases = _default_cases(
        "bench@example.com",
        collection_name="perf_retrieve",
        qdrant_location=".qdrant/perf-suite",
        chat_model_name="llama3.2:1b",
        chat_max_new_tokens=192,
    )

    case_names = {case.name for case in cases}
    assert "retrieve_rems_thematic" in case_names
    assert "chat_rems_thematic" in case_names
    assert "retrieve_quantum_thematic" in case_names
    assert "chat_quantum_thematic" in case_names

    rems_case = next(
        case for case in cases if case.name == "retrieve_rems_thematic"
    )
    quantum_case = next(
        case for case in cases if case.name == "retrieve_quantum_thematic"
    )
    assert "rare earth export controls" in " ".join(rems_case.args)
    assert "quantum defense contracts" in " ".join(quantum_case.args)


def test_default_cases_include_flow_benchmark_comparisons() -> None:
    """Build default perf cases and include flow benchmark candidates."""
    cases = _default_cases(
        "bench@example.com",
        collection_name="perf_retrieve",
        qdrant_location=".qdrant/perf-suite",
        chat_model_name="llama3.2:1b",
        chat_max_new_tokens=192,
    )

    flow_cases = {case.name: case for case in cases if case.pipeline == "flow"}
    assert "flow_rems_conflict_monopoly_large" in flow_cases
    assert "flow_rems_high_qwen" in flow_cases
    assert "flow_rems_large_merged" in flow_cases
    assert "flow_quantum_conflict_monopoly_large" in flow_cases
    assert "flow_quantum_high_qwen_ministral" in flow_cases
    assert "flow_quantum_large_merged" in flow_cases

    rems_conflict_case = flow_cases["flow_rems_conflict_monopoly_large"]
    quantum_merged_case = flow_cases["flow_quantum_large_merged"]
    assert rems_conflict_case.flow_spec is not None
    assert quantum_merged_case.flow_spec is not None
    assert str(rems_conflict_case.flow_spec).endswith(
        "jobs/conflict_monopoly_flows/01_rems_conflict_monopoly_large.yaml"
    )
    assert str(quantum_merged_case.flow_spec).endswith(
        "jobs/merged_basket_high_models/11_quantum_large.yaml"
    )
