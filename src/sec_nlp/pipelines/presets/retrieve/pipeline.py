# src/sec_nlp/pipelines/presets/retrieve/pipeline.py
"""Pipeline for EFTS-first retrieval and ranked hit exports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import ClassVar, Literal

from langchain_core.runnables import Runnable
from langchain_ollama.embeddings import OllamaEmbeddings
from pydantic import PrivateAttr
from qdrant_client import QdrantClient
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.market_analytics import build_market_context
from sec_nlp.core.types import (
    as_json_dict,
    coerce_result_json_dict,
    coerce_unknown_json_value,
)
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_output_context
from sec_nlp.types import JsonValue, ResultDict

from ..chat.bridge import ChatRetrievedChunk
from .bridge import RetrieveChatSeedBundle, RetrieveChatSeedChunk
from .config import RetrieveSettings
from .io import (
    RankedResultsPayload,
    write_ranked_results_csv,
    write_ranked_results_json,
    write_ranked_results_yaml,
)
from .models import RetrievalHit, RetrieveResult
from .run_stages import (
    RetrieveRunState,
    build_retrieve_stage_chain,
    create_initial_retrieve_state,
)
from .steps import (
    RetrieveCandidateSearcher,
    download_and_chunk_hits,
    index_retrieval_hits,
    prune_hits_by_query_terms,
    rank_retrieval_hits,
    rerank_with_embeddings,
    run_candidate_search,
)
from .steps.tokenization import DEFAULT_QUERY_STOPWORDS

_ORIGINAL_RUN_CANDIDATE_SEARCH = run_candidate_search


@dataclass(slots=True, frozen=True)
class _FlowChunkValues:
    """Normalized chunk fields shared across retrieve flow handoff types."""

    collection: str
    score: float
    symbol: str | None
    accession_number: str | None
    form_type: str | None
    filed_date: str | None
    source: str | None
    snippet: str


class RetrievePipeline(BasePipeline):
    """Retrieve filing candidates and emit ranked results."""

    pipeline_type: ClassVar[Literal["retrieve"]] = "retrieve"
    description: ClassVar[str] = (
        "Run EFTS candidate search and return ranked filing hits"
    )
    requires_llm: ClassVar[bool] = False

    config: RetrieveSettings
    _embedder: OllamaEmbeddings | None = PrivateAttr(default=None)
    _embedding_dim: int | None = PrivateAttr(default=None)
    _qdrant_client: QdrantClient | None = PrivateAttr(default=None)
    _embedder_init_attempts: int = PrivateAttr(default=0)
    _qdrant_init_attempts: int = PrivateAttr(default=0)
    _stage_chain: Runnable[RetrieveRunState, RetrieveRunState] | None = (
        PrivateAttr(default=None)
    )

    @classmethod
    def config_model(cls) -> type[RetrieveSettings]:
        return RetrieveSettings

    @classmethod
    def result_model(cls) -> type[RetrieveResult]:
        return RetrieveResult

    def _build_components(self) -> None:
        """Initialize reusable pipeline components for this run."""
        self._ensure_embedding_components()
        self._ensure_qdrant_client()
        self._stage_chain = build_retrieve_stage_chain(self)

    def run_for_flow(self) -> tuple[RetrieveResult, RetrieveChatSeedBundle]:
        """Run retrieve and return an in-memory handoff bundle for chat."""
        result, bundle, _ = self._run_internal(
            include_bridge=True,
            include_prebuilt_chunks=False,
        )
        if bundle is not None:
            return result, bundle
        return result, self._empty_seed_bundle()

    def run_for_flow_with_chunks(
        self,
    ) -> tuple[
        RetrieveResult,
        RetrieveChatSeedBundle,
        tuple[ChatRetrievedChunk, ...],
    ]:
        """Run retrieve and return flow bundle plus prebuilt chat chunks."""
        result, bundle, chunks = self._run_internal(
            include_bridge=True,
            include_prebuilt_chunks=True,
        )
        if bundle is None:
            bundle = self._empty_seed_bundle()
        if chunks is None:
            chunks = ()
        return result, bundle, chunks

    def _ensure_embedding_components(self) -> None:
        """Ensure embedding components are initialized before use."""
        if not (
            self.config.rerank_with_embeddings or self.config.index_results
        ):
            return
        if self._embedder is not None and self._embedding_dim is not None:
            return
        if self._embedder_init_attempts >= 2:
            return

        self._embedder_init_attempts += 1
        try:
            self._embedder, self._embedding_dim = (
                self.config.vdb.setup_embedding_model()
            )
        except Exception as exc:
            if self._embedder_init_attempts == 1:
                logger.warning(
                    "Retrieve embedding model prewarm failed; retrying once during run: %s",
                    exc,
                )
            else:
                logger.warning(
                    "Retrieve embedding model setup failed; skipping embedding-dependent stages for this run: %s",
                    exc,
                )
            self._embedder = None
            self._embedding_dim = None

    def _ensure_qdrant_client(self) -> None:
        """Ensure a Qdrant client is available for vector operations."""
        if not self.config.index_results:
            return
        if self._qdrant_client is not None:
            return
        if self._qdrant_init_attempts >= 2:
            return

        self._qdrant_init_attempts += 1
        try:
            self._qdrant_client = self.config.vdb.setup_qdrant_client()
        except Exception as exc:
            if self._qdrant_init_attempts == 1:
                logger.warning(
                    "Retrieve Qdrant preconnect failed; retrying once during run: %s",
                    exc,
                )
            else:
                logger.warning(
                    "Retrieve Qdrant setup failed; skipping index stage for this run: %s",
                    exc,
                )
            self._qdrant_client = None

    def run(self) -> RetrieveResult:
        result, _, _ = self._run_internal(
            include_bridge=False,
            include_prebuilt_chunks=False,
        )
        return result

    def _search_candidates_for_symbol(
        self,
        *,
        search_symbol: str | None,
        candidate_searcher: RetrieveCandidateSearcher | None,
    ) -> dict[str, list[EFTSHit]]:
        """Run candidate search for a symbol and return scoped EFTS hits."""
        if (
            candidate_searcher is not None
            and run_candidate_search is _ORIGINAL_RUN_CANDIDATE_SEARCH
        ):
            return candidate_searcher.search(
                symbol=search_symbol,
                queries=self.config.queries,
            )
        # Preserve monkeypatch compatibility for unit tests.
        return run_candidate_search(
            symbol=search_symbol,
            queries=self.config.queries,
            settings=self.config,
        )

    def _rank_hits(
        self,
        *,
        output_symbol: str,
        candidates_by_query: dict[str, list[EFTSHit]],
    ) -> list[RetrievalHit]:
        """Rank candidate hits by relevance and configured ranking signals."""
        return rank_retrieval_hits(
            symbol=output_symbol,
            candidates_by_query=candidates_by_query,
            top_k=self.config.top_k,
        )

    def _prune_ranked_hits(
        self,
        *,
        hits: list[RetrievalHit],
    ) -> list[RetrievalHit]:
        """Prune ranked hits using lexical overlap and hydration gates."""
        return prune_hits_by_query_terms(
            hits=hits,
            min_hits=self.config.query_term_min_hits,
            min_ratio=self.config.query_term_min_ratio,
            stopwords=(
                DEFAULT_QUERY_STOPWORDS
                if self.config.stopword_aware_lexical
                else None
            ),
        )

    def _download_and_chunk_hits(
        self,
        *,
        output_symbol: str,
        hits: list[RetrievalHit],
    ) -> list[RetrievalHit]:
        """Download missing filings and extract chunked snippets for hits."""
        return download_and_chunk_hits(
            symbol=output_symbol,
            hits=hits,
            settings=self.config,
        )

    def _rerank_with_embeddings(
        self,
        *,
        hits: list[RetrievalHit],
    ) -> list[RetrievalHit]:
        """Apply embedding-based reranking to hydrated chunk candidates."""
        self._ensure_embedding_components()
        return rerank_with_embeddings(
            hits=hits,
            settings=self.config,
            embedder=self._embedder,
            allow_setup_fallback=False,
        )

    def _index_hits(
        self,
        *,
        output_symbol: str,
        hits: list[RetrievalHit],
        market_signals: dict[str, JsonValue] | None,
    ) -> list[RetrievalHit]:
        """Index selected hits into the configured vector store."""
        self._ensure_qdrant_client()
        return index_retrieval_hits(
            symbol=output_symbol,
            hits=hits,
            settings=self.config,
            qdrant_client=self._qdrant_client,
            embedder=self._embedder,
            embedding_dim=self._embedding_dim,
            market_signals=market_signals,
            allow_setup_fallback=False,
        )

    def _run_internal(
        self,
        *,
        include_bridge: bool,
        include_prebuilt_chunks: bool,
    ) -> tuple[
        RetrieveResult,
        RetrieveChatSeedBundle | None,
        tuple[ChatRetrievedChunk, ...] | None,
    ]:
        """Execute the main pipeline workflow and return a result object."""
        try:
            self.config.setup_paths()
            if not self.config.queries:
                raise ValueError(
                    "Retrieve pipeline requires at least one --queries value"
                )

            outputs: list[Path] = []
            metadata: ResultDict = {}
            total_queries = 0
            total_hits = 0
            bridge_chunks: list[RetrieveChatSeedChunk] = []
            prebuilt_chunks: list[ChatRetrievedChunk] = []
            symbol_targets: list[tuple[str | None, str]]
            if self.config.symbols:
                symbol_targets = [
                    (symbol.upper(), symbol.upper())
                    for symbol in self.config.symbols
                ]
            else:
                symbol_targets = [(None, "ALL")]

            console = get_rich_console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(complete_style="green", finished_style="bold green"),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TextColumn("[dim]-[/dim]"),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            ) as progress:
                overall_task = progress.add_task(
                    "Processing symbols",
                    total=len(symbol_targets),
                )
                phase_task = progress.add_task("", total=None, visible=False)
                aggregate_stage_timings: dict[str, float] = {
                    "candidate_search": 0.0,
                    "ranking": 0.0,
                    "hydrate": 0.0,
                    "embedding_rerank": 0.0,
                    "index": 0.0,
                    "write": 0.0,
                }
                precomputed_candidates_by_symbol: dict[
                    str, dict[str, list[EFTSHit]]
                ] = {}
                shared_candidate_overhead = 0.0

                if run_candidate_search is _ORIGINAL_RUN_CANDIDATE_SEARCH:
                    with RetrieveCandidateSearcher(
                        self.config
                    ) as candidate_searcher:
                        if len(symbol_targets) > 1 and all(
                            search_symbol is not None
                            for search_symbol, _ in symbol_targets
                        ):
                            t0 = perf_counter()
                            precomputed_candidates_by_symbol = (
                                candidate_searcher.search_many(
                                    symbols=[
                                        search_symbol
                                        for search_symbol, _ in symbol_targets
                                    ],
                                    queries=self.config.queries,
                                )
                            )
                            prefetch_elapsed = perf_counter() - t0
                            if symbol_targets:
                                shared_candidate_overhead = (
                                    prefetch_elapsed / len(symbol_targets)
                                )

                        for search_symbol, output_symbol in symbol_targets:
                            progress.update(
                                overall_task,
                                description=f"Processing {output_symbol}",
                            )

                            (
                                symbol_outputs,
                                symbol_meta,
                                symbol_stage_timings,
                                queries_processed,
                                hits_count,
                                symbol_hits,
                            ) = self._process_symbol(
                                search_symbol=search_symbol,
                                output_symbol=output_symbol,
                                candidate_searcher=candidate_searcher,
                                precomputed_candidates=(
                                    precomputed_candidates_by_symbol.get(
                                        output_symbol
                                    )
                                ),
                                shared_candidate_overhead=shared_candidate_overhead,
                                progress=progress,
                                phase_task=phase_task,
                            )
                            for name, value in symbol_stage_timings.items():
                                aggregate_stage_timings[name] = (
                                    aggregate_stage_timings.get(name, 0.0)
                                    + value
                                )

                            outputs.extend(symbol_outputs)
                            metadata[output_symbol] = symbol_meta
                            total_queries += queries_processed
                            total_hits += hits_count
                            if include_prebuilt_chunks:
                                prebuilt_chunks.extend(
                                    self._hits_to_chat_chunks(symbol_hits)
                                )
                            elif include_bridge:
                                bridge_chunks.extend(
                                    self._hits_to_seed_chunks(symbol_hits)
                                )

                            progress.update(phase_task, visible=False)
                            progress.advance(overall_task)
                else:
                    for search_symbol, output_symbol in symbol_targets:
                        progress.update(
                            overall_task,
                            description=f"Processing {output_symbol}",
                        )

                        (
                            symbol_outputs,
                            symbol_meta,
                            symbol_stage_timings,
                            queries_processed,
                            hits_count,
                            symbol_hits,
                        ) = self._process_symbol(
                            search_symbol=search_symbol,
                            output_symbol=output_symbol,
                            candidate_searcher=None,
                            progress=progress,
                            phase_task=phase_task,
                        )
                        for name, value in symbol_stage_timings.items():
                            aggregate_stage_timings[name] = (
                                aggregate_stage_timings.get(name, 0.0) + value
                            )

                        outputs.extend(symbol_outputs)
                        metadata[output_symbol] = symbol_meta
                        total_queries += queries_processed
                        total_hits += hits_count
                        if include_prebuilt_chunks:
                            prebuilt_chunks.extend(
                                self._hits_to_chat_chunks(symbol_hits)
                            )
                        elif include_bridge:
                            bridge_chunks.extend(
                                self._hits_to_seed_chunks(symbol_hits)
                            )

                        progress.update(phase_task, visible=False)
                        progress.advance(overall_task)

            metadata["stage_timings"] = {
                name: round(value, 6)
                for name, value in aggregate_stage_timings.items()
            }

            self.config.complete_run(
                success=True,
                metadata=coerce_result_json_dict(metadata),
            )
            result = RetrieveResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                symbols_processed=len(symbol_targets),
                queries_processed=total_queries,
                hits_returned=total_hits,
            )
            bundle = (
                RetrieveChatSeedBundle(
                    upstream_pipeline="retrieve",
                    upstream_run_id=str(self.config.run_id),
                    upstream_short_id=self.config.short_id
                    if self.config.short_id > 0
                    else None,
                    symbols=[
                        output_symbol
                        for _, output_symbol in symbol_targets
                        if output_symbol != "ALL"
                    ],
                    queries=list(self.config.queries),
                    chunks=([] if include_prebuilt_chunks else bridge_chunks),
                )
                if include_bridge
                else None
            )
            return (
                result,
                bundle,
                (tuple(prebuilt_chunks) if include_prebuilt_chunks else None),
            )
        except Exception as exc:
            logger.exception("Retrieve pipeline failed")
            self.config.complete_run(success=False)
            return (
                RetrieveResult(
                    success=False,
                    error=f"{type(exc).__name__}: {exc}",
                ),
                self._empty_seed_bundle() if include_bridge else None,
                () if include_prebuilt_chunks else None,
            )

    def _empty_seed_bundle(self) -> RetrieveChatSeedBundle:
        """Return an empty handoff bundle for unsuccessful retrieve runs."""
        return RetrieveChatSeedBundle(
            upstream_pipeline="retrieve",
            upstream_run_id=str(self.config.run_id),
            upstream_short_id=self.config.short_id
            if self.config.short_id > 0
            else None,
            symbols=[],
            queries=list(self.config.queries),
            chunks=[],
        )

    def _hits_to_seed_chunks(
        self, hits: list[RetrievalHit]
    ) -> list[RetrieveChatSeedChunk]:
        """Convert ranked retrieval hits into compact `FlowSeedChunk` payloads.

        This is used when downstream chat will reconstruct retrieval chunks from
        seed metadata instead of consuming prebuilt chat chunks.
        """
        return [
            RetrieveChatSeedChunk(
                collection=chunk.collection,
                symbol=chunk.symbol,
                accession_number=chunk.accession_number,
                form_type=chunk.form_type,
                filed_date=chunk.filed_date,
                source=chunk.source,
                score=chunk.score,
                snippet=chunk.snippet,
            )
            for chunk in self._flow_chunk_values(hits)
        ]

    def _hits_to_chat_chunks(
        self,
        hits: list[RetrievalHit],
    ) -> list[ChatRetrievedChunk]:
        """Convert ranked hits into chat-ready chunk dataclasses.

        The output mirrors chat's native chunk shape, enabling direct in-memory
        handoff with no additional validation/remapping in flow runner.
        """
        return [
            ChatRetrievedChunk(
                collection=chunk.collection,
                score=chunk.score,
                symbol=chunk.symbol,
                accession_number=chunk.accession_number,
                form_type=chunk.form_type,
                filed_date=chunk.filed_date,
                source=chunk.source,
                snippet=chunk.snippet,
                vector=None,
            )
            for chunk in self._flow_chunk_values(hits)
        ]

    def _flow_chunk_values(
        self, hits: list[RetrievalHit]
    ) -> list[_FlowChunkValues]:
        """Normalize retrieval hits into shared chunk fields for flow handoff.

        Empty snippets are dropped here so both seed and chat chunk builders
        operate on identical, citation-eligible source values.
        """
        collection_name = self.config.vdb.collection_name or "retrieve"
        chunks: list[_FlowChunkValues] = []
        for hit in hits:
            snippet = (hit.snippet or "").strip()
            if not snippet:
                continue
            chunks.append(
                _FlowChunkValues(
                    collection=collection_name,
                    score=float(hit.score),
                    symbol=hit.symbol or None,
                    accession_number=hit.accession_number or None,
                    form_type=hit.form_type or None,
                    filed_date=hit.filed_date or None,
                    source=hit.edgar_url or None,
                    snippet=snippet,
                )
            )
        return chunks

    def _process_symbol(
        self,
        *,
        search_symbol: str | None,
        output_symbol: str,
        candidate_searcher: RetrieveCandidateSearcher | None,
        precomputed_candidates: dict[str, list[EFTSHit]] | None = None,
        shared_candidate_overhead: float = 0.0,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[
        list[Path],
        dict[str, JsonValue],
        dict[str, float],
        int,
        int,
        list[RetrievalHit],
    ]:
        """Run retrieval for one symbol and return symbol-level output metadata."""
        stage_chain = self._stage_chain
        if stage_chain is None:
            stage_chain = build_retrieve_stage_chain(self)
            self._stage_chain = stage_chain
        state = create_initial_retrieve_state(
            runtime=self,
            search_symbol=search_symbol,
            output_symbol=output_symbol,
            candidate_searcher=candidate_searcher,
            precomputed_candidates=precomputed_candidates,
            shared_candidate_overhead=shared_candidate_overhead,
            progress=progress,
            phase_task=phase_task,
        )
        final_state = self.run_stage_chain(
            initial_state=state,
            stage_chain=stage_chain,
        )
        return (
            final_state.outputs,
            final_state.metadata,
            final_state.stage_timings,
            len(self.config.queries),
            len(final_state.final_hits),
            final_state.final_hits,
        )

    def _market_context_metadata(
        self,
        *,
        output_symbol: str,
    ) -> dict[str, JsonValue]:
        """Build market context metadata attached to retrieve outputs."""
        if not self.config.include_market_signals:
            return {}
        if output_symbol == "ALL":
            return {}

        start_date, end_date = self.config.date_range
        try:
            bundle = build_market_context(
                symbols=[output_symbol],
                start_date=start_date,
                end_date=end_date,
                benchmark="SPY",
            )
        except Exception as exc:
            logger.warning(
                "Failed to compute market signals for %s: %s",
                output_symbol,
                exc,
            )
            return {}

        payload = as_json_dict(
            bundle.model_dump(mode="json", exclude_none=True)
        )
        return payload or {}

    @staticmethod
    def _market_signals_for_payload(
        market_context: dict[str, JsonValue],
    ) -> dict[str, JsonValue] | None:
        """Build compact market signal payloads for vector indexing."""
        metrics_raw = market_context.get("metrics")
        if not isinstance(metrics_raw, list) or not metrics_raw:
            return None
        metric = metrics_raw[0]
        if not isinstance(metric, dict):
            return None
        payload: dict[str, JsonValue] = {
            "window": market_context.get("window"),
            "benchmark": market_context.get("benchmark"),
        }
        for key, value in metric.items():
            if isinstance(key, str):
                normalized = coerce_unknown_json_value(value)
                if normalized is not None:
                    payload[key] = normalized
        return payload

    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
    ) -> None:
        """Update progress state and current pipeline phase metadata."""
        if progress is None or phase_task is None:
            return

        progress.reset(
            phase_task,
            start=True,
            description=f"  - {symbol}: {phase}",
            visible=True,
            completed=0,
        )
        progress.update(
            phase_task,
            total=None,
            completed=0,
        )

    def _write_outputs(
        self,
        *,
        symbol: str,
        hits: list[RetrievalHit],
        symbol_metadata: dict[str, JsonValue] | None = None,
    ) -> list[Path]:
        """Write pipeline outputs and return generated artifact paths."""
        symbol_out = self.config.get_symbol_output_dir(symbol)
        output_context = build_run_output_context(
            symbol=symbol,
            suffix="retrieve",
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        base_stem = output_context.base_stem
        run_header = output_context.run_header
        run_short_id = output_context.run_short_id

        metadata: dict[str, JsonValue] = {
            "forms": self.config.forms or ["10-K", "10-Q"],
            "sections": self.config.sections,
            "top_k": self.config.top_k,
            "efts_candidates": self.config.efts_candidates,
            "download_missing": self.config.download_missing,
            "rerank_with_embeddings": self.config.rerank_with_embeddings,
            "embedding_weight": self.config.embedding_weight,
            "index_results": self.config.index_results,
            "embedding_cache": self.config.embedding_cache,
            "embedding_cache_file": str(self.config.embedding_cache_file),
            "embedding_cache_max_entries": self.config.embedding_cache_max_entries,
            "chunk_size": self.config.chunk_size,
            "chunk_overlap": self.config.chunk_overlap,
            "max_chunks_per_accession": self.config.max_chunks_per_accession,
        }
        if symbol_metadata:
            metadata.update(symbol_metadata)

        payload = RankedResultsPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            queries=self.config.queries,
            hits=hits,
            metadata=metadata,
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            csv_path = symbol_out / f"{base_stem}_ranked.csv"
            write_ranked_results_csv(
                csv_path,
                hits,
                header_fields=run_header,
            )
            outputs.append(csv_path)

        if self.config.output_format in ("json", "all"):
            json_path = symbol_out / f"{base_stem}_summary.json"
            write_ranked_results_json(json_path, payload)
            outputs.append(json_path)

        if self.config.output_format in ("yaml", "all"):
            yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            write_ranked_results_yaml(yaml_path, payload)
            outputs.append(yaml_path)

        return outputs
