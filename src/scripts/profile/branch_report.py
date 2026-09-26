# src/scripts/profile/branch_report.py
"""Generate local benchmark reports for the current branch versus a baseline ref.

This script orchestrates benchmark suites against the current checkout and a
temporary git worktree for a baseline ref, then writes stable JSON summaries
and a Markdown report for review before merge. Raw per-suite artifacts stay
local under ``logs/perf`` while the curated report set is written to
``docs/benchmarks/conflict_monopoly``.
"""

# ruff: noqa: E402

import json
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.profile.perf_suite import (
    PerfCase,
    PerfIteration,
    _apply_flow_benchmark_overrides,
    _build_artifact_payload,
    _build_summary,
    _default_cases,
    _safe_output_counts,
    _safe_stage_timings,
    _select_cases,
    _stable_summary_from_artifact,
    _write_json_payload,
)
from scripts.utils import find_project_root, setup_import_path

setup_import_path()

from sec_nlp.app.workspace.recipes import load_recipe
from sec_nlp.core.infra.logger import logger, setup_logging
from sec_nlp.core.types import as_json_dict
from sec_nlp.pipelines.observability.run_registry import RunRegistry
from sec_nlp.types import JsonValue

type ReportPayload = dict[str, JsonValue]
_LEGACY_BASELINE_LABEL = "main"
_CANONICAL_BASELINE_LABEL = "baseline"

_FLOW_RUN_SNIPPET = """
import json
import sys
from time import perf_counter

from sec_nlp.app.workspace.recipes import run_recipe
from sec_nlp.app.workspace.recipes import load_recipe

spec_path = sys.argv[1]

try:
    started = perf_counter()
    result = run_recipe(load_recipe(spec_path))
    elapsed_seconds = perf_counter() - started
    stage_timings = {}
    for stage_result in result.stage_results:
        if stage_result.skipped:
            continue
        stage_timings[stage_result.stage_id] = round(
            stage_result.duration_seconds,
            6,
        )
    overhead_seconds = round(
        max(0.0, elapsed_seconds - sum(stage_timings.values())),
        6,
    )
    if overhead_seconds > 0.0:
        stage_timings["flow_overhead"] = overhead_seconds
    answer_files = 0
    answer_paths = result.metadata.get("answer_output_paths")
    if isinstance(answer_paths, list):
        answer_files = sum(
            1 for answer_path in answer_paths if isinstance(answer_path, str)
        )
    error_tail = None
    for stage_result in result.stage_results:
        if stage_result.error:
            error_tail = f"{stage_result.stage_id}: {stage_result.error}"
            break
    payload = {
        "run_id": result.flow_run_id,
        "success": result.success,
        "return_code": 0 if result.success else 1,
        "stage_timings": stage_timings,
        "output_counts": {
            "stages_total": len(result.stage_results),
            "stages_successful": sum(
                1 for stage_result in result.stage_results if stage_result.success
            ),
            "stages_skipped": sum(
                1 for stage_result in result.stage_results if stage_result.skipped
            ),
            "stages_failed": sum(
                1
                for stage_result in result.stage_results
                if not stage_result.success and not stage_result.skipped
            ),
            "answer_files": answer_files,
        },
        "stderr_tail": error_tail,
    }
    print(json.dumps(payload, sort_keys=True))
except Exception as exc:
    payload = {
        "run_id": "",
        "success": False,
        "return_code": 1,
        "stage_timings": {},
        "output_counts": {},
        "stderr_tail": f"{type(exc).__name__}: {exc}",
    }
    print(json.dumps(payload, sort_keys=True))
    raise
"""


@dataclass(frozen=True)
class BenchmarkSuite:
    """One benchmark suite included in the branch comparison report."""

    name: str
    include_tags: list[str]
    repeats: int
    description: str


@dataclass(frozen=True)
class RefMetadata:
    """Git reference metadata used for one benchmark report side."""

    label: str
    ref: str
    branch: str
    commit: str
    workdir: Path


def _suite_definitions() -> tuple[BenchmarkSuite, ...]:
    """Return the benchmark suites included in the branch report."""
    return (
        BenchmarkSuite(
            name="thematic_retrieve_chat",
            include_tags=["thematic", "benchmark"],
            repeats=2,
            description=(
                "Directional retrieve/chat cases for REM and quantum baskets."
            ),
        ),
        BenchmarkSuite(
            name="flow_rems_candidates",
            include_tags=["flow", "rems", "benchmark"],
            repeats=1,
            description=(
                "Aligned REM flow comparisons across conflict, merged, and "
                "model-variety candidates."
            ),
        ),
        BenchmarkSuite(
            name="flow_quantum_candidates",
            include_tags=["flow", "quantum", "benchmark"],
            repeats=1,
            description=(
                "Aligned quantum flow comparisons across conflict, merged, and "
                "model-variety candidates."
            ),
        ),
    )


def _resolve_raw_suite_artifact_path(
    *,
    raw_output_dir: Path,
    label: str,
    suite_name: str,
) -> Path:
    """Resolve one raw suite artifact path with legacy baseline fallback."""
    candidates = [raw_output_dir / label / f"{suite_name}.json"]
    if label == _CANONICAL_BASELINE_LABEL:
        candidates.append(
            raw_output_dir / _LEGACY_BASELINE_LABEL / f"{suite_name}.json"
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _sanitize_token(value: str) -> str:
    """Return a filesystem-safe token for refs, suites, and collections."""
    token_parts = [
        character.lower() if character.isalnum() else "_" for character in value
    ]
    token = "".join(token_parts).strip("_")
    return token or "value"


def _suite_collection_name(
    *,
    suite_name: str,
    ref_label: str,
    repeat_index: int,
) -> str:
    """Build a stable suite-scoped collection name."""
    return (
        "branch_report_"
        f"{_sanitize_token(ref_label)}_"
        f"{_sanitize_token(suite_name)}_"
        f"r{repeat_index}"
    )


def _replace_option_value(
    args: Sequence[str],
    *,
    option_name: str,
    value: str,
) -> list[str]:
    """Return args with one option value replaced."""
    replaced = list(args)
    option_index = -1
    for index, argument in enumerate(replaced):
        if argument == option_name:
            option_index = index
            break
    if option_index < 0 or option_index + 1 >= len(replaced):
        raise ValueError(f"Missing option {option_name}")
    replaced[option_index + 1] = value
    return replaced


def _retarget_cli_case(
    case: PerfCase,
    *,
    collection_name: str,
    qdrant_location: Path,
) -> PerfCase:
    """Clone one retrieve/chat case with suite-scoped vector settings."""
    args = _replace_option_value(
        case.args,
        option_name="--vdb.collection-name",
        value=collection_name,
    )
    args = _replace_option_value(
        args,
        option_name="--vdb.qdrant-location",
        value=str(qdrant_location),
    )
    if case.pipeline == "chat":
        args = _replace_option_value(
            args,
            option_name="--collections",
            value=collection_name,
        )
    return PerfCase(
        name=case.name,
        pipeline=case.pipeline,
        args=args,
        tags=list(case.tags),
        flow_spec=case.flow_spec,
    )


def _flow_spec_snapshot_path(
    *,
    temp_dir: Path,
    suite_name: str,
    ref_label: str,
    case_name: str,
    repeat_index: int,
) -> Path:
    """Build a stable temporary JSON spec path for one flow run."""
    filename = (
        f"{_sanitize_token(ref_label)}_"
        f"{_sanitize_token(suite_name)}_"
        f"{_sanitize_token(case_name)}_"
        f"r{repeat_index}.json"
    )
    return temp_dir / filename


def _write_flow_spec_snapshot(
    case: PerfCase,
    *,
    email: str,
    suite_name: str,
    ref_label: str,
    repeat_index: int,
    temp_dir: Path,
) -> Path:
    """Write a temporary aligned flow spec for subprocess execution."""
    if case.flow_spec is None:
        raise ValueError(f"Flow case {case.name} is missing flow_spec")
    spec = load_recipe(case.flow_spec)
    aligned_spec = _apply_flow_benchmark_overrides(
        spec,
        email=email,
        case_name=f"{ref_label}_{suite_name}_{case.name}",
        iteration=repeat_index,
    )
    output_path = _flow_spec_snapshot_path(
        temp_dir=temp_dir,
        suite_name=suite_name,
        ref_label=ref_label,
        case_name=case.name,
        repeat_index=repeat_index,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            aligned_spec.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=False,
            ),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return output_path


def _subprocess_env(*, qdrant_location: Path) -> dict[str, str]:
    """Build subprocess environment overrides for benchmark subprocesses."""
    env = dict(os.environ)
    env["SEC_NLP_VDB_QDRANT_LOCATION"] = str(qdrant_location)
    for key in (
        "SEC_NLP_VDB_QDRANT_URL",
        "SEC_NLP_VDB_QDRANT_HOST",
        "SEC_NLP_VDB_QDRANT_PORT",
        "SEC_NLP_VDB_QDRANT_GRPC_PORT",
        "SEC_NLP_VDB_QDRANT_API_KEY",
    ):
        env.pop(key, None)
    return env


def _git_output(*, cwd: Path, args: Sequence[str]) -> str:
    """Return stripped stdout from one git command."""
    completed = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _ref_metadata(*, label: str, ref: str, workdir: Path) -> RefMetadata:
    """Build git metadata for one benchmark ref."""
    branch_name = _git_output(
        cwd=workdir,
        args=["rev-parse", "--abbrev-ref", "HEAD"],
    )
    commit_sha = _git_output(cwd=workdir, args=["rev-parse", "HEAD"])
    return RefMetadata(
        label=label,
        ref=ref,
        branch=branch_name,
        commit=commit_sha,
        workdir=workdir,
    )


def _prepare_baseline_worktree(
    *,
    repo_root: Path,
    baseline_ref: str,
    baseline_worktree: Path,
) -> None:
    """Prune stale git worktrees and add one detached baseline checkout."""
    subprocess.run(
        ["git", "worktree", "prune", "--expire", "now"],
        cwd=str(repo_root),
        check=False,
        text=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "worktree",
            "add",
            "--quiet",
            "--detach",
            str(baseline_worktree),
            baseline_ref,
        ],
        cwd=str(repo_root),
        check=True,
        text=True,
        capture_output=True,
    )


def _cleanup_baseline_worktree(
    *,
    repo_root: Path,
    baseline_worktree: Path,
) -> None:
    """Remove one temporary baseline worktree and prune stale metadata."""
    subprocess.run(
        [
            "git",
            "worktree",
            "remove",
            "--force",
            str(baseline_worktree),
        ],
        cwd=str(repo_root),
        check=False,
        text=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "worktree", "prune", "--expire", "now"],
        cwd=str(repo_root),
        check=False,
        text=True,
        capture_output=True,
    )


def _coerce_case_output_counts(
    case_payload: Mapping[str, JsonValue],
) -> dict[str, int]:
    """Return normalized output counts from one raw case payload."""
    raw_output_counts = case_payload.get("output_counts")
    if not isinstance(raw_output_counts, Mapping):
        return {}
    output_counts: dict[str, int] = {}
    for key, value in raw_output_counts.items():
        if isinstance(key, str) and isinstance(value, int):
            output_counts[key] = value
    return output_counts


def _coerce_case_stage_timings(
    case_payload: Mapping[str, JsonValue],
) -> dict[str, float]:
    """Return normalized stage timings from one raw case payload."""
    raw_stage_timings = case_payload.get("stage_timings")
    if not isinstance(raw_stage_timings, Mapping):
        return {}
    stage_timings: dict[str, float] = {}
    for key, value in raw_stage_timings.items():
        if isinstance(key, str) and isinstance(value, (int, float)):
            stage_timings[key] = float(value)
    return stage_timings


def _is_empty_chunk_warning(stderr_tail: str | None) -> bool:
    """Return whether stderr indicates an empty flow handoff."""
    return (
        isinstance(stderr_tail, str)
        and "No retrieved filing chunks" in stderr_tail
    )


def _has_cli_benchmark_output(
    *,
    pipeline: str,
    output_counts: Mapping[str, int],
) -> bool:
    """Return whether one retrieve/chat benchmark produced usable output."""
    if pipeline == "retrieve":
        return output_counts.get("ranked_hits", 0) > 0
    if pipeline == "chat":
        return (
            output_counts.get("hits_retrieved", 0) > 0
            or output_counts.get("citations_returned", 0) > 0
        )
    return True


def _normalize_case_success(
    *,
    pipeline: str,
    reported_success: bool,
    return_code: int,
    output_counts: Mapping[str, int],
    stderr_tail: str | None,
) -> bool:
    """Return benchmark success after filtering empty-context runs."""
    if not reported_success or return_code != 0:
        return False
    if pipeline == "flow":
        return not _is_empty_chunk_warning(stderr_tail)
    return _has_cli_benchmark_output(
        pipeline=pipeline,
        output_counts=output_counts,
    )


def _normalized_artifact_for_summary(
    artifact: ReportPayload,
) -> ReportPayload:
    """Rebuild one artifact summary from raw case records."""
    raw_cases = artifact.get("cases")
    if not isinstance(raw_cases, list):
        return artifact

    iterations: list[PerfIteration] = []
    for raw_case in raw_cases:
        case_payload = as_json_dict(raw_case)
        if case_payload is None:
            continue
        case_name = case_payload.get("case")
        pipeline = case_payload.get("pipeline")
        raw_started_at = case_payload.get("started_at")
        if not isinstance(case_name, str) or not isinstance(pipeline, str):
            continue
        output_counts = _coerce_case_output_counts(case_payload)
        raw_stderr_tail = case_payload.get("stderr_tail")
        stderr_tail = (
            raw_stderr_tail if isinstance(raw_stderr_tail, str) else None
        )
        raw_return_code = case_payload.get("return_code")
        return_code = raw_return_code if isinstance(raw_return_code, int) else 1
        raw_success = case_payload.get("success")
        reported_success = (
            raw_success if isinstance(raw_success, bool) else return_code == 0
        )
        raw_elapsed_seconds = case_payload.get("elapsed_seconds")
        elapsed_seconds = (
            float(raw_elapsed_seconds)
            if isinstance(raw_elapsed_seconds, (int, float))
            else 0.0
        )
        raw_iteration = case_payload.get("iteration")
        iteration = raw_iteration if isinstance(raw_iteration, int) else 0
        raw_run_id = case_payload.get("run_id")
        run_id = raw_run_id if isinstance(raw_run_id, str) else ""
        started_at = raw_started_at if isinstance(raw_started_at, str) else ""
        iterations.append(
            PerfIteration(
                case=case_name,
                pipeline=pipeline,
                iteration=iteration,
                run_id=run_id,
                success=_normalize_case_success(
                    pipeline=pipeline,
                    reported_success=reported_success,
                    return_code=return_code,
                    output_counts=output_counts,
                    stderr_tail=stderr_tail,
                ),
                return_code=return_code,
                elapsed_seconds=elapsed_seconds,
                started_at=started_at,
                stage_timings=_coerce_case_stage_timings(case_payload),
                output_counts=output_counts,
                stderr_tail=stderr_tail,
            )
        )

    if not iterations:
        return artifact

    normalized_artifact = dict(artifact)
    normalized_artifact["summary"] = _build_summary(iterations)
    return normalized_artifact


def _run_cli_case_in_worktree(
    case: PerfCase,
    *,
    repeat_index: int,
    workdir: Path,
    qdrant_location: Path,
    registry: RunRegistry,
) -> PerfIteration:
    """Run one retrieve/chat case in a target worktree."""
    run_id = str(uuid4())
    started = datetime.now(UTC).isoformat()
    action, *arguments = case.args
    capability = "ask" if action == "chat" else action
    cmd = [
        "uv",
        "run",
        "sec-nlp",
        "research",
        capability,
        *arguments,
        "--run-id",
        run_id,
    ]
    logger.info(
        "Running %s in %s (repeat %d)",
        case.name,
        workdir.name,
        repeat_index,
    )
    start = datetime.now(UTC)
    completed = subprocess.run(
        cmd,
        cwd=str(workdir),
        env=_subprocess_env(qdrant_location=qdrant_location),
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed_seconds = (datetime.now(UTC) - start).total_seconds()
    run_record = registry.get_run(run_id)
    metadata: dict[str, JsonValue] = {}
    if run_record is not None and run_record.metadata:
        parsed = json.loads(run_record.metadata)
        if isinstance(parsed, dict):
            metadata = parsed
    stderr_tail = None
    if completed.stderr:
        stderr_lines = completed.stderr.strip().splitlines()
        if stderr_lines:
            stderr_tail = stderr_lines[-1]
    output_counts = _safe_output_counts(case.pipeline, metadata)
    return PerfIteration(
        case=case.name,
        pipeline=case.pipeline,
        iteration=repeat_index,
        run_id=run_id,
        success=_normalize_case_success(
            pipeline=case.pipeline,
            reported_success=completed.returncode == 0,
            return_code=completed.returncode,
            output_counts=output_counts,
            stderr_tail=stderr_tail,
        ),
        return_code=completed.returncode,
        elapsed_seconds=round(elapsed_seconds, 6),
        started_at=started,
        stage_timings=_safe_stage_timings(metadata),
        output_counts=output_counts,
        stderr_tail=stderr_tail,
    )


def _run_flow_case_in_worktree(
    *,
    case_name: str,
    repeat_index: int,
    spec_path: Path,
    workdir: Path,
    qdrant_location: Path,
) -> PerfIteration:
    """Run one aligned flow spec in a target worktree."""
    started = datetime.now(UTC).isoformat()
    cmd = [
        "uv",
        "run",
        "python3",
        "-c",
        _FLOW_RUN_SNIPPET,
        str(spec_path),
    ]
    logger.info(
        "Running %s in %s (repeat %d)",
        case_name,
        workdir.name,
        repeat_index,
    )
    start = datetime.now(UTC)
    completed = subprocess.run(
        cmd,
        cwd=str(workdir),
        env=_subprocess_env(qdrant_location=qdrant_location),
        text=True,
        capture_output=True,
        check=False,
    )
    elapsed_seconds = (datetime.now(UTC) - start).total_seconds()
    stderr_tail = None
    if completed.stderr:
        stderr_lines = completed.stderr.strip().splitlines()
        if stderr_lines:
            stderr_tail = stderr_lines[-1]

    stdout_lines = completed.stdout.strip().splitlines()
    payload: dict[str, JsonValue] = {}
    if stdout_lines:
        parsed = json.loads(stdout_lines[-1])
        if isinstance(parsed, dict):
            payload = parsed
    return_code_raw = payload.get("return_code")
    output_counts = as_json_dict(payload.get("output_counts"))
    payload_stderr_tail = payload.get("stderr_tail")
    resolved_stderr_tail = (
        str(payload_stderr_tail)
        if isinstance(payload_stderr_tail, str)
        else stderr_tail
    )
    empty_chunk_run = _is_empty_chunk_warning(resolved_stderr_tail)
    resolved_return_code = (
        return_code_raw
        if isinstance(return_code_raw, int)
        else completed.returncode
    )
    if empty_chunk_run and resolved_return_code == 0:
        resolved_return_code = 3
    return PerfIteration(
        case=case_name,
        pipeline="flow",
        iteration=repeat_index,
        run_id=str(payload.get("run_id", "")),
        success=bool(payload.get("success", False)) and not empty_chunk_run,
        return_code=resolved_return_code,
        elapsed_seconds=round(elapsed_seconds, 6),
        started_at=started,
        stage_timings=_safe_stage_timings(
            {"stage_timings": payload.get("stage_timings")}
        ),
        output_counts=_safe_output_counts("flow", output_counts or {}),
        stderr_tail=resolved_stderr_tail,
    )


def _suite_cases(
    *,
    email: str,
    qdrant_location: Path,
    chat_model_name: str | None,
    chat_max_new_tokens: int | None,
    suite: BenchmarkSuite,
) -> list[PerfCase]:
    """Build the selected cases for one suite."""
    all_cases = _default_cases(
        email,
        collection_name="branch_report_seed",
        qdrant_location=str(qdrant_location),
        chat_model_name=chat_model_name,
        chat_max_new_tokens=chat_max_new_tokens,
    )
    return _select_cases(
        all_cases,
        include_cases=[],
        include_tags=suite.include_tags,
    )


def _run_suite_for_ref(
    *,
    ref_meta: RefMetadata,
    suite: BenchmarkSuite,
    email: str,
    qdrant_root: Path,
    raw_output_dir: Path,
    chat_model_name: str | None,
    chat_max_new_tokens: int | None,
) -> ReportPayload:
    """Run one suite for one ref and return its stable summary payload."""
    iterations: list[PerfIteration] = []
    registry = RunRegistry()
    suite_cases = _suite_cases(
        email=email,
        qdrant_location=qdrant_root,
        chat_model_name=chat_model_name,
        chat_max_new_tokens=chat_max_new_tokens,
        suite=suite,
    )
    raw_suite_dir = raw_output_dir / ref_meta.label
    raw_suite_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="sec-nlp-branch-report-"
    ) as tmp_dir:
        temp_root = Path(tmp_dir)
        for repeat_index in range(1, suite.repeats + 1):
            qdrant_location = (
                qdrant_root
                / ref_meta.label
                / suite.name
                / f"repeat_{repeat_index}"
            )
            collection_name = _suite_collection_name(
                suite_name=suite.name,
                ref_label=ref_meta.label,
                repeat_index=repeat_index,
            )
            for case in suite_cases:
                if case.pipeline == "flow":
                    spec_path = _write_flow_spec_snapshot(
                        case,
                        email=email,
                        suite_name=suite.name,
                        ref_label=ref_meta.label,
                        repeat_index=repeat_index,
                        temp_dir=temp_root,
                    )
                    iterations.append(
                        _run_flow_case_in_worktree(
                            case_name=case.name,
                            repeat_index=repeat_index,
                            spec_path=spec_path,
                            workdir=ref_meta.workdir,
                            qdrant_location=qdrant_location,
                        )
                    )
                    continue

                iterations.append(
                    _run_cli_case_in_worktree(
                        _retarget_cli_case(
                            case,
                            collection_name=collection_name,
                            qdrant_location=qdrant_location,
                        ),
                        repeat_index=repeat_index,
                        workdir=ref_meta.workdir,
                        qdrant_location=qdrant_location,
                        registry=registry,
                    )
                )

    raw_artifact = _build_artifact_payload(iterations, repeats=suite.repeats)
    raw_artifact_path = raw_suite_dir / f"{suite.name}.json"
    _write_json_payload(raw_artifact_path, raw_artifact)
    return _stable_summary_from_artifact(
        raw_artifact,
        suite_name=suite.name,
        summary_label=ref_meta.label,
        source_ref=ref_meta.ref,
        source_commit=ref_meta.commit,
        source_artifact=raw_artifact_path,
    )


def _branch_summary_payload(
    *,
    ref_meta: RefMetadata,
    suites: Sequence[BenchmarkSuite],
    suite_summaries: Mapping[str, ReportPayload],
) -> ReportPayload:
    """Build one stable summary payload for a benchmark ref."""
    suite_repeats = {suite.name: suite.repeats for suite in suites}
    ordered_suites = {
        suite.name: suite_summaries[suite.name]
        for suite in suites
        if suite.name in suite_summaries
    }
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "label": ref_meta.label,
        "source_ref": ref_meta.ref,
        "branch": ref_meta.branch,
        "commit": ref_meta.commit,
        "suite_repeats": suite_repeats,
        "suites": ordered_suites,
    }


def _compare_case_metrics(
    feature_case: Mapping[str, JsonValue],
    baseline_case: Mapping[str, JsonValue],
) -> ReportPayload:
    """Build one case comparison payload."""
    comparison: ReportPayload = {}
    for key in ("pipeline", "iterations", "success_count"):
        feature_value = feature_case.get(key)
        baseline_value = baseline_case.get(key)
        if feature_value is not None:
            comparison[f"feature_{key}"] = feature_value
        if baseline_value is not None:
            comparison[f"baseline_{key}"] = baseline_value

    feature_success_count = feature_case.get("success_count")
    feature_iterations = feature_case.get("iterations")
    baseline_success_count = baseline_case.get("success_count")
    baseline_iterations = baseline_case.get("iterations")
    feature_valid = (
        isinstance(feature_success_count, int)
        and isinstance(feature_iterations, int)
        and feature_iterations > 0
        and feature_success_count == feature_iterations
    )
    baseline_valid = (
        isinstance(baseline_success_count, int)
        and isinstance(baseline_iterations, int)
        and baseline_iterations > 0
        and baseline_success_count == baseline_iterations
    )
    if feature_valid and baseline_valid:
        comparison["status"] = "ok"
    elif feature_valid:
        comparison["status"] = "baseline_invalid"
    elif baseline_valid:
        comparison["status"] = "feature_invalid"
    else:
        comparison["status"] = "both_invalid"

    feature_p95 = feature_case.get("p95_seconds")
    baseline_p95 = baseline_case.get("p95_seconds")
    if feature_valid and isinstance(feature_p95, (int, float)):
        comparison["feature_p95_seconds"] = round(float(feature_p95), 6)
    if baseline_valid and isinstance(baseline_p95, (int, float)):
        comparison["baseline_p95_seconds"] = round(float(baseline_p95), 6)
    if (
        feature_valid
        and baseline_valid
        and isinstance(feature_p95, (int, float))
        and isinstance(
            baseline_p95,
            (int, float),
        )
    ):
        delta_seconds = round(float(feature_p95) - float(baseline_p95), 6)
        comparison["delta_p95_seconds"] = delta_seconds
        comparison["delta_p95_pct"] = (
            round(
                (delta_seconds / float(baseline_p95)) * 100.0,
                6,
            )
            if float(baseline_p95) > 0
            else 0.0
        )

    feature_mean = feature_case.get("mean_seconds")
    baseline_mean = baseline_case.get("mean_seconds")
    if feature_valid and isinstance(feature_mean, (int, float)):
        comparison["feature_mean_seconds"] = round(float(feature_mean), 6)
    if baseline_valid and isinstance(baseline_mean, (int, float)):
        comparison["baseline_mean_seconds"] = round(float(baseline_mean), 6)
    if (
        feature_valid
        and baseline_valid
        and isinstance(feature_mean, (int, float))
        and isinstance(
            baseline_mean,
            (int, float),
        )
    ):
        comparison["delta_mean_seconds"] = round(
            float(feature_mean) - float(baseline_mean),
            6,
        )

    stage_feature = feature_case.get("stage_mean_seconds")
    feature_stage_dict = as_json_dict(stage_feature)
    if feature_stage_dict is not None:
        comparison["feature_stage_mean_seconds"] = feature_stage_dict
    stage_baseline = baseline_case.get("stage_mean_seconds")
    baseline_stage_dict = as_json_dict(stage_baseline)
    if baseline_stage_dict is not None:
        comparison["baseline_stage_mean_seconds"] = baseline_stage_dict

    output_feature = feature_case.get("output_mean_counts")
    feature_output_dict = as_json_dict(output_feature)
    if feature_output_dict is not None:
        comparison["feature_output_mean_counts"] = feature_output_dict
    output_baseline = baseline_case.get("output_mean_counts")
    baseline_output_dict = as_json_dict(output_baseline)
    if baseline_output_dict is not None:
        comparison["baseline_output_mean_counts"] = baseline_output_dict
    return comparison


def _comparison_summary_payload(
    *,
    feature_summary: ReportPayload,
    baseline_summary: ReportPayload,
    suites: Sequence[BenchmarkSuite],
) -> ReportPayload:
    """Build one comparison payload from feature and baseline summaries."""
    feature_suites = as_json_dict(feature_summary.get("suites"))
    baseline_suites = as_json_dict(baseline_summary.get("suites"))
    if feature_suites is None or baseline_suites is None:
        raise ValueError("Branch summaries are missing suite payloads")

    suite_payloads: ReportPayload = {}
    for suite in suites:
        feature_suite = feature_suites.get(suite.name)
        baseline_suite = baseline_suites.get(suite.name)
        feature_suite_dict = as_json_dict(feature_suite)
        baseline_suite_dict = as_json_dict(baseline_suite)
        if feature_suite_dict is None or baseline_suite_dict is None:
            continue
        feature_cases = as_json_dict(feature_suite_dict.get("summary"))
        baseline_cases = as_json_dict(baseline_suite_dict.get("summary"))
        if feature_cases is None or baseline_cases is None:
            continue
        case_payloads: ReportPayload = {}
        case_names = sorted(
            {
                case_name
                for case_name in feature_cases
                if isinstance(case_name, str)
            }
            | {
                case_name
                for case_name in baseline_cases
                if isinstance(case_name, str)
            }
        )
        for case_name in case_names:
            feature_case = feature_cases.get(case_name)
            baseline_case = baseline_cases.get(case_name)
            feature_case_dict = as_json_dict(feature_case)
            baseline_case_dict = as_json_dict(baseline_case)
            if feature_case_dict is None or baseline_case_dict is None:
                continue
            case_payloads[case_name] = _compare_case_metrics(
                feature_case_dict,
                baseline_case_dict,
            )
        suite_payloads[suite.name] = {
            "description": suite.description,
            "repeats": suite.repeats,
            "cases": case_payloads,
        }

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "feature_label": feature_summary.get("label"),
        "feature_ref": feature_summary.get("source_ref"),
        "feature_branch": feature_summary.get("branch"),
        "feature_commit": feature_summary.get("commit"),
        "baseline_label": baseline_summary.get("label"),
        "baseline_ref": baseline_summary.get("source_ref"),
        "baseline_branch": baseline_summary.get("branch"),
        "baseline_commit": baseline_summary.get("commit"),
        "suites": suite_payloads,
    }


def _report_table(
    comparison_cases: Mapping[str, JsonValue],
) -> str:
    """Render one Markdown table for suite case deltas."""
    lines = [
        "| Case | Status | Feature ok/iters | Baseline ok/iters | Feature p95 (s) | Baseline p95 (s) | Delta (s) | Delta (%) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case_name in sorted(
        case_name
        for case_name in comparison_cases
        if isinstance(case_name, str)
    ):
        comparison_raw = comparison_cases.get(case_name)
        comparison = as_json_dict(comparison_raw)
        if comparison is None:
            continue
        feature_success = comparison.get("feature_success_count")
        feature_iterations = comparison.get("feature_iterations")
        baseline_success = comparison.get("baseline_success_count")
        baseline_iterations = comparison.get("baseline_iterations")
        feature_p95 = comparison.get("feature_p95_seconds")
        baseline_p95 = comparison.get("baseline_p95_seconds")
        delta_seconds = comparison.get("delta_p95_seconds")
        delta_pct = comparison.get("delta_p95_pct")
        status = comparison.get("status")
        lines.append(
            "| "
            f"{case_name} | "
            f"{status if isinstance(status, str) else 'n/a'} | "
            f"{feature_success if isinstance(feature_success, int) else 'n/a'}/"
            f"{feature_iterations if isinstance(feature_iterations, int) else 'n/a'} | "
            f"{baseline_success if isinstance(baseline_success, int) else 'n/a'}/"
            f"{baseline_iterations if isinstance(baseline_iterations, int) else 'n/a'} | "
            f"{feature_p95 if isinstance(feature_p95, (int, float)) else 'n/a'} | "
            f"{baseline_p95 if isinstance(baseline_p95, (int, float)) else 'n/a'} | "
            f"{delta_seconds if isinstance(delta_seconds, (int, float)) else 'n/a'} | "
            f"{delta_pct if isinstance(delta_pct, (int, float)) else 'n/a'} |"
        )
    return "\n".join(lines)


def _render_markdown_report(
    *,
    feature_summary: ReportPayload,
    baseline_summary: ReportPayload,
    comparison_summary: ReportPayload,
    suites: Sequence[BenchmarkSuite],
) -> str:
    """Render the committed Markdown benchmark comparison report."""
    feature_branch = feature_summary.get("branch")
    feature_commit = feature_summary.get("commit")
    baseline_ref = baseline_summary.get("source_ref")
    baseline_commit = baseline_summary.get("commit")
    generated_at = comparison_summary.get("generated_at")

    lines = [
        "# Conflict/Monopoly Benchmark Report",
        "",
        f"- Generated at: `{generated_at}`",
        f"- Feature branch: `{feature_branch}` at `{feature_commit}`",
        f"- Baseline ref: `{baseline_ref}` at `{baseline_commit}`",
        "- Stable JSON summaries: "
        "[feature_summary.json](feature_summary.json), "
        "[baseline_summary.json](baseline_summary.json), "
        "[comparison_summary.json](comparison_summary.json)",
        "",
        "## Environment assumptions",
        "",
        "- Local Ollama is available for chat/flow cases.",
        "- Local Qdrant is available at `http://localhost:6333` for flow suites.",
        "- Raw run artifacts are local-only under `logs/perf/branch_report/` and "
        "are not committed.",
        "",
        "## Suite configuration",
        "",
    ]
    for suite in suites:
        lines.append(
            f"- `{suite.name}`: repeats={suite.repeats}; {suite.description}"
        )

    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- Thematic retrieve/chat suites are directional latency and retrieval "
            "checks rather than full flow comparisons.",
            "- Flow baseline shadow specs align date windows, baskets, timeout policy, "
            "and dedicated collection names with the conflict/monopoly flows.",
            "- Cases without fully successful iterations are marked invalid and "
            "render timing deltas as `n/a` instead of treating empty-context "
            "runs as real wins.",
            "- `flow_overhead` captures setup and warmup work outside stage "
            "`invoke()` timings and is preserved in the JSON summaries.",
        ]
    )

    comparison_suites = as_json_dict(comparison_summary.get("suites"))
    if comparison_suites is not None:
        for suite in suites:
            suite_payload = comparison_suites.get(suite.name)
            suite_payload_dict = as_json_dict(suite_payload)
            if suite_payload_dict is None:
                continue
            suite_cases = as_json_dict(suite_payload_dict.get("cases"))
            if suite_cases is None:
                continue
            lines.extend(
                [
                    "",
                    f"## {suite.name}",
                    "",
                    suite.description,
                    "",
                    _report_table(suite_cases),
                ]
            )
    return "\n".join(lines) + "\n"


def _write_report_outputs(
    *,
    output_dir: Path,
    feature_summary: ReportPayload,
    baseline_summary: ReportPayload,
    comparison_summary: ReportPayload,
    markdown_report: str,
    write_markdown: bool,
) -> None:
    """Write stable JSON summaries and, optionally, the Markdown report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    _write_json_payload(output_dir / "feature_summary.json", feature_summary)
    _write_json_payload(
        output_dir / "baseline_summary.json",
        baseline_summary,
    )
    _write_json_payload(output_dir / "main_summary.json", baseline_summary)
    _write_json_payload(
        output_dir / "comparison_summary.json",
        comparison_summary,
    )
    if write_markdown:
        (output_dir / "report.md").write_text(
            markdown_report,
            encoding="utf-8",
        )


def _existing_suite_artifacts(
    *,
    raw_output_dir: Path,
    label: str,
    suites: Sequence[BenchmarkSuite],
) -> dict[str, ReportPayload]:
    """Load existing raw suite artifacts for one ref label."""
    artifacts: dict[str, ReportPayload] = {}
    for suite in suites:
        suite_path = _resolve_raw_suite_artifact_path(
            raw_output_dir=raw_output_dir,
            label=label,
            suite_name=suite.name,
        )
        payload = json.loads(suite_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            artifacts[suite.name] = _normalized_artifact_for_summary(payload)
    return artifacts


class BranchReportConfig(BaseSettings):
    """CLI settings for branch benchmark comparison reporting."""

    model_config = SettingsConfigDict(
        cli_prog_name="branch_report",
        cli_exit_on_error=True,
        cli_implicit_flags=True,
        extra="ignore",
    )

    mode: str = Field(
        default="run",
        description="Mode: run or render.",
    )
    baseline_ref: str = Field(
        default="main",
        description="Baseline git ref benchmarked in a temporary worktree.",
    )
    email: str = Field(
        default="you@example.com",
        description="Email passed through to SEC benchmark runs.",
    )
    output_dir: Path = Field(
        default=Path("docs/benchmarks/conflict_monopoly"),
        description="Committed benchmark report output directory.",
    )
    raw_output_dir: Path = Field(
        default=Path("logs/perf/branch_report"),
        description="Local-only raw artifact directory.",
    )
    qdrant_root: Path = Field(
        default=Path(".qdrant/branch_report"),
        description="Root for suite-specific Qdrant local data.",
    )
    chat_model_name: str | None = Field(
        default="llama3.2:1b",
        description="Optional chat model override for thematic cases.",
    )
    chat_max_new_tokens: int | None = Field(
        default=192,
        ge=32,
        le=4096,
        description="Optional max-new-tokens override for thematic chat cases.",
    )
    write_markdown: bool = Field(
        default=True,
        description="Write Markdown alongside stable JSON outputs.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level.",
    )

    def cli_cmd(self) -> None:
        """Run the selected report workflow."""
        setup_logging(level=self.log_level, format_type="simple")
        mode = self.mode.strip().lower()
        if mode == "run":
            self._run()
            return
        if mode == "render":
            self._render_only()
            return
        raise ValueError("mode must be 'run' or 'render'")

    def _run(self) -> None:
        """Run the full feature-vs-baseline benchmark matrix and write outputs."""
        repo_root = find_project_root()
        feature_meta = _ref_metadata(
            label="feature",
            ref="HEAD",
            workdir=repo_root,
        )
        suites = _suite_definitions()
        baseline_ref = self.baseline_ref.strip()
        if not baseline_ref:
            raise ValueError("baseline_ref cannot be empty")

        with tempfile.TemporaryDirectory(
            prefix="sec-nlp-baseline-worktree-"
        ) as tmp_dir:
            baseline_worktree = Path(tmp_dir) / "baseline"
            _prepare_baseline_worktree(
                repo_root=repo_root,
                baseline_ref=baseline_ref,
                baseline_worktree=baseline_worktree,
            )
            baseline_meta: RefMetadata | None = None
            try:
                baseline_meta = RefMetadata(
                    label=_CANONICAL_BASELINE_LABEL,
                    ref=baseline_ref,
                    branch=baseline_ref,
                    commit=_git_output(
                        cwd=baseline_worktree,
                        args=["rev-parse", "HEAD"],
                    ),
                    workdir=baseline_worktree,
                )
                feature_summaries = {
                    suite.name: _run_suite_for_ref(
                        ref_meta=feature_meta,
                        suite=suite,
                        email=self.email,
                        qdrant_root=self.qdrant_root.resolve(),
                        raw_output_dir=self.raw_output_dir.resolve(),
                        chat_model_name=self.chat_model_name,
                        chat_max_new_tokens=self.chat_max_new_tokens,
                    )
                    for suite in suites
                }
                baseline_summaries = {
                    suite.name: _run_suite_for_ref(
                        ref_meta=baseline_meta,
                        suite=suite,
                        email=self.email,
                        qdrant_root=self.qdrant_root.resolve(),
                        raw_output_dir=self.raw_output_dir.resolve(),
                        chat_model_name=self.chat_model_name,
                        chat_max_new_tokens=self.chat_max_new_tokens,
                    )
                    for suite in suites
                }
            finally:
                _cleanup_baseline_worktree(
                    repo_root=repo_root,
                    baseline_worktree=baseline_worktree,
                )
        if baseline_meta is None:
            raise ValueError("Failed to build baseline ref metadata")

        self._write_outputs(
            suites=suites,
            feature_meta=feature_meta,
            baseline_meta=baseline_meta,
            feature_summaries=feature_summaries,
            baseline_summaries=baseline_summaries,
        )

    def _render_only(self) -> None:
        """Render stable outputs from existing raw suite artifacts."""
        repo_root = find_project_root()
        suites = _suite_definitions()
        feature_meta = _ref_metadata(
            label="feature",
            ref="HEAD",
            workdir=repo_root,
        )
        baseline_ref = self.baseline_ref.strip()
        if not baseline_ref:
            raise ValueError("baseline_ref cannot be empty")
        baseline_commit = _git_output(
            cwd=repo_root,
            args=["rev-parse", baseline_ref],
        )
        baseline_meta = RefMetadata(
            label=_CANONICAL_BASELINE_LABEL,
            ref=baseline_ref,
            branch=baseline_ref,
            commit=baseline_commit,
            workdir=repo_root,
        )
        feature_raw = _existing_suite_artifacts(
            raw_output_dir=self.raw_output_dir.resolve(),
            label="feature",
            suites=suites,
        )
        baseline_raw = _existing_suite_artifacts(
            raw_output_dir=self.raw_output_dir.resolve(),
            label=_CANONICAL_BASELINE_LABEL,
            suites=suites,
        )
        feature_summaries = {
            suite.name: _stable_summary_from_artifact(
                feature_raw[suite.name],
                suite_name=suite.name,
                summary_label="feature",
                source_ref="HEAD",
                source_commit=feature_meta.commit,
                source_artifact=(
                    self.raw_output_dir.resolve()
                    / "feature"
                    / f"{suite.name}.json"
                ),
            )
            for suite in suites
        }
        baseline_summaries = {
            suite.name: _stable_summary_from_artifact(
                baseline_raw[suite.name],
                suite_name=suite.name,
                summary_label=_CANONICAL_BASELINE_LABEL,
                source_ref=baseline_ref,
                source_commit=baseline_meta.commit,
                source_artifact=_resolve_raw_suite_artifact_path(
                    raw_output_dir=self.raw_output_dir.resolve(),
                    label=_CANONICAL_BASELINE_LABEL,
                    suite_name=suite.name,
                ),
            )
            for suite in suites
        }
        self._write_outputs(
            suites=suites,
            feature_meta=feature_meta,
            baseline_meta=baseline_meta,
            feature_summaries=feature_summaries,
            baseline_summaries=baseline_summaries,
        )

    def _write_outputs(
        self,
        *,
        suites: Sequence[BenchmarkSuite],
        feature_meta: RefMetadata,
        baseline_meta: RefMetadata,
        feature_summaries: Mapping[str, ReportPayload],
        baseline_summaries: Mapping[str, ReportPayload],
    ) -> None:
        """Write stable JSON summaries and the optional Markdown report."""
        feature_summary = _branch_summary_payload(
            ref_meta=feature_meta,
            suites=suites,
            suite_summaries=feature_summaries,
        )
        baseline_summary = _branch_summary_payload(
            ref_meta=baseline_meta,
            suites=suites,
            suite_summaries=baseline_summaries,
        )
        comparison_summary = _comparison_summary_payload(
            feature_summary=feature_summary,
            baseline_summary=baseline_summary,
            suites=suites,
        )
        markdown_report = _render_markdown_report(
            feature_summary=feature_summary,
            baseline_summary=baseline_summary,
            comparison_summary=comparison_summary,
            suites=suites,
        )
        _write_report_outputs(
            output_dir=self.output_dir.resolve(),
            feature_summary=feature_summary,
            baseline_summary=baseline_summary,
            comparison_summary=comparison_summary,
            markdown_report=markdown_report,
            write_markdown=self.write_markdown,
        )
        logger.info(
            "Branch benchmark report written to %s",
            self.output_dir.resolve(),
        )


def main() -> None:
    """Run the command-line entrypoint."""
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    CliApp.run(BranchReportConfig)


if __name__ == "__main__":
    main()
