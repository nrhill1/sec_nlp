# src/sec_nlp/pipelines/presets/retrieve/__init__.py
"""Retrieve pipeline preset."""

from .bridge import RetrieveChatSeedBundle, RetrieveChatSeedChunk
from .config import RetrieveSettings
from .defaults import (
    DEFAULT_RETRIEVE_COLLECTION_NAME,
    DEFAULT_RETRIEVE_EMBEDDING_MODEL,
    DEFAULT_RETRIEVE_VECTOR_SIZE,
)
from .models import RetrievalHit, RetrieveResult
from .pipeline import RetrievePipeline

__all__: tuple[str, ...] = (
    "DEFAULT_RETRIEVE_COLLECTION_NAME",
    "DEFAULT_RETRIEVE_EMBEDDING_MODEL",
    "DEFAULT_RETRIEVE_VECTOR_SIZE",
    "RetrieveChatSeedBundle",
    "RetrieveChatSeedChunk",
    "RetrievalHit",
    "RetrievePipeline",
    "RetrieveResult",
    "RetrieveSettings",
)
