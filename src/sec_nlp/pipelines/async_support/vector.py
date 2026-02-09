# src/sec_nlp/pipelines/async_support/vector.py
"""Async vector store operations for embeddings and uploads."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_qdrant import QdrantVectorStore

from sec_nlp.core.infra.logger import logger


async def embed_documents_async(
    embedder: Embeddings,
    texts: list[str],
    *,
    batch_size: int = 32,
    max_concurrent: int = 4,
) -> list[list[float]]:
    """Embed documents asynchronously with batching.

    Args:
        embedder: Embedding model to use
        texts: List of text strings to embed
        batch_size: Number of texts per batch
        max_concurrent: Maximum concurrent embedding operations

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    semaphore = asyncio.Semaphore(max_concurrent)
    all_embeddings: list[list[float]] = []

    # Split into batches
    batches = [
        texts[i : i + batch_size] for i in range(0, len(texts), batch_size)
    ]

    async def embed_batch(batch: list[str]) -> list[list[float]]:
        async with semaphore:
            # Use to_thread since most embedders are sync
            return await asyncio.to_thread(embedder.embed_documents, batch)

    # Process all batches concurrently
    batch_results = await asyncio.gather(
        *[embed_batch(batch) for batch in batches],
        return_exceptions=True,
    )

    # Flatten results
    for result in batch_results:
        if isinstance(result, BaseException):
            logger.error("Batch embedding failed: %s", result)
            raise result
        all_embeddings.extend(result)

    return all_embeddings


async def embed_query_async(embedder: Embeddings, query: str) -> list[float]:
    """Embed a query asynchronously.

    Args:
        embedder: Embedding model to use
        query: Query string to embed

    Returns:
        Embedding vector
    """
    return await asyncio.to_thread(embedder.embed_query, query)


async def upload_documents_async(
    vector_store: QdrantVectorStore,
    documents: Sequence[Document],
    *,
    batch_size: int = 32,
    max_concurrent: int = 2,
    desc: str | None = None,
) -> int:
    """Upload documents to vector store asynchronously.

    Args:
        vector_store: Qdrant vector store to upload to
        documents: Documents to upload
        batch_size: Number of documents per batch
        max_concurrent: Maximum concurrent upload operations
        desc: Optional description for logging

    Returns:
        Number of documents uploaded
    """
    if not documents:
        return 0

    semaphore = asyncio.Semaphore(max_concurrent)
    uploaded_count = 0
    total_batches = (len(documents) + batch_size - 1) // batch_size

    # Split into batches
    batches = [
        list(documents[i : i + batch_size])
        for i in range(0, len(documents), batch_size)
    ]

    async def upload_batch(batch: list[Document], batch_idx: int) -> int:
        async with semaphore:
            try:
                await asyncio.to_thread(vector_store.add_documents, batch)
                if desc:
                    logger.debug(
                        "%s: batch %d/%d (%d docs)",
                        desc,
                        batch_idx + 1,
                        total_batches,
                        len(batch),
                    )
                return len(batch)
            except Exception as e:
                logger.error(
                    "Failed to upload batch %d/%d: %s",
                    batch_idx + 1,
                    total_batches,
                    e,
                )
                raise

    results = await asyncio.gather(
        *[upload_batch(batch, i) for i, batch in enumerate(batches)],
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, BaseException):
            raise result
        uploaded_count += result

    logger.info(
        "Uploaded %d documents in %d batches",
        uploaded_count,
        len(batches),
    )

    return uploaded_count


async def search_async(
    vector_store: QdrantVectorStore,
    query: str,
    *,
    k: int = 10,
) -> list[Document]:
    """Search vector store asynchronously.

    Args:
        vector_store: Qdrant vector store to search
        query: Search query
        k: Number of results to return

    Returns:
        List of matching documents
    """
    return await asyncio.to_thread(
        vector_store.similarity_search,
        query,
        k=k,
    )


async def search_with_scores_async(
    vector_store: QdrantVectorStore,
    query: str,
    *,
    k: int = 10,
) -> list[tuple[Document, float]]:
    """Search vector store asynchronously with similarity scores.

    Args:
        vector_store: Qdrant vector store to search
        query: Search query
        k: Number of results to return

    Returns:
        List of (document, score) tuples
    """
    return await asyncio.to_thread(
        vector_store.similarity_search_with_score,
        query,
        k=k,
    )


async def search_batch_async(
    vector_store: QdrantVectorStore,
    queries: list[str],
    *,
    k: int = 10,
    max_concurrent: int = 4,
) -> dict[str, list[Document]]:
    """Search multiple queries concurrently.

    Args:
        vector_store: Qdrant vector store to search
        queries: List of search queries
        k: Number of results per query
        max_concurrent: Maximum concurrent searches

    Returns:
        Dictionary mapping query to results
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def search_one(query: str) -> tuple[str, list[Document]]:
        async with semaphore:
            search_results = await search_async(
                vector_store,
                query,
                k=k,
            )
            return query, search_results

    results = await asyncio.gather(
        *[search_one(q) for q in queries],
        return_exceptions=True,
    )

    result_dict: dict[str, list[Document]] = {}
    for result in results:
        if isinstance(result, BaseException):
            logger.error("Search failed: %s", result)
            continue
        query, docs = result
        result_dict[query] = docs

    return result_dict
