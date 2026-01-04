# src/sec_nlp/pipelines/vector/store.py
"""Shared vector-store utilities for pipelines."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import uuid4

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from tqdm import tqdm


def upload_documents(
    *,
    vector_store: QdrantVectorStore,
    documents: Iterable[Document],
    symbol: str | None = None,
    batch_size: int = 32,
    bar_color: str = "magenta",
    desc: str | None = None,
) -> None:
    """Upload documents to a vector store with a compact progress bar."""
    docs: list[Document] = list(documents)
    if not docs:
        return

    ids: list[str] = [uuid4().hex for _ in range(len(docs))]
    label: str = (
        desc or f"Uploading vectors{f' for {symbol}' if symbol else ''}"
    )

    with tqdm(
        total=len(docs),
        desc=label,
        unit="chunk",
        colour=bar_color,
        leave=False,
    ) as pbar:
        for start in range(0, len(docs), batch_size):
            end = start + batch_size
            vector_store.add_documents(
                documents=docs[start:end],
                ids=ids[start:end],
            )
            pbar.update(end - start)
