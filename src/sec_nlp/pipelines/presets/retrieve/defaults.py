# src/sec_nlp/pipelines/presets/retrieve/defaults.py
"""Shared default model and collection constants for the retrieve pipeline.

These defaults are imported by both retrieve and chat so the embedding model,
vector size, and collection name stay aligned across indexing and query-time
retrieval. The collection name is versioned to avoid mixing new embeddings
with older retrieve collections.
"""

DEFAULT_RETRIEVE_COLLECTION_NAME: str = "retrieve_bge_m3"
DEFAULT_RETRIEVE_EMBEDDING_MODEL: str = "bge-m3"
DEFAULT_RETRIEVE_VECTOR_SIZE: int = 1024
