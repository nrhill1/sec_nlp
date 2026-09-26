# src/sec_nlp/pipelines/presets/analyze/steps/indexing/vector_index.py
"""Vector indexing utilities for the analyze pipeline.

The indexer filters duplicate chunks locally, batches remote existence checks
against Qdrant, and only submits new symbol-scoped chunks for embedding and
storage.
"""

from __future__ import annotations

from time import perf_counter

from langchain_qdrant import QdrantVectorStore

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.deduplication import SimHashDeduplicator
from sec_nlp.pipelines.types import MetadataRecord
from sec_nlp.pipelines.vector.query import scroll_records

from ...config import AnalyzeConfig
from ...types import Timings

_SIMHASH_SCROLL_BATCH_SIZE = 128


class VectorIndexer:
    """Handle chunk indexing into the vector store."""

    def __init__(
        self,
        *,
        config: AnalyzeConfig,
        vector_store: QdrantVectorStore | None,
        deduplicator: SimHashDeduplicator,
    ) -> None:
        """Initialize vector-index manager with configured vector store backend."""
        self.config = config
        self.vector_store = vector_store
        self.deduplicator = deduplicator

    def index(self, symbol: str, docs: list[Document], timings: Timings) -> int:
        """Store chunks in the vector store (deduped) before analysis."""
        if self.vector_store is None:
            logger.debug(
                "Vector store not initialized; skipping indexing for %s", symbol
            )
            return 0

        t_store_start = perf_counter()
        vstore = self.vector_store
        candidates: list[tuple[Document, MetadataRecord, int | None]] = []
        unique_hashes: list[int] = []
        seen_hashes: set[int] = set()
        to_store: list[Document] = []

        for doc in docs:
            base_meta = dict(doc.metadata or {})
            content = doc.page_content or ""

            is_unique, hash_value = self.deduplicator.add_if_unique(content)
            if not is_unique:
                continue

            candidates.append((doc, base_meta, hash_value))
            if hash_value is None or hash_value in seen_hashes:
                continue
            seen_hashes.add(hash_value)
            unique_hashes.append(hash_value)

        existing_hashes = self._existing_simhashes(
            simhashes=unique_hashes,
            symbol=symbol,
        )

        for doc, base_meta, hash_value in candidates:
            if hash_value is not None and hash_value in existing_hashes:
                continue
            doc.metadata.update(
                {
                    **base_meta,
                    "symbol": symbol,
                    "simhash": hash_value,
                }
            )
            to_store.append(doc)

        if not to_store:
            logger.info(
                "No new chunks to index for %s (all duplicates or empty)",
                symbol,
            )
            return 0

        duplicates = len(docs) - len(to_store)
        logger.info(
            "Prepared %d/%d chunks for indexing for %s (deduped=%d)",
            len(to_store),
            len(docs),
            symbol,
            max(duplicates, 0),
        )

        from sec_nlp.adapters.documents import to_langchain

        vstore.add_documents(documents=[to_langchain(doc) for doc in to_store])
        timings["store"] = perf_counter() - t_store_start
        added = len(to_store)
        collection = vstore.collection_name
        if collection:
            logger.info(
                "Indexed %d chunks for %s (collection=%s)",
                added,
                symbol,
                collection,
            )
        return added

    def _existing_simhashes(
        self,
        *,
        simhashes: list[int],
        symbol: str,
    ) -> set[int]:
        """Return the subset of simhash values already present in Qdrant."""
        if not simhashes:
            return set()
        try:
            vstore = self.vector_store
            if not vstore:
                return set()
            try:
                client = vstore.client
                collection = vstore.collection_name
            except AttributeError:
                return set()
            if not client or not collection:
                return set()

            existing: set[int] = set()
            for start in range(0, len(simhashes), _SIMHASH_SCROLL_BATCH_SIZE):
                batch = simhashes[start : start + _SIMHASH_SCROLL_BATCH_SIZE]
                records = scroll_records(
                    client,
                    collection,
                    {"simhash": batch, "symbol": [symbol]},
                    limit=max(len(batch), 1),
                )
                for record in records:
                    payload = record.payload
                    if not isinstance(payload, dict):
                        continue
                    metadata = payload.get("metadata")
                    if not isinstance(metadata, dict):
                        continue
                    simhash_value = metadata.get("simhash")
                    if isinstance(simhash_value, int):
                        existing.add(simhash_value)
            return existing
        except Exception as exc:
            logger.debug(
                "simhash existence check failed for %s: %s",
                symbol,
                exc,
            )
            return set()
