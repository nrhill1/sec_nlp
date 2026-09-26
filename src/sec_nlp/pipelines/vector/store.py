# src/sec_nlp/pipelines/vector/store.py
"""Shared vector-store utilities for pipelines."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from langchain_qdrant import QdrantVectorStore

from sec_nlp.core.documents import DocumentRecord as Document


def upload_documents(
    *,
    vector_store: QdrantVectorStore,
    documents: Iterable[Document],
    batch_size: int = 32,
) -> None:
    """Upload internal records to the optional vector adapter in bounded batches.

    Args:
        vector_store: Configured vector backend selected by the caller.
        documents: Source records whose provenance must survive indexing.
        batch_size: Maximum records sent in one insertion request.
    """
    from sec_nlp.adapters.documents import to_langchain

    docs: list[Document] = list(documents)
    if not docs:
        return

    ids: list[str] = [uuid4().hex for _ in range(len(docs))]
    for start in range(0, len(docs), batch_size):
        end = start + batch_size
        vector_store.add_documents(
            documents=[to_langchain(doc) for doc in docs[start:end]],
            ids=ids[start:end],
        )
