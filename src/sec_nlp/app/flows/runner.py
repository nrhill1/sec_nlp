# src/sec_nlp/app/flows/runner.py
"""Flow runner for local multi-pipeline execution."""

from __future__ import annotations

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
    FlowStageInputBinding,
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

    def __init__(self, *, spec: FlowSpec) -> None:
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
        pipeline_name = stage.stage.pipeline
        if pipeline_name == "retrieve":
            return self._run_retrieve_stage(stage, artifacts)
        if pipeline_name == "chat":
            return self._run_chat_stage(stage, artifacts)
        if pipeline_name == "exhibit":
            return self._run_exhibit_stage(stage, artifacts)
        if pipeline_name == "analyze":
            return self._run_analyze_stage(stage, artifacts)
        if pipeline_name == "warranty":
            return self._run_warranty_stage(stage, artifacts)
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

    @staticmethod
    def _build_unexecuted_stage_result(
        *,
        stage: FlowStageSpec,
        success: bool,
        skipped: bool,
        error: str,
    ) -> FlowStageResult:
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
    def _resolve_seed_binding(
        stage: FlowStageSpec,
    ) -> tuple[FlowStageInputBinding | None, str | None]:
        resolved: FlowStageInputBinding | None = None
        for binding in stage.inputs:
            binding_error = FlowRunner._validate_input_binding(
                stage=stage,
                binding=binding,
            )
            if binding_error is not None:
                return None, binding_error
            if resolved is not None:
                return (
                    None,
                    f"chat stage '{stage.id}' accepts at most one input binding",
                )
            resolved = binding

        return resolved, None

    @staticmethod
    def _validate_input_binding(
        *,
        stage: FlowStageSpec,
        binding: FlowStageInputBinding,
    ) -> str | None:
        if binding.artifact not in {"retrieve_seed", "contract_evidence"}:
            return (
                f"chat stage '{stage.id}' does not support input artifact "
                f"'{binding.artifact}'"
            )
        if (
            binding.target_field is not None
            and binding.target_field != "seed_context"
        ):
            return (
                f"chat stage '{stage.id}' input binding target_field "
                "must be 'seed_context'"
            )
        return None

    @staticmethod
    def _seed_from_contract_evidence(
        evidence: ContractEvidenceBundle,
    ) -> FlowSeedBundle:
        return FlowSeedBundle(
            upstream_pipeline=evidence.upstream_pipeline,
            upstream_run_id=evidence.upstream_run_id,
            upstream_short_id=evidence.upstream_short_id,
            symbols=list(evidence.symbols),
            queries=list(evidence.queries),
            chunks=[],
        )

    @staticmethod
    def _seed_chunks_from_contract_evidence(
        evidence: ContractEvidenceBundle,
    ) -> tuple[FlowRetrievedChunk, ...]:
        chunks: list[FlowRetrievedChunk] = []
        for contract_chunk in evidence.chunks:
            snippet = contract_chunk.snippet.strip()
            if not snippet:
                continue
            chunks.append(
                FlowRetrievedChunk(
                    collection="exhibit",
                    score=float(contract_chunk.score),
                    symbol=contract_chunk.symbol,
                    accession_number=contract_chunk.accession_number,
                    form_type=contract_chunk.form_type,
                    filed_date=contract_chunk.filed_date,
                    source=contract_chunk.source,
                    snippet=snippet,
                    vector=None,
                )
            )
        return tuple(chunks)

    @staticmethod
    def _answer_preview(answer: str, *, max_chars: int = 160) -> str:
        normalized = " ".join(answer.split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1].rstrip()}…"

    @classmethod
    def _run_plain_pipeline_stage[
        SettingsT: BasePipelineSettings,
        PipelineT: BasePipeline,
    ](
        cls,
        *,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
        settings_type: type[SettingsT],
        pipeline_type: str,
        pipeline_class: type[PipelineT],
    ) -> FlowStageResult:
        _ = artifacts
        if not isinstance(stage.settings, settings_type):
            raise ValueError(
                f"{pipeline_type} stage received non-{pipeline_type} settings"
            )
        settings = stage.settings
        started = perf_counter()
        pipeline = pipeline_class(config=settings)
        result = pipeline.invoke()
        elapsed = perf_counter() - started
        return cls._build_stage_result(
            stage=stage.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(settings.run_id),
            run_short_id=settings.short_id,
        )

    @classmethod
    def _run_retrieve_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        if not isinstance(stage.settings, RetrieveSettings):
            raise ValueError("retrieve stage received non-retrieve settings")

        started = perf_counter()
        pipeline = RetrievePipeline(config=stage.settings)
        result, seed_bundle, seed_chunks = pipeline.run_for_flow_with_chunks()
        elapsed = perf_counter() - started
        if result.success:
            artifacts.put_retrieve_seed(stage.stage.id, seed_bundle)
            artifacts.put_seed_chunks(stage.stage.id, seed_chunks)

        return cls._build_stage_result(
            stage=stage.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(stage.settings.run_id),
            run_short_id=stage.settings.short_id,
        )

    @classmethod
    def _run_chat_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        if not isinstance(stage.settings, ChatSettings):
            raise ValueError("chat stage received non-chat settings")

        seed_binding, seed_error = cls._resolve_seed_binding(stage.stage)
        if seed_error is not None:
            return cls._build_unexecuted_stage_result(
                stage=stage.stage,
                success=False,
                skipped=False,
                error=seed_error,
            )

        seed_bundle: FlowSeedBundle | None = None
        seed_chunks: tuple[FlowRetrievedChunk, ...] = ()
        if seed_binding is not None:
            if seed_binding.artifact == "retrieve_seed":
                seed_bundle = artifacts.get_chat_seed(seed_binding.from_stage)
                seed_chunks = (
                    artifacts.get_seed_chunks(seed_binding.from_stage) or ()
                )
            elif seed_binding.artifact == "contract_evidence":
                contract_bundle = artifacts.get_contract_evidence(
                    seed_binding.from_stage
                )
                seed_chunks = (
                    artifacts.get_seed_chunks(seed_binding.from_stage) or ()
                )
                if contract_bundle is not None:
                    seed_bundle = cls._seed_from_contract_evidence(
                        contract_bundle
                    )
                    if not seed_chunks:
                        seed_chunks = cls._seed_chunks_from_contract_evidence(
                            contract_bundle
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

        started = perf_counter()
        result = ChatPipeline(config=stage.settings).run_for_flow(
            seed_context=seed_bundle,
            seed_chunks=seed_chunks,
        )
        elapsed = perf_counter() - started

        stage_result = cls._build_stage_result(
            stage=stage.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(stage.settings.run_id),
            run_short_id=stage.settings.short_id,
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
        if not isinstance(stage.settings, ExhibitConfig):
            raise ValueError("exhibit stage received non-exhibit settings")

        started = perf_counter()
        pipeline = ExhibitPipeline(config=stage.settings)
        result, evidence_bundle, seed_chunks = (
            pipeline.run_for_flow_with_chunks()
        )
        elapsed = perf_counter() - started
        if result.success:
            artifacts.put_contract_evidence(stage.stage.id, evidence_bundle)
            artifacts.put_seed_chunks(stage.stage.id, seed_chunks)

        return cls._build_stage_result(
            stage=stage.stage,
            pipeline_result=result,
            duration_seconds=elapsed,
            run_id=str(stage.settings.run_id),
            run_short_id=stage.settings.short_id,
        )

    @classmethod
    def _run_analyze_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        return cls._run_plain_pipeline_stage(
            stage=stage,
            artifacts=artifacts,
            settings_type=AnalyzeConfig,
            pipeline_type="analyze",
            pipeline_class=AnalyzePipeline,
        )

    @classmethod
    def _run_warranty_stage(
        cls,
        stage: CompiledStage,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        return cls._run_plain_pipeline_stage(
            stage=stage,
            artifacts=artifacts,
            settings_type=WarrantyConfig,
            pipeline_type="warranty",
            pipeline_class=WarrantyPipeline,
        )

    @staticmethod
    def _should_run_stage(
        stage: FlowStageSpec,
        previous: FlowStageResult | None,
    ) -> bool:
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
