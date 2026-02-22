"""CLI commands for multi-pipeline flow execution."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import CliSubCommand, SettingsConfigDict

from sec_nlp.app.flows import FlowRunner, load_flow_spec
from sec_nlp.cli.formatting import (
    format_key_value,
    format_section_header,
    format_status,
)
from sec_nlp.core.infra.logger import logger


class FlowRun(BaseModel):
    """Run a multi-stage flow spec."""

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

        status = "success" if result.success else "error"
        logger.info(
            format_section_header(f"Flow Run: {result.flow_name}", style="box")
        )
        logger.info(format_key_value("Flow Run ID", result.flow_run_id))
        logger.info(format_key_value("Stages", str(len(result.stage_results))))
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
            if stage_result.error:
                logger.info(format_key_value("Reason", stage_result.error))


class FlowValidate(BaseModel):
    """Validate a flow spec without executing pipelines."""

    model_config = SettingsConfigDict(
        defer_build=True,
        frozen=True,
    )

    spec: Path = Field(
        description="Path to a flow spec file (YAML or JSON).",
    )

    def cli_cmd(self) -> None:
        spec = load_flow_spec(self.spec)
        logger.info(
            format_section_header(f"Flow Spec: {spec.name}", style="box")
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
    """Flow orchestration command group."""

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
