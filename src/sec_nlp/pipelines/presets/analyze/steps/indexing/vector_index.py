# src/sec_nlp/pipelines/presets/analyze/steps/indexing/vector_index.py
"""Vector indexing utilities for the analyze pipeline."""

from __future__ import annotations

from time import perf_counter

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.deduplication import SimHashDeduplicator
from sec_nlp.pipelines.vector.query import scroll_exists

from ...config import AnalyzeConfig
from ...types import Timings


class VectorIndexer:
    """Handle chunk indexing into the vector store."""

    def __init__(
        self,
        *,
        config: AnalyzeConfig,
        vector_store: QdrantVectorStore | None,
        deduplicator: SimHashDeduplicator,
    ) -> None:
        self.config = config
        self.vector_store = vector_store
        self.deduplicator = deduplicator

    def index(self, symbol: str, docs: list[Document], timings: Timings) -> int:
        """Store chunks in the vector store (deduped) before analysis."""
        if (
            not self.vector_store
            or self.config.vector_mode == "off"
            or not docs
        ):
            if not docs:
                logger.info(
                    "Skipping indexing for %s: no chunks after preprocessing",
                    symbol,
                )
            elif self.config.vector_mode == "off":
                logger.info(
                    "Skipping indexing for %s: vector_mode is 'off'",
                    symbol,
                )
            else:
                logger.info(
                    "Skipping indexing for %s: vector store unavailable",
                    symbol,
                )
            return 0

        t_store_start = perf_counter()
        vstore = self.vector_store
        to_store: list[Document] = []

        for doc in docs:
            base_meta = doc.metadata or {}
            content = doc.page_content or ""

            is_unique, hash_value = self.deduplicator.add_if_unique(content)
            if not is_unique:
                continue

            if hash_value is not None and self._simhash_exists(
                hash_value, symbol
            ):
                continue

            doc.metadata = {
                **base_meta,
                "symbol": symbol,
                "simhash": hash_value,
            }
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

        vstore.add_documents(documents=to_store)
        timings["store"] = perf_counter() - t_store_start
        added = len(to_store)

        try:
            collection = vstore.collection_name
            client = vstore.client
            if collection and client:
                count = client.count(collection, exact=True).count
                logger.info(
                    "Indexed %d chunks for %s (collection=%s total=%d)",
                    added,
                    symbol,
                    collection,
                    count,
                )
                return added
        except Exception:
            logger.debug("Could not fetch Qdrant count after indexing")

        return added

    def _simhash_exists(self, simhash: int, symbol: str) -> bool:
        """Check if a simhash is already stored in the collection."""
        try:
            vstore = self.vector_store
            if not vstore:
                return False
            try:
                client = vstore.client
                collection = vstore.collection_name
            except AttributeError:
                return False
            if not client or not collection:
                return False

            return scroll_exists(
                client,
                collection,
                {"simhash": [simhash], "symbol": [symbol]},
            )
        except Exception:
            return False
