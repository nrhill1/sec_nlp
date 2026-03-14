# tests/benchmarks/test_branch_report.py
"""Tests for branch benchmark report helpers and Markdown rendering."""

import subprocess
from pathlib import Path

from scripts.profile.branch_report import (
    BenchmarkSuite,
    RefMetadata,
    _branch_summary_payload,
    _cleanup_baseline_worktree,
    _comparison_summary_payload,
    _existing_suite_artifacts,
    _normalized_artifact_for_summary,
    _prepare_baseline_worktree,
    _render_markdown_report,
    _resolve_raw_suite_artifact_path,
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


def test_prepare_baseline_worktree_prunes_before_detached_add(
    monkeypatch,
) -> None:
    """Prune stale worktree metadata before adding the baseline checkout."""
    calls: list[tuple[list[str], bool, str]] = []

    def fake_run(
        args: list[str],
        *,
        cwd: str,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert text is True
        assert capture_output is True
        calls.append((args, check, cwd))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    _prepare_baseline_worktree(
        repo_root=Path("/repo"),
        baseline_ref="main",
        baseline_worktree=Path("/tmp/baseline"),
    )

    assert calls == [
        (
            ["git", "worktree", "prune", "--expire", "now"],
            False,
            "/repo",
        ),
        (
            [
                "git",
                "worktree",
                "add",
                "--quiet",
                "--detach",
                "/tmp/baseline",
                "main",
            ],
            True,
            "/repo",
        ),
    ]


def test_cleanup_baseline_worktree_removes_then_prunes(
    monkeypatch,
) -> None:
    """Remove the temporary worktree before pruning stale metadata."""
    calls: list[tuple[list[str], bool, str]] = []

    def fake_run(
        args: list[str],
        *,
        cwd: str,
        check: bool,
        text: bool,
        capture_output: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert text is True
        assert capture_output is True
        calls.append((args, check, cwd))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cleanup_baseline_worktree(
        repo_root=Path("/repo"),
        baseline_worktree=Path("/tmp/baseline"),
    )

    assert calls == [
        (
            [
                "git",
                "worktree",
                "remove",
                "--force",
                "/tmp/baseline",
            ],
            False,
            "/repo",
        ),
        (
            ["git", "worktree", "prune", "--expire", "now"],
            False,
            "/repo",
        ),
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
        label="baseline",
        ref="5dadf05",
        branch="dev/improvements-v2",
        commit="baseline456",
        workdir=Path("/tmp/baseline"),
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
    assert case_payload.get("status") == "ok"
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
    assert "`5dadf05` at `baseline456`" in markdown
    assert "[baseline_summary.json](baseline_summary.json)" in markdown
    assert (
        "| chat_rems_thematic | ok | 2/2 | 2/2 | 13.0 | 11.0 | 2.0 | 18.181818 |"
        in markdown
    )


def test_normalized_artifact_marks_empty_cases_unsuccessful() -> None:
    """Rebuild summary success counts from raw case payloads."""
    artifact = {
        "generated_at": "2026-03-14T00:00:00+00:00",
        "repeats": 1,
        "summary": {},
        "cases": [
            {
                "case": "retrieve_rems_thematic",
                "pipeline": "retrieve",
                "iteration": 1,
                "run_id": "retrieve-1",
                "success": True,
                "return_code": 0,
                "elapsed_seconds": 4.0,
                "started_at": "2026-03-14T00:00:00+00:00",
                "stage_timings": {},
                "output_counts": {"ranked_hits": 0},
                "stderr_tail": "Finished in 4s",
            },
            {
                "case": "flow_rems_conflict_monopoly_large",
                "pipeline": "flow",
                "iteration": 1,
                "run_id": "flow-1",
                "success": True,
                "return_code": 0,
                "elapsed_seconds": 12.0,
                "started_at": "2026-03-14T00:01:00+00:00",
                "stage_timings": {
                    "retrieve_seed": 0.02,
                    "chat_answer": 0.45,
                    "flow_overhead": 11.0,
                },
                "output_counts": {
                    "stages_total": 2,
                    "stages_successful": 2,
                    "stages_skipped": 0,
                    "stages_failed": 0,
                    "answer_files": 1,
                },
                "stderr_tail": (
                    "WARNING:sec_nlp:No retrieved filing chunks for 6 symbols"
                ),
            },
        ],
    }

    normalized = _normalized_artifact_for_summary(artifact)
    summary_payload = as_json_dict(normalized.get("summary"))
    assert summary_payload is not None
    retrieve_summary_raw = as_json_dict(
        summary_payload.get("retrieve_rems_thematic")
    )
    assert retrieve_summary_raw is not None
    assert retrieve_summary_raw.get("success_count") == 0
    flow_summary_raw = as_json_dict(
        summary_payload.get("flow_rems_conflict_monopoly_large")
    )
    assert flow_summary_raw is not None
    assert flow_summary_raw.get("success_count") == 0


def test_invalid_baseline_renders_na_delta() -> None:
    """Mark empty-context baselines invalid in comparisons and Markdown."""
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
        label="baseline",
        ref="5dadf05",
        branch="dev/improvements-v2",
        commit="baseline456",
        workdir=Path("/tmp/baseline"),
    )
    feature_summary = _branch_summary_payload(
        ref_meta=feature_meta,
        suites=[suite],
        suite_summaries={
            "thematic_retrieve_chat": {
                "summary": {
                    "retrieve_rems_thematic": {
                        "pipeline": "retrieve",
                        "iterations": 2,
                        "success_count": 2,
                        "mean_seconds": 12.0,
                        "p95_seconds": 13.0,
                        "stage_mean_seconds": {"candidate_search": 5.0},
                        "output_mean_counts": {"ranked_hits": 10.0},
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
                    "retrieve_rems_thematic": {
                        "pipeline": "retrieve",
                        "iterations": 2,
                        "success_count": 0,
                        "mean_seconds": 4.0,
                        "p95_seconds": 4.5,
                        "stage_mean_seconds": {},
                        "output_mean_counts": {"ranked_hits": 0.0},
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
    suites_payload = as_json_dict(comparison.get("suites"))
    assert suites_payload is not None
    suite_payload = as_json_dict(suites_payload.get("thematic_retrieve_chat"))
    assert suite_payload is not None
    cases_payload = as_json_dict(suite_payload.get("cases"))
    assert cases_payload is not None
    case_payload = as_json_dict(cases_payload.get("retrieve_rems_thematic"))
    assert case_payload is not None
    assert case_payload.get("status") == "baseline_invalid"
    assert case_payload.get("delta_p95_seconds") is None
    assert case_payload.get("baseline_p95_seconds") is None

    markdown = _render_markdown_report(
        feature_summary=feature_summary,
        baseline_summary=baseline_summary,
        comparison_summary=comparison,
        suites=[suite],
    )

    assert (
        "| retrieve_rems_thematic | baseline_invalid | 2/2 | 0/2 | 13.0 | n/a | n/a | n/a |"
        in markdown
    )


def test_resolve_raw_suite_artifact_path_falls_back_to_legacy_main(
    tmp_path: Path,
) -> None:
    """Resolve legacy `main/` artifacts for baseline renders."""
    legacy_path = tmp_path / "main" / "thematic_retrieve_chat.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text("{}", encoding="utf-8")

    resolved = _resolve_raw_suite_artifact_path(
        raw_output_dir=tmp_path,
        label="baseline",
        suite_name="thematic_retrieve_chat",
    )

    assert resolved == legacy_path


def test_existing_suite_artifacts_load_legacy_baseline_payloads(
    tmp_path: Path,
) -> None:
    """Load normalized baseline artifacts from legacy raw paths."""
    suite = BenchmarkSuite(
        name="thematic_retrieve_chat",
        include_tags=["thematic", "benchmark"],
        repeats=2,
        description="Directional thematic retrieve/chat comparisons.",
    )
    legacy_path = tmp_path / "main" / "thematic_retrieve_chat.json"
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(
        """
{
  "generated_at": "2026-03-14T00:00:00+00:00",
  "repeats": 1,
  "summary": {},
  "cases": [
    {
      "case": "retrieve_rems_thematic",
      "pipeline": "retrieve",
      "iteration": 1,
      "run_id": "retrieve-1",
      "success": true,
      "return_code": 0,
      "elapsed_seconds": 4.0,
      "started_at": "2026-03-14T00:00:00+00:00",
      "stage_timings": {},
      "output_counts": {"ranked_hits": 0},
      "stderr_tail": "Finished in 4s"
    }
  ]
}
        """.strip(),
        encoding="utf-8",
    )

    artifacts = _existing_suite_artifacts(
        raw_output_dir=tmp_path,
        label="baseline",
        suites=[suite],
    )

    suite_payload = artifacts["thematic_retrieve_chat"]
    summary_payload = as_json_dict(suite_payload.get("summary"))
    assert summary_payload is not None
    retrieve_summary = as_json_dict(
        summary_payload.get("retrieve_rems_thematic")
    )
    assert retrieve_summary is not None
    assert retrieve_summary.get("success_count") == 0
