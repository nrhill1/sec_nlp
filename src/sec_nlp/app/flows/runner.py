"""Flow runner for local multi-pipeline execution."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.models import (
    FlowRunResult,
    FlowSpec,
    FlowStageResult,
    FlowStageSpec,
)
from sec_nlp.app.flows.runnables import (
    ChatFlowInvokeInput,
    ChatFlowRunnable,
    RetrieveFlowInvokeInput,
    RetrieveFlowRunnable,
)
from sec_nlp.app.flows.runnables.utils import build_unexecuted_stage_result
from sec_nlp.pipelines.vector import clear_runtime_caches
from sec_nlp.types import JsonValue


class FlowRunner:
    """Execute a flow spec with stage-level runnable adapters."""

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

            previous: FlowStageResult | None = None
            failed_at: int | None = None
            for idx, stage in enumerate(self.spec.stages):
                if not self._should_run_stage(stage, previous):
                    skipped = build_unexecuted_stage_result(
                        stage=stage,
                        success=True,
                        skipped=True,
                        error="Skipped because stage condition was not met",
                    )
                    stage_results.append(skipped)
                    previous = skipped
                    continue

                stage_result = self._run_stage(stage, artifacts)
                stage_results.append(stage_result)
                outputs.extend(stage_result.outputs)
                previous = stage_result

                if not stage_result.success and self.spec.on_failure == "stop":
                    failed_at = idx
                    break

            if failed_at is not None and failed_at + 1 < len(self.spec.stages):
                for stage in self.spec.stages[failed_at + 1 :]:
                    stage_results.append(
                        build_unexecuted_stage_result(
                            stage=stage,
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
        stage: FlowStageSpec,
        artifacts: FlowArtifactStore,
    ) -> FlowStageResult:
        if stage.pipeline == "retrieve":
            return RetrieveFlowRunnable(
                stage=stage,
                defaults=self.spec.defaults,
                artifacts=artifacts,
            ).invoke(RetrieveFlowInvokeInput())
        if stage.pipeline == "chat":
            return ChatFlowRunnable(
                stage=stage,
                defaults=self.spec.defaults,
                artifacts=artifacts,
            ).invoke(ChatFlowInvokeInput())
        raise ValueError(f"Unsupported flow pipeline '{stage.pipeline}'")

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
