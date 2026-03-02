# src/sec_nlp/app/flows/runner.py
"""Flow runner for local multi-pipeline execution."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from uuid import uuid4

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.compiled import CompiledStage, compile_flow_stages
from sec_nlp.app.flows.contracts import (
    ContractEvidenceBundle,
    FlowRetrievedChunk,
    FlowSeedBundle,
)
from sec_nlp.app.flows.models import (
    FlowRunResult,
    FlowSpec,
    FlowStageResult,
    FlowStageSpec,
)
from sec_nlp.core.types import coerce_result_json_dict
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.base.pipeline import BasePipeline
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.pipelines.presets.analyze import AnalyzeConfig, AnalyzePipeline
from sec_nlp.pipelines.presets.chat import ChatPipeline, ChatSettings
from sec_nlp.pipelines.presets.exb import ExhibitConfig, ExhibitPipeline
from sec_nlp.pipelines.presets.retrieve import (
    RetrieveChatSeedBundle,
    RetrievePipeline,
    RetrieveSettings,
)
from sec_nlp.pipelines.presets.warranty import (
    WarrantyConfig,
    WarrantyPipeline,
)
from sec_nlp.pipelines.vector import clear_runtime_caches
from sec_nlp.types import JsonValue


class FlowRunner:
    """Execute a flow spec with direct compiled-stage pipeline dispatch."""

    __slots__ = ("spec",)

    def __init__(self, *, spec: FlowSpec) -> None:
        """Initialize the object."""
        self.spec = spec

    def run(self) -> FlowRunResult:
        """Execute all stages in order and return aggregate flow result."""
        flow_started = perf_counter()
        clear_runtime_caches()
        try:
            flow_run_id = str(uuid4())
            artifacts = FlowArtifactStore()
            stage_results: list[FlowStageResult] = []
            outputs: list[str] = []
            compiled_stages = compile_flow_stages(self.spec)

            previous: FlowStageResult | None = None
            failed_at: int | None = None
            for idx, compiled_stage in enumerate(compiled_stages):
                stage = compiled_stage.stage
                if not self._should_run_stage(stage, previous):
                    skipped = self._build_unexecuted_stage_result(
                        stage=stage,
                        success=True,
                        skipped=True,
                        error="Skipped because stage condition was not met",
                    )
                    stage_results.append(skipped)
                    previous = skipped
                    continue

                stage_result = self._run_stage(compiled_stage, artifacts)
                stage_results.append(stage_result)
                outputs.extend(stage_result.outputs)
                previous = stage_result

                if not stage_result.success and self.spec.on_failure == "stop":
                    failed_at = idx
                    break

            if failed_at is not None and failed_at + 1 < len(compiled_stages):
                for compiled_stage in compiled_stages[failed_at + 1 :]:
                    stage_results.append(
                        self._build_unexecuted_stage_result(
                            stage=compiled_stage.stage,
                            success=False,
                            skipped=True,
                            error="Skipped due to previous stage failure",
                        )
                    )

            success = all(
                result.success or result.skipped for result in stage_results
            )
            metadata: dict[str, JsonValue] = {
                "on_failure": self.spec.on_failure,
                "stages_total": len(self.spec.stages),
                "stages_successful": sum(
                    1 for result in stage_results if result.success
                ),
                "stages_skipped": sum(
                    1 for result in stage_results if result.skipped
                ),
                "stages_failed": sum(
                    1
                    for result in stage_results
                    if not result.success and not result.skipped
                ),
                "duration_seconds": perf_counter() - flow_started,
            }
            return FlowRunResult(
                flow_run_id=flow_run_id,
                flow_name=self.spec.name,
                success=success,
                stage_results=stage_results,
                outputs=outputs,
                metadata=metadata,
            )
        finally:
            clear_runtime_caches()

    def _run_stage(
        self,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Run stage."""
        pipeline_name = stage.stage.pipeline
        match pipeline_name:
            case "retrieve":
                return self._run_retrieve_stage(stage, artifacts)
            case "chat":
                return self._run_chat_stage(stage, artifacts)
            case "exhibit":
                return self._run_exhibit_stage(stage, artifacts)
            case "analyze":
                return self._run_analyze_stage(stage, artifacts)
            case "warranty":
                return self._run_warranty_stage(stage, artifacts)
            case _:
                raise ValueError(f"Unsupported flow pipeline '{pipeline_name}'")

    @classmethod
    def _build_stage_result(
        cls,
        *,
        stage: FlowStageSpec,
        pipeline_result: BasePipelineResult,
        duration_seconds: float,
        run_id: str,
        run_short_id: int,
    ) -> FlowStageResult:
        """Build stage result."""
        return FlowStageResult(
            stage_id=stage.id,
            pipeline=stage.pipeline,
            success=pipeline_result.success,
            skipped=False,
            error=pipeline_result.error,
            duration_seconds=duration_seconds,
            run_id=run_id,
            run_short_id=run_short_id if run_short_id > 0 else None,
            outputs=[str(path) for path in pipeline_result.outputs],
            metadata=coerce_result_json_dict(pipeline_result.metadata),
        )

    @classmethod
    def _build_stage_result_for_settings(
        cls,
        *,
        stage: FlowStageSpec,
        pipeline_result: BasePipelineResult,
        duration_seconds: float,
        settings: BasePipelineSettings,
    ) -> FlowStageResult:
        """Build stage result using run identifiers from validated settings."""
        return cls._build_stage_result(
            stage=stage,
            pipeline_result=pipeline_result,
            duration_seconds=duration_seconds,
            run_id=str(settings.run_id),
            run_short_id=settings.short_id,
        )

    @classmethod
    def _invoke_pipeline(
        cls,
        *,
        stage: FlowStageSpec,
        settings: BasePipelineSettings,
        pipeline: BasePipeline,
    ) -> FlowStageResult:
        """Invoke a plain pipeline and normalize the stage result envelope."""
        result, elapsed = cls._timed_call(pipeline.invoke)
        return cls._build_stage_result_for_settings(
            stage=stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            settings=settings,
        )

    @staticmethod
    def _timed_call[ResultT](
        callback: Callable[[], ResultT],
    ) -> tuple[ResultT, float]:
        """Execute a zero-argument callback and return result plus duration."""
        started = perf_counter()
        result = callback()
        return result, perf_counter() - started

    @staticmethod
    def _require_stage_settings[SettingsT: BasePipelineSettings](
        stage: CompiledStage,
        *,
        expected_type: type[SettingsT],
        pipeline_name: str,
    ) -> SettingsT:
        """Return validated stage settings for one pipeline name."""
        if not isinstance(stage.settings, expected_type):
            raise ValueError(
                f"{pipeline_name} stage received non-{pipeline_name} settings"
            )
        return stage.settings

    @classmethod
    def _run_chunk_handoff_stage[BundleT](
        cls,
        *,
        stage: FlowStageSpec,
        settings: BasePipelineSettings,
        artifacts: FlowArtifactStore,
        run_callback: Callable[
            [],
            tuple[BasePipelineResult, BundleT, tuple[FlowRetrievedChunk, ...]],
        ],
        persist_callback: Callable[
            [FlowArtifactStore, str, BundleT, tuple[FlowRetrievedChunk, ...]],
            None,
        ],
    ) -> FlowStageResult:
        """Run a stage that returns both a result and chunk-based handoff artifacts."""
        (result, bundle, seed_chunks), elapsed = cls._timed_call(run_callback)
        if result.success:
            persist_callback(artifacts, stage.id, bundle, seed_chunks)
        return cls._build_stage_result_for_settings(
            stage=stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            settings=settings,
        )

    @classmethod
    def _run_typed_pipeline_stage[SettingsT: BasePipelineSettings](
        cls,
        *,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
        expected_type: type[SettingsT],
        pipeline_name: str,
        pipeline_factory: Callable[[SettingsT], BasePipeline],
    ) -> FlowStageResult:
        """Run a stage backed by one strongly typed pipeline settings model."""
        _ = artifacts
        settings = cls._require_stage_settings(
            stage,
            expected_type=expected_type,
            pipeline_name=pipeline_name,
        )
        return cls._invoke_pipeline(
            stage=stage.stage,
            settings=settings,
            pipeline=pipeline_factory(settings),
        )

    @staticmethod
    def _persist_retrieve_artifacts(
        artifacts: FlowArtifactStore,
        stage_id: str,
        bundle: RetrieveChatSeedBundle,
        seed_chunks: tuple[FlowRetrievedChunk, ...],
    ) -> None:
        """Persist retrieve handoff artifacts into flow artifact storage."""
        artifacts.put_seed_bundle(stage_id, bundle)
        artifacts.put_seed_chunks(stage_id, seed_chunks)

    @staticmethod
    def _persist_exhibit_artifacts(
        artifacts: FlowArtifactStore,
        stage_id: str,
        bundle: ContractEvidenceBundle,
        seed_chunks: tuple[FlowRetrievedChunk, ...],
    ) -> None:
        """Persist exhibit handoff artifacts into flow artifact storage."""
        artifacts.put_contract_evidence(stage_id, bundle)
        artifacts.put_seed_chunks(stage_id, seed_chunks)

    @staticmethod
    def _build_unexecuted_stage_result(
        *,
        stage: FlowStageSpec,
        success: bool,
        skipped: bool,
        error: str,
    ) -> FlowStageResult:
        """Build unexecuted stage result."""
        return FlowStageResult(
            stage_id=stage.id,
            pipeline=stage.pipeline,
            success=success,
            skipped=skipped,
            error=error,
            duration_seconds=0.0,
            outputs=[],
            metadata={},
        )

    @staticmethod
    def _answer_preview(answer: str, *, max_chars: int = 160) -> str:
        """Extract a one-line answer preview for flow logging."""
        normalized = " ".join(answer.split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1].rstrip()}…"

    @classmethod
    def _run_analyze_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Run analyze stage."""
        return cls._run_typed_pipeline_stage(
            stage=stage,
            artifacts=artifacts,
            expected_type=AnalyzeConfig,
            pipeline_name="analyze",
            pipeline_factory=lambda settings: AnalyzePipeline(config=settings),
        )

    @classmethod
    def _run_warranty_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Run warranty stage."""
        return cls._run_typed_pipeline_stage(
            stage=stage,
            artifacts=artifacts,
            expected_type=WarrantyConfig,
            pipeline_name="warranty",
            pipeline_factory=lambda settings: WarrantyPipeline(config=settings),
        )

    @classmethod
    def _run_retrieve_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Run retrieve stage."""
        settings = cls._require_stage_settings(
            stage,
            expected_type=RetrieveSettings,
            pipeline_name="retrieve",
        )
        return cls._run_chunk_handoff_stage(
            stage=stage.stage,
            settings=settings,
            artifacts=artifacts,
            run_callback=RetrievePipeline(
                config=settings
            ).run_for_flow_with_chunks,
            persist_callback=cls._persist_retrieve_artifacts,
        )

    @classmethod
    def _run_chat_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Run chat stage."""
        settings = cls._require_stage_settings(
            stage,
            expected_type=ChatSettings,
            pipeline_name="chat",
        )

        seed_binding = stage.stage.inputs[0] if stage.stage.inputs else None

        seed_bundle: FlowSeedBundle | None = None
        seed_chunks: tuple[FlowRetrievedChunk, ...] = ()
        if seed_binding is not None:
            seed_bundle, seed_chunks = artifacts.resolve_chat_seed_input(
                seed_binding
            )

            if seed_bundle is None and not seed_chunks:
                return cls._build_unexecuted_stage_result(
                    stage=stage.stage,
                    success=False,
                    skipped=False,
                    error=(
                        f"Missing {seed_binding.artifact} artifact from stage "
                        f"'{seed_binding.from_stage}'"
                    ),
                )

        chat_pipeline = ChatPipeline(config=settings)
        started = perf_counter()
        result = chat_pipeline.run_for_flow(
            seed_context=seed_bundle,
            seed_chunks=seed_chunks,
        )
        elapsed = perf_counter() - started

        stage_result = cls._build_stage_result_for_settings(
            stage=stage.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            settings=settings,
        )
        if result.success and isinstance(result.answer, str) and result.answer:
            metadata = dict(stage_result.metadata)
            metadata["answer_preview"] = cls._answer_preview(result.answer)
            return stage_result.model_copy(update={"metadata": metadata})
        return stage_result

    @classmethod
    def _run_exhibit_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Run exhibit stage."""
        settings = cls._require_stage_settings(
            stage,
            expected_type=ExhibitConfig,
            pipeline_name="exhibit",
        )
        return cls._run_chunk_handoff_stage(
            stage=stage.stage,
            settings=settings,
            artifacts=artifacts,
            run_callback=ExhibitPipeline(
                config=settings
            ).run_for_flow_with_chunks,
            persist_callback=cls._persist_exhibit_artifacts,
        )

    @staticmethod
    def _should_run_stage(
        stage: FlowStageSpec,
        previous: FlowStageResult | None,
    ) -> bool:
        """Return whether run stage."""
        if stage.condition == "always":
            return True
        if previous is None:
            return stage.condition in {
                "previous_success",
                "previous_has_outputs",
            }
        if stage.condition == "previous_success":
            return previous.success
        if stage.condition == "previous_has_outputs":
            return bool(previous.outputs)
        return True
