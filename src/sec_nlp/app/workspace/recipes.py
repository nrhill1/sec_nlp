# src/sec_nlp/app/workspace/recipes.py
"""Validate and execute explicit saved research recipes.

These models define the contract between user-authored flow specs, selected specialist settings and execution-time result reporting. They intentionally
centralize validation at ingress so stage execution can remain lightweight.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from time import perf_counter
from typing import Literal
from uuid import uuid4

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)

from sec_nlp.types import JsonDict, JsonValue

logger = logging.getLogger(__name__)

type PipelineName = Literal[
    "retrieve",
    "chat",
    "exhibit",
    "analyze",
    "warranty",
]
type FlowArtifactName = Literal["retrieve_seed", "contract_evidence"]


class RecipeDefaults(BaseModel):
    """Flow-level defaults merged into every stage's settings at compile time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: str = Field(
        description="SEC contact email used by downstream pipelines."
    )


class RecipeStep(BaseModel):
    """One stage entry in a flow spec, identifying a pipeline and its overrides."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(description="Stable stage identifier in this flow.")
    pipeline: PipelineName = Field(
        description="Pipeline executed by this stage.",
    )
    overrides: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Stage-level config overrides merged over defaults.",
    )
    condition: Literal["always", "previous_success", "previous_has_outputs"] = (
        Field(
            default="always",
            description="Execution condition relative to previous stage result.",
        )
    )
    inputs: list[EvidenceInput] = Field(
        default_factory=list,
        description=(
            "Typed artifact inputs sourced from prior stages and injected into "
            "this stage at runtime."
        ),
    )

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        """Validate flow and stage identifiers against allowed patterns."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("stage id cannot be empty")
        return cleaned


class EvidenceInput(BaseModel):
    """Declarative artifact binding wiring one stage's output to another's input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_stage: str = Field(
        description="Source stage ID that produced the artifact.",
    )
    artifact: FlowArtifactName = Field(
        description="Artifact family produced by the source stage.",
    )
    target_field: str | None = Field(
        default=None,
        description="Optional stage config field name for artifact injection.",
    )

    @field_validator("from_stage")
    @classmethod
    def _validate_from_stage(cls, value: str) -> str:
        """Reject empty ``from_stage`` references in input bindings."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("inputs.from_stage cannot be empty")
        return cleaned


class ResearchRecipe(BaseModel):
    """Top-level flow specification parsed from user-authored YAML or JSON.

    The model validates stage ordering, unique IDs, and input-binding
    constraints at construction time so that the compile/run layers can
    operate without redundant checks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        default="retrieve_chat_flow",
        description="Human-readable name for the flow definition.",
    )
    defaults: RecipeDefaults = Field(
        description="Shared defaults inherited by stage configs.",
    )
    stages: list[RecipeStep] = Field(
        default_factory=list,
        description="Ordered stage execution plan.",
    )
    on_failure: Literal["stop", "continue"] = Field(
        default="stop",
        description="Flow behavior after a stage failure.",
    )

    @model_validator(mode="after")
    def _validate_stage_graph(self) -> ResearchRecipe:
        """Enforce unique stage IDs, valid input bindings, and pipeline compatibility."""
        if not self.stages:
            raise ValueError("flow spec requires at least one stage")

        stage_ids: set[str] = set()
        stage_pipelines: dict[str, str] = {}
        for stage in self.stages:
            if stage.id in stage_ids:
                raise ValueError(f"duplicate stage id '{stage.id}'")
            stage_ids.add(stage.id)
            stage_pipelines[stage.id] = stage.pipeline

        preceding: set[str] = set()
        for stage in self.stages:
            if stage.pipeline != "chat" and stage.inputs:
                raise ValueError(
                    f"stage '{stage.id}' ({stage.pipeline}) does not accept "
                    "input bindings yet"
                )
            if stage.pipeline == "chat" and len(stage.inputs) > 1:
                raise ValueError(
                    f"stage '{stage.id}' accepts at most one input binding"
                )
            for binding in stage.inputs:
                if (
                    binding.target_field is not None
                    and binding.target_field != "seed_context"
                ):
                    raise ValueError(
                        f"stage '{stage.id}' input binding target_field "
                        "must be 'seed_context'"
                    )
                if binding.from_stage not in preceding:
                    raise ValueError(
                        f"stage '{stage.id}' references unknown input stage "
                        f"'{binding.from_stage}'"
                    )
                upstream_pipeline = stage_pipelines.get(binding.from_stage)
                if (
                    binding.artifact == "retrieve_seed"
                    and upstream_pipeline != "retrieve"
                ):
                    raise ValueError(
                        f"stage '{stage.id}' retrieve_seed input must reference "
                        "a retrieve stage"
                    )
                if (
                    binding.artifact == "contract_evidence"
                    and upstream_pipeline != "exhibit"
                ):
                    raise ValueError(
                        f"stage '{stage.id}' contract_evidence input must "
                        "reference an exhibit stage"
                    )
            preceding.add(stage.id)
        return self


class RecipeStepResult(BaseModel):
    """Frozen result envelope for a single flow stage execution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_id: str
    pipeline: str
    success: bool
    skipped: bool = False
    error: str | None = None
    duration_seconds: float = 0.0
    run_id: str | None = None
    run_short_id: int | None = None
    outputs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class RecipeRunResult(BaseModel):
    """Aggregate result carrying per-stage outcomes and flow-level metadata."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    flow_run_id: str
    flow_name: str
    success: bool
    stage_results: list[RecipeStepResult] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


def load_recipe(spec_path: str | Path) -> ResearchRecipe:
    """Load a compact catalog reference or a migrated standalone recipe.

    Args:
        spec_path: JSON/YAML recipe file or small catalog reference file.

    Returns:
        A validated ordered recipe with profile defaults expanded.
    """
    path = Path(spec_path).expanduser().resolve()
    parsed = TypeAdapter(JsonDict).validate_python(
        yaml.safe_load(path.read_text(encoding="utf-8"))
    )
    catalog_name = parsed.get("catalog")
    selected = parsed.get("recipe")
    if isinstance(catalog_name, str) and isinstance(selected, str):
        catalog_path = (path.parent / catalog_name).resolve()
        catalog = RecipeCatalog.model_validate(
            yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
        )
        recipe = catalog.recipes.get(selected)
        if recipe is None:
            raise ValueError(
                f"Recipe {selected!r} is absent from {catalog_path}"
            )
        stages = [
            step.model_copy(
                update={
                    "overrides": _merge_settings(
                        catalog.profiles.get(step.pipeline, {}), step.overrides
                    )
                }
            )
            for step in recipe.stages
        ]
        return ResearchRecipe.model_validate(
            recipe.model_copy(update={"stages": stages}).model_dump()
        )
    return ResearchRecipe.model_validate(parsed)


class RecipeCatalog(BaseModel):
    """Share repeated specialist settings across explicitly named research recipes.

    Profiles are data defaults rather than executable templates. Expanding a
    catalog reconstructs each authored settings payload without network access.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = Field(
        default=1, description="Catalog format version."
    )
    profiles: dict[str, JsonDict] = Field(
        default_factory=dict,
        description="Shared settings per specialist capability.",
    )
    recipes: dict[str, ResearchRecipe] = Field(
        description="Authored recipes keyed by stable catalog name."
    )


def _merge_settings(base: JsonDict, updates: JsonDict) -> JsonDict:
    """Merge nested recipe settings while preserving explicit scalar replacements."""
    result = dict(base)
    for key, value in updates.items():
        previous = result.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            result[key] = _merge_settings(
                TypeAdapter(JsonDict).validate_python(previous),
                TypeAdapter(JsonDict).validate_python(value),
            )
        else:
            result[key] = value
    return result


def run_recipe(spec: ResearchRecipe) -> RecipeRunResult:
    """Execute a fixed ordered research recipe with direct typed evidence handoff.

    Args:
        spec: Validated authored recipe, including failure and input conditions.

    Returns:
        Preserved specialist outputs and explicit outcomes for every attempted step.
    """
    from sec_nlp.app.workspace.evidence import (
        FlowRetrievedChunk,
        FlowSeedBundle,
    )
    from sec_nlp.app.workspace.research import specialist_types

    run_id = uuid4().hex
    results: list[RecipeStepResult] = []
    seeds: dict[str, FlowSeedBundle] = {}
    chunks: dict[str, tuple[FlowRetrievedChunk, ...]] = {}
    outputs: list[str] = []
    started = perf_counter()
    from sec_nlp.core.infra.settings import DATA_DIR

    configured_output = spec.stages[0].overrides.get("out_path")
    output_root = (
        Path(configured_output)
        if isinstance(configured_output, str)
        else DATA_DIR / "outputs"
    )
    output_root.mkdir(parents=True, exist_ok=True)
    snapshot = output_root / f"recipe_{run_id}_settings.json"
    snapshot.write_text(spec.model_dump_json(indent=2) + "\n", encoding="utf-8")
    outputs.append(str(snapshot))
    answer_paths: list[str] = []
    try:
        for position, step in enumerate(spec.stages):
            previous = results[-1] if results else None
            permitted = (
                step.condition == "always"
                or previous is not None
                and previous.success
                and (
                    step.condition == "previous_success"
                    or bool(previous.outputs)
                )
            )
            if not permitted:
                results.append(
                    RecipeStepResult(
                        stage_id=step.id,
                        pipeline=step.pipeline,
                        success=True,
                        skipped=True,
                    )
                )
                continue
            values: JsonDict = {"email": spec.defaults.email, **step.overrides}
            stage_started = perf_counter()
            extra: JsonDict = {}
            try:
                if step.pipeline == "retrieve":
                    from sec_nlp.pipelines.presets.retrieve.config import (
                        RetrieveSettings,
                    )
                    from sec_nlp.pipelines.presets.retrieve.pipeline import (
                        RetrievePipeline,
                    )

                    configuration = RetrieveSettings.model_validate(values)
                    result, seed, evidence = RetrievePipeline(
                        config=configuration
                    ).run_for_flow_with_chunks()
                    if result.success:
                        seeds[step.id], chunks[step.id] = seed, evidence
                elif step.pipeline == "exhibit":
                    from sec_nlp.pipelines.presets.exb.config import (
                        ExhibitConfig,
                    )
                    from sec_nlp.pipelines.presets.exb.pipeline import (
                        ExhibitPipeline,
                    )

                    configuration = ExhibitConfig.model_validate(values)
                    result, contract, evidence = ExhibitPipeline(
                        config=configuration
                    ).run_for_flow_with_chunks()
                    if result.success:
                        seeds[step.id] = FlowSeedBundle(
                            upstream_pipeline=contract.upstream_pipeline,
                            upstream_run_id=contract.upstream_run_id,
                            upstream_short_id=contract.upstream_short_id,
                            symbols=contract.symbols,
                            queries=contract.queries,
                            chunks=[],
                        )
                        chunks[step.id] = evidence
                elif step.pipeline == "chat":
                    from sec_nlp.pipelines.presets.chat.config import (
                        ChatSettings,
                    )
                    from sec_nlp.pipelines.presets.chat.pipeline import (
                        ChatPipeline,
                    )

                    configuration = ChatSettings.model_validate(values)
                    binding = step.inputs[0] if step.inputs else None
                    seed = seeds.get(binding.from_stage) if binding else None
                    evidence = (
                        chunks.get(binding.from_stage, ()) if binding else ()
                    )
                    if binding and seed is None and not evidence:
                        raise ValueError(
                            f"Missing {binding.artifact} artifact from stage '{binding.from_stage}'"
                        )
                    result = ChatPipeline(config=configuration).run_for_flow(
                        seed_context=seed, seed_chunks=evidence
                    )
                    if result.success and result.answer:
                        preview = " ".join(result.answer.split())
                        extra["answer_preview"] = (
                            preview
                            if len(preview) <= 160
                            else preview[:159].rstrip() + "…"
                        )
                    stage_answers = [
                        str(path)
                        for path in result.outputs
                        if not path.name.endswith("_settings.json")
                    ]
                    extra["answer_output_paths"] = list(stage_answers)
                    answer_paths.extend(stage_answers)
                else:
                    config_type, pipeline_type = specialist_types(step.pipeline)
                    configuration = config_type.model_validate(values)
                    result = pipeline_type(config=configuration).run()
                stage_outputs = [str(path) for path in result.outputs]
                stage_result = RecipeStepResult(
                    stage_id=step.id,
                    pipeline=step.pipeline,
                    success=result.is_success(),
                    error=result.error,
                    duration_seconds=perf_counter() - stage_started,
                    run_id=str(configuration.run_id),
                    run_short_id=configuration.short_id,
                    outputs=stage_outputs,
                    metadata={
                        **TypeAdapter(JsonDict).validate_python(
                            result.metadata
                        ),
                        **extra,
                    },
                )
                outputs.extend(stage_outputs)
            except (OSError, ValueError, RuntimeError, ImportError) as exc:
                logger.debug("Research recipe step failed", exc_info=True)
                stage_result = RecipeStepResult(
                    stage_id=step.id,
                    pipeline=step.pipeline,
                    success=False,
                    error=str(exc),
                    duration_seconds=perf_counter() - stage_started,
                )
            results.append(stage_result)
            if not stage_result.success and spec.on_failure == "stop":
                results.extend(
                    RecipeStepResult(
                        stage_id=pending.id,
                        pipeline=pending.pipeline,
                        success=False,
                        skipped=True,
                        error="Skipped due to previous stage failure",
                    )
                    for pending in spec.stages[position + 1 :]
                )
                break
        return RecipeRunResult(
            flow_run_id=run_id,
            flow_name=spec.name,
            success=all(item.success or item.skipped for item in results),
            stage_results=results,
            outputs=outputs,
            metadata={
                "duration_seconds": perf_counter() - started,
                "flow_settings_snapshot": str(snapshot),
                "answer_output_paths": list(dict.fromkeys(answer_paths)),
                "on_failure": spec.on_failure,
                "stages_total": len(spec.stages),
                "stages_successful": sum(item.success for item in results),
                "stages_skipped": sum(item.skipped for item in results),
                "stages_failed": sum(
                    not item.success and not item.skipped for item in results
                ),
            },
        )
    finally:
        if "sec_nlp.pipelines.vector.config" in sys.modules:
            from sec_nlp.pipelines.vector.config import clear_runtime_caches

            clear_runtime_caches()
