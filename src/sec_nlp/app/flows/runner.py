# src/sec_nlp/app/flows/runner.py
"""Executor for compiled flow stages and in-memory artifact handoff.

The runner consumes typed compiled stages, dispatches each pipeline, and
records stage-level envelopes. It avoids config re-validation by relying on
compile-time guarantees and only operating on compiled stage types.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter
from uuid import uuid4

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.compiled import (
    CompiledAnalyzeStage,
    CompiledChatStage,
    CompiledExhibitStage,
    CompiledRetrieveStage,
    CompiledStage,
    CompiledWarrantyStage,
    compile_flow_stages,
)
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
from sec_nlp.pipelines.base.pipeline import BasePipeline
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.pipelines.presets.analyze import AnalyzePipeline
from sec_nlp.pipelines.presets.chat import ChatPipeline
from sec_nlp.pipelines.presets.exb import ExhibitPipeline
from sec_nlp.pipelines.presets.retrieve import (
    RetrieveChatSeedBundle,
    RetrievePipeline,
)
from sec_nlp.pipelines.presets.warranty import WarrantyPipeline
from sec_nlp.pipelines.vector import clear_runtime_caches
from sec_nlp.types import JsonValue


class FlowRunner:
    """Compile and execute a multi-stage flow spec end-to-end.

    The runner compiles stages once, dispatches each to its typed pipeline,
    manages in-memory artifact handoff between stages, enforces
    ``on_failure`` policy, and aggregates results into a ``FlowRunResult``.
    Runtime caches are cleared before and after every run.
    """

    __slots__ = ("spec",)

    def __init__(self, *, spec: FlowSpec) -> None:
        """Construct a runner for the given validated flow spec."""
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
                stage_results.extend(
                    self._build_unexecuted_stage_result(
                        stage=cs.stage,
                        success=False,
                        skipped=True,
                        error="Skipped due to previous stage failure",
                    )
                    for cs in compiled_stages[failed_at + 1 :]
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
        """Dispatch a compiled stage to its typed pipeline runner."""
        if isinstance(stage, CompiledRetrieveStage):
            return self._run_retrieve_stage(stage, artifacts)
        if isinstance(stage, CompiledChatStage):
            return self._run_chat_stage(stage, artifacts)
        if isinstance(stage, CompiledExhibitStage):
            return self._run_exhibit_stage(stage, artifacts)
        if isinstance(stage, CompiledAnalyzeStage):
            return self._run_analyze_stage(stage, artifacts)
        if isinstance(stage, CompiledWarrantyStage):
            return self._run_warranty_stage(stage, artifacts)
        raise ValueError(
            f"Unsupported compiled stage type: {type(stage).__name__}"
        )

    @classmethod
    def _build_stage_result(
        cls,
        *,
        stage: FlowStageSpec,
        pipeline_result: BasePipelineResult,
        duration_seconds: float,
        run_id: str,
        run_short_id: int | None,
        extra_metadata: Mapping[str, JsonValue] | None = None,
    ) -> FlowStageResult:
        """Wrap a pipeline result into a ``FlowStageResult`` with run identifiers."""
        metadata = coerce_result_json_dict(pipeline_result.metadata)
        if extra_metadata is not None:
            metadata.update(extra_metadata)
        return FlowStageResult(
            stage_id=stage.id,
            pipeline=stage.pipeline,
            success=pipeline_result.success,
            skipped=False,
            error=pipeline_result.error,
            duration_seconds=duration_seconds,
            run_id=run_id,
            run_short_id=run_short_id,
            outputs=[str(path) for path in pipeline_result.outputs],
            metadata=metadata,
        )

    @classmethod
    def _invoke_pipeline(
        cls,
        *,
        compiled: CompiledStage,
        pipeline: BasePipeline,
    ) -> FlowStageResult:
        """Invoke a plain pipeline and normalize the stage result envelope."""
        result, elapsed = cls._timed_call(pipeline.invoke)
        return cls._build_stage_result(
            stage=compiled.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=compiled.run_id,
            run_short_id=compiled.run_short_id,
        )

    @staticmethod
    def _timed_call[ResultT](
        callback: Callable[[], ResultT],
    ) -> tuple[ResultT, float]:
        """Execute a zero-argument callback and return result plus duration."""
        started = perf_counter()
        result = callback()
        return result, perf_counter() - started

    @classmethod
    def _run_chunk_handoff_stage[BundleT](
        cls,
        *,
        compiled: CompiledStage,
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
        """Execute a pipeline that emits both a result and typed handoff artifacts."""
        (result, bundle, seed_chunks), elapsed = cls._timed_call(run_callback)
        if result.success:
            persist_callback(artifacts, compiled.stage.id, bundle, seed_chunks)
        return cls._build_stage_result(
            stage=compiled.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=compiled.run_id,
            run_short_id=compiled.run_short_id,
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
        """Build a zero-duration result for a stage that was not executed."""
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
        stage: CompiledAnalyzeStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Dispatch a compiled analyze stage to ``AnalyzePipeline``."""
        _ = artifacts
        return cls._invoke_pipeline(
            compiled=stage, pipeline=AnalyzePipeline(config=stage.settings)
        )

    @classmethod
    def _run_warranty_stage(
        cls,
        stage: CompiledWarrantyStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Dispatch a compiled warranty stage to ``WarrantyPipeline``."""
        _ = artifacts
        return cls._invoke_pipeline(
            compiled=stage, pipeline=WarrantyPipeline(config=stage.settings)
        )

    @classmethod
    def _run_retrieve_stage(
        cls,
        stage: CompiledRetrieveStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Dispatch a compiled retrieve stage and persist seed artifacts."""
        pipeline = RetrievePipeline(config=stage.settings)
        return cls._run_chunk_handoff_stage(
            compiled=stage,
            artifacts=artifacts,
            run_callback=pipeline.run_for_flow_with_chunks,
            persist_callback=cls._persist_retrieve_artifacts,
        )

    @classmethod
    def _run_chat_stage(
        cls,
        stage: CompiledChatStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Resolve seed inputs from upstream artifacts and run the chat pipeline."""
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

        chat_pipeline = ChatPipeline(config=stage.settings)
        started = perf_counter()
        result = chat_pipeline.run_for_flow(
            seed_context=seed_bundle,
            seed_chunks=seed_chunks,
        )
        elapsed = perf_counter() - started

        answer_preview: str | None = None
        if result.success and isinstance(result.answer, str) and result.answer:
            answer_preview = cls._answer_preview(result.answer)
        return cls._build_stage_result(
            stage=stage.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=stage.run_id,
            run_short_id=stage.run_short_id,
            extra_metadata={
                "answer_preview": answer_preview,
            }
            if answer_preview is not None
            else None,
        )

    @classmethod
    def _run_exhibit_stage(
        cls,
        stage: CompiledExhibitStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        """Run exhibit stage."""
        pipeline = ExhibitPipeline(config=stage.settings)
        return cls._run_chunk_handoff_stage(
            compiled=stage,
            artifacts=artifacts,
            run_callback=pipeline.run_for_flow_with_chunks,
            persist_callback=cls._persist_exhibit_artifacts,
        )

    @staticmethod
    def _should_run_stage(
        stage: FlowStageSpec,
        previous: FlowStageResult | None,
    ) -> bool:
        """Evaluate the stage condition against the previous result."""
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
