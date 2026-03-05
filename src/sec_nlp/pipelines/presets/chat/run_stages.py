# src/sec_nlp/pipelines/presets/chat/run_stages.py
"""Runnable stage helpers for chat pipeline execution."""

from __future__ import annotations

from collections.abc import Callable
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
from .config import ChatSettings
from .models import ChatCitation, ChatTurn

if TYPE_CHECKING:
    from .pipeline import ChatPipeline


@dataclass(slots=True)
class ChatRunState:
    """In-place state carrier for chat stages from context retrieval to output persistence."""

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


@dataclass(slots=True, frozen=True)
class ChatStageContext:
    """Shared runtime context for chat stage runnables."""

    config: ChatSettings
    update_phase: Callable[[Progress | None, TaskID | None, str], None]
    search_collections: Callable[
        [str, Progress | None, TaskID | None],
        list[ChatRetrievedChunk],
    ]
    search_seed_context: Callable[
        [str, ChatSeedBundle | None, tuple[ChatRetrievedChunk, ...]],
        list[ChatRetrievedChunk],
    ]
    get_search_timings: Callable[[], dict[str, float]]
    to_citations: Callable[[list[ChatRetrievedChunk]], list[ChatCitation]]
    symbol_coverage_metadata: Callable[
        [list[ChatCitation]],
        dict[str, JsonValue],
    ]
    build_external_context: Callable[
        [str, list[ChatCitation]],
        tuple[str, dict[str, JsonValue]],
    ]
    build_answer: Callable[
        [str, list[ChatCitation], str], tuple[str, list[str]]
    ]
    get_answer_timings: Callable[[], dict[str, float]]
    build_turns: Callable[[str, str, list[str]], list[ChatTurn]]
    write_outputs: Callable[
        [
            str,
            str,
            list[ChatCitation],
            list[str],
            list[ChatTurn],
            str,
            dict[str, JsonValue],
        ],
        list[Path],
    ]


class SearchContextStage(PipelineStageRunnable[ChatRunState]):
    """Ingress retrieval stage that sources context from seeds first, then vector search."""

    name: str = Field(default="search_context")
    context: ChatStageContext = Field(repr=False)

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the search context stage and return updated run state."""
        has_seed_context = (
            state.seed_context is not None or len(state.seed_chunks) > 0
        )
        self.context.update_phase(
            state.progress,
            state.phase_task,
            (
                "Using seeded retrieve context"
                if has_seed_context
                else "Searching indexed collections"
            ),
        )
        if not has_seed_context:
            state.chunks = self.context.search_collections(
                state.question,
                state.progress,
                state.phase_task,
            )
        else:
            state.chunks = self.context.search_seed_context(
                state.question,
                state.seed_context,
                state.seed_chunks,
            )
            if not state.chunks:
                logger.warning(
                    "Seeded context returned no chunks; falling back to indexed collections",
                )
                self.context.update_phase(
                    state.progress,
                    state.phase_task,
                    "Seed context empty; searching indexed collections",
                )
                state.chunks = self.context.search_collections(
                    state.question,
                    state.progress,
                    state.phase_task,
                )
                state.seeded_context_fallback = True

        search_timings = self.context.get_search_timings()
        state.stage_timings.update(
            {
                "vector_search": search_timings.get(
                    "vector_search",
                    0.0,
                ),
                "rerank": search_timings.get("rerank", 0.0),
            }
        )
        state.progress.advance(state.overall_task)
        return state


class PrepareContextStage(PipelineStageRunnable[ChatRunState]):
    """Context assembly stage that builds citations, coverage metadata, and external context."""

    name: str = Field(default="prepare_context")
    context: ChatStageContext = Field(repr=False)

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the prepare context stage and return updated run state."""
        self.context.update_phase(
            state.progress,
            state.phase_task,
            "Preparing citations and context",
        )
        state.citations = self.context.to_citations(state.chunks)
        coverage_metadata = self.context.symbol_coverage_metadata(
            state.citations
        )
        t0 = perf_counter()
        state.external_context, state.external_metadata = (
            self.context.build_external_context(state.question, state.citations)
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
    context: ChatStageContext = Field(repr=False)

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the generate answer stage and return updated run state."""
        self.context.update_phase(
            state.progress,
            state.phase_task,
            "Generating answer",
        )
        state.answer, state.used_citation_ids = self.context.build_answer(
            state.question,
            state.citations,
            state.external_context,
        )
        answer_timings = self.context.get_answer_timings()
        state.stage_timings.update(
            {
                "prompt_build": answer_timings.get(
                    "prompt_build",
                    0.0,
                ),
                "llm_generate": answer_timings.get(
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
    context: ChatStageContext = Field(repr=False)

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the build turns stage and return updated run state."""
        self.context.update_phase(
            state.progress,
            state.phase_task,
            "Building transcript",
        )
        state.turns = self.context.build_turns(
            state.question,
            state.answer,
            state.used_citation_ids,
        )
        state.progress.advance(state.overall_task)
        return state


class WriteChatOutputsStage(PipelineStageRunnable[ChatRunState]):
    """Egress stage that persists chat transcript and summary artifacts when enabled."""

    name: str = Field(default="write_outputs")
    context: ChatStageContext = Field(repr=False)

    def _run(self, state: ChatRunState) -> ChatRunState:
        """Execute the write chat outputs stage and return updated run state."""
        self.context.update_phase(
            state.progress,
            state.phase_task,
            "Writing outputs",
        )
        if self.context.config.transcript_autosave:
            t0 = perf_counter()
            state.outputs = self.context.write_outputs(
                state.question,
                state.answer,
                state.citations,
                state.used_citation_ids,
                state.turns,
                state.external_context,
                state.external_metadata,
            )
            state.stage_timings["write"] = perf_counter() - t0
        state.progress.advance(state.overall_task)
        return state


def build_chat_stage_chain(
    pipeline: ChatPipeline,
) -> Runnable[ChatRunState, ChatRunState]:
    """Build deterministic chat stage chain."""
    context = ChatStageContext(
        config=pipeline.config,
        update_phase=pipeline._update_phase,
        search_collections=(
            lambda question, progress, phase_task: pipeline._search_collections(
                question=question,
                progress=progress,
                phase_task=phase_task,
            )
        ),
        search_seed_context=(
            lambda question, seed, seed_chunks: pipeline._search_seed_context(
                question=question,
                seed=seed,
                seed_chunks=seed_chunks,
            )
        ),
        get_search_timings=lambda: pipeline._last_search_timings,
        to_citations=pipeline._to_citations,
        symbol_coverage_metadata=pipeline._symbol_coverage_metadata,
        build_external_context=(
            lambda question, citations: pipeline._build_external_context(
                question=question,
                citations=citations,
            )
        ),
        build_answer=(
            lambda question, citations, external_context: (
                pipeline._build_answer(
                    question=question,
                    citations=citations,
                    external_context=external_context,
                )
            )
        ),
        get_answer_timings=lambda: pipeline._last_answer_timings,
        build_turns=(
            lambda question, answer, citation_ids: pipeline._build_turns(
                question=question,
                answer=answer,
                citation_ids=citation_ids,
            )
        ),
        write_outputs=(
            lambda question, answer, citations, citation_ids, turns, external_context, external_metadata: (
                pipeline._write_outputs(
                    question=question,
                    answer=answer,
                    citations=citations,
                    citation_ids=citation_ids,
                    turns=turns,
                    external_context=external_context,
                    external_metadata=external_metadata,
                )
            )
        ),
    )
    stages: tuple[PipelineStageRunnable[ChatRunState], ...] = (
        SearchContextStage(context=context),
        PrepareContextStage(context=context),
        GenerateAnswerStage(context=context),
        BuildTurnsStage(context=context),
        WriteChatOutputsStage(context=context),
    )
    return pipeline.build_configured_stage_chain(stages=stages)
