# src/sec_nlp/pipelines/presets/chat/run_stages.py
"""Runnable stage helpers for chat pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from langchain_core.runnables import RunnableLambda
from rich.progress import Progress, TaskID

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonValue

from .bridge import ChatRetrievedChunk
from .models import ChatCitation, ChatTurn

if TYPE_CHECKING:
    from .pipeline import ChatPipeline


@dataclass(slots=True)
class ChatRunState:
    """Mutable in-process state shared across chat runnable stages."""

    question: str
    progress: Progress
    overall_task: TaskID
    phase_task: TaskID
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
    question: str,
    progress: Progress,
    overall_task: TaskID,
    phase_task: TaskID,
) -> ChatRunState:
    """Create initial mutable state for chat runnable stage execution."""
    return ChatRunState(
        question=question,
        progress=progress,
        overall_task=overall_task,
        phase_task=phase_task,
    )


@dataclass(slots=True)
class ChatStageRunner:
    """Bound stage methods to avoid per-stage lambda/closure allocations."""

    pipeline: ChatPipeline

    def search_context(self, state: ChatRunState) -> ChatRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            (
                "Using seeded retrieve context"
                if self.pipeline.config.seed_context is not None
                else "Searching indexed collections"
            ),
        )
        if self.pipeline.config.seed_context is None:
            state.chunks = self.pipeline._search_collections(
                state.question,
                progress=state.progress,
                phase_task=state.phase_task,
            )
        else:
            state.chunks = self.pipeline._search_seed_context(state.question)
            if not state.chunks:
                logger.warning(
                    "Seeded context returned no chunks; falling back to indexed collections",
                )
                self.pipeline._update_phase(
                    state.progress,
                    state.phase_task,
                    "Seed context empty; searching indexed collections",
                )
                state.chunks = self.pipeline._search_collections(
                    state.question,
                    progress=state.progress,
                    phase_task=state.phase_task,
                )
                state.seeded_context_fallback = True

        state.stage_timings.update(
            {
                "vector_search": self.pipeline._last_search_timings.get(
                    "vector_search",
                    0.0,
                ),
                "rerank": self.pipeline._last_search_timings.get("rerank", 0.0),
            }
        )
        state.progress.advance(state.overall_task)
        return state

    def prepare_context(self, state: ChatRunState) -> ChatRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            "Preparing citations and context",
        )
        state.citations = self.pipeline._to_citations(state.chunks)
        coverage_metadata = self.pipeline._symbol_coverage_metadata(
            state.citations
        )
        t0 = perf_counter()
        state.external_context, state.external_metadata = (
            self.pipeline._build_external_context(
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

    def generate_answer(self, state: ChatRunState) -> ChatRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            "Generating answer",
        )
        state.answer, state.used_citation_ids = self.pipeline._build_answer(
            question=state.question,
            citations=state.citations,
            external_context=state.external_context,
        )
        state.stage_timings.update(
            {
                "prompt_build": self.pipeline._last_answer_timings.get(
                    "prompt_build",
                    0.0,
                ),
                "llm_generate": self.pipeline._last_answer_timings.get(
                    "llm_generate",
                    0.0,
                ),
            }
        )
        state.progress.advance(state.overall_task)
        return state

    def build_turns(self, state: ChatRunState) -> ChatRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            "Building transcript",
        )
        state.turns = self.pipeline._build_turns(
            question=state.question,
            answer=state.answer,
            citation_ids=state.used_citation_ids,
        )
        state.progress.advance(state.overall_task)
        return state

    def write_outputs(self, state: ChatRunState) -> ChatRunState:
        self.pipeline._update_phase(
            state.progress,
            state.phase_task,
            "Writing outputs",
        )
        if self.pipeline.config.transcript_autosave:
            t0 = perf_counter()
            state.outputs = self.pipeline._write_outputs(
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


def build_chat_stage_runnables(
    pipeline: ChatPipeline,
) -> tuple[RunnableLambda[ChatRunState, ChatRunState], ...]:
    """Build deterministic chat stage runnables for readable orchestration."""
    runner = ChatStageRunner(pipeline)
    return pipeline.build_stage_runnables(
        named_stages=(
            ("search_context", runner.search_context),
            ("prepare_context", runner.prepare_context),
            ("generate_answer", runner.generate_answer),
            ("build_turns", runner.build_turns),
            ("write_outputs", runner.write_outputs),
        )
    )
