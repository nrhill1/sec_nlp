# src/sec_nlp/pipelines/presets/retrieve/run_stages.py
"""Runnable stage helpers for retrieve pipeline execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from langchain_core.runnables import Runnable
from pydantic import Field
from rich.progress import Progress, TaskID

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.pipelines.base.stages import PipelineStageRunnable
from sec_nlp.types import JsonValue

from .models import RetrievalHit
from .steps import RetrieveCandidateSearcher

if TYPE_CHECKING:
    from .pipeline import RetrievePipeline


@dataclass(slots=True)
class RetrieveRunState:
    """In-place state carrier for retrieve stages from candidate search to output write."""

    runtime: RetrievePipeline
    search_symbol: str | None
    output_symbol: str
    candidate_searcher: RetrieveCandidateSearcher | None
    precomputed_candidates: dict[str, list[EFTSHit]] | None
    shared_candidate_overhead: float
    progress: Progress | None
    phase_task: TaskID | None
    candidates_by_query: dict[str, list[EFTSHit]] = field(default_factory=dict)
    candidate_count: int = 0
    ranked_hits: list[RetrievalHit] = field(default_factory=list)
    hydrated_input: list[RetrievalHit] = field(default_factory=list)
    passthrough_hits: list[RetrievalHit] = field(default_factory=list)
    hydrated_hits: list[RetrievalHit] = field(default_factory=list)
    reranked_hits: list[RetrievalHit] = field(default_factory=list)
    indexed_hits: list[RetrievalHit] = field(default_factory=list)
    final_hits: list[RetrievalHit] = field(default_factory=list)
    lexical_pruned: int = 0
    outputs: list[Path] = field(default_factory=list)
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    market_context_metadata: dict[str, JsonValue] = field(default_factory=dict)
    stage_timings: dict[str, float] = field(
        default_factory=lambda: {
            "candidate_search": 0.0,
            "ranking": 0.0,
            "hydrate": 0.0,
            "embedding_rerank": 0.0,
            "index": 0.0,
            "write": 0.0,
        }
    )


def create_initial_retrieve_state(
    *,
    runtime: RetrievePipeline,
    search_symbol: str | None,
    output_symbol: str,
    candidate_searcher: RetrieveCandidateSearcher | None,
    precomputed_candidates: dict[str, list[EFTSHit]] | None,
    shared_candidate_overhead: float,
    progress: Progress | None,
    phase_task: TaskID | None,
) -> RetrieveRunState:
    """Create initial mutable state for retrieve runnable stage execution."""
    return RetrieveRunState(
        runtime=runtime,
        search_symbol=search_symbol,
        output_symbol=output_symbol,
        candidate_searcher=candidate_searcher,
        precomputed_candidates=precomputed_candidates,
        shared_candidate_overhead=shared_candidate_overhead,
        progress=progress,
        phase_task=phase_task,
    )


class CandidateSearchStage(PipelineStageRunnable[RetrieveRunState]):
    """Ingress stage that materializes per-query EFTS candidates for downstream ranking."""

    name: str = Field(default="candidate_search")

    def _run(self, state: RetrieveRunState) -> RetrieveRunState:
        """Execute the candidate search stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.output_symbol,
            "Candidate search",
        )
        if state.precomputed_candidates is not None:
            state.candidates_by_query = state.precomputed_candidates
            state.stage_timings["candidate_search"] = max(
                0.0,
                state.shared_candidate_overhead,
            )
        else:
            t0 = perf_counter()
            state.candidates_by_query = (
                state.runtime._search_candidates_for_symbol(
                    search_symbol=state.search_symbol,
                    candidate_searcher=state.candidate_searcher,
                )
            )
            state.stage_timings["candidate_search"] = perf_counter() - t0
        state.candidate_count = sum(
            len(hits) for hits in state.candidates_by_query.values()
        )
        return state


class RankHitsStage(PipelineStageRunnable[RetrieveRunState]):
    """Selection stage that scores, prunes, and partitions candidates for hydration."""

    name: str = Field(default="rank_hits")

    def _run(self, state: RetrieveRunState) -> RetrieveRunState:
        """Execute the rank hits stage and return updated run state."""
        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.output_symbol,
            "Ranking",
        )
        t0 = perf_counter()
        ranked_hits = state.runtime._rank_hits(
            output_symbol=state.output_symbol,
            candidates_by_query=state.candidates_by_query,
        )
        ranked_before_prune = len(ranked_hits)
        ranked_hits = state.runtime._prune_ranked_hits(
            hits=ranked_hits,
        )
        state.stage_timings["ranking"] = perf_counter() - t0
        state.lexical_pruned = max(0, ranked_before_prune - len(ranked_hits))

        hydrate_limit = min(
            len(ranked_hits), state.runtime.config.hydrate_top_n
        )
        state.hydrated_input = ranked_hits[:hydrate_limit]
        state.passthrough_hits = ranked_hits[hydrate_limit:]
        state.ranked_hits = ranked_hits
        return state


class HydrateStage(PipelineStageRunnable[RetrieveRunState]):
    """Acquisition stage that resolves top-ranked hits into hydrated chunk snippets."""

    name: str = Field(default="hydrate_hits")

    def _run(self, state: RetrieveRunState) -> RetrieveRunState:
        """Execute the hydrate stage and return updated run state."""
        t0 = perf_counter()
        state.hydrated_hits = state.runtime._download_and_chunk_hits(
            output_symbol=state.output_symbol,
            hits=state.hydrated_input,
        )
        state.stage_timings["hydrate"] = perf_counter() - t0
        return state


class EmbeddingRerankStage(PipelineStageRunnable[RetrieveRunState]):
    """Semantic refinement stage that reorders hydrated snippets by embedding relevance."""

    name: str = Field(default="embedding_rerank")

    def _run(self, state: RetrieveRunState) -> RetrieveRunState:
        """Execute the embedding rerank stage and return updated run state."""
        t0 = perf_counter()
        state.reranked_hits = state.runtime._rerank_with_embeddings(
            hits=state.hydrated_hits,
        )
        state.stage_timings["embedding_rerank"] = perf_counter() - t0
        return state


class IndexStage(PipelineStageRunnable[RetrieveRunState]):
    """Persistence stage that indexes reranked chunks and composes final hit ordering."""

    name: str = Field(default="index_hits")

    def _run(self, state: RetrieveRunState) -> RetrieveRunState:
        """Execute the index stage and return updated run state."""
        state.market_context_metadata = state.runtime._market_context_metadata(
            output_symbol=state.output_symbol,
        )
        market_signals = state.runtime._market_signals_for_payload(
            state.market_context_metadata
        )
        t0 = perf_counter()
        state.indexed_hits = state.runtime._index_hits(
            output_symbol=state.output_symbol,
            hits=state.reranked_hits,
            market_signals=market_signals,
        )
        state.stage_timings["index"] = perf_counter() - t0
        state.final_hits = state.indexed_hits + state.passthrough_hits
        state.final_hits.sort(key=lambda hit: hit.score, reverse=True)
        return state


class WriteOutputsStage(PipelineStageRunnable[RetrieveRunState]):
    """Egress stage that emits ranked hit artifacts and final stage timing metadata."""

    name: str = Field(default="write_outputs")

    def _run(self, state: RetrieveRunState) -> RetrieveRunState:
        """Execute the write outputs stage and return updated run state."""
        state.metadata = {
            "queries_processed": len(state.runtime.config.queries),
            "candidate_hits": state.candidate_count,
            "ranked_hits": len(state.final_hits),
            "lexical_pruned_hits": state.lexical_pruned,
            "hydrated_hits": len(state.hydrated_input),
            "passthrough_hits": len(state.passthrough_hits),
            "chunk_snippets": sum(
                1 for hit in state.final_hits if hit.chunk_index is not None
            ),
            "top_k": state.runtime.config.top_k,
            "efts_candidates": state.runtime.config.efts_candidates,
        }
        if state.market_context_metadata:
            state.metadata["market_context"] = state.market_context_metadata
        state.metadata["stage_timings"] = {
            name: round(value, 6) for name, value in state.stage_timings.items()
        }

        state.runtime._update_phase(
            state.progress,
            state.phase_task,
            state.output_symbol,
            "Writing",
        )
        t0 = perf_counter()
        state.outputs = state.runtime._write_outputs(
            symbol=state.output_symbol,
            hits=state.final_hits,
            symbol_metadata=state.metadata,
        )
        state.stage_timings["write"] = perf_counter() - t0
        state.metadata["stage_timings"] = {
            name: round(value, 6) for name, value in state.stage_timings.items()
        }
        return state


def build_retrieve_stage_chain(
    pipeline: RetrievePipeline,
) -> Runnable[RetrieveRunState, RetrieveRunState]:
    """Build deterministic retrieve stage chain."""
    stages: tuple[PipelineStageRunnable[RetrieveRunState], ...] = (
        CandidateSearchStage(),
        RankHitsStage(),
        HydrateStage(),
        EmbeddingRerankStage(),
        IndexStage(),
        WriteOutputsStage(),
    )
    configured_stages = tuple(
        stage.configured(
            pipeline_type=pipeline.pipeline_type,
            run_id=str(pipeline.config.run_id),
        )
        for stage in stages
    )
    return pipeline.build_stage_chain(stages=configured_stages)
