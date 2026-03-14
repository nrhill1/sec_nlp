# src/sec_nlp/pipelines/presets/analyze/runnables/analysis.py
"""LLM analysis runner for analyze pipeline chunks.

This module executes batched analyze prompts, formats model outputs, and
optionally persists successful results in a disk-backed cache. The cache uses
SQLite so repeated runs can reuse prior chunk analyses without rewriting an
entire JSON file on each batch flush.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Iterator, Sequence
from pathlib import Path
from time import perf_counter
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.runnables import (
    Runnable,
    RunnableConfig,
    RunnableSerializable,
)
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from rich.progress import Progress, TaskID

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.runtime import get_accession_from_metadata
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord
from sec_nlp.types import JsonValue

from ..models import AnalysisInput, AnalysisResult
from ..types import is_abort_requested
from ..utils import query_term_overlap, resolve_symbol_for_output

NUMERIC_SIGNAL_RE = re.compile(r"[$€£]?\d")
_LLM_CACHE_SCHEMA_VERSION = 1
_LLM_CACHE_BATCH_SIZE = 400


def _cache_db_path(path: Path) -> Path:
    """Resolve the SQLite cache path for analyze responses."""
    if path.suffix.casefold() == ".json":
        return path.with_suffix(".sqlite3")
    return path


def _chunked_keys(keys: Sequence[str]) -> Iterator[Sequence[str]]:
    """Yield cache keys in bounded batches for SQLite `IN` queries."""
    for idx in range(0, len(keys), _LLM_CACHE_BATCH_SIZE):
        yield keys[idx : idx + _LLM_CACHE_BATCH_SIZE]


class AnalysisBatchInput(BaseModel):
    """Runnable input for analyzing a batch of documents."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    symbol: str
    docs: list[Document]


class AnalyzerRunnable(
    RunnableSerializable[AnalysisBatchInput, list[AnalysisResultDict]]
):
    """Run LLM analysis over prepared document chunks."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
        frozen=True,
        defer_build=True,
    )

    graph: Runnable[AnalysisInput, AnalysisResult] = Field(
        description="Runnable LLM graph"
    )
    callbacks: list[BaseCallbackHandler] = Field(default_factory=list)
    analysis_instructions: str = Field(default="")
    symbols: list[str] = Field(default_factory=list)
    llm_retry_attempts: int = Field(default=0, ge=0)
    llm_retry_backoff: float = Field(default=0.0, ge=0.0)
    confidence_mode: str = Field(default="basic")
    analysis_fields: list[str] = Field(default_factory=list)
    compact_result_output: bool = Field(default=False)
    include_raw_chunks: bool = Field(default=False)
    batch_size: int = Field(default=8, ge=1)
    adaptive_batch_token_budget: int = Field(
        default=32000,
        ge=1000,
        description="Token budget for adaptive batch sizing (chars / 4)",
    )
    query_term_min_len: int = Field(default=3, ge=1)
    run_id: UUID | None = None
    ensemble_graphs: list[Runnable[AnalysisInput, AnalysisResult]] = Field(
        default_factory=list,
        description="Additional model graphs used for ensemble voting.",
    )
    ensemble_model_names: list[str] = Field(default_factory=list)
    llm_cache_enabled: bool = Field(default=False)
    llm_cache_file: Path | None = None
    llm_cache_max_entries: int = Field(default=20000, ge=100)
    llm_cache_namespace: str = Field(default="")

    _cache_loaded: bool = PrivateAttr(default=False)
    _cache_conn: sqlite3.Connection | None = PrivateAttr(default=None)
    _cache_pending_entries: dict[str, str] = PrivateAttr(default_factory=dict)
    _cache_touched_keys: set[str] = PrivateAttr(default_factory=set)

    def invoke(
        self,
        input: AnalysisBatchInput,
        config: RunnableConfig | None = None,
        **kwargs: JsonValue,
    ) -> list[AnalysisResultDict]:
        """Invoke the runnable for chaining in a sequence."""
        _ = config
        _ = kwargs
        if not input.docs:
            return []
        return self.analyze_chunks(input.symbol, input.docs)

    def analyze_chunks(
        self,
        symbol: str,
        docs: list[Document],
        *,
        progress: Progress | None = None,
        task_id: TaskID | None = None,
    ) -> list[AnalysisResultDict]:
        """Analyze document chunks using the LLM graph.

        Args:
            symbol: Ticker symbol being analyzed.
            docs: Document chunks to analyze.
            progress: Optional Rich Progress instance for unified progress display.
            task_id: Optional task ID within the Progress to update per-chunk.
        """
        if len(docs) == 0:
            raise ValueError("Cannot analyze empty docs list")

        inputs: list[AnalysisInput] = []
        for doc in docs:
            metadata = doc.metadata or {}
            doc_symbol = resolve_symbol_for_output(symbol, metadata)
            matched_queries = self._extract_matched_queries(metadata)
            matched_query_value = self._select_primary_query(
                matched_queries, doc.page_content
            )
            matched_query_list = self._build_matched_query_list(matched_queries)
            inputs.append(
                AnalysisInput(
                    symbol=doc_symbol,
                    chunk=doc.page_content,
                    matched_query=matched_query_value,
                    matched_queries=matched_query_list,
                    context=self._build_context(doc),
                    topic_hits=metadata.get("topic_hits"),
                    analysis_instructions=self.analysis_instructions,
                )
            )

        results: list[AnalysisResultDict] = []
        effective_batch_size = self._compute_adaptive_batch_size(inputs)

        # Update the shared Rich progress task if provided
        total_chunks = len(inputs)
        if progress is not None and task_id is not None:
            progress.update(
                task_id,
                total=total_chunks,
                completed=0,
                description=f"  ├─ {symbol}: Analyzing [0/{total_chunks}]",
            )

        analysis_start = perf_counter()
        processed = 0
        for i in range(0, total_chunks, effective_batch_size):
            if is_abort_requested():
                logger.info(
                    "Abort requested — returning %d/%d partial results for %s",
                    processed,
                    total_chunks,
                    symbol,
                )
                break
            batch = inputs[i : i + effective_batch_size]
            batch_docs = docs[i : i + effective_batch_size]
            batch_results = self._process_batch(batch, batch_docs)
            results.extend(batch_results)
            processed += len(batch)

            if progress is not None and task_id is not None:
                elapsed = perf_counter() - analysis_start
                rate = processed / elapsed if elapsed > 0 else 0
                avg_time = elapsed / processed if processed > 0 else 0
                progress.update(
                    task_id,
                    completed=processed,
                    description=(
                        f"  ├─ {symbol}: Analyzing [{processed}/{total_chunks}]"
                        f" · {rate:.1f} chunks/s"
                        f" · {avg_time:.1f}s/chunk"
                    ),
                )

        self._flush_cache()
        return results

    def _compute_adaptive_batch_size(self, inputs: list[AnalysisInput]) -> int:
        """Compute batch size based on total token budget.

        Smaller chunks allow larger batches for better GPU saturation;
        larger chunks use smaller batches to stay within context limits.
        """
        if not inputs:
            return self.batch_size
        avg_chunk_chars = sum(len(inp.chunk) for inp in inputs) / len(inputs)
        # Rough estimate: ~4 chars per token
        avg_tokens = avg_chunk_chars / 4
        if avg_tokens <= 0:
            return self.batch_size
        adaptive = max(1, int(self.adaptive_batch_token_budget / avg_tokens))
        return min(adaptive, self.batch_size)

    def _selected_output_fields(self) -> set[str]:
        """Filter model output to selected analysis fields."""
        selected = {
            field.strip()
            for field in self.analysis_fields
            if isinstance(field, str) and field.strip()
        }
        selected.update(
            {
                "is_relevant",
                "confidence_score",
                "source_metadata",
                "matched_queries",
            }
        )
        if self.include_raw_chunks:
            selected.add("raw_chunk")
        return selected

    def _cache_path(self) -> Path | None:
        """Cache path."""
        cache_file = self.llm_cache_file
        if not self.llm_cache_enabled or cache_file is None:
            return None
        return _cache_db_path(cache_file)

    def _legacy_cache_path(self) -> Path | None:
        """Return the legacy JSON cache path, when one exists."""
        cache_file = self.llm_cache_file
        if cache_file is None or cache_file.suffix.casefold() != ".json":
            return None
        return cache_file

    @staticmethod
    def _open_cache_db(path: Path) -> sqlite3.Connection:
        """Open the SQLite cache database and ensure the schema exists."""
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA user_version={_LLM_CACHE_SCHEMA_VERSION}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_cache (
                cache_key TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_analysis_cache_updated_at
            ON analysis_cache(updated_at)
            """
        )
        return conn

    @staticmethod
    def _cache_count(conn: sqlite3.Connection) -> int:
        """Return the number of cached analysis rows."""
        row = conn.execute("SELECT COUNT(*) FROM analysis_cache").fetchone()
        if row is None:
            return 0
        count = row[0]
        return int(count) if isinstance(count, int) else 0

    def _migrate_legacy_cache(
        self,
        *,
        conn: sqlite3.Connection,
        legacy_path: Path,
    ) -> None:
        """Migrate the legacy JSON cache file into SQLite on first use."""
        if not legacy_path.exists():
            return
        if self._cache_count(conn) > 0:
            return

        try:
            payload = json.loads(legacy_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.debug(
                "Failed to read legacy analyze cache %s: %s",
                legacy_path,
                exc,
            )
            return

        if not isinstance(payload, dict):
            return
        entries_raw = payload.get("entries")
        if not isinstance(entries_raw, dict):
            return

        updated_at = int(time.time())
        entries: list[tuple[str, str, int]] = []
        for key, raw in entries_raw.items():
            if not isinstance(key, str) or not isinstance(raw, dict):
                continue
            try:
                parsed = AnalysisResult.model_validate(raw)
            except Exception:
                continue
            entries.append(
                (
                    key,
                    parsed.model_dump_json(exclude_none=True),
                    updated_at,
                )
            )

        if not entries:
            return

        conn.executemany(
            """
            INSERT INTO analysis_cache (cache_key, result_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(cache_key)
            DO UPDATE SET
                result_json = excluded.result_json,
                updated_at = excluded.updated_at
            """,
            entries,
        )
        logger.info(
            "Migrated %d analyze LLM cache entries from %s",
            len(entries),
            legacy_path,
        )

    def _ensure_cache_loaded(self) -> None:
        """Ensure the SQLite cache connection is initialized and available."""
        cache_path = self._cache_path()
        if self._cache_loaded or cache_path is None:
            return
        self._cache_loaded = True
        self._cache_pending_entries.clear()
        self._cache_touched_keys.clear()
        try:
            conn = self._open_cache_db(cache_path)
        except Exception as exc:
            logger.debug(
                "Failed to open analyze LLM cache DB %s: %s",
                cache_path,
                exc,
            )
            return

        self._cache_conn = conn
        legacy_path = self._legacy_cache_path()
        if legacy_path is None or legacy_path == cache_path:
            return
        try:
            with conn:
                self._migrate_legacy_cache(conn=conn, legacy_path=legacy_path)
        except Exception as exc:
            logger.debug(
                "Failed to migrate analyze cache %s: %s",
                legacy_path,
                exc,
            )

    def _cache_key(self, item: AnalysisInput) -> str:
        """Build a deterministic cache key for analysis input."""
        payload = {
            "namespace": self.llm_cache_namespace,
            "input": item.model_dump(mode="json", exclude_none=True),
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _lookup_cached_results(
        self,
        items: Sequence[AnalysisInput],
    ) -> dict[str, AnalysisResult]:
        """Look up cached analysis results for a batch of items."""
        if not items:
            return {}

        self._ensure_cache_loaded()
        conn = self._cache_conn
        if conn is None:
            return {}

        keys = [self._cache_key(item) for item in items]
        found: dict[str, AnalysisResult] = {}
        invalid_keys: list[str] = []

        try:
            for batch in _chunked_keys(keys):
                placeholders = ",".join("?" for _ in batch)
                query = (
                    "SELECT cache_key, result_json "
                    f"FROM analysis_cache WHERE cache_key IN ({placeholders})"
                )
                rows = conn.execute(query, tuple(batch)).fetchall()
                for row in rows:
                    cache_key = row[0]
                    result_json = row[1]
                    if not isinstance(cache_key, str) or not isinstance(
                        result_json, str
                    ):
                        if isinstance(cache_key, str):
                            invalid_keys.append(cache_key)
                        continue
                    try:
                        found[cache_key] = AnalysisResult.model_validate_json(
                            result_json
                        )
                    except Exception:
                        invalid_keys.append(cache_key)
        except Exception as exc:
            logger.debug(
                "Failed to read analyze cache entries from %s: %s",
                self._cache_path(),
                exc,
            )
            return {}

        if invalid_keys:
            try:
                with conn:
                    conn.executemany(
                        "DELETE FROM analysis_cache WHERE cache_key = ?",
                        [(cache_key,) for cache_key in invalid_keys],
                    )
            except Exception as exc:
                logger.debug(
                    "Failed to clean invalid analyze cache entries from %s: %s",
                    self._cache_path(),
                    exc,
                )

        self._cache_touched_keys.update(found.keys())
        return found

    def _lookup_cached_result(
        self, item: AnalysisInput
    ) -> AnalysisResult | None:
        """Look up a cached analysis result for the current item."""
        key = self._cache_key(item)
        return self._lookup_cached_results([item]).get(key)

    def _store_cached_result(
        self,
        *,
        item: AnalysisInput,
        result: AnalysisResult,
    ) -> None:
        """Store a computed analysis result in the response cache."""
        self._ensure_cache_loaded()
        if self._cache_conn is None:
            return
        key = self._cache_key(item)
        self._cache_pending_entries[key] = result.model_dump_json(
            exclude_none=True
        )

    def _prune_cache(self, conn: sqlite3.Connection) -> None:
        """Prune least-recently-used cache entries over the configured cap."""
        if self.llm_cache_max_entries <= 0:
            return
        overflow = self._cache_count(conn) - self.llm_cache_max_entries
        if overflow <= 0:
            return
        conn.execute(
            """
            DELETE FROM analysis_cache
            WHERE cache_key IN (
                SELECT cache_key
                FROM analysis_cache
                ORDER BY updated_at ASC, cache_key ASC
                LIMIT ?
            )
            """,
            (overflow,),
        )

    def _flush_cache(self) -> None:
        """Flush pending cache writes to disk."""
        if not self._cache_pending_entries and not self._cache_touched_keys:
            return
        self._ensure_cache_loaded()
        conn = self._cache_conn
        if conn is None:
            self._cache_pending_entries.clear()
            self._cache_touched_keys.clear()
            return

        now = int(time.time())
        pending_keys = set(self._cache_pending_entries)
        touch_keys = [
            key for key in self._cache_touched_keys if key not in pending_keys
        ]
        try:
            with conn:
                if touch_keys:
                    conn.executemany(
                        "UPDATE analysis_cache SET updated_at = ? WHERE cache_key = ?",
                        [(now, key) for key in touch_keys],
                    )
                if self._cache_pending_entries:
                    conn.executemany(
                        """
                        INSERT INTO analysis_cache (cache_key, result_json, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(cache_key)
                        DO UPDATE SET
                            result_json = excluded.result_json,
                            updated_at = excluded.updated_at
                        """,
                        [
                            (key, value, now)
                            for key, value in self._cache_pending_entries.items()
                        ],
                    )
                self._prune_cache(conn)
            self._cache_pending_entries.clear()
            self._cache_touched_keys.clear()
        except Exception as exc:
            logger.debug(
                "Failed to flush analyze LLM cache %s: %s",
                self._cache_path(),
                exc,
            )

    def analyze_search_hits(
        self,
        query: str,
        results: list[tuple[Document, float]],
    ) -> list[AnalysisResultDict]:
        """Run LLM analysis on search hits (limited subset)."""
        if not results:
            return []

        docs: list[Document] = []
        inputs: list[AnalysisInput] = []

        for doc, score in results:
            meta = doc.metadata or {}
            meta = {
                **meta,
                "matched_queries": [
                    {"query": query, "score": float(score)},
                ],
            }
            doc.metadata = meta
            symbol_value = meta.get("symbol")
            symbol = (
                symbol_value
                if isinstance(symbol_value, str) and symbol_value
                else (self.symbols[0] if self.symbols else "<unknown>")
            )
            topic_hits_value = meta.get("topic_hits")
            topic_hits = (
                [str(hit) for hit in topic_hits_value]
                if isinstance(topic_hits_value, list)
                else None
            )
            inputs.append(
                AnalysisInput(
                    symbol=symbol,
                    chunk=doc.page_content,
                    matched_query=query,
                    matched_queries=[query],
                    context=self._build_context(doc),
                    topic_hits=topic_hits,
                    analysis_instructions=self.analysis_instructions,
                )
            )
            docs.append(doc)

        analyzed_results = self._process_batch(inputs, docs)
        self._flush_cache()
        return analyzed_results

    def _process_batch(
        self, batch: list[AnalysisInput], docs: list[Document]
    ) -> list[AnalysisResultDict]:
        """Run batch analysis, falling back to per-item execution when needed."""
        if not batch:
            raise ValueError("Cannot process empty batch")
        if len(batch) != len(docs):
            raise ValueError(
                f"Batch size mismatch: {len(batch)} inputs vs {len(docs)} docs"
            )

        cache_path = self._cache_path()
        if cache_path is None:
            model_results = self._invoke_batch_models(batch)
            return self._format_model_results(batch, docs, model_results)

        formatted_results: list[AnalysisResultDict | None] = []
        for _ in batch:
            formatted_results.append(None)
        cached_results = self._lookup_cached_results(batch)
        missing_indices: list[int] = []
        missing_items: list[AnalysisInput] = []
        missing_docs: list[Document] = []

        for idx, (item, doc) in enumerate(zip(batch, docs, strict=True)):
            cached_result = cached_results.get(self._cache_key(item))
            if cached_result is None:
                missing_indices.append(idx)
                missing_items.append(item)
                missing_docs.append(doc)
                continue
            formatted_results[idx] = self._format_result(cached_result, doc)

        if missing_items:
            model_results = self._invoke_batch_models(missing_items)
            freshly_formatted = self._format_model_results(
                missing_items,
                missing_docs,
                model_results,
                cache_items=missing_items,
            )
            for idx, payload in zip(
                missing_indices, freshly_formatted, strict=True
            ):
                formatted_results[idx] = payload

        return [item for item in formatted_results if item is not None]

    def _invoke_batch_models(
        self, batch: list[AnalysisInput]
    ) -> list[AnalysisResult | Exception]:
        """Invoke all configured batch models for the current batch."""
        if not self.ensemble_graphs:
            return self._invoke_batch_for_graph(
                graph=self.graph,
                batch=batch,
                label="primary",
            )

        per_model_results: list[list[AnalysisResult | Exception]] = []
        per_model_results.append(
            self._invoke_batch_for_graph(
                graph=self.graph,
                batch=batch,
                label="primary",
            )
        )
        for idx, ensemble_graph in enumerate(self.ensemble_graphs):
            label = (
                self.ensemble_model_names[idx]
                if idx < len(self.ensemble_model_names)
                else f"ensemble-{idx + 1}"
            )
            per_model_results.append(
                self._invoke_batch_for_graph(
                    graph=ensemble_graph,
                    batch=batch,
                    label=label,
                )
            )

        return self._aggregate_ensemble_results(per_model_results)

    def _invoke_batch_for_graph(
        self,
        *,
        graph: Runnable[AnalysisInput, AnalysisResult],
        batch: list[AnalysisInput],
        label: str,
    ) -> list[AnalysisResult | Exception]:
        """Invoke one graph for the current batch payload."""
        config_callbacks = self._build_runnable_config(include_run_id=False)
        attempts = self.llm_retry_attempts + 1
        backoff = self.llm_retry_backoff

        for attempt in range(attempts):
            try:
                results = graph.batch(batch, config=config_callbacks)
                if len(results) != len(batch):
                    raise RuntimeError(
                        f"{label} batch result length mismatch: "
                        f"{len(results)} results for {len(batch)} inputs"
                    )
                return list(results)
            except Exception as e:
                if attempt < attempts - 1:
                    logger.warning(
                        "%s batch failed (attempt %d/%d): %s. Retrying after %.1fs...",
                        label,
                        attempt + 1,
                        attempts,
                        e,
                        backoff,
                    )
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = None
                    if loop is not None and loop.is_running():
                        # Inside an async context — yield to the event loop.
                        import concurrent.futures

                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=1
                        ) as pool:
                            loop.run_in_executor(pool, time.sleep, backoff)
                    else:
                        time.sleep(backoff)
                    backoff *= 2
                    continue
                logger.warning(
                    "%s batch failed after %d attempts: %s. Processing items individually...",
                    label,
                    attempts,
                    e,
                )
                return [
                    self._invoke_single_model_for_graph(
                        item,
                        graph=graph,
                        label=label,
                    )
                    for item in batch
                ]
        return []

    def _aggregate_ensemble_results(
        self,
        per_model_results: list[list[AnalysisResult | Exception]],
    ) -> list[AnalysisResult | Exception]:
        """Aggregate ensemble model outputs into one result set."""
        if not per_model_results:
            return []

        size = len(per_model_results[0])
        aggregated: list[AnalysisResult | Exception] = []
        for idx in range(size):
            successful: list[AnalysisResult] = []
            first_error: Exception | None = None
            for model_results in per_model_results:
                payload = model_results[idx]
                if isinstance(payload, Exception):
                    if first_error is None:
                        first_error = payload
                    continue
                successful.append(payload)

            if not successful:
                aggregated.append(
                    first_error
                    if first_error is not None
                    else RuntimeError("All ensemble models failed")
                )
                continue

            anchor = self._select_anchor_result(successful)
            relevant_votes = sum(1 for item in successful if item.is_relevant)
            total_votes = len(successful)
            majority_is_relevant = relevant_votes >= (total_votes / 2.0)
            confidence_values = [
                float(item.confidence_score)
                for item in successful
                if item.confidence_score is not None
            ]
            confidence = (
                sum(confidence_values) / len(confidence_values)
                if confidence_values
                else anchor.confidence_score
            )
            aggregated.append(
                anchor.model_copy(
                    update={
                        "is_relevant": majority_is_relevant,
                        "confidence_score": confidence,
                    }
                )
            )

        return aggregated

    @staticmethod
    def _select_anchor_result(results: list[AnalysisResult]) -> AnalysisResult:
        """Select anchor result."""
        anchor = results[0]
        anchor_score = (
            float(anchor.confidence_score)
            if anchor.confidence_score is not None
            else -1.0
        )
        for result in results[1:]:
            score = (
                float(result.confidence_score)
                if result.confidence_score is not None
                else -1.0
            )
            if score > anchor_score:
                anchor = result
                anchor_score = score
        return anchor

    def _format_model_results(
        self,
        batch: list[AnalysisInput],
        docs: list[Document],
        results: list[AnalysisResult | Exception],
        *,
        cache_items: list[AnalysisInput] | None = None,
    ) -> list[AnalysisResultDict]:
        """Format model results."""
        formatted_results: list[AnalysisResultDict] = []
        cache_candidates = cache_items if cache_items is not None else []
        for idx, (item, doc, result) in enumerate(
            zip(batch, docs, results, strict=True)
        ):
            if isinstance(result, Exception):
                formatted_results.append(
                    self._create_error_result(item, doc, result)
                )
                continue
            if cache_candidates:
                self._store_cached_result(
                    item=cache_candidates[idx], result=result
                )
            formatted_results.append(self._format_result(result, doc))
        return formatted_results

    def _process_single_item(
        self, item: AnalysisInput, doc: Document
    ) -> AnalysisResultDict:
        """Analyze one item and return a normalized result payload."""
        result = self._invoke_single_model(item)
        if isinstance(result, Exception):
            return self._create_error_result(item, doc, result)
        return self._format_result(result, doc)

    def _invoke_single_model(
        self, item: AnalysisInput
    ) -> AnalysisResult | Exception:
        """Invoke one model for a single analysis item."""
        return self._invoke_single_model_for_graph(
            item,
            graph=self.graph,
            label="primary",
        )

    def _invoke_single_model_for_graph(
        self,
        item: AnalysisInput,
        *,
        graph: Runnable[AnalysisInput, AnalysisResult],
        label: str,
    ) -> AnalysisResult | Exception:
        """Invoke one graph for a single analysis item."""
        try:
            config_callbacks = self._build_runnable_config(include_run_id=True)
            return graph.invoke(item, config=config_callbacks)
        except Exception as e:
            logger.error("%s item processing failed: %s", label, e)
            return e

    @staticmethod
    def _build_context(doc: Document) -> str | None:
        """Assemble contextual hints for the LLM."""
        context_parts: list[str] = []
        section = (doc.metadata or {}).get("section_number")
        if section:
            context_parts.append(f"section: {section}")

        topic_hits = (doc.metadata or {}).get("topic_hits")
        if topic_hits:
            context_parts.append("topics: " + ", ".join(topic_hits[:5]))

        market_hint = (doc.metadata or {}).get("market_enrichment_context")
        if isinstance(market_hint, str) and market_hint:
            context_parts.append(market_hint)

        return " | ".join(context_parts) if context_parts else None

    @staticmethod
    def _build_matched_query_list(
        matched_queries: list[dict[str, float | str]],
    ) -> list[str] | None:
        """Build matched query list."""
        queries: list[str] = []
        seen: set[str] = set()
        for item in matched_queries:
            query = item.get("query")
            if not isinstance(query, str):
                continue
            cleaned = query.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            queries.append(cleaned)
            if len(queries) >= 3:
                break
        return queries or None

    def _select_primary_query(
        self,
        matched_queries: list[dict[str, float | str]],
        content: str | None,
    ) -> str | None:
        """Select primary query."""
        if not matched_queries:
            return None
        best_query: str | None = None
        best_ratio = -1.0
        for item in matched_queries:
            query = item.get("query")
            if not isinstance(query, str):
                continue
            cleaned = query.strip()
            if not cleaned:
                continue
            _, _, ratio = query_term_overlap(
                cleaned,
                content,
                min_len=self.query_term_min_len,
            )
            if ratio > best_ratio:
                best_ratio = ratio
                best_query = cleaned
        if best_query is not None:
            return best_query
        first_query = matched_queries[0].get("query")
        return (
            str(first_query).strip()
            if isinstance(first_query, str) and first_query.strip()
            else None
        )

    @classmethod
    def _has_numeric_signal(cls, *values: str | None) -> bool:
        """Return whether numeric signal."""
        for value in values:
            if value and NUMERIC_SIGNAL_RE.search(value):
                return True
        return False

    def _calibrate_confidence(
        self,
        *,
        llm_confidence: float | None,
        is_relevant: bool,
        matched_terms: list[str],
        missing_terms: list[str],
        overlap_ratio: float,
        result: AnalysisResult,
    ) -> float | None:
        """Calibrate confidence scores for returned analysis results."""
        if llm_confidence is None and not matched_terms and not missing_terms:
            return None

        score = 0.2 + (0.6 * overlap_ratio)
        if result.source_excerpt or result.evidence_spans:
            score += 0.1
        key_points = "; ".join(result.key_points or []) or None
        if self._has_numeric_signal(result.summary, key_points):
            score += 0.1
        if result.binding_status == "binding":
            score += 0.05
        elif result.binding_status == "non_binding":
            score -= 0.05
        if missing_terms:
            score -= 0.15
        if not is_relevant:
            score = min(score, 0.4)
        score = max(0.05, min(score, 0.99))
        return score

    @staticmethod
    def _extract_matched_queries(
        metadata: MetadataRecord | None,
    ) -> list[dict[str, float | str]]:
        """Extract matched queries."""
        raw_matches = (metadata or {}).get("matched_queries")
        if isinstance(raw_matches, list):
            cleaned: list[dict[str, float | str]] = []
            for item in raw_matches:
                if not isinstance(item, dict):
                    continue
                query = item.get("query")
                score = item.get("score")
                if not isinstance(query, str) or not query.strip():
                    continue
                payload: dict[str, float | str] = {"query": query.strip()}
                if isinstance(score, (int, float)):
                    payload["score"] = float(score)
                cleaned.append(payload)
            return cleaned

        query = (metadata or {}).get("search_query")
        if isinstance(query, str) and query.strip():
            payload: dict[str, float | str] = {"query": query.strip()}
            score = (metadata or {}).get("search_score")
            if isinstance(score, (int, float)):
                payload["score"] = float(score)
            return [payload]
        return []

    def _format_result(
        self, result: AnalysisResult, doc: Document
    ) -> AnalysisResultDict:
        """Format result."""
        source_metadata: MetadataRecord = {
            **(doc.metadata or {}),
            "accession_number": get_accession_from_metadata(doc.metadata),
        }
        matched_queries = self._extract_matched_queries(source_metadata)
        primary_query = self._select_primary_query(
            matched_queries, doc.page_content
        )
        query_match_terms, missing_query_terms, overlap_ratio = (
            query_term_overlap(
                primary_query,
                doc.page_content,
                min_len=self.query_term_min_len,
            )
        )
        for key in ("matched_queries", "search_query", "search_score"):
            source_metadata.pop(key, None)
        is_relevant = result.is_relevant
        if primary_query and not query_match_terms and is_relevant:
            is_relevant = False

        confidence_score = result.confidence_score
        if self.confidence_mode == "calibrated":
            calibrated = self._calibrate_confidence(
                llm_confidence=confidence_score,
                is_relevant=is_relevant,
                matched_terms=query_match_terms,
                missing_terms=missing_query_terms,
                overlap_ratio=overlap_ratio,
                result=result,
            )
            if calibrated is not None:
                if confidence_score is None:
                    confidence_score = calibrated
                else:
                    confidence_score = min(float(confidence_score), calibrated)

        if not self.compact_result_output:
            result_dict: AnalysisResultDict = {
                "is_relevant": is_relevant,
                "confidence_score": confidence_score,
                "summary": result.summary,
                "key_points": result.key_points,
                "reasoning": result.reasoning,
                "query_match_terms": query_match_terms,
                "missing_query_terms": missing_query_terms,
                "binding_status": result.binding_status,
                "contingencies": result.contingencies,
                "impact_channels": result.impact_channels,
                "impact_direction": result.impact_direction,
                "impact_magnitude": result.impact_magnitude,
                "impact_horizon": result.impact_horizon,
                "impact_confidence": result.impact_confidence,
                "impact_rationale": result.impact_rationale,
                "extracted_entities": result.extracted_entities,
                "compensation_data": result.compensation_data,
                "proposal_info": result.proposal_info,
                "performance_metrics": result.performance_metrics,
                "peer_set": result.peer_set,
                "pay_for_performance_flags": result.pay_for_performance_flags,
                "tags": result.tags,
                "evidence_spans": result.evidence_spans,
                "source_excerpt": result.source_excerpt,
                "severity": result.severity,
                "sentiment": result.sentiment,
                "forward_looking": result.forward_looking,
                "follow_up_questions": result.follow_up_questions,
                "source_metadata": source_metadata,
            }
            if matched_queries:
                result_dict["matched_queries"] = matched_queries
            if self.include_raw_chunks:
                result_dict["raw_chunk"] = doc.page_content
            return result_dict

        selected = self._selected_output_fields()
        compact: AnalysisResultDict = {
            "is_relevant": is_relevant,
            "source_metadata": source_metadata,
        }
        if confidence_score is not None:
            compact["confidence_score"] = confidence_score
        if matched_queries:
            compact["matched_queries"] = matched_queries

        if "summary" in selected and result.summary:
            compact["summary"] = result.summary
        if "key_points" in selected and result.key_points:
            compact["key_points"] = result.key_points
        if "reasoning" in selected and result.reasoning:
            compact["reasoning"] = result.reasoning
        if "query_match_terms" in selected and query_match_terms:
            compact["query_match_terms"] = query_match_terms
        if "missing_query_terms" in selected and missing_query_terms:
            compact["missing_query_terms"] = missing_query_terms
        if "binding_status" in selected and result.binding_status:
            compact["binding_status"] = result.binding_status
        if "contingencies" in selected and result.contingencies:
            compact["contingencies"] = result.contingencies
        if "impact_channels" in selected and result.impact_channels:
            compact["impact_channels"] = result.impact_channels
        if "impact_direction" in selected and result.impact_direction:
            compact["impact_direction"] = result.impact_direction
        if "impact_magnitude" in selected and result.impact_magnitude:
            compact["impact_magnitude"] = result.impact_magnitude
        if "impact_horizon" in selected and result.impact_horizon:
            compact["impact_horizon"] = result.impact_horizon
        if (
            "impact_confidence" in selected
            and result.impact_confidence is not None
        ):
            compact["impact_confidence"] = result.impact_confidence
        if "impact_rationale" in selected and result.impact_rationale:
            compact["impact_rationale"] = result.impact_rationale
        if "extracted_entities" in selected and result.extracted_entities:
            compact["extracted_entities"] = result.extracted_entities
        if (
            "compensation_data" in selected
            and result.compensation_data is not None
        ):
            compact["compensation_data"] = result.compensation_data
        if "proposal_info" in selected and result.proposal_info is not None:
            compact["proposal_info"] = result.proposal_info
        if "performance_metrics" in selected and result.performance_metrics:
            compact["performance_metrics"] = result.performance_metrics
        if "peer_set" in selected and result.peer_set:
            compact["peer_set"] = result.peer_set
        if (
            "pay_for_performance_flags" in selected
            and result.pay_for_performance_flags
        ):
            compact["pay_for_performance_flags"] = (
                result.pay_for_performance_flags
            )
        if "tags" in selected and result.tags:
            compact["tags"] = result.tags
        if "evidence_spans" in selected and result.evidence_spans:
            compact["evidence_spans"] = result.evidence_spans
        if "source_excerpt" in selected and result.source_excerpt:
            compact["source_excerpt"] = result.source_excerpt
        if "severity" in selected and result.severity:
            compact["severity"] = result.severity
        if "sentiment" in selected and result.sentiment:
            compact["sentiment"] = result.sentiment
        if "forward_looking" in selected:
            compact["forward_looking"] = result.forward_looking
        if "follow_up_questions" in selected and result.follow_up_questions:
            compact["follow_up_questions"] = result.follow_up_questions
        if self.include_raw_chunks and "raw_chunk" in selected:
            compact["raw_chunk"] = doc.page_content
        return compact

    def _create_error_result(
        self, item: AnalysisInput, doc: Document, error: Exception
    ) -> AnalysisResultDict:
        """Create an error result dict for a failed item."""
        chunk_preview = (
            item.chunk[:100] + "..." if len(item.chunk) > 100 else item.chunk
        )

        source_metadata: MetadataRecord = {
            **(doc.metadata or {}),
            "accession_number": get_accession_from_metadata(doc.metadata),
        }
        matched_queries = self._extract_matched_queries(source_metadata)
        for key in ("matched_queries", "search_query", "search_score"):
            source_metadata.pop(key, None)
        return {
            "error": "Processing failed",
            "exception": f"{type(error).__name__}: {error}",
            "chunk_preview": chunk_preview,
            "source_metadata": source_metadata,
            **({"matched_queries": matched_queries} if matched_queries else {}),
            **({"raw_chunk": item.chunk} if self.include_raw_chunks else {}),
        }

    def _build_runnable_config(
        self, *, include_run_id: bool
    ) -> RunnableConfig | None:
        """Build runnable config."""
        config: RunnableConfig = {}
        if self.callbacks:
            config["callbacks"] = self.callbacks
        if self.run_id is not None:
            config["metadata"] = {"pipeline_run_id": str(self.run_id)}
            if include_run_id:
                config["run_id"] = self.run_id
        return config or None
