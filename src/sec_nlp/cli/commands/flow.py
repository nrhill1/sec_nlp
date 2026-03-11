# src/sec_nlp/cli/commands/flow.py
"""CLI commands for multi-pipeline flow execution and spec validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import CliSubCommand, SettingsConfigDict

from sec_nlp.app.flows.runner import FlowRunner
from sec_nlp.app.flows.spec import load_flow_spec
from sec_nlp.cli.formatting import (
    build_section_header_renderable,
    format_key_value,
    format_status,
)
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import (
    create_rich_console,
    get_rich_console,
)
from sec_nlp.types import JsonValue


def _answer_output_paths(metadata: Mapping[str, JsonValue]) -> list[str]:
    """Return flow-level chat answer output paths from result metadata."""
    answer_paths = metadata.get("answer_output_paths")
    if not isinstance(answer_paths, list):
        return []
    normalized_paths: list[str] = []
    for answer_path in answer_paths:
        if isinstance(answer_path, str):
            normalized_paths.append(answer_path)
    return normalized_paths


def _emit_answer_output_paths(answer_paths: Sequence[str]) -> None:
    """Write machine-readable answer output paths to stdout."""
    stdout_console = create_rich_console(stderr=False, no_color=True)
    for answer_path in answer_paths:
        stdout_console.print(answer_path, markup=False, highlight=False)


class FlowRun(BaseModel):
    """Execute a multi-stage flow spec and display per-stage results."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    spec: Path = Field(
        description="Path to a flow spec file (YAML or JSON).",
    )

    def cli_cmd(self) -> None:
        spec = load_flow_spec(self.spec)
        runner = FlowRunner(spec=spec)
        result = runner.run()
        console = get_rich_console()

        status = "success" if result.success else "error"
        console.print(
            build_section_header_renderable(
                f"Flow Run: {result.flow_name}",
                style="box",
                centered=True,
            )
        )
        logger.info(format_key_value("Flow Run ID", result.flow_run_id))
        logger.info(format_key_value("Stages", str(len(result.stage_results))))
        duration_raw = result.metadata.get("duration_seconds")
        if isinstance(duration_raw, int | float):
            logger.info(
                format_key_value("Duration", f"{float(duration_raw):.2f}s")
            )
        logger.info(
            format_status(
                "Flow completed" if result.success else "Flow failed",
                status=status,
            )
        )
        for stage_result in result.stage_results:
            stage_status = "success" if stage_result.success else "error"
            if stage_result.skipped:
                stage_status = "warning"
            logger.info(
                format_status(
                    (
                        f"{stage_result.stage_id} ({stage_result.pipeline})"
                        f" [{stage_result.duration_seconds:.2f}s]"
                    ),
                    status=stage_status,
                )
            )
            if stage_result.pipeline == "chat":
                answer_preview = stage_result.metadata.get("answer_preview")
                if isinstance(answer_preview, str) and answer_preview:
                    logger.info(
                        format_key_value("Answer Snippet", answer_preview)
                    )
                answer_paths = stage_result.metadata.get("answer_output_paths")
                if isinstance(answer_paths, list):
                    for answer_path in answer_paths:
                        if not isinstance(answer_path, str):
                            continue
                        logger.info(
                            format_key_value("Answer File", answer_path)
                        )
            if stage_result.error:
                logger.info(format_key_value("Reason", stage_result.error))
        answer_output_paths = _answer_output_paths(result.metadata)
        if answer_output_paths:
            logger.info(
                format_key_value("Answer Files", str(len(answer_output_paths)))
            )
            for answer_path in answer_output_paths:
                logger.info(format_key_value("  →", answer_path))
            _emit_answer_output_paths(answer_output_paths)


class FlowValidate(BaseModel):
    """Parse and validate a flow spec, reporting stage graph structure."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    spec: Path = Field(
        description="Path to a flow spec file (YAML or JSON).",
    )

    def cli_cmd(self) -> None:
        spec = load_flow_spec(self.spec)
        console = get_rich_console()
        console.print(
            build_section_header_renderable(
                f"Flow Spec: {spec.name}",
                style="box",
                centered=True,
            )
        )
        logger.info(format_key_value("Stages", str(len(spec.stages))))
        logger.info(format_key_value("On Failure", spec.on_failure))
        for stage in spec.stages:
            logger.info(
                format_key_value(
                    f"Stage {stage.id}",
                    f"{stage.pipeline} (condition={stage.condition})",
                )
            )
        logger.info(format_status("Flow spec is valid", status="success"))


class Flow(BaseModel):
    """CLI command group for flow orchestration (run, validate)."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
        populate_by_name=True,
    )

    run: CliSubCommand[FlowRun] = Field(
        description="Run a multi-stage flow spec.",
    )
    validate_cmd: CliSubCommand[FlowValidate] = Field(
        alias="validate",
        serialization_alias="validate",
        description="Validate a flow spec.",
    )

    def cli_cmd(self) -> None:
        from pydantic_settings import CliApp

        CliApp.run_subcommand(self)
