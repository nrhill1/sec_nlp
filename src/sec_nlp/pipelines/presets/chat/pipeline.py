# src/sec_nlp/pipelines/presets/chat/pipeline.py
"""Pipeline for RAG chat over indexed filing chunks."""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import perf_counter
from typing import ClassVar, Literal, Protocol

import numpy as np
from langchain_core.runnables import Runnable
from langchain_ollama.embeddings import OllamaEmbeddings
from pydantic import PrivateAttr
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Condition,
    FieldCondition,
    Filter,
    MatchValue,
)
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

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.market_analytics import build_market_context
from sec_nlp.core.news.client import (
    NewswatchExtensionError,
    create_news_retriever,
)
from sec_nlp.core.types import as_json_dict, coerce_result_json_dict
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import build_run_output_context
from sec_nlp.types import JsonValue, ResultDict

from ..retrieve import RetrievePipeline, RetrieveSettings
from .bridge import ChatRetrievedChunk, ChatSeedBundle
from .config import ChatSettings
from .io import (
    write_chat_transcript_csv,
    write_chat_transcript_json,
    write_chat_transcript_yaml,
)
from .models import ChatCitation, ChatResult, ChatTranscriptPayload, ChatTurn
from .run_stages import (
    ChatRunState,
    build_chat_stage_chain,
    create_initial_chat_state,
)

_CITATION_RE = re.compile(r"\[(C\d+)\]")
_WHITESPACE_RE = re.compile(r"\s+")
_FILTER_FETCH_MULTIPLIER = 4
_FILTER_FETCH_MAX_POINTS = 200
_QUESTION_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9/-]{2,}")
_STOPWORDS = {
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "how",
    "from",
    "into",
    "that",
    "this",
    "with",
    "without",
    "about",
    "across",
    "between",
    "recent",
    "changes",
    "change",
    "risk",
    "risks",
    "opportunity",
    "opportunities",
    "material",
    "company",
    "filing",
    "filings",
}


_RetrievedChunk = ChatRetrievedChunk


class _SnippetEmbedder(Protocol):
    """Internal embedder adapter for snippet-level reranking."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class ChatPipeline(BasePipeline):
    """Answer questions against indexed SEC filing chunks."""

    pipeline_type: ClassVar[Literal["chat"]] = "chat"
    description: ClassVar[str] = (
        "Interactive retrieval-augmented Q&A over indexed filings"
    )
    requires_llm: ClassVar[bool] = True

    config: ChatSettings
    _embedder: OllamaEmbeddings | None = PrivateAttr(default=None)
    _embedding_dim: int | None = PrivateAttr(default=None)
    _qdrant_client: QdrantClient | None = PrivateAttr(default=None)
    _last_search_timings: dict[str, float] = PrivateAttr(
        default_factory=lambda: {"vector_search": 0.0, "rerank": 0.0}
    )
    _last_answer_timings: dict[str, float] = PrivateAttr(
        default_factory=lambda: {"prompt_build": 0.0, "llm_generate": 0.0}
    )
    _last_llm_max_new_tokens: int | None = PrivateAttr(default=None)
    _last_context_token_budget: int | None = PrivateAttr(default=None)
    _stage_chain: Runnable[ChatRunState, ChatRunState] | None = PrivateAttr(
        default=None
    )

    @classmethod
    def config_model(cls) -> type[ChatSettings]:
        return ChatSettings

    @classmethod
    def result_model(cls) -> type[ChatResult]:
        return ChatResult

    def _build_components(self) -> None:
        """Initialize reusable pipeline components for this run."""
        use_seed_only = (
            self.config.seed_context is not None
            or len(self.config.seed_chunks) > 0
        ) and self.config.rerank_mode != "mmr"
        if not use_seed_only:
            try:
                self._embedder, self._embedding_dim = (
                    self.config.vdb.setup_embedding_model()
                )
            except Exception as exc:
                logger.warning(
                    "Chat embedding model prewarm failed; falling back to lazy init: %s",
                    exc,
                )
                self._embedder = None
                self._embedding_dim = None

        if self.config.seed_context is not None or self.config.seed_chunks:
            self._qdrant_client = None
        else:
            try:
                self._qdrant_client = self.config.vdb.setup_qdrant_client()
            except Exception as exc:
                logger.warning(
                    "Chat Qdrant preconnect failed; falling back to lazy init: %s",
                    exc,
                )
                self._qdrant_client = None

        self._stage_chain = build_chat_stage_chain(self)

    def _effective_end_date(self) -> date:
        """Resolve the effective end date for the current run."""
        return self.config.end_date or date.today()

    def _chunk_identity(self, chunk: _RetrievedChunk) -> tuple[str, str, str]:
        """Build a stable identity key for a retrieved chunk."""
        return (
            chunk.collection.casefold(),
            (chunk.accession_number or "").casefold(),
            self._snippet_fingerprint(chunk.snippet),
        )

    def _base_metadata(
        self,
        *,
        external_context: str,
        external_metadata: dict[str, JsonValue],
    ) -> ResultDict:
        """Build base run metadata for chat result outputs."""
        metadata: ResultDict = {
            "collections": list(self.config.collections),
            "forms_filter": self.config.forms or [],
            "filed_after": (
                self.config.start_date.isoformat()
                if self.config.start_date
                else None
            ),
            "filed_before": (
                self.config.end_date.isoformat()
                if self.config.end_date
                else None
            ),
            "rerank_mode": self.config.rerank_mode,
            "prefetch_retrieve": self.config.prefetch_retrieve,
            "include_market_context": self.config.include_market_context,
            "include_news_context": self.config.include_news_context,
            "external_context": external_context,
            **external_metadata,
        }
        return metadata

    def _symbol_coverage_metadata(
        self,
        citations: list[ChatCitation],
    ) -> dict[str, JsonValue]:
        """Summarize symbol coverage statistics for selected context chunks."""
        requested = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        requested = list(dict.fromkeys(requested))
        retrieved = [
            citation.symbol.upper()
            for citation in citations
            if citation.symbol and citation.symbol.strip()
        ]
        retrieved = list(dict.fromkeys(retrieved))
        missing = [symbol for symbol in requested if symbol not in retrieved]
        return {
            "requested_symbols": requested,
            "retrieved_symbols": retrieved,
            "missing_symbols": missing,
        }

    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        phase: str,
    ) -> None:
        """Update progress state and current pipeline phase metadata."""
        if progress is None or phase_task is None:
            return

        progress.reset(
            phase_task,
            start=True,
            description=f"  - {phase}",
            visible=True,
            completed=0,
        )
        progress.update(
            phase_task,
            total=None,
            completed=0,
        )

    def run(self) -> ChatResult:
        return self.run_for_flow(
            seed_context=self.config.seed_context,
            seed_chunks=self.config.seed_chunks,
        )

    def run_for_flow(
        self,
        *,
        seed_context: ChatSeedBundle | None = None,
        seed_chunks: tuple[ChatRetrievedChunk, ...] = (),
    ) -> ChatResult:
        """Run chat with optional in-memory seeded context overrides."""
        try:
            self.config.setup_paths()
            question = (self.config.question or "").strip()
            if not question:
                raise ValueError(
                    "Chat pipeline requires a question (--question or --query)."
                )

            self._last_search_timings = {"vector_search": 0.0, "rerank": 0.0}
            self._last_answer_timings = {
                "prompt_build": 0.0,
                "llm_generate": 0.0,
            }
            self._last_llm_max_new_tokens = None
            self._last_context_token_budget = None
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
                    "Chat pipeline",
                    total=5,
                )
                phase_task = progress.add_task("", total=None, visible=False)
                stage_chain = self._stage_chain
                if stage_chain is None:
                    stage_chain = build_chat_stage_chain(self)
                    self._stage_chain = stage_chain
                stage_state = create_initial_chat_state(
                    runtime=self,
                    question=question,
                    progress=progress,
                    overall_task=overall_task,
                    phase_task=phase_task,
                    seed_context=seed_context,
                    seed_chunks=seed_chunks,
                )
                stage_state = self.run_stage_chain(
                    initial_state=stage_state,
                    stage_chain=stage_chain,
                )
                progress.update(phase_task, visible=False)

            metadata = self._base_metadata(
                external_context=stage_state.external_context,
                external_metadata=stage_state.external_metadata,
            )
            metadata.update(
                self._seed_context_metadata(
                    seed=stage_state.seed_context,
                    seed_chunk_count=len(stage_state.seed_chunks),
                )
            )
            metadata.update(
                {
                    "hits_retrieved": len(stage_state.citations),
                    "citations_returned": len(stage_state.used_citation_ids),
                    "strict_citations": self.config.strict_citations,
                    "symbol_scope": self.config.symbols,
                    "llm_model_name": self.config.llm.model_name,
                    "llm_max_new_tokens_configured": self.config.llm.max_new_tokens,
                    "llm_max_new_tokens_effective": (
                        self._last_llm_max_new_tokens
                        if self._last_llm_max_new_tokens is not None
                        else self.config.llm.max_new_tokens
                    ),
                    "generation_token_cap": self.config.generation_token_cap,
                    "context_token_budget_configured": self.config.context_token_budget,
                    "context_token_budget_effective": (
                        self._last_context_token_budget
                        if self._last_context_token_budget is not None
                        else self._effective_context_token_budget(
                            len(stage_state.citations)
                        )
                    ),
                    "stage_timings": {
                        name: round(value, 6)
                        for name, value in stage_state.stage_timings.items()
                    },
                }
            )

            self.config.complete_run(
                success=True,
                metadata=coerce_result_json_dict(metadata),
            )
            return ChatResult(
                success=True,
                outputs=stage_state.outputs,
                metadata=metadata,
                turns_processed=len(stage_state.turns),
                hits_retrieved=len(stage_state.citations),
                citations_returned=len(stage_state.used_citation_ids),
                answer=stage_state.answer,
                citation_ids=stage_state.used_citation_ids,
            )
        except Exception as exc:
            logger.exception("Chat pipeline failed")
            self.config.complete_run(success=False)
            return ChatResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _search_collections(
        self,
        question: str,
        *,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> list[_RetrievedChunk]:
        """Search configured vector collections for relevant context chunks."""
        search_timings: dict[str, float] = {
            "vector_search": 0.0,
            "rerank": 0.0,
        }
        t_vector_start = perf_counter()
        self._update_phase(progress, phase_task, "Loading embedding model")
        embedder = self._embedder
        if embedder is None:
            embedder, embedding_dim = self.config.vdb.setup_embedding_model()
            self._embedder = embedder
            self._embedding_dim = embedding_dim
        query_vector = list(embedder.embed_query(question))

        self._update_phase(progress, phase_task, "Connecting to Qdrant")
        qdrant = self._qdrant_client
        if qdrant is None:
            qdrant = self.config.vdb.setup_qdrant_client()
            self._qdrant_client = qdrant

        symbols = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        allowed_forms = self._normalized_form_filters(self.config.forms)
        filed_after = self.config.start_date
        filed_before = self.config.end_date
        apply_post_filters = bool(
            allowed_forms
            or filed_after
            or filed_before
            or self.config.rerank_mode == "mmr"
        )
        query_limit = max(self.config.top_k, self.config.rerank_candidates)
        if apply_post_filters:
            query_limit = min(
                _FILTER_FETCH_MAX_POINTS,
                max(
                    query_limit,
                    self.config.top_k * _FILTER_FETCH_MULTIPLIER,
                ),
            )

        combined: list[_RetrievedChunk] = []
        collections = [
            collection.strip()
            for collection in self.config.collections
            if collection.strip()
        ]
        collection_task: TaskID | None = None
        if progress is not None:
            collection_task = progress.add_task(
                "  - Collections",
                total=max(len(collections), 1),
            )

        for idx, name in enumerate(collections, start=1):
            try:
                if progress is not None and collection_task is not None:
                    progress.update(
                        collection_task,
                        description=(
                            f"  - Collection {idx}/{len(collections)}: {name}"
                        ),
                    )
                if not qdrant.collection_exists(name):
                    self._maybe_prefetch_collection(
                        qdrant=qdrant,
                        collection=name,
                        symbols=symbols,
                        question=question,
                    )
                if not qdrant.collection_exists(name):
                    logger.debug("Skipping unavailable collection '%s'", name)
                    continue

                if (
                    self.config.prefetch_retrieve
                    and self.config.prefetch_min_points > 0
                ):
                    point_count = self._collection_points(
                        qdrant=qdrant,
                        collection=name,
                    )
                    if (
                        point_count is not None
                        and point_count < self.config.prefetch_min_points
                    ):
                        self._maybe_prefetch_collection(
                            qdrant=qdrant,
                            collection=name,
                            symbols=symbols,
                            question=question,
                        )
                    point_count = self._collection_points(
                        qdrant=qdrant,
                        collection=name,
                    )
                    if (
                        point_count is not None
                        and point_count < self.config.prefetch_min_points
                    ):
                        logger.debug(
                            "Collection '%s' remains sparse (%d points < %d)",
                            name,
                            point_count,
                            self.config.prefetch_min_points,
                        )
                if not qdrant.collection_exists(name):
                    continue

                query_filter = self._build_symbol_filter(symbols)
                response = qdrant.query_points(
                    collection_name=name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=query_limit,
                    with_payload=True,
                    with_vectors=self.config.rerank_mode == "mmr",
                    score_threshold=self.config.min_score,
                )
                points = getattr(response, "points", [])
                for point in points:
                    chunk = self._point_to_chunk(collection=name, point=point)
                    if chunk is None:
                        continue
                    if not self._chunk_matches_filters(
                        chunk,
                        forms=allowed_forms,
                        filed_after=filed_after,
                        filed_before=filed_before,
                    ):
                        continue
                    combined.append(chunk)
            finally:
                if progress is not None and collection_task is not None:
                    progress.advance(collection_task)

        if progress is not None and collection_task is not None:
            if not collections:
                progress.advance(collection_task)
            progress.update(collection_task, visible=False)

        combined.sort(key=lambda chunk: chunk.score, reverse=True)
        deduped: list[_RetrievedChunk] = []
        seen: set[tuple[str, str, str]] = set()
        dedupe_limit = max(self.config.top_k, self.config.rerank_candidates)

        for chunk in combined:
            key = self._chunk_identity(chunk)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(chunk)
            if len(deduped) >= dedupe_limit:
                break
        search_timings["vector_search"] = perf_counter() - t_vector_start

        if self.config.rerank_mode == "mmr":
            t_rerank_start = perf_counter()
            reranked = self._rerank_chunks_mmr(
                chunks=deduped,
                query_vector=query_vector,
                embedder=embedder,
            )
            search_timings["rerank"] = perf_counter() - t_rerank_start
            self._last_search_timings = search_timings
            return self._select_context_chunks(reranked)

        self._last_search_timings = search_timings
        return self._select_context_chunks(deduped)

    def _search_seed_context(
        self,
        *,
        question: str,
        seed: ChatSeedBundle | None,
        seed_chunks: tuple[ChatRetrievedChunk, ...],
    ) -> list[_RetrievedChunk]:
        """Search provided seed context before falling back to vector search."""
        if seed is None and not seed_chunks:
            self._last_search_timings = {"vector_search": 0.0, "rerank": 0.0}
            return []

        t_vector_start = perf_counter()
        symbols = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        allowed_forms = self._normalized_form_filters(self.config.forms)
        filed_after = self.config.start_date
        filed_before = self.config.end_date

        seeded_chunks: list[_RetrievedChunk] = []
        if seed_chunks:
            for chunk in seed_chunks:
                snippet = chunk.snippet.strip()
                if not snippet:
                    continue
                if symbols and (chunk.symbol or "").upper() not in symbols:
                    continue
                if not self._chunk_matches_filters(
                    chunk,
                    forms=allowed_forms,
                    filed_after=filed_after,
                    filed_before=filed_before,
                ):
                    continue
                seeded_chunks.append(chunk)
        elif seed is not None:
            for item in seed.chunks:
                snippet = item.snippet.strip()
                if not snippet:
                    continue
                symbol = (
                    item.symbol.strip().upper()
                    if isinstance(item.symbol, str) and item.symbol.strip()
                    else None
                )
                chunk = _RetrievedChunk(
                    collection=item.collection.strip() or "retrieve",
                    score=float(item.score),
                    symbol=symbol,
                    accession_number=item.accession_number,
                    form_type=item.form_type,
                    filed_date=item.filed_date,
                    source=item.source,
                    snippet=snippet,
                    vector=None,
                )
                if symbols and (chunk.symbol or "").upper() not in symbols:
                    continue
                if not self._chunk_matches_filters(
                    chunk,
                    forms=allowed_forms,
                    filed_after=filed_after,
                    filed_before=filed_before,
                ):
                    continue
                seeded_chunks.append(chunk)

        seeded_chunks.sort(key=lambda current: current.score, reverse=True)
        deduped: list[_RetrievedChunk] = []
        seen: set[tuple[str, str, str]] = set()
        dedupe_limit = max(self.config.top_k, self.config.rerank_candidates)
        for chunk in seeded_chunks:
            key = self._chunk_identity(chunk)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(chunk)
            if len(deduped) >= dedupe_limit:
                break

        search_timings: dict[str, float] = {
            "vector_search": perf_counter() - t_vector_start,
            "rerank": 0.0,
        }
        if self.config.rerank_mode == "mmr" and deduped:
            t_rerank_start = perf_counter()
            embedder = self._embedder
            if embedder is None:
                embedder, embedding_dim = (
                    self.config.vdb.setup_embedding_model()
                )
                self._embedder = embedder
                self._embedding_dim = embedding_dim
            query_vector = list(embedder.embed_query(question))
            reranked = self._rerank_chunks_mmr(
                chunks=deduped,
                query_vector=query_vector,
                embedder=embedder,
            )
            search_timings["rerank"] = perf_counter() - t_rerank_start
            self._last_search_timings = search_timings
            return self._select_context_chunks(reranked)

        self._last_search_timings = search_timings
        return self._select_context_chunks(deduped)

    def _select_context_chunks(
        self, chunks: list[_RetrievedChunk]
    ) -> list[_RetrievedChunk]:
        """Select final context chunks after scoring and fairness constraints."""
        if not chunks:
            return []

        requested_symbols = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        requested_symbols = list(dict.fromkeys(requested_symbols))
        if not requested_symbols or self.config.per_symbol_min_chunks <= 0:
            return chunks[: self.config.top_k]

        selected: list[_RetrievedChunk] = []
        selected_keys: set[tuple[str, str, str]] = set()
        min_per_symbol = self.config.per_symbol_min_chunks

        for symbol in requested_symbols:
            picked = 0
            for chunk in chunks:
                chunk_symbol = (chunk.symbol or "").strip().upper()
                if chunk_symbol != symbol:
                    continue
                key = self._chunk_identity(chunk)
                if key in selected_keys:
                    continue
                selected.append(chunk)
                selected_keys.add(key)
                picked += 1
                if (
                    picked >= min_per_symbol
                    or len(selected) >= self.config.top_k
                ):
                    break
            if len(selected) >= self.config.top_k:
                break

        if len(selected) < self.config.top_k:
            for chunk in chunks:
                key = self._chunk_identity(chunk)
                if key in selected_keys:
                    continue
                selected.append(chunk)
                selected_keys.add(key)
                if len(selected) >= self.config.top_k:
                    break

        return selected[: self.config.top_k]

    def _build_symbol_filter(self, symbols: list[str]) -> Filter | None:
        """Build a symbol-scoped metadata filter for vector queries."""
        if not symbols:
            return None

        symbol_conditions: list[Condition] = []
        for symbol in symbols:
            symbol_conditions.extend(
                [
                    FieldCondition(
                        key="symbol", match=MatchValue(value=symbol)
                    ),
                    FieldCondition(
                        key="ticker", match=MatchValue(value=symbol)
                    ),
                    FieldCondition(
                        key="metadata.symbol",
                        match=MatchValue(value=symbol),
                    ),
                    FieldCondition(
                        key="metadata.ticker",
                        match=MatchValue(value=symbol),
                    ),
                ]
            )
        return Filter(should=symbol_conditions)

    @staticmethod
    def _seed_context_metadata(
        *,
        seed: ChatSeedBundle | None,
        seed_chunk_count: int,
    ) -> dict[str, JsonValue]:
        """Build metadata summary for seeded context chunks."""
        if seed is None:
            if seed_chunk_count > 0:
                return {
                    "seeded_context": True,
                    "seeded_context_chunk_count": seed_chunk_count,
                }
            return {"seeded_context": False}
        return {
            "seeded_context": True,
            "seeded_context_source": seed.upstream_pipeline,
            "seeded_context_run_id": seed.upstream_run_id,
            "seeded_context_short_id": seed.upstream_short_id,
            "seeded_context_symbols": list(seed.symbols),
            "seeded_context_queries": list(seed.queries),
            "seeded_context_chunk_count": max(
                len(seed.chunks), seed_chunk_count
            ),
        }

    @staticmethod
    def _snippet_fingerprint(text: str) -> str:
        """Build a stable fingerprint for snippet deduplication."""
        return hashlib.blake2b(
            text.casefold().encode("utf-8"),
            digest_size=8,
        ).hexdigest()

    def _collection_points(
        self,
        *,
        qdrant: QdrantClient,
        collection: str,
    ) -> int | None:
        """Collect vector points from a Qdrant collection with optional filters."""
        try:
            info = qdrant.get_collection(collection)
            points_count = getattr(info, "points_count", None)
            if isinstance(points_count, int):
                return points_count
        except Exception as exc:
            logger.debug(
                "Failed to inspect collection '%s': %s", collection, exc
            )
        return None

    def _maybe_prefetch_collection(
        self,
        *,
        qdrant: QdrantClient,
        collection: str,
        symbols: list[str],
        question: str,
    ) -> None:
        """Prefetch collection metadata when configured and available."""
        if not self.config.prefetch_retrieve:
            return
        if "retrieve" not in collection.casefold():
            return
        if not symbols:
            logger.debug(
                "Prefetch skipped for '%s': symbol scope required",
                collection,
            )
            return

        hydrated = self._hydrate_retrieve_collection(
            collection=collection,
            symbols=symbols,
            question=question,
        )
        if hydrated and qdrant.collection_exists(collection):
            logger.info(
                "Prefetch populated collection '%s' for symbols=%s",
                collection,
                ",".join(symbols),
            )

    def _hydrate_retrieve_collection(
        self,
        *,
        collection: str,
        symbols: list[str],
        question: str,
    ) -> bool:
        """Hydrate retrieve collection records into chat-ready chunks."""
        queries = (
            self.config.prefetch_queries
            if self.config.prefetch_queries
            else [question.strip()]
        )
        queries = [query for query in queries if query]
        if not queries:
            return False

        try:
            vdb_config = self.config.vdb.model_dump(mode="python")
            vdb_config["collection_name"] = collection
            retrieve_config = RetrieveSettings(
                email=self.config.email,
                symbols=symbols,
                forms=self.config.forms,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                queries=queries,
                efts_candidates=self.config.prefetch_efts_candidates,
                top_k=self.config.prefetch_top_k,
                index_results=True,
                dry_run=False,
                output_format="json",
                dl_path=self.config.dl_path,
                out_path=self.config.out_path,
                vdb=vdb_config,
            )
            retrieve_result = RetrievePipeline(config=retrieve_config).run()
            return retrieve_result.success
        except Exception as exc:
            logger.warning(
                "Prefetch retrieve failed for collection '%s': %s",
                collection,
                exc,
            )
            logger.debug(
                "Prefetch retrieve traceback for collection '%s'",
                collection,
                exc_info=True,
            )
            return False

    @staticmethod
    def _coerce_vector(
        values: list[float] | tuple[float, ...] | None,
        *,
        expected_dim: int | None = None,
    ) -> np.ndarray | None:
        """Coerce embedding payloads into float vectors."""
        if values is None:
            return None
        vector = np.asarray(values, dtype=np.float32)
        if vector.ndim != 1 or vector.size == 0:
            return None
        if expected_dim is not None and vector.size != expected_dim:
            return None
        norm = float(np.linalg.norm(vector))
        if norm <= 0.0:
            return None
        return vector / norm

    def _rerank_chunks_mmr(
        self,
        *,
        chunks: list[_RetrievedChunk],
        query_vector: list[float],
        embedder: _SnippetEmbedder,
    ) -> list[_RetrievedChunk]:
        """Rerank candidate chunks with MMR for diversity and relevance."""
        if len(chunks) <= 1:
            return chunks

        candidates = chunks[: self.config.rerank_candidates]
        query_unit = self._coerce_vector(query_vector)
        if query_unit is None:
            return chunks

        vectors: list[np.ndarray | None] = []
        missing_indices: list[int] = []
        for idx, chunk in enumerate(candidates):
            coerced = self._coerce_vector(
                chunk.vector,
                expected_dim=query_unit.size,
            )
            vectors.append(coerced)
            if coerced is None:
                missing_indices.append(idx)

        if missing_indices:
            snippets = [candidates[idx].snippet for idx in missing_indices]
            try:
                raw_vectors = embedder.embed_documents(snippets)
            except Exception as exc:
                logger.debug("MMR rerank skipped (embedding failure): %s", exc)
                return chunks

            if len(raw_vectors) != len(missing_indices):
                return chunks
            for idx, raw in zip(missing_indices, raw_vectors, strict=False):
                if not isinstance(raw, list):
                    return chunks
                numeric = [
                    float(value)
                    for value in raw
                    if isinstance(value, (int, float))
                ]
                coerced = self._coerce_vector(
                    numeric, expected_dim=query_unit.size
                )
                if coerced is None:
                    return chunks
                vectors[idx] = coerced

        if any(vector is None for vector in vectors):
            return chunks
        dense_vectors = [vector for vector in vectors if vector is not None]
        if len(dense_vectors) != len(vectors):
            return chunks
        matrix = np.vstack(dense_vectors)

        selected_indices: list[int] = []
        remaining = list(range(len(candidates)))

        while remaining and len(selected_indices) < self.config.top_k:
            best_idx = remaining[0]
            best_score = float("-inf")
            for idx in remaining:
                relevance = float(np.dot(matrix[idx], query_unit))
                diversity = 0.0
                if selected_indices:
                    selected_matrix = matrix[selected_indices]
                    similarities = selected_matrix @ matrix[idx]
                    diversity = float(np.max(similarities))
                mmr_score = (
                    self.config.rerank_lambda * relevance
                    - (1.0 - self.config.rerank_lambda) * diversity
                )
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            selected_indices.append(best_idx)
            remaining.remove(best_idx)

        selected = [candidates[idx] for idx in selected_indices]
        selected_keys = {self._chunk_identity(chunk) for chunk in selected}
        for chunk in chunks:
            key = self._chunk_identity(chunk)
            if key in selected_keys:
                continue
            selected.append(chunk)
        return selected

    @staticmethod
    def _normalized_form_filters(forms: list[str] | None) -> set[str]:
        """Normalize form filters for consistent metadata matching."""
        if not forms:
            return set()

        normalized: set[str] = set()
        for raw in forms:
            cleaned = raw.strip().upper()
            if cleaned in {"10K", "10Q", "8K", "6K"}:
                cleaned = cleaned[:-1] + "-" + cleaned[-1]
            base = cleaned[:-2] if cleaned.endswith("/A") else cleaned
            if base:
                normalized.add(base)
        return normalized

    @staticmethod
    def _parse_filed_date(value: str | None) -> date | None:
        """Parse filed date."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if "T" in cleaned:
            cleaned = cleaned.split("T", 1)[0]
        if len(cleaned) == 8 and cleaned.isdigit():
            try:
                return date(
                    int(cleaned[:4]),
                    int(cleaned[4:6]),
                    int(cleaned[6:8]),
                )
            except ValueError:
                return None
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            return None

    @classmethod
    def _chunk_matches_filters(
        cls,
        chunk: _RetrievedChunk,
        *,
        forms: set[str],
        filed_after: date | None,
        filed_before: date | None,
    ) -> bool:
        """Return whether a chunk satisfies symbol/date/form filters."""
        if forms:
            chunk_form = cls._normalized_form_filters([chunk.form_type or ""])
            if not chunk_form.intersection(forms):
                return False

        if filed_after is None and filed_before is None:
            return True

        filing_date = cls._parse_filed_date(chunk.filed_date)
        if filing_date is None:
            return False
        if filed_after is not None and filing_date < filed_after:
            return False
        return filed_before is None or filing_date <= filed_before

    @staticmethod
    def _parse_news_timestamp(value: str | None) -> datetime | None:
        """Parse a news timestamp into a timezone-aware datetime when possible."""
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(cleaned)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _question_keywords(question: str, max_keywords: int = 8) -> list[str]:
        """Extract question keywords."""
        keywords: list[str] = []
        seen: set[str] = set()
        for match in _QUESTION_TOKEN_RE.finditer(question):
            token = match.group(0).lower()
            if token in _STOPWORDS:
                continue
            if token in seen:
                continue
            seen.add(token)
            keywords.append(token)
            if len(keywords) >= max_keywords:
                break
        return keywords

    def _context_symbol(self, citations: list[ChatCitation]) -> str | None:
        """Resolve the primary symbol associated with a context chunk."""
        configured = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        unique_configured = list(dict.fromkeys(configured))
        if len(unique_configured) > 1:
            return "MULTI"
        if len(unique_configured) == 1:
            return unique_configured[0]
        if citations and citations[0].symbol:
            return citations[0].symbol.upper()
        return None

    def _external_context_symbol(
        self,
        citations: list[ChatCitation],
    ) -> str | None:
        """Resolve the symbol associated with an external context record."""
        configured = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        unique_configured = list(dict.fromkeys(configured))
        if len(unique_configured) == 1:
            return unique_configured[0]
        if len(unique_configured) > 1:
            return None
        if citations and citations[0].symbol:
            return citations[0].symbol.upper()
        return None

    @staticmethod
    def _citation_symbols(citations: list[ChatCitation]) -> list[str]:
        """Extract citation symbols."""
        symbols = [
            citation.symbol.upper()
            for citation in citations
            if citation.symbol and citation.symbol.strip()
        ]
        return list(dict.fromkeys(symbols))

    def _resolve_market_context_symbols(
        self,
        citations: list[ChatCitation],
    ) -> list[str]:
        """Resolve market context symbols."""
        symbol_scope = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        symbol_scope = list(dict.fromkeys(symbol_scope))
        citation_symbols = self._citation_symbols(citations)
        max_symbols = self.config.market_context_max_symbols

        if self.config.market_context_scope == "single":
            symbol = self._external_context_symbol(citations)
            return [symbol] if symbol else []

        if self.config.market_context_scope == "multi":
            if citation_symbols:
                return citation_symbols[:max_symbols]
            return symbol_scope[:max_symbols]

        # auto mode
        if len(symbol_scope) <= 1:
            symbol = self._external_context_symbol(citations)
            return [symbol] if symbol else []
        if citation_symbols:
            return citation_symbols[:max_symbols]
        return []

    def _build_external_context(
        self,
        *,
        question: str,
        citations: list[ChatCitation],
    ) -> tuple[str, dict[str, JsonValue]]:
        """Build external market and news context blocks for prompt injection."""
        symbol_scope = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]

        sections: list[str] = []
        metadata: dict[str, JsonValue] = {
            "market_context_items": 0,
            "news_context_items": 0,
        }
        if symbol_scope:
            metadata["symbol_scope"] = symbol_scope

        if self.config.include_market_context:
            market_symbols = self._resolve_market_context_symbols(citations)
            if market_symbols:
                metadata["market_context_requested_symbols"] = market_symbols
            lines: list[str] = []
            covered_symbols: list[str] = []
            market_context_bundle: dict[str, JsonValue] = {}
            if market_symbols:
                (
                    lines,
                    covered_symbols,
                    market_context_bundle,
                ) = self._market_context_lines(symbols=market_symbols)
            if lines:
                sections.append("Market context:\n" + "\n".join(lines))
                metadata["market_context_items"] = len(lines)
            if market_context_bundle:
                metadata["market_context_bundle"] = market_context_bundle
                metadata["market_context_profile"] = (
                    self.config.market_context_profile
                )
            if covered_symbols:
                metadata["market_context_symbols"] = covered_symbols
            if market_symbols:
                missing_symbols = [
                    symbol
                    for symbol in market_symbols
                    if symbol not in covered_symbols
                ]
                if missing_symbols:
                    metadata["market_context_missing_symbols"] = missing_symbols
            elif (
                self.config.market_context_scope != "single"
                and len(symbol_scope) > 1
            ):
                metadata["market_context_skipped"] = (
                    "no_retrieved_symbols_for_multi_scope"
                )

        if self.config.include_news_context:
            symbol = self._external_context_symbol(citations)
            if symbol:
                metadata["external_context_symbol"] = symbol
                lines = self._news_context_lines(
                    symbol=symbol, question=question
                )
                if lines:
                    sections.append(
                        "News/geopolitics context:\n" + "\n".join(lines)
                    )
                    metadata["news_context_items"] = len(lines)
            elif len(symbol_scope) > 1:
                metadata["news_context_skipped"] = "multiple_symbols"

        if not sections:
            return "", metadata
        return "\n\n".join(sections), metadata

    def _market_context_lines(
        self, *, symbols: list[str]
    ) -> tuple[list[str], list[str], dict[str, JsonValue]]:
        """Format market context records into prompt-ready lines."""
        if not symbols:
            return [], [], {}

        end = self._effective_end_date()
        start = max(
            self.config.start_date
            or (end - timedelta(days=self.config.market_lookback_days)),
            end - timedelta(days=self.config.market_lookback_days),
        )
        try:
            bundle = build_market_context(
                symbols=symbols,
                start_date=start,
                end_date=end,
                benchmark=self.config.market_benchmark_symbol,
            )
        except Exception as exc:
            logger.debug("Market context unavailable: %s", exc)
            return [], [], {}

        bundle_payload = as_json_dict(
            bundle.model_dump(mode="json", exclude_none=True)
        )
        if bundle_payload is None:
            bundle_payload = {}
        metrics_by_symbol = {metric.symbol: metric for metric in bundle.metrics}
        covered_symbols = [
            symbol for symbol in symbols if symbol in metrics_by_symbol
        ]
        if not covered_symbols:
            return [], [], bundle_payload

        benchmark_return_pct = next(
            (
                metric.benchmark_return_pct
                for metric in bundle.metrics
                if metric.benchmark_return_pct is not None
            ),
            None,
        )

        lines: list[str] = []
        if (
            benchmark_return_pct is not None
            and self.config.market_context_profile == "standard"
        ):
            lines.append(
                f"- Benchmark {bundle.benchmark}: {bundle.window} return {benchmark_return_pct:+.2f}%."
            )

        for symbol in covered_symbols:
            metric = metrics_by_symbol[symbol]
            return_pct = (
                f"{metric.return_pct:+.2f}%"
                if metric.return_pct is not None
                else "n/a"
            )
            spread_pct = (
                f"{metric.spread_pct:+.2f}%"
                if metric.spread_pct is not None
                else "n/a"
            )
            beta_value = (
                f"{metric.beta:.2f}" if metric.beta is not None else "n/a"
            )
            if self.config.market_context_profile == "compact":
                lines.append(
                    f"- {symbol}: return {return_pct}, spread vs {bundle.benchmark} {spread_pct}, beta {beta_value}."
                )
                continue

            max_drawdown = (
                f"{metric.max_drawdown:.2f}%"
                if metric.max_drawdown is not None
                else "n/a"
            )
            lines.append(
                f"- {symbol}: return {return_pct} (spread vs {bundle.benchmark} {spread_pct}, beta {beta_value}, max drawdown {max_drawdown})."
            )
            atr_value = f"{metric.atr:.4f}" if metric.atr is not None else "n/a"
            std_dev_value = (
                f"{metric.std_dev:.4f}" if metric.std_dev is not None else "n/a"
            )
            volume_spike_value = (
                f"{metric.volume_spike:.2f}"
                if metric.volume_spike is not None
                else "n/a"
            )
            lines.append(
                f"- {symbol}: ATR {atr_value}, return std-dev {std_dev_value}, volume spike {volume_spike_value}, observations {metric.observations}."
            )

        return lines, covered_symbols, bundle_payload

    def _news_context_lines(self, *, symbol: str, question: str) -> list[str]:
        """Format news context records into prompt-ready lines."""
        lookback_start = self._effective_end_date() - timedelta(
            days=self.config.news_lookback_days
        )
        keywords = [symbol]
        keywords.extend(self._question_keywords(question))
        keywords = list(dict.fromkeys(keywords))

        try:
            retriever = create_news_retriever(
                user_agent=f"SEC NLP Tool ({self.config.email})",
                rate_limit_secs=0.15,
            )
            raw_items = retriever.fetch(
                keywords=keywords,
                max_results=max(self.config.max_news_items * 4, 20),
            )
        except NewswatchExtensionError as exc:
            logger.debug("News context unavailable: %s", exc)
            return []
        except Exception as exc:
            logger.debug("News context fetch failed: %s", exc)
            return []

        deduped: list[tuple[datetime, str, str]] = []
        seen: set[str] = set()
        for item in raw_items:
            timestamp = self._parse_news_timestamp(item.published_at)
            if timestamp is None:
                continue
            published = timestamp.astimezone(UTC)
            published_date = published.date()
            if published_date < lookback_start:
                continue
            title = item.title.strip()
            url = item.url.strip()
            dedupe_key = f"{title.casefold()}::{url.casefold()}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            source = item.source.strip() or "unknown"
            deduped.append((published, source, title))

        deduped.sort(key=lambda current: current[0], reverse=True)
        deduped = deduped[: self.config.max_news_items]
        lines = [
            f"- {published.date().isoformat()} | {source} | {title}"
            for published, source, title in deduped
        ]
        return lines

    def _point_to_chunk(
        self,
        *,
        collection: str,
        point,
    ) -> _RetrievedChunk | None:
        """Map a bullet point back to its best-matching source chunk."""
        payload = getattr(point, "payload", None)
        if not isinstance(payload, dict):
            return None

        snippet = self._extract_snippet(payload)
        if snippet is None:
            return None

        metadata = payload.get("metadata")
        metadata_dict: dict[str, JsonValue] = {}
        if isinstance(metadata, dict):
            for raw_key, raw_value in metadata.items():
                if not isinstance(raw_key, str):
                    continue
                if isinstance(raw_value, str):
                    metadata_dict[raw_key] = raw_value

        score_raw = getattr(point, "score", None)
        score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0

        symbol = self._first_text(
            payload,
            metadata_dict,
            keys=("symbol", "ticker"),
        )
        accession = self._first_text(
            payload,
            metadata_dict,
            keys=("accession_number", "accession"),
        )
        form_type = self._first_text(
            payload,
            metadata_dict,
            keys=("form_type",),
        )
        filed_date = self._first_text(
            payload,
            metadata_dict,
            keys=("filed_date",),
        )
        source = self._first_text(
            payload,
            metadata_dict,
            keys=("source", "edgar_url"),
        )
        vector = self._extract_point_vector(point)

        return _RetrievedChunk(
            collection=collection,
            score=score,
            symbol=symbol,
            accession_number=accession,
            form_type=form_type,
            filed_date=filed_date,
            source=source,
            snippet=snippet,
            vector=vector,
        )

    @staticmethod
    def _first_text(
        payload: dict[str, JsonValue],
        metadata: dict[str, JsonValue],
        *,
        keys: tuple[str, ...],
    ) -> str | None:
        """Return the first non-empty string from candidate values."""
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            meta_value = metadata.get(key)
            if isinstance(meta_value, str) and meta_value.strip():
                return meta_value.strip()
        return None

    @staticmethod
    def _extract_snippet(payload: dict[str, JsonValue]) -> str | None:
        """Extract snippet."""
        candidates: list[str] = []

        direct_keys = ("snippet", "page_content", "content", "text")
        for key in direct_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata_dict: dict[str, JsonValue] = {}
            for raw_key, raw_value in metadata.items():
                if not isinstance(raw_key, str):
                    continue
                if isinstance(raw_value, str):
                    metadata_dict[raw_key] = raw_value
            for key in ("raw_chunk", "page_content", "snippet", "content"):
                value = metadata_dict.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value)

        if not candidates:
            return None

        snippet = _WHITESPACE_RE.sub(" ", candidates[0]).strip()
        if len(snippet) > 700:
            snippet = snippet[:697].rstrip() + "..."
        return snippet

    @staticmethod
    def _extract_point_vector(point) -> list[float] | None:
        """Extract point vector."""
        candidate = getattr(point, "vector", None)
        if candidate is None:
            candidate = getattr(point, "vectors", None)

        if isinstance(candidate, dict):
            # Named vectors are stored as mapping[name, vector]; use first vector.
            for value in candidate.values():
                if isinstance(value, list):
                    candidate = value
                    break
            else:
                return None

        if not isinstance(candidate, list):
            return None
        numeric = [
            float(value)
            for value in candidate
            if isinstance(value, (int, float))
        ]
        return numeric or None

    def _to_citations(
        self, chunks: list[_RetrievedChunk]
    ) -> list[ChatCitation]:
        """Convert selected chunks into citation payload entries."""
        citations: list[ChatCitation] = []
        for idx, chunk in enumerate(chunks, start=1):
            citations.append(
                ChatCitation(
                    citation_id=f"C{idx}",
                    collection=chunk.collection,
                    score=float(chunk.score),
                    symbol=chunk.symbol,
                    accession_number=chunk.accession_number,
                    form_type=chunk.form_type,
                    filed_date=chunk.filed_date,
                    source=chunk.source,
                    snippet=chunk.snippet,
                )
            )
        return citations

    def _build_answer(
        self,
        *,
        question: str,
        citations: list[ChatCitation],
        external_context: str = "",
    ) -> tuple[str, list[str]]:
        """Build the final answer payload with citations and metadata."""
        if not citations:
            return (
                "I could not find indexed evidence for this question in the selected collections.",
                [],
            )

        t_prompt = perf_counter()
        prompt = self._build_prompt(
            question=question,
            citations=citations,
            external_context=external_context,
        )
        prompt_elapsed = perf_counter() - t_prompt

        t_llm = perf_counter()
        llm_max_new_tokens = self._effective_max_new_tokens(len(citations))
        self._last_llm_max_new_tokens = llm_max_new_tokens
        llm_config = self.config.llm
        if llm_max_new_tokens != llm_config.max_new_tokens:
            llm_config = llm_config.model_copy(
                update={"max_new_tokens": llm_max_new_tokens}
            )
        llm = llm_config.setup_ollama_model()
        raw_answer = self._invoke_llm_with_timeout(llm=llm, prompt=prompt)
        llm_elapsed = perf_counter() - t_llm
        self._last_answer_timings = {
            "prompt_build": prompt_elapsed,
            "llm_generate": llm_elapsed,
        }
        answer = raw_answer if isinstance(raw_answer, str) else str(raw_answer)
        answer = answer.strip()
        if not answer:
            answer = "I could not generate a grounded answer from the retrieved evidence."

        available = {citation.citation_id for citation in citations}
        used_ids = [
            cid for cid in _CITATION_RE.findall(answer) if cid in available
        ]
        used_ids = list(dict.fromkeys(used_ids))

        if self.config.strict_citations and not used_ids:
            fallback_ids = [
                citation.citation_id
                for citation in citations[: min(3, len(citations))]
            ]
            if fallback_ids:
                suffix = " ".join(f"[{cid}]" for cid in fallback_ids)
                answer = f"{answer}\n\nSources: {suffix}"
                used_ids = fallback_ids

        return answer, used_ids

    def _effective_max_new_tokens(self, citation_count: int) -> int:
        """Resolve the effective max new tokens for the current run."""
        configured = max(1, self.config.llm.max_new_tokens)
        cap = self.config.generation_token_cap
        if cap <= 0:
            return configured

        context_chunks = max(
            1,
            min(citation_count, self.config.max_context_chunks),
        )
        adaptive_target = 96 + (32 * context_chunks)
        return max(96, min(configured, cap, adaptive_target))

    def _effective_context_token_budget(self, citation_count: int) -> int:
        """Resolve the effective context token budget for the current run."""
        configured = max(1, self.config.context_token_budget)
        effective_generation = self._effective_max_new_tokens(citation_count)
        adaptive_cap = max(512, effective_generation * 4)
        return max(256, min(configured, adaptive_cap))

    def _invoke_llm_with_timeout(self, *, llm, prompt: str):
        """Invoke the LLM with explicit timeout handling."""
        invoke = getattr(llm, "invoke", None)
        if not callable(invoke):
            raise TypeError("Configured LLM does not expose invoke(prompt)")

        timeout_seconds = self.config.llm_timeout_seconds
        if timeout_seconds <= 0:
            return invoke(prompt)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(invoke, prompt)
            try:
                return future.result(timeout=float(timeout_seconds))
            except TimeoutError as exc:
                future.cancel()
                raise TimeoutError(
                    f"LLM generation timed out after {timeout_seconds}s"
                ) from exc

    def _build_prompt(
        self,
        *,
        question: str,
        citations: list[ChatCitation],
        external_context: str = "",
    ) -> str:
        """Build the LLM prompt from question, context, and output constraints."""
        symbol_scope = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        if not symbol_scope:
            symbol_scope = [
                citation.symbol.upper()
                for citation in citations
                if citation.symbol and citation.symbol.strip()
            ]
        symbol_scope = list(dict.fromkeys(symbol_scope))
        symbol_scope_line = (
            ", ".join(symbol_scope) if symbol_scope else "(unspecified)"
        )
        covered_symbols = [
            citation.symbol.upper()
            for citation in citations
            if citation.symbol and citation.symbol.strip()
        ]
        covered_symbols = list(dict.fromkeys(covered_symbols))
        missing_scope_symbols = [
            symbol for symbol in symbol_scope if symbol not in covered_symbols
        ]
        covered_line = (
            ", ".join(covered_symbols) if covered_symbols else "(none)"
        )
        missing_line = (
            ", ".join(missing_scope_symbols)
            if missing_scope_symbols
            else "(none)"
        )

        history_lines: list[str] = []
        if self.config.include_history and self.config.chat_history:
            keep = self.config.history_turns
            turns = self.config.chat_history[-keep:] if keep > 0 else []
            for turn in turns:
                role = "User" if turn.role == "user" else "Assistant"
                history_lines.append(f"{role}: {turn.message}")

        context_sections: list[str] = []
        for citation, snippet in self._pack_context_citations(citations):
            summary_parts = [f"Collection={citation.collection}"]
            if citation.symbol:
                summary_parts.append(f"Symbol={citation.symbol}")
            if citation.form_type:
                summary_parts.append(f"Form={citation.form_type}")
            if citation.filed_date:
                summary_parts.append(f"Filed={citation.filed_date}")
            if citation.accession_number:
                summary_parts.append(f"Accession={citation.accession_number}")
            summary = "; ".join(summary_parts)
            context_sections.append(
                f"[{citation.citation_id}] {summary}\n{snippet}"
            )

        history_block = (
            "\n".join(history_lines)
            if history_lines
            else "(no prior conversation)"
        )
        context_block = "\n\n".join(context_sections)
        external_block = (
            external_context if external_context.strip() else "(none)"
        )

        return (
            "You are a financial filings assistant.\n"
            "Use only the provided context.\n"
            "If context is insufficient, say so directly.\n"
            "Treat each ticker symbol as a distinct issuer.\n"
            "Never claim two different tickers are the same entity unless a cited chunk explicitly states a ticker change, rename, or merger.\n"
            "Every factual claim must include citation IDs in [C#] form.\n\n"
            f"Ticker scope:\n{symbol_scope_line}\n\n"
            f"Symbols with retrieved filing evidence:\n{covered_line}\n\n"
            f"Symbols without retrieved filing evidence:\n{missing_line}\n\n"
            "Do not generalize claims to symbols without retrieved filing evidence.\n\n"
            f"Conversation history:\n{history_block}\n\n"
            f"Question:\n{question}\n\n"
            f"Context chunks:\n{context_block}\n\n"
            "Supplemental context (market/news; non-filing evidence):\n"
            f"{external_block}\n\n"
            "Use supplemental context only for macro framing. "
            "Company-specific factual claims must still cite filing chunks.\n\n"
            "Answer succinctly with grounded evidence and citations."
        )

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count for a text segment."""
        normalized = text.strip()
        if not normalized:
            return 0
        return max(1, len(normalized) // 4)

    @classmethod
    def _clip_to_token_budget(cls, text: str, budget_tokens: int) -> str:
        """Clip text to fit within the requested token budget."""
        if budget_tokens <= 0:
            return ""
        max_chars = max(1, budget_tokens * 4)
        normalized = _WHITESPACE_RE.sub(" ", text).strip()
        if len(normalized) <= max_chars:
            return normalized
        if max_chars <= 3:
            return normalized[:max_chars]
        return f"{normalized[: max_chars - 3].rstrip()}..."

    def _pack_context_citations(
        self, citations: list[ChatCitation]
    ) -> list[tuple[ChatCitation, str]]:
        """Pack context chunks and citations within the token budget."""
        effective_budget = self._effective_context_token_budget(len(citations))
        self._last_context_token_budget = effective_budget
        budget_remaining = effective_budget
        packed: list[tuple[ChatCitation, str]] = []
        for citation in citations[: self.config.max_context_chunks]:
            summary_parts = [f"Collection={citation.collection}"]
            if citation.symbol:
                summary_parts.append(f"Symbol={citation.symbol}")
            if citation.form_type:
                summary_parts.append(f"Form={citation.form_type}")
            if citation.filed_date:
                summary_parts.append(f"Filed={citation.filed_date}")
            if citation.accession_number:
                summary_parts.append(f"Accession={citation.accession_number}")
            summary = "; ".join(summary_parts)
            summary_tokens = self._estimate_tokens(summary)
            if summary_tokens >= budget_remaining:
                if not packed:
                    packed.append((citation, ""))
                break

            snippet_budget = budget_remaining - summary_tokens
            clipped_snippet = self._clip_to_token_budget(
                citation.snippet,
                snippet_budget,
            )
            snippet_tokens = self._estimate_tokens(clipped_snippet)
            packed.append((citation, clipped_snippet))
            budget_remaining -= summary_tokens + snippet_tokens
            if budget_remaining <= 0:
                break
        return packed

    def _build_turns(
        self,
        *,
        question: str,
        answer: str,
        citation_ids: list[str],
    ) -> list[ChatTurn]:
        """Build transcript turns for chat output artifacts."""
        turns: list[ChatTurn] = [
            ChatTurn(role=turn.role, message=turn.message)
            for turn in self.config.chat_history
        ]
        turns.append(ChatTurn(role="user", message=question))
        turns.append(
            ChatTurn(
                role="assistant",
                message=answer,
                citations=citation_ids,
            )
        )
        return turns

    def _write_outputs(
        self,
        *,
        question: str,
        answer: str,
        citations: list[ChatCitation],
        citation_ids: list[str],
        turns: list[ChatTurn],
        external_context: str,
        external_metadata: dict[str, JsonValue],
    ) -> list[Path]:
        """Write pipeline outputs and return generated artifact paths."""
        symbol = self._context_symbol(citations) or "ALL"

        symbol_out = self.config.get_symbol_output_dir(symbol)
        output_context = build_run_output_context(
            symbol=symbol,
            suffix="chat",
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        base_stem = output_context.base_stem
        run_header = output_context.run_header
        run_short_id = output_context.run_short_id

        payload_metadata = self._base_metadata(
            external_context=external_context,
            external_metadata=external_metadata,
        )
        payload_metadata.update(
            {
                "output_scope_symbol": symbol,
                "top_k": self.config.top_k,
                "max_context_chunks": self.config.max_context_chunks,
                "strict_citations": self.config.strict_citations,
                "include_history": self.config.include_history,
                "history_turns": self.config.history_turns,
            }
        )

        payload = ChatTranscriptPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            question=question,
            answer=answer,
            citations=citations,
            citation_ids=citation_ids,
            turns=turns,
            metadata=coerce_result_json_dict(payload_metadata),
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            csv_path = symbol_out / f"{base_stem}_transcript.csv"
            write_chat_transcript_csv(
                csv_path,
                payload,
                header_fields=run_header,
            )
            outputs.append(csv_path)

        if self.config.output_format in ("json", "all"):
            json_path = symbol_out / f"{base_stem}_summary.json"
            write_chat_transcript_json(json_path, payload)
            outputs.append(json_path)

        if self.config.output_format in ("yaml", "all"):
            yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            write_chat_transcript_yaml(yaml_path, payload)
            outputs.append(yaml_path)

        return outputs
