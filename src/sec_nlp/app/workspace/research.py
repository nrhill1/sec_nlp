# src/sec_nlp/app/workspace/research.py
"""Run selected research capabilities through one cancellable application action.

Specialist imports occur only after the user selects a capability. A child
process isolates model/native work and permits cancellation without leaving a
worker thread writing outputs after the terminal reports it stopped.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from sec_nlp.app.workspace.models import JobRecord
from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.types import ConfigData, JsonDict

if TYPE_CHECKING:
    from sec_nlp.pipelines.base.config import BasePipelineSettings
    from sec_nlp.pipelines.base.pipeline import BasePipeline

CAPABILITIES = (
    "analyze",
    "ask",
    "index",
    "retrieve",
    "exb",
    "warranty",
    "financials",
    "holdings",
    "insider",
    "events",
    "recipe",
)


class ResearchResult(BaseModel):
    """Return specialist outputs without coupling them to terminal rendering.

    Output paths retain the existing specialist serializers; the compact
    summary is suitable for either terminal display or machine-readable export.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    capability: str = Field(description="Selected research action.")
    success: bool = Field(
        description="Whether the specialist completed successfully."
    )
    outputs: tuple[Path, ...] = Field(
        default=(), description="Preserved specialist result files."
    )
    summary: JsonDict = Field(
        default_factory=dict, description="Specialist summary fields."
    )
    error: str | None = Field(
        default=None, description="Failure explanation when unsuccessful."
    )


def specialist_types(
    capability: str,
) -> tuple[type[BasePipelineSettings], type[BasePipeline]]:
    """Load only the settings and implementation for the selected capability.

    Raises:
        ValueError: If the capability is unknown.
        RuntimeError: If optional research dependencies have not been installed.
    """
    try:
        match capability:
            case "financials":
                from sec_nlp.pipelines.presets.financials.config import (
                    FinancialsSettings,
                )
                from sec_nlp.pipelines.presets.financials.pipeline import (
                    FinancialsPipeline,
                )

                return FinancialsSettings, FinancialsPipeline
            case "holdings":
                from sec_nlp.pipelines.presets.holdings.config import (
                    HoldingsSettings,
                )
                from sec_nlp.pipelines.presets.holdings.pipeline import (
                    HoldingsPipeline,
                )

                return HoldingsSettings, HoldingsPipeline
            case "insider":
                from sec_nlp.pipelines.presets.insider.config import (
                    InsiderSettings,
                )
                from sec_nlp.pipelines.presets.insider.pipeline import (
                    InsiderPipeline,
                )

                return InsiderSettings, InsiderPipeline
            case "events":
                from sec_nlp.pipelines.presets.events.config import (
                    EventsSettings,
                )
                from sec_nlp.pipelines.presets.events.pipeline import (
                    EventsPipeline,
                )

                return EventsSettings, EventsPipeline
            case "warranty":
                from sec_nlp.pipelines.presets.warranty.config import (
                    WarrantyConfig,
                )
                from sec_nlp.pipelines.presets.warranty.pipeline import (
                    WarrantyPipeline,
                )

                return WarrantyConfig, WarrantyPipeline
            case "exb":
                from sec_nlp.pipelines.presets.exb.config import ExhibitConfig
                from sec_nlp.pipelines.presets.exb.pipeline import (
                    ExhibitPipeline,
                )

                return ExhibitConfig, ExhibitPipeline
            case "analyze":
                from sec_nlp.pipelines.presets.analyze.config import (
                    AnalyzeConfig,
                )
                from sec_nlp.pipelines.presets.analyze.pipeline import (
                    AnalyzePipeline,
                )

                return AnalyzeConfig, AnalyzePipeline
            case "ask":
                from sec_nlp.pipelines.presets.chat.config import ChatSettings
                from sec_nlp.pipelines.presets.chat.pipeline import ChatPipeline

                return ChatSettings, ChatPipeline
            case "index" | "retrieve":
                from sec_nlp.pipelines.presets.retrieve.config import (
                    RetrieveSettings,
                )
                from sec_nlp.pipelines.presets.retrieve.pipeline import (
                    RetrievePipeline,
                )

                return RetrieveSettings, RetrievePipeline
            case _:
                raise ValueError(f"Unknown research capability: {capability}")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"{capability} needs optional research dependencies. Install with uv sync --extra ai --extra vector. Missing: {exc.name}"
        ) from exc


def run_specialist(capability: str, settings: JsonDict) -> ResearchResult:
    """Run a selected capability with one owned SEC connection session.

    Args:
        capability: Selected specialist or explicit recipe action.
        settings: JSON settings passed to that capability.

    Returns:
        Preserved specialist outputs and its typed completion summary.
    """
    from sec_nlp.core.edgar.transport import sec_sync_session

    with sec_sync_session():
        return _run_specialist(capability, settings)


def _run_specialist(capability: str, settings: JsonDict) -> ResearchResult:
    """Execute one selected specialist and preserve its existing output contract.

    Args:
        capability: Name from the research capability catalog.
        settings: Validated-by-specialist JSON settings supplied by the user.

    Returns:
        A compact typed result pointing to the unchanged specialist artifacts.
    """
    if capability == "recipe":
        from sec_nlp.app.workspace.recipes import ResearchRecipe, run_recipe

        recipe_result = run_recipe(ResearchRecipe.model_validate(settings))
        return ResearchResult(
            capability=capability,
            success=recipe_result.success,
            outputs=tuple(Path(value) for value in recipe_result.outputs),
            summary=TypeAdapter(JsonDict).validate_json(
                recipe_result.model_dump_json()
            ),
            error="; ".join(
                step.error for step in recipe_result.stage_results if step.error
            )
            or None,
        )
    config_type, pipeline_type = specialist_types(capability)
    values = dict(settings)
    if capability == "analyze" and isinstance(values.get("preset"), str):
        from sec_nlp.pipelines.presets.analyze.profiles import (
            AnalyzePreset,
            get_preset_config,
        )

        preset = AnalyzePreset(str(values["preset"]))
        defaults = TypeAdapter(JsonDict).validate_json(
            TypeAdapter(ConfigData).dump_json(get_preset_config(preset))
        )
        values = {**defaults, **values}
    if capability == "index":
        values["index_results"] = True
    configuration = config_type.model_validate(values)
    result = pipeline_type(config=configuration).run()
    return ResearchResult(
        capability=capability,
        success=result.is_success(),
        outputs=tuple(result.outputs),
        summary=dict(result.summary_fields()),
        error=result.error,
    )


async def execute_research(
    store: WorkspaceStore, capability: str, settings: JsonDict
) -> ResearchResult:
    """Run specialist work with cancellable process ownership and persisted status.

    Args:
        store: Workspace owning the action record and request artifacts.
        capability: Selected specialist name.
        settings: Specialist configuration without terminal-specific fields.

    Returns:
        The same typed specialist result used by the command line and terminal.
    """
    if capability not in CAPABILITIES:
        raise ValueError(f"Unknown research capability: {capability}")
    job = JobRecord(kind=f"research:{capability}", status="running")
    store.save_job(job)
    folder = store.path / "research" / job.job_id
    folder.mkdir(parents=True, exist_ok=True)
    request = folder / "request.json"
    result_path = folder / "result.json"
    values = dict(settings)
    if capability != "recipe":
        contact = next(
            (
                part.strip("<>()[],;")
                for part in store.load_settings().user_agent.split()
                if "@" in part
            ),
            None,
        )
        if contact:
            values.setdefault("email", contact)
        values.setdefault("out_path", str(folder / "outputs"))
        values.setdefault("dl_path", str(store.path / "downloads"))
    request.write_text(json.dumps(values), encoding="utf-8")
    environment = dict(os.environ)
    environment["SEC_NLP_QUIET"] = "1"
    process: asyncio.subprocess.Process | None = None
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "sec_nlp.app.workspace.research",
            capability,
            str(request),
            str(result_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=environment,
        )
        stdout, stderr = await process.communicate()
        (folder / "execution.log").write_bytes(stdout + stderr)
        if result_path.exists():
            result = ResearchResult.model_validate_json(
                result_path.read_text(encoding="utf-8")
            )
        else:
            detail = stderr.decode(errors="replace").strip()[-2000:]
            result = ResearchResult(
                capability=capability,
                success=False,
                error=detail
                or f"Research process exited with status {process.returncode}",
            )
        store.save_job(
            job.model_copy(
                update={
                    "status": "complete" if result.success else "error",
                    "updated_at": datetime.now(UTC),
                    "message": result.error
                    or f"Saved {len(result.outputs)} specialist artifacts.",
                }
            )
        )
        return result
    except asyncio.CancelledError:
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5)
            except TimeoutError:
                process.kill()
                await process.wait()
        store.save_job(
            job.model_copy(
                update={
                    "status": "cancelled",
                    "updated_at": datetime.now(UTC),
                    "message": "Research cancelled; completed artifacts retained.",
                }
            )
        )
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        store.save_job(
            job.model_copy(
                update={
                    "status": "error",
                    "updated_at": datetime.now(UTC),
                    "message": str(exc),
                }
            )
        )
        raise


def _worker() -> int:
    """Execute an internally generated request without writing terminal output."""
    from pydantic import TypeAdapter

    capability, request_name, result_name = sys.argv[1:]
    values = TypeAdapter(JsonDict).validate_json(
        Path(request_name).read_text(encoding="utf-8")
    )
    try:
        result = run_specialist(capability, values)
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        result = ResearchResult(
            capability=capability, success=False, error=str(exc)
        )
    Path(result_name).write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(_worker())
