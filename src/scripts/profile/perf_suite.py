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
from typing import cast
from uuid import uuid4

from pydantic import Field
from pydantic_settings import BaseSettings, CliApp, SettingsConfigDict

# Add project src/ root so "scripts.*" and "sec_nlp.*" imports resolve
# without shadowing stdlib modules like "profile".
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.utils import setup_import_path

setup_import_path()

from sec_nlp.core.infra.logger import logger, setup_logging  # noqa: E402
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

    return counts


def _default_cases(
    email: str,
    *,
    collection_name: str,
    qdrant_location: str,
    chat_model_name: str | None,
    chat_max_new_tokens: int | None,
) -> list[PerfCase]:
    forms = "10-K,10-Q,8-K,6-K"
    start_date = "2023-01-01"
    tech_symbols = ["NVDA", "AMD", "AVGO", "QCOM", "INTC"]
    mining_symbols = ["MP", "LAC", "UUUU", "AREC", "USAR"]

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
    chat_question_tech = (
        "Compare demand durability, margin risk, and execution risk across "
        "the selected issuers using filing evidence."
    )
    chat_question_mining = (
        "Compare rare-earth supply chain risk, pricing power, and execution "
        "risk across the selected issuers using filing evidence."
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
    return cases


def _build_summary(iterations: list[PerfIteration]) -> dict[str, JsonValue]:
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
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%z")
    return output_dir / f"perf_suite_{stamp}.json"


def _load_artifact(path: Path) -> dict[str, JsonValue]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Invalid artifact payload: {path}")
    normalized: JsonDict = {}
    for key, value in payload.items():
        if isinstance(key, str):
            normalized[key] = cast(JsonValue, value)
    return normalized


def _latest_artifacts(output_dir: Path, count: int = 2) -> list[Path]:
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
        default=None,
        description="Optional chat LLM model name override for perf runs.",
    )
    chat_max_new_tokens: int | None = Field(
        default=None,
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
                run_id = str(uuid4())
                started = datetime.now(UTC).isoformat()
                cmd = ["uv", "run", "sec-nlp", *case.args, "--run-id", run_id]
                logger.info(
                    "Running perf case %s (%d/%d)",
                    case.name,
                    idx,
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

                iterations.append(
                    PerfIteration(
                        case=case.name,
                        pipeline=case.pipeline,
                        iteration=idx,
                        run_id=run_id,
                        success=completed.returncode == 0,
                        return_code=completed.returncode,
                        elapsed_seconds=round(elapsed_seconds, 6),
                        started_at=started,
                        stage_timings=_safe_stage_timings(metadata),
                        output_counts=_safe_output_counts(
                            case.pipeline,
                            metadata,
                        ),
                        stderr_tail=stderr_tail,
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
                slo_pass: JsonValue | None = None
                for key, value in metrics_raw.items():
                    if key == "slo_pass":
                        slo_pass = cast(JsonValue, value)
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

    def _compare_latest(self) -> None:
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
        baseline_summary: dict[str, JsonValue] = {
            key: cast(JsonValue, value)
            for key, value in baseline_summary_raw.items()
            if isinstance(key, str)
        }
        current_summary: dict[str, JsonValue] = {
            key: cast(JsonValue, value)
            for key, value in current_summary_raw.items()
            if isinstance(key, str)
        }

        logger.info("Comparing %s -> %s", artifacts[0].name, artifacts[1].name)
        for case_name, current_metrics_raw in current_summary.items():
            if not isinstance(current_metrics_raw, Mapping):
                continue
            baseline_metrics_raw = baseline_summary.get(case_name)
            if not isinstance(baseline_metrics_raw, Mapping):
                logger.info("Case %s: new", case_name)
                continue

            current_p95: JsonValue | None = None
            baseline_p95: JsonValue | None = None
            for key, value in current_metrics_raw.items():
                if key == "p95_seconds":
                    current_p95 = cast(JsonValue, value)
                    break
            for key, value in baseline_metrics_raw.items():
                if key == "p95_seconds":
                    baseline_p95 = cast(JsonValue, value)
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
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    CliApp.run(PerfSuiteConfig)


if __name__ == "__main__":
    main()
