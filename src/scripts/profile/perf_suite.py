# src/scripts/profile/perf_suite.py
"""Run and compare chat/retrieve performance suites."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict

# Add project src/ root so "scripts.*" and "sec_nlp.*" imports resolve
# without shadowing stdlib modules like "profile".
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils import setup_import_path

setup_import_path()

from sec_nlp.app.flows.models import (  # noqa: E402
    FlowDefaults,  # noqa: E402
    FlowRunResult,  # noqa: E402
    FlowSpec,  # noqa: E402
)
from sec_nlp.app.flows.runner import FlowRunner  # noqa: E402
from sec_nlp.app.flows.spec import load_flow_spec  # noqa: E402
from sec_nlp.core.infra.logger import logger, setup_logging  # noqa: E402
from sec_nlp.core.types import as_json_dict  # noqa: E402
from sec_nlp.pipelines.observability.run_registry import (  # noqa: E402
    RunRegistry,
)
from sec_nlp.types import (  # noqa: E402
    JsonDict,  # noqa: E402
    JsonValue,  # noqa: E402
)


@dataclass(frozen=True)
class PerfCase:
    """Single benchmark case definition."""

    name: str
    pipeline: str
    args: list[str]
    tags: list[str]
    flow_spec: Path | None = None


@dataclass(frozen=True)
class PerfIteration:
    """Single command execution result."""

    case: str
    pipeline: str
    iteration: int
    run_id: str
    success: bool
    return_code: int
    elapsed_seconds: float
    started_at: str
    stage_timings: dict[str, float]
    output_counts: dict[str, int]
    stderr_tail: str | None


def _percentile(values: list[float], pct: float) -> float:
    """Compute an interpolated percentile for a numeric series."""
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    if pct <= 0:
        return ordered[0]
    if pct >= 100:
        return ordered[-1]
    rank = (len(ordered) - 1) * (pct / 100.0)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * weight


def _safe_stage_timings(metadata: dict[str, JsonValue]) -> dict[str, float]:
    """Safely read stage timings."""
    timings: dict[str, float] = {}
    raw = metadata.get("stage_timings")
    if not isinstance(raw, dict):
        return timings
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if isinstance(value, (int, float)):
            timings[key] = float(value)
    return timings


def _safe_output_counts(
    pipeline: str, metadata: dict[str, JsonValue]
) -> dict[str, int]:
    """Safely read output counts."""
    counts: dict[str, int] = {}
    if pipeline == "chat":
        hits = metadata.get("hits_retrieved")
        citations = metadata.get("citations_returned")
        if isinstance(hits, int):
            counts["hits_retrieved"] = hits
        if isinstance(citations, int):
            counts["citations_returned"] = citations
        return counts

    if pipeline == "retrieve":
        total_ranked = 0
        for key, value in metadata.items():
            if key == "stage_timings":
                continue
            if not isinstance(value, Mapping):
                continue
            for field, field_value in value.items():
                if field == "ranked_hits" and isinstance(field_value, int):
                    total_ranked += field_value
                    break
        counts["ranked_hits"] = total_ranked
        return counts

    if pipeline == "flow":
        for key in (
            "stages_total",
            "stages_successful",
            "stages_skipped",
            "stages_failed",
            "answer_files",
        ):
            value = metadata.get(key)
            if isinstance(value, int):
                counts[key] = value
        return counts

    return counts


def _flow_stage_timings(result: FlowRunResult) -> dict[str, float]:
    """Build per-stage duration metrics from one flow result."""
    stage_timings: dict[str, float] = {}
    for stage_result in result.stage_results:
        if stage_result.skipped:
            continue
        stage_timings[stage_result.stage_id] = round(
            stage_result.duration_seconds, 6
        )
    return stage_timings


def _flow_output_counts(result: FlowRunResult) -> dict[str, int]:
    """Build normalized count metrics from one flow result."""
    metadata: dict[str, JsonValue] = {
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
        "answer_files": 0,
    }
    answer_paths = result.metadata.get("answer_output_paths")
    if isinstance(answer_paths, list):
        metadata["answer_files"] = sum(
            1 for answer_path in answer_paths if isinstance(answer_path, str)
        )
    return _safe_output_counts("flow", metadata)


def _flow_error_tail(result: FlowRunResult) -> str | None:
    """Return one concise failure summary for a flow result."""
    for stage_result in result.stage_results:
        if stage_result.error:
            return f"{stage_result.stage_id}: {stage_result.error}"
    return None


def _flow_stage_timings_for_iteration(
    result: FlowRunResult,
    *,
    elapsed_seconds: float,
) -> dict[str, float]:
    """Build flow stage timings plus explicit setup and warmup overhead."""
    stage_timings = _flow_stage_timings(result)
    measured_seconds = sum(stage_timings.values())
    overhead_seconds = round(
        max(0.0, elapsed_seconds - measured_seconds),
        6,
    )
    if overhead_seconds > 0.0:
        stage_timings["flow_overhead"] = overhead_seconds
    return stage_timings


def _case_slug(value: str) -> str:
    """Build a filesystem- and collection-safe case slug."""
    slug_parts = [
        character.lower() if character.isalnum() else "_" for character in value
    ]
    slug = "".join(slug_parts).strip("_")
    return slug or "perf_case"


def _benchmark_collection_name(
    original_name: str,
    *,
    case_name: str,
    iteration: int,
) -> str:
    """Return one unique collection name for a flow benchmark case."""
    return f"{original_name}_{_case_slug(case_name)}_r{iteration}"


def _collection_overrides_for_flow_case(
    spec: FlowSpec,
    *,
    case_name: str,
    iteration: int,
) -> dict[str, str]:
    """Build per-flow collection overrides to avoid warmed-index bias."""
    overrides: dict[str, str] = {}
    for stage in spec.stages:
        stage_overrides = stage.overrides
        vdb_raw = stage_overrides.get("vdb")
        vdb = as_json_dict(vdb_raw)
        if vdb is not None:
            collection_name = vdb.get("collection_name")
            if (
                isinstance(collection_name, str)
                and collection_name not in overrides
            ):
                overrides[collection_name] = _benchmark_collection_name(
                    collection_name,
                    case_name=case_name,
                    iteration=iteration,
                )
        collections_raw = stage_overrides.get("collections")
        if not isinstance(collections_raw, list):
            continue
        for collection_name in collections_raw:
            if (
                isinstance(collection_name, str)
                and collection_name not in overrides
            ):
                overrides[collection_name] = _benchmark_collection_name(
                    collection_name,
                    case_name=case_name,
                    iteration=iteration,
                )
    return overrides


def _apply_flow_benchmark_overrides(
    spec: FlowSpec,
    *,
    email: str,
    case_name: str,
    iteration: int,
) -> FlowSpec:
    """Clone a flow spec with benchmark-safe email and collection overrides."""
    collection_overrides = _collection_overrides_for_flow_case(
        spec,
        case_name=case_name,
        iteration=iteration,
    )
    stage_updates = []
    for stage in spec.stages:
        stage_overrides = dict(stage.overrides)
        vdb_raw = stage_overrides.get("vdb")
        vdb = as_json_dict(vdb_raw)
        if vdb is not None:
            collection_name = vdb.get("collection_name")
            if isinstance(collection_name, str):
                vdb["collection_name"] = collection_overrides.get(
                    collection_name,
                    collection_name,
                )
            stage_overrides["vdb"] = vdb
        collections_raw = stage_overrides.get("collections")
        if isinstance(collections_raw, list):
            stage_overrides["collections"] = [
                collection_overrides.get(collection_name, collection_name)
                if isinstance(collection_name, str)
                else collection_name
                for collection_name in collections_raw
            ]
        stage_updates.append(
            stage.model_copy(update={"overrides": stage_overrides})
        )
    return spec.model_copy(
        update={
            "defaults": FlowDefaults(email=email),
            "stages": stage_updates,
        }
    )


def _default_cases(
    email: str,
    *,
    collection_name: str,
    qdrant_location: str,
    chat_model_name: str | None,
    chat_max_new_tokens: int | None,
) -> list[PerfCase]:
    """Return default cases."""
    forms = "10-K,10-Q,8-K,6-K"
    start_date = "2023-01-01"
    tech_symbols = ["NVDA", "AMD", "AVGO", "QCOM", "INTC"]
    mining_symbols = ["MP", "LAC", "UUUU", "AREC", "USAR"]
    rems_symbols = ["MP", "LAC", "UUUU", "AREC", "USAR"]
    quantum_symbols = ["IONQ", "RGTI", "QBTS", "QUBT", "IBM"]
    flow_cases = [
        (
            "flow_rems_conflict_monopoly_large",
            Path(
                "jobs/conflict_monopoly_flows/01_rems_conflict_monopoly_large.yaml"
            ),
            ["flow", "rems", "benchmark", "conflict-monopoly"],
        ),
        (
            "flow_rems_high_qwen",
            Path("jobs/model_variety_flows/03_rems_high_qwen.yaml"),
            ["flow", "rems", "benchmark", "baseline", "model-variety"],
        ),
        (
            "flow_rems_large_merged",
            Path("jobs/merged_basket_high_models/05_rems_large.yaml"),
            ["flow", "rems", "benchmark", "baseline", "merged"],
        ),
        (
            "flow_quantum_conflict_monopoly_large",
            Path(
                "jobs/conflict_monopoly_flows/02_quantum_conflict_monopoly_large.yaml"
            ),
            ["flow", "quantum", "benchmark", "conflict-monopoly"],
        ),
        (
            "flow_quantum_high_qwen_ministral",
            Path(
                "jobs/model_variety_flows/05_quantum_high_qwen_ministral.yaml"
            ),
            ["flow", "quantum", "benchmark", "baseline", "model-variety"],
        ),
        (
            "flow_quantum_large_merged",
            Path("jobs/merged_basket_high_models/11_quantum_large.yaml"),
            ["flow", "quantum", "benchmark", "baseline", "merged"],
        ),
    ]

    retrieve_queries_tech = (
        "AI accelerator demand and lead-time normalization||"
        "capex cycle and margin sensitivity||"
        "policy and export-control exposure"
    )
    retrieve_queries_mining = (
        "rare earth production expansion and throughput||"
        "NdPr pricing sensitivity and offtake visibility||"
        "permitting, geopolitics, and supply chain concentration risk"
    )
    retrieve_queries_rems_thematic = (
        "rare earth export controls||"
        "rare earth defense demand||"
        "magnet supply chain concentration||"
        "rare earth consolidation||"
        "mine to magnet integration"
    )
    retrieve_queries_quantum_thematic = (
        "quantum export controls||"
        "quantum defense contracts||"
        "sovereign compute requirements||"
        "exclusive cloud partnership||"
        "quantum commercialization concentration"
    )
    chat_question_tech = (
        "Compare demand durability, margin risk, and execution risk across "
        "the selected issuers using filing evidence."
    )
    chat_question_mining = (
        "Compare rare-earth supply chain risk, pricing power, and execution "
        "risk across the selected issuers using filing evidence."
    )
    chat_question_rems_thematic = (
        "Compare export-control exposure, supply-chain concentration, and "
        "pricing leverage across the rare-earth issuers using filing evidence."
    )
    chat_question_quantum_thematic = (
        "Compare export-control exposure, gatekeeper dynamics, and customer "
        "concentration across the quantum issuers using filing evidence."
    )
    vdb_args = [
        "--vdb.collection-name",
        collection_name,
        "--vdb.qdrant-location",
        qdrant_location,
        "--vdb.qdrant-url",
        "null",
    ]
    chat_llm_args: list[str] = []
    if chat_model_name and chat_model_name.strip():
        chat_llm_args.extend(["--llm.model-name", chat_model_name.strip()])
    if chat_max_new_tokens is not None:
        chat_llm_args.extend(["--llm.max-new-tokens", str(chat_max_new_tokens)])

    cases: list[PerfCase] = []
    for top_k in (40, 80):
        cases.append(
            PerfCase(
                name=f"retrieve_tech_topk{top_k}",
                pipeline="retrieve",
                tags=["retrieve", "tech", f"topk{top_k}"],
                args=[
                    "retrieve",
                    *tech_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    "--no-incremental",
                    *vdb_args,
                    "--no-download-missing",
                    "--index-results",
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--queries",
                    retrieve_queries_tech,
                    "--efts-candidates",
                    "220",
                    "--top-k",
                    str(top_k),
                    "--output-format",
                    "json",
                ],
            )
        )
        cases.append(
            PerfCase(
                name=f"chat_tech_topk{top_k}",
                pipeline="chat",
                tags=["chat", "tech", f"topk{top_k}"],
                args=[
                    "chat",
                    *tech_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    *vdb_args,
                    "--collections",
                    collection_name,
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--question",
                    chat_question_tech,
                    *chat_llm_args,
                    "--rerank-mode",
                    "mmr",
                    "--top-k",
                    str(top_k),
                    "--max-context-chunks",
                    "8" if top_k == 40 else "10",
                    "--output-format",
                    "json",
                ],
            )
        )
        cases.append(
            PerfCase(
                name=f"retrieve_mining_topk{top_k}",
                pipeline="retrieve",
                tags=["retrieve", "mining", f"topk{top_k}"],
                args=[
                    "retrieve",
                    *mining_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    "--no-incremental",
                    *vdb_args,
                    "--no-download-missing",
                    "--index-results",
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--queries",
                    retrieve_queries_mining,
                    "--efts-candidates",
                    "220",
                    "--top-k",
                    str(top_k),
                    "--output-format",
                    "json",
                ],
            )
        )
        cases.append(
            PerfCase(
                name=f"chat_mining_topk{top_k}",
                pipeline="chat",
                tags=["chat", "mining", f"topk{top_k}"],
                args=[
                    "chat",
                    *mining_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    *vdb_args,
                    "--collections",
                    collection_name,
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--question",
                    chat_question_mining,
                    *chat_llm_args,
                    "--rerank-mode",
                    "mmr",
                    "--top-k",
                    str(top_k),
                    "--max-context-chunks",
                    "8" if top_k == 40 else "10",
                    "--output-format",
                    "json",
                ],
            )
        )
    cases.extend(
        [
            PerfCase(
                name="retrieve_rems_thematic",
                pipeline="retrieve",
                tags=["retrieve", "rems", "thematic", "benchmark"],
                args=[
                    "retrieve",
                    *rems_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    "--no-incremental",
                    *vdb_args,
                    "--no-download-missing",
                    "--index-results",
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--queries",
                    retrieve_queries_rems_thematic,
                    "--efts-candidates",
                    "260",
                    "--top-k",
                    "60",
                    "--output-format",
                    "json",
                ],
            ),
            PerfCase(
                name="chat_rems_thematic",
                pipeline="chat",
                tags=["chat", "rems", "thematic", "benchmark"],
                args=[
                    "chat",
                    *rems_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    *vdb_args,
                    "--collections",
                    collection_name,
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--question",
                    chat_question_rems_thematic,
                    *chat_llm_args,
                    "--rerank-mode",
                    "mmr",
                    "--top-k",
                    "12",
                    "--max-context-chunks",
                    "10",
                    "--context-token-budget",
                    "10000",
                    "--output-format",
                    "json",
                ],
            ),
            PerfCase(
                name="retrieve_quantum_thematic",
                pipeline="retrieve",
                tags=["retrieve", "quantum", "thematic", "benchmark"],
                args=[
                    "retrieve",
                    *quantum_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    "--no-incremental",
                    *vdb_args,
                    "--no-download-missing",
                    "--index-results",
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--queries",
                    retrieve_queries_quantum_thematic,
                    "--efts-candidates",
                    "260",
                    "--top-k",
                    "60",
                    "--output-format",
                    "json",
                ],
            ),
            PerfCase(
                name="chat_quantum_thematic",
                pipeline="chat",
                tags=["chat", "quantum", "thematic", "benchmark"],
                args=[
                    "chat",
                    *quantum_symbols,
                    "--email",
                    email,
                    "--no-dry-run",
                    *vdb_args,
                    "--collections",
                    collection_name,
                    "--forms",
                    forms,
                    "--start-date",
                    start_date,
                    "--question",
                    chat_question_quantum_thematic,
                    *chat_llm_args,
                    "--rerank-mode",
                    "mmr",
                    "--top-k",
                    "12",
                    "--max-context-chunks",
                    "10",
                    "--context-token-budget",
                    "10000",
                    "--output-format",
                    "json",
                ],
            ),
        ]
    )
    for case_name, flow_spec, tags in flow_cases:
        cases.append(
            PerfCase(
                name=case_name,
                pipeline="flow",
                args=[
                    "flow",
                    "run",
                    "--spec",
                    str(flow_spec),
                ],
                tags=tags,
                flow_spec=flow_spec,
            )
        )
    return cases


def _build_summary(iterations: list[PerfIteration]) -> dict[str, JsonValue]:
    """Build summary."""
    grouped: dict[str, list[PerfIteration]] = {}
    for iteration in iterations:
        grouped.setdefault(iteration.case, []).append(iteration)

    summary: dict[str, JsonValue] = {}
    for case_name, case_runs in grouped.items():
        elapsed = [item.elapsed_seconds for item in case_runs]
        success_count = sum(1 for item in case_runs if item.success)
        pipeline = case_runs[0].pipeline if case_runs else ""
        slo_target_seconds: float | None = None
        if pipeline == "chat":
            slo_target_seconds = 20.0
        elif pipeline == "retrieve":
            slo_target_seconds = 25.0
        stage_totals: dict[str, float] = {}
        for run in case_runs:
            for stage_name, stage_value in run.stage_timings.items():
                stage_totals[stage_name] = (
                    stage_totals.get(stage_name, 0.0) + stage_value
                )

        stage_means = {
            stage_name: round(total / len(case_runs), 6)
            for stage_name, total in stage_totals.items()
        }
        p95_seconds = round(_percentile(elapsed, 95), 6)

        case_summary: dict[str, JsonValue] = {
            "pipeline": pipeline,
            "iterations": len(case_runs),
            "success_count": success_count,
            "mean_seconds": round(mean(elapsed), 6),
            "p95_seconds": p95_seconds,
            "max_seconds": round(max(elapsed), 6),
            "min_seconds": round(min(elapsed), 6),
            "stage_mean_seconds": stage_means,
        }
        if slo_target_seconds is not None:
            case_summary["slo_p95_seconds"] = slo_target_seconds
            case_summary["slo_pass"] = p95_seconds <= slo_target_seconds
        summary[case_name] = case_summary
    return summary


def _artifact_path(output_dir: Path) -> Path:
    """Build an artifact path with a UTC timestamp suffix."""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%z")
    return output_dir / f"perf_suite_{stamp}.json"


def _load_artifact(path: Path) -> dict[str, JsonValue]:
    """Load and normalize a perf artifact JSON payload."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid artifact payload: {path}")
    normalized: JsonDict = {}
    for key, value in payload.items():
        if isinstance(key, str):
            normalized[key] = _normalize_artifact_value(value)
    return normalized


def _normalize_artifact_value(value: object) -> JsonValue:
    """Normalize loaded artifact values to JsonValue type."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        result: dict[str, JsonValue] = {}
        for k, v in value.items():
            if isinstance(k, str):
                result[k] = _normalize_artifact_value(v)
        return result
    if isinstance(value, (list, tuple)):
        return [_normalize_artifact_value(item) for item in value]
    # Fallback for any other type
    return str(value)


def _build_json_dict(mapping: object) -> dict[str, JsonValue]:
    """Build a JsonValue dict from a Mapping, filtering for JsonValue types."""
    result: dict[str, JsonValue] = {}
    if not isinstance(mapping, Mapping):
        return result
    for key, value in mapping.items():
        if isinstance(key, str) and isinstance(
            value, (str, int, float, bool, dict, list, type(None))
        ):
            result[key] = _normalize_artifact_value(value)
    return result


def _latest_artifacts(output_dir: Path, count: int = 2) -> list[Path]:
    """Return the most recent perf suite artifacts."""
    return sorted(output_dir.glob("perf_suite_*.json"))[-count:]


class PerfSuiteConfig(BaseSettings):
    """CLI config for perf suite execution."""

    model_config = SettingsConfigDict(
        cli_prog_name="perf_suite",
        cli_exit_on_error=True,
        cli_implicit_flags=True,
        extra="ignore",
    )

    mode: str = Field(
        default="run",
        description="Mode: run or compare",
    )
    repeats: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Command repeats per case in run mode.",
    )
    output_dir: Path = Field(
        default=Path("logs/perf"),
        description="Directory for perf JSON artifacts.",
    )
    email: str = Field(
        default="you@example.com",
        description="Email passed through to sec-nlp runs.",
    )
    collection_name: str = Field(
        default="perf_retrieve",
        description="Qdrant collection used by retrieve/chat perf cases.",
    )
    qdrant_location: Path = Field(
        default=Path(".qdrant/perf-suite"),
        description="Local Qdrant location used during perf runs.",
    )
    chat_model_name: str | None = Field(
        default="llama3.2:1b",
        description="Optional chat LLM model name override for perf runs.",
    )
    chat_max_new_tokens: int | None = Field(
        default=192,
        ge=32,
        le=4096,
        description="Optional chat max-new-tokens override for perf runs.",
    )
    include_cases: list[str] = Field(
        default_factory=list,
        description="Optional case-name allowlist.",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level.",
    )
    enforce_slo: bool = Field(
        default=False,
        description=(
            "Fail run mode when any case misses its p95 SLO "
            "(chat<=20s, retrieve<=25s)."
        ),
    )

    def cli_cmd(self) -> None:
        setup_logging(level=self.log_level, format_type="simple")
        mode = self.mode.strip().lower()
        if mode == "run":
            self._run_suite()
            return
        if mode == "compare":
            self._compare_latest()
            return
        raise ValueError("mode must be 'run' or 'compare'")

    def _run_suite(self) -> None:
        """Run the selected perf matrix and write the artifact summary."""
        output_dir = self.output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        cases = _default_cases(
            self.email,
            collection_name=self.collection_name,
            qdrant_location=str(self.qdrant_location),
            chat_model_name=self.chat_model_name,
            chat_max_new_tokens=self.chat_max_new_tokens,
        )
        if self.include_cases:
            allow = {
                name.strip() for name in self.include_cases if name.strip()
            }
            cases = [case for case in cases if case.name in allow]
        if not cases:
            raise ValueError("No perf cases selected")

        registry = RunRegistry()
        iterations: list[PerfIteration] = []
        for case in cases:
            for idx in range(1, self.repeats + 1):
                if case.pipeline == "flow":
                    iterations.append(self._run_flow_case(case, iteration=idx))
                    continue

                iterations.append(
                    self._run_cli_case(
                        case=case,
                        iteration=idx,
                        registry=registry,
                    )
                )

        payload: dict[str, JsonValue] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "repeats": self.repeats,
            "cases": [asdict(iteration) for iteration in iterations],
            "summary": _build_summary(iterations),
        }
        artifact = _artifact_path(output_dir)
        artifact.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.info("Perf suite artifact written to %s", artifact)

        summary = payload.get("summary")
        if isinstance(summary, Mapping):
            failed_slo_cases: list[str] = []
            for case_name, metrics_raw in summary.items():
                if not isinstance(case_name, str):
                    continue
                if not isinstance(metrics_raw, Mapping):
                    continue
                slo_pass: object | None = None
                for key, value in metrics_raw.items():
                    if key == "slo_pass":
                        slo_pass = value
                        break
                if slo_pass is False:
                    failed_slo_cases.append(case_name)
            if failed_slo_cases:
                logger.warning(
                    "SLO misses detected for %d case(s): %s",
                    len(failed_slo_cases),
                    ", ".join(failed_slo_cases),
                )
                if self.enforce_slo:
                    raise ValueError(
                        "Perf SLO check failed for cases: "
                        + ", ".join(failed_slo_cases)
                    )

    def _subprocess_env(self) -> dict[str, str]:
        """Build subprocess environment overrides for stable perf runs."""
        env = dict(os.environ)
        env["SEC_NLP_VDB_COLLECTION_NAME"] = self.collection_name
        env["SEC_NLP_VDB_QDRANT_LOCATION"] = str(self.qdrant_location)
        # Force local embedded Qdrant for stable local perf runs.
        for key in (
            "SEC_NLP_VDB_QDRANT_URL",
            "SEC_NLP_VDB_QDRANT_HOST",
            "SEC_NLP_VDB_QDRANT_PORT",
            "SEC_NLP_VDB_QDRANT_GRPC_PORT",
            "SEC_NLP_VDB_QDRANT_API_KEY",
        ):
            env.pop(key, None)
        return env

    def _run_cli_case(
        self,
        *,
        case: PerfCase,
        iteration: int,
        registry: RunRegistry,
    ) -> PerfIteration:
        """Run one retrieve/chat case through the CLI entrypoint."""
        run_id = str(uuid4())
        started = datetime.now(UTC).isoformat()
        cmd = ["uv", "run", "sec-nlp", *case.args, "--run-id", run_id]
        logger.info(
            "Running perf case %s (%d/%d)",
            case.name,
            iteration,
            self.repeats,
        )
        start = datetime.now(UTC)
        completed = subprocess.run(
            cmd,
            cwd=str(Path.cwd()),
            env=self._subprocess_env(),
            text=True,
            capture_output=True,
            check=False,
        )
        elapsed_seconds = (datetime.now(UTC) - start).total_seconds()
        run_record = registry.get_run(run_id)
        metadata: dict[str, JsonValue] = {}
        if run_record and run_record.metadata:
            parsed = json.loads(run_record.metadata)
            if isinstance(parsed, dict):
                metadata = parsed

        stderr_tail = None
        if completed.stderr:
            stderr_lines = completed.stderr.strip().splitlines()
            if stderr_lines:
                stderr_tail = stderr_lines[-1]

        return PerfIteration(
            case=case.name,
            pipeline=case.pipeline,
            iteration=iteration,
            run_id=run_id,
            success=completed.returncode == 0,
            return_code=completed.returncode,
            elapsed_seconds=round(elapsed_seconds, 6),
            started_at=started,
            stage_timings=_safe_stage_timings(metadata),
            output_counts=_safe_output_counts(case.pipeline, metadata),
            stderr_tail=stderr_tail,
        )

    def _run_flow_case(
        self,
        case: PerfCase,
        *,
        iteration: int,
    ) -> PerfIteration:
        """Run one authored flow spec directly through ``FlowRunner``."""
        if case.flow_spec is None:
            raise ValueError(f"flow case {case.name} is missing flow_spec")

        started = datetime.now(UTC).isoformat()
        logger.info(
            "Running perf case %s (%d/%d)",
            case.name,
            iteration,
            self.repeats,
        )
        start = datetime.now(UTC)
        try:
            spec = load_flow_spec(case.flow_spec)
            spec = _apply_flow_benchmark_overrides(
                spec,
                email=self.email,
                case_name=case.name,
                iteration=iteration,
            )
            result = FlowRunner(spec=spec).run()
            elapsed_seconds = (datetime.now(UTC) - start).total_seconds()
            return PerfIteration(
                case=case.name,
                pipeline=case.pipeline,
                iteration=iteration,
                run_id=result.flow_run_id,
                success=result.success,
                return_code=0 if result.success else 1,
                elapsed_seconds=round(elapsed_seconds, 6),
                started_at=started,
                stage_timings=_flow_stage_timings_for_iteration(
                    result,
                    elapsed_seconds=elapsed_seconds,
                ),
                output_counts=_flow_output_counts(result),
                stderr_tail=_flow_error_tail(result),
            )
        except Exception as exc:
            elapsed_seconds = (datetime.now(UTC) - start).total_seconds()
            return PerfIteration(
                case=case.name,
                pipeline=case.pipeline,
                iteration=iteration,
                run_id="",
                success=False,
                return_code=1,
                elapsed_seconds=round(elapsed_seconds, 6),
                started_at=started,
                stage_timings={},
                output_counts={},
                stderr_tail=f"{type(exc).__name__}: {exc}",
            )

    def _compare_latest(self) -> None:
        """Compare p95 metrics between the two latest perf artifacts."""
        output_dir = self.output_dir.resolve()
        artifacts = _latest_artifacts(output_dir, count=2)
        if len(artifacts) < 2:
            raise ValueError(
                f"Need at least 2 artifacts in {output_dir} for compare mode"
            )

        baseline = _load_artifact(artifacts[0])
        current = _load_artifact(artifacts[1])
        baseline_summary_raw = baseline.get("summary")
        current_summary_raw = current.get("summary")
        if not isinstance(baseline_summary_raw, Mapping) or not isinstance(
            current_summary_raw, Mapping
        ):
            raise ValueError("Artifacts missing summary payload")
        baseline_summary: dict[str, JsonValue] = _build_json_dict(
            baseline_summary_raw
        )
        current_summary: dict[str, JsonValue] = _build_json_dict(
            current_summary_raw
        )

        logger.info("Comparing %s -> %s", artifacts[0].name, artifacts[1].name)
        for case_name, current_metrics_raw in current_summary.items():
            if not isinstance(current_metrics_raw, Mapping):
                continue
            baseline_metrics_raw = baseline_summary.get(case_name)
            if not isinstance(baseline_metrics_raw, Mapping):
                logger.info("Case %s: new", case_name)
                continue

            current_p95: object | None = None
            baseline_p95: object | None = None
            for key, value in current_metrics_raw.items():
                if key == "p95_seconds":
                    current_p95 = value
                    break
            for key, value in baseline_metrics_raw.items():
                if key == "p95_seconds":
                    baseline_p95 = value
                    break
            if not isinstance(current_p95, (int, float)) or not isinstance(
                baseline_p95, (int, float)
            ):
                continue

            delta = float(current_p95) - float(baseline_p95)
            delta_pct = (
                (delta / float(baseline_p95)) * 100.0
                if float(baseline_p95) > 0
                else 0.0
            )
            logger.info(
                "Case %s: p95 %.3fs -> %.3fs (Δ %.3fs, %.2f%%)",
                case_name,
                float(baseline_p95),
                float(current_p95),
                delta,
                delta_pct,
            )


def main() -> None:
    """Run the command-line entrypoint."""
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    CliApp.run(PerfSuiteConfig)


if __name__ == "__main__":
    main()
