# src/sec_nlp/pipelines/presets/chat/run_stages.py
"""Runnable stage helpers for chat pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from langchain_core.runnables import Runnable
from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.base.stages import PipelineStageRunnable
from sec_nlp.types import JsonValue

from .bridge import ChatRetrievedChunk, ChatSeedBundle
from .models import ChatCitation, ChatTurn

if TYPE_CHECKING:
    from .pipeline import ChatPipeline


@dataclass(slots=True)
class ChatRunState:
    """In-place state carrier for chat stages from context retrieval to output persistence."""

    runtime: ChatPipeline
    question: str
    progress: Progress
    overall_task: TaskID
    phase_task: TaskID
    seed_context: ChatSeedBundle | None = None
    seed_chunks: tuple[ChatRetrievedChunk, ...] = ()
    outputs: list[Path] = field(default_factory=list)
    chunks: list[ChatRetrievedChunk] = field(default_factory=list)
    citations: list[ChatCitation] = field(default_factory=list)
    external_context: str = ""
    external_metadata: dict[str, JsonValue] = field(default_factory=dict)
    answer: str = ""
    used_citation_ids: list[str] = field(default_factory=list)
    turns: list[ChatTurn] = field(default_factory=list)
    seeded_context_fallback: bool = False
    stage_timings: dict[str, float] = field(
        default_factory=lambda: {
            "vector_search": 0.0,
            "rerank": 0.0,
            "external_context": 0.0,
            "prompt_build": 0.0,
            "llm_generate": 0.0,
            "write": 0.0,
        }
    )


def create_initial_chat_state(
    *,
    runtime: ChatPipeline,
    question: str,
    progress: Progress,
    overall_task: TaskID,
    phase_task: TaskID,
    seed_context: ChatSeedBundle | None = None,
    seed_chunks: tuple[ChatRetrievedChunk, ...] = (),
) -> ChatRunState:
    """Create initial mutable state for chat runnable stage execution."""
    return ChatRunState(
        runtime=runtime,
        question=question,
        progress=progress,
        overall_task=overall_task,
        phase_task=phase_task,
        seed_context=seed_context,
        seed_chunks=seed_chunks,
    )


class SearchContextStage(PipelineStageRunnable[ChatRunState]):
    """Ingress retrieval stage that sources context from seeds first, then vector search."""

    name: str = Field(default="search_context")

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the search context stage and return updated run state."""
        has_seed_context = (
            state.seed_context is not None or len(state.seed_chunks) > 0
        )
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            (
                "Using seeded retrieve context"
                if has_seed_context
                else "Searching indexed collections"
            ),
        )
        if not has_seed_context:
            state.chunks = state.runtime._search_collections(
                state.question,
                progress=state.progress,
                phase_task=state.phase_task,
            )
        else:
            state.chunks = state.runtime._search_seed_context(
                question=state.question,
                seed=state.seed_context,
                seed_chunks=state.seed_chunks,
            )
            if not state.chunks:
                logger.warning(
                    "Seeded context returned no chunks; falling back to indexed collections",
                )
                state.runtime._update_phase(
                    state.progress,
                    state.phase_task,
                    "Seed context empty; searching indexed collections",
                )
                state.chunks = state.runtime._search_collections(
                    state.question,
                    progress=state.progress,
                    phase_task=state.phase_task,
                )
                state.seeded_context_fallback = True

        state.stage_timings.update(
            {
                "vector_search": state.runtime._last_search_timings.get(
                    "vector_search",
                    0.0,
                ),
                "rerank": state.runtime._last_search_timings.get("rerank", 0.0),
            }
        )
        state.progress.advance(state.overall_task)
        return state


class PrepareContextStage(PipelineStageRunnable[ChatRunState]):
    """Context assembly stage that builds citations, coverage metadata, and external context."""

    name: str = Field(default="prepare_context")

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the prepare context stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            "Preparing citations and context",
        )
        state.citations = state.runtime._to_citations(state.chunks)
        coverage_metadata = state.runtime._symbol_coverage_metadata(
            state.citations
        )
        t0 = perf_counter()
        state.external_context, state.external_metadata = (
            state.runtime._build_external_context(
                question=state.question,
                citations=state.citations,
            )
        )
        state.stage_timings["external_context"] = perf_counter() - t0
        if state.seeded_context_fallback:
            coverage_metadata["seeded_context_fallback_to_vector_search"] = True
        state.external_metadata.update(coverage_metadata)
        missing_symbols = coverage_metadata.get("missing_symbols")
        if isinstance(missing_symbols, list) and missing_symbols:
            logger.warning(
                "No retrieved filing chunks for %d symbols: %s",
                len(missing_symbols),
                ", ".join(str(symbol) for symbol in missing_symbols),
            )
        state.progress.advance(state.overall_task)
        return state


class GenerateAnswerStage(PipelineStageRunnable[ChatRunState]):
    """Generation stage that produces grounded answer text and used citation identifiers."""

    name: str = Field(default="generate_answer")

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the generate answer stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            "Generating answer",
        )
        state.answer, state.used_citation_ids = state.runtime._build_answer(
            question=state.question,
            citations=state.citations,
            external_context=state.external_context,
        )
        state.stage_timings.update(
            {
                "prompt_build": state.runtime._last_answer_timings.get(
                    "prompt_build",
                    0.0,
                ),
                "llm_generate": state.runtime._last_answer_timings.get(
                    "llm_generate",
                    0.0,
                ),
            }
        )
        state.progress.advance(state.overall_task)
        return state


class BuildTurnsStage(PipelineStageRunnable[ChatRunState]):
    """Transcript stage that materializes question-answer turns for downstream writing."""

    name: str = Field(default="build_turns")

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the build turns stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            "Building transcript",
        )
        state.turns = state.runtime._build_turns(
            question=state.question,
            answer=state.answer,
            citation_ids=state.used_citation_ids,
        )
        state.progress.advance(state.overall_task)
        return state


class WriteChatOutputsStage(PipelineStageRunnable[ChatRunState]):
    """Egress stage that persists chat transcript and summary artifacts when enabled."""

    name: str = Field(default="write_outputs")

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the write chat outputs stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            "Writing outputs",
        )
        if state.runtime.config.transcript_autosave:
            t0 = perf_counter()
            state.outputs = state.runtime._write_outputs(
                question=state.question,
                answer=state.answer,
                citations=state.citations,
                citation_ids=state.used_citation_ids,
                turns=state.turns,
                external_context=state.external_context,
                external_metadata=state.external_metadata,
            )
            state.stage_timings["write"] = perf_counter() - t0
        state.progress.advance(state.overall_task)
        return state


def build_chat_stage_chain(
    pipeline: ChatPipeline,
) -> Runnable[ChatRunState, ChatRunState]:
    """Build deterministic chat stage chain."""
    stages: tuple[PipelineStageRunnable[ChatRunState], ...] = (
        SearchContextStage(),
        PrepareContextStage(),
        GenerateAnswerStage(),
        BuildTurnsStage(),
        WriteChatOutputsStage(),
    )
    configured_stages = tuple(
        stage.configured(
            pipeline_type=pipeline.pipeline_type,
            run_id=str(pipeline.config.run_id),
        )
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
