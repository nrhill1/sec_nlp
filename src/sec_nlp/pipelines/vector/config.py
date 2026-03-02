# src/sec_nlp/pipelines/vector/config.py
"""Vector database configuration and operations for pipelines."""

import os
from collections.abc import Iterable
from threading import Lock
from typing import Literal
from uuid import uuid4

from langchain_core.documents import Document
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, ConfigDict, Field, field_validator
from qdrant_client import QdrantClient
from qdrant_client.models import Distance
from tqdm import tqdm

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.llm.ollama import resolve_ollama_base_url
from sec_nlp.pipelines.vector.client import (
    create_qdrant_client,
    format_qdrant_endpoint,
)

type EmbedderCacheKey = tuple[str, str | None]
type QdrantClientCacheKey = tuple[
    str | None,
    str | None,
    str,
    int,
    int,
    str | None,
    bool,
    bool,
    int,
]
type QdrantClientTarget = tuple[QdrantClient, str]
type QdrantConnectionAttempt = tuple[str | None, str | None, str, bool]

_EMBEDDER_CACHE: dict[EmbedderCacheKey, tuple[OllamaEmbeddings, int]] = {}
_QDRANT_CLIENT_CACHE: dict[QdrantClientCacheKey, QdrantClient] = {}
_QDRANT_ENDPOINT_CACHE: dict[QdrantClientCacheKey, str] = {}
_EMBEDDER_CACHE_LOCK = Lock()
_QDRANT_CACHE_LOCK = Lock()
_QDRANT_DISK_FALLBACK_LOCATION = ".qdrant"


def _env_flag_enabled(name: str) -> bool:
    """Return whether an environment flag should be treated as enabled."""
    value = os.getenv(name, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def clear_runtime_caches() -> None:
    """Clear process-level embedder and Qdrant client caches."""
    with _EMBEDDER_CACHE_LOCK:
        _EMBEDDER_CACHE.clear()
    with _QDRANT_CACHE_LOCK:
        _QDRANT_CLIENT_CACHE.clear()
        _QDRANT_ENDPOINT_CACHE.clear()


class VectorConfig(BaseModel):
    """Configuration for vector database settings."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
    )

    # Collection settings
    collection_name: str | None = Field(
        default=None,
        description="Name prefix for vector database collections",
    )

    # Embedding settings
    embedding_model: str = Field(
        default="granite-embedding:30m",
        description="Sentence transformer model for embeddings",
    )
    embedding_device: str = Field(
        default="cpu",
        description="Device for embedding model (cpu, cuda, mps)",
    )
    embedding_batch_size: int = Field(
        default=32,
        ge=1,
        description="Batch size for embedding generation",
    )
    vector_size: int = Field(
        default=2048,
        ge=1,
        description="Dimension of embedding vectors (default: 2048)",
    )

    # Qdrant settings
    qdrant_location: str | None = Field(
        default=None,
        description="Local Qdrant location (e.g., ':memory:' or a storage path). "
        "Overrides host/port when set.",
    )
    qdrant_url: str | None = Field(
        default=None,
        description=(
            "Optional Qdrant server URL override "
            "(default target uses host/port, typically localhost:6333)."
        ),
    )
    qdrant_host: str = Field(
        default="localhost",
        description="Qdrant server host",
    )
    qdrant_port: int = Field(
        default=6333,
        ge=1,
        le=65535,
        description="Qdrant HTTP port",
    )
    qdrant_grpc_port: int = Field(
        default=6334,
        ge=1,
        le=65535,
        description="Qdrant gRPC port",
    )
    qdrant_api_key: str | None = Field(
        default=None,
        description="Qdrant API key for authentication",
    )
    qdrant_https: bool = Field(
        default=False,
        description="Use HTTPS for Qdrant connection",
    )
    qdrant_prefer_grpc: bool = Field(
        default=False,
        description="Prefer gRPC over HTTP",
    )
    qdrant_timeout: int = Field(
        default=60,
        ge=1,
        description="Qdrant request timeout in seconds",
    )

    # Qdrant collection configuration
    qdrant_distance: Literal["Cosine", "Euclid", "Dot"] = Field(
        default="Cosine",
        description="Distance metric for vector similarity",
    )
    qdrant_on_disk_payload: bool = Field(
        default=False,
        description="Store payload on disk to save RAM",
    )
    qdrant_replication_factor: int = Field(
        default=1,
        ge=1,
        description="Number of replicas for the collection",
    )
    qdrant_write_consistency_factor: int = Field(
        default=1,
        ge=1,
        description="Write consistency factor",
    )
    search_type: str = Field(
        default="similarity",
        description="Search type passed to vector store (e.g., similarity, mmr)",
    )

    def setup_qdrant_client(self) -> QdrantClient:
        """Initialize Qdrant client."""
        client, _target = self.setup_qdrant_client_with_target()
        return client

    def _configured_qdrant_target(self) -> str:
        """Return the configured endpoint before fallback is applied."""
        location = None if self.qdrant_url else self.qdrant_location
        return format_qdrant_endpoint(
            location=location,
            url=self.qdrant_url,
            host=self.qdrant_host,
            port=self.qdrant_port,
            https=self.qdrant_https,
        )

    def _connect_qdrant(
        self,
        *,
        location: str | None,
        url: str | None,
    ) -> QdrantClient:
        """Construct a Qdrant client and verify connectivity."""
        qdrant = create_qdrant_client(
            location=location,
            url=url,
            host=self.qdrant_host,
            port=self.qdrant_port,
            grpc_port=self.qdrant_grpc_port,
            api_key=self.qdrant_api_key,
            timeout=self.qdrant_timeout,
            prefer_grpc=self.qdrant_prefer_grpc,
            https=self.qdrant_https,
        )
        # Verify the target is usable before caching it.
        qdrant.get_collections()
        return qdrant

    def _connection_attempts(self) -> list[QdrantConnectionAttempt]:
        """Build ordered Qdrant connection attempts for this config."""
        location = None if self.qdrant_url else self.qdrant_location
        if location:
            normalized_location = location.strip()
            return [
                (normalized_location, None, normalized_location, False),
            ]

        configured_target = self._configured_qdrant_target()
        return [
            (None, self.qdrant_url, configured_target, False),
            (
                _QDRANT_DISK_FALLBACK_LOCATION,
                None,
                _QDRANT_DISK_FALLBACK_LOCATION,
                True,
            ),
            (":memory:", None, ":memory:", True),
        ]

    def setup_qdrant_client_with_target(self) -> QdrantClientTarget:
        """Initialize Qdrant client and return the resolved target string."""
        cache_key: QdrantClientCacheKey = (
            self.qdrant_location,
            self.qdrant_url,
            self.qdrant_host,
            self.qdrant_port,
            self.qdrant_grpc_port,
            self.qdrant_api_key,
            self.qdrant_https,
            self.qdrant_prefer_grpc,
            self.qdrant_timeout,
        )
        disable_cache = _env_flag_enabled("SEC_NLP_DISABLE_QDRANT_CLIENT_CACHE")
        if not disable_cache:
            with _QDRANT_CACHE_LOCK:
                cached = _QDRANT_CLIENT_CACHE.get(cache_key)
                cached_target = _QDRANT_ENDPOINT_CACHE.get(cache_key)
            if cached is not None:
                target = cached_target or self._configured_qdrant_target()
                logger.debug("Reusing cached Qdrant client at %s", target)
                return cached, target

        attempts = self._connection_attempts()
        configured_target = attempts[0][2]
        errors: list[str] = []
        for location, url, target, is_fallback in attempts:
            try:
                qdrant = self._connect_qdrant(location=location, url=url)
            except Exception as exc:
                errors.append(f"{target}: {type(exc).__name__}: {exc}")
                continue

            if is_fallback:
                logger.warning(
                    "Qdrant endpoint %s unavailable; falling back to %s",
                    configured_target,
                    target,
                )

            if not disable_cache:
                with _QDRANT_CACHE_LOCK:
                    _QDRANT_CLIENT_CACHE[cache_key] = qdrant
                    _QDRANT_ENDPOINT_CACHE[cache_key] = target

            logger.info("Connected to Qdrant at %s", target)
            return qdrant, target

        if len(attempts) == 1:
            raise RuntimeError(
                f"Cannot connect to Qdrant at {configured_target}: {errors[0]}"
            )
        joined_errors = "; ".join(errors)
        raise RuntimeError(
            "Cannot connect to configured Qdrant endpoint or local fallbacks: "
            f"{joined_errors}"
        )

    @field_validator("qdrant_location", mode="before")
    @classmethod
    def _normalize_qdrant_location(cls, value: str | None) -> str | None:
        """Treat blank strings and explicit null markers as unset."""
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {
            "",
            "none",
            "null",
        }:
            return None
        return value

    @staticmethod
    def recreate_collection_if_fresh(
        qdrant_client: QdrantClient,
        collection_name: str,
        fresh: bool,
    ) -> None:
        """Delete collection if fresh=True to ensure clean state.

        Args:
            qdrant_client: Initialized Qdrant client
            collection_name: Name of the collection
            fresh: Whether to delete existing collection
        """
        if not fresh:
            return

        try:
            if qdrant_client.collection_exists(collection_name):
                logger.info(
                    "Deleting existing Qdrant collection: %s", collection_name
                )
                qdrant_client.delete_collection(collection_name)
        except Exception as e:
            logger.warning(
                "Failed to delete collection %s: %s. Continuing anyway.",
                collection_name,
                e,
            )

    def setup_embedding_model(self) -> tuple[OllamaEmbeddings, int]:
        """Initialize Ollama embedder, probe dimension, and warmup.

        Returns:
            Tuple of (embedder, embedding_dimension).
        """
        from time import perf_counter

        cache_key: EmbedderCacheKey = (
            self.embedding_model,
            resolve_ollama_base_url(),
        )
        disable_cache = _env_flag_enabled("SEC_NLP_DISABLE_EMBEDDER_CACHE")
        if not disable_cache:
            with _EMBEDDER_CACHE_LOCK:
                cached = _EMBEDDER_CACHE.get(cache_key)
            if cached is not None:
                logger.debug(
                    "Reusing cached embedding model: %s",
                    self.embedding_model,
                )
                return cached

        logger.info("Loading embedding model: %s", self.embedding_model)

        embedder = OllamaEmbeddings(
            model=self.embedding_model,
            base_url=resolve_ollama_base_url(),
            validate_model_on_init=True,
        )

        test_embedding: list[int | float] = embedder.embed_query("test")
        embedding_dim = len(test_embedding)
        logger.info("Embedding dimension: %d", embedding_dim)

        # Warmup: run a small batch to ensure the model is fully
        # resident in GPU/CPU memory before real work begins.
        warmup_texts = [
            "SEC filing annual report revenue",
            "Risk factors and forward-looking statements",
            "Executive compensation equity awards",
        ]
        t0 = perf_counter()
        embedder.embed_documents(warmup_texts)
        warmup_elapsed = perf_counter() - t0
        logger.info(
            "Embedding warmup: %d texts in %.1fs",
            len(warmup_texts),
            warmup_elapsed,
        )

        result = (embedder, embedding_dim)
        if not disable_cache:
            with _EMBEDDER_CACHE_LOCK:
                _EMBEDDER_CACHE[cache_key] = result
        return result

    def create_vector_store(
        self,
        qdrant_client: QdrantClient,
        embedder: OllamaEmbeddings,
        collection_name: str | None = None,
    ) -> QdrantVectorStore:
        """Create a VectorStore instance with this config.

        Args:
            qdrant_client: Initialized Qdrant client
            embedder: Initialized embedding model
            collection_name: Optional explicit collection name to use; defaults
                to the configured name or a generated one.

        Returns:
            Configured VectorStore instance
        """
        distance_mapping = {
            "Cosine": Distance.COSINE,
            "Euclid": Distance.EUCLID,
            "Dot": Distance.DOT,
        }
        distance_metric: Distance = distance_mapping.get(
            self.qdrant_distance, Distance.COSINE
        )

        resolved_collection: str = (
            collection_name or self.collection_name or f"sec_nlp_{uuid4().hex}"
        )

        return QdrantVectorStore(
            client=qdrant_client,
            collection_name=resolved_collection,
            embedding=embedder,
            distance=distance_metric,
        )

    def batch_embed_documents(
        self,
        embedder: OllamaEmbeddings,
        texts: list[str],
        show_progress: bool = True,
    ) -> list[list[float]]:
        """Generate embeddings in batches for efficiency.

        Args:
            embedder: Embedding model
            texts: List of text strings to embed
            show_progress: Show progress bar

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []
        num_batches = (
            len(texts) + self.embedding_batch_size - 1
        ) // self.embedding_batch_size

        indices: Iterable[int] = range(0, len(texts), self.embedding_batch_size)
        if show_progress:
            indices = tqdm(
                indices,
                desc="Generating embeddings",
                unit="batch",
                total=num_batches,
                leave=False,
            )

        for i in indices:
            batch = texts[i : i + self.embedding_batch_size]
            try:
                batch_embeddings = embedder.embed_documents(batch)
                # Ensure alignment between inputs and outputs
                if len(batch_embeddings) < len(batch):
                    missing = len(batch) - len(batch_embeddings)
                    batch_embeddings = list(batch_embeddings) + ([[]] * missing)
                elif len(batch_embeddings) > len(batch):
                    batch_embeddings = list(batch_embeddings)[: len(batch)]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error("Failed to embed batch at index %d: %s", i, e)
                # Fill with empty embeddings to maintain alignment
                all_embeddings.extend([[] for _ in batch])

        logger.debug(
            "Generated %d embeddings in %d batches",
            len(all_embeddings),
            num_batches,
        )
        return all_embeddings

    def batch_add_to_vector_store(
        self,
        vector_store: QdrantVectorStore,
        documents: list[Document],
        show_progress: bool = True,
    ) -> list[str]:
        """Add documents to vector store in batches.

        Args:
            vector_store: Vector store instance
            documents: Documents to add
            show_progress: Show progress bar

        Returns:
            List of document IDs
        """
        if not documents:
            return []

        all_ids: list[str] = []
        num_batches = (
            len(documents) + self.embedding_batch_size - 1
        ) // self.embedding_batch_size

        indices: Iterable[int] = range(
            0, len(documents), self.embedding_batch_size
        )
        if show_progress:
            indices = tqdm(
                indices,
                desc="Adding to vector store",
                unit="batch",
                total=num_batches,
                leave=False,
            )

        for i in indices:
            batch = documents[i : i + self.embedding_batch_size]
            try:
                batch_ids = vector_store.add_documents(batch)
                all_ids.extend(batch_ids)
            except Exception as e:
                logger.error("Failed to add batch at index %d: %s", i, e)

        logger.info(
            "Added %d documents in %d batches",
            len(all_ids),
            num_batches,
        )
        return all_ids

    async def batch_embed_documents_async(
        self,
        embedder: OllamaEmbeddings,
        texts: list[str],
    ) -> list[list[float]]:
        """Generate embeddings asynchronously in batches.

        Uses the async embedding API for non-blocking operation.

        Args:
            embedder: Embedding model
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self.embedding_batch_size):
            batch = texts[i : i + self.embedding_batch_size]
            try:
                batch_embeddings = await embedder.aembed_documents(batch)
                # Ensure alignment between inputs and outputs
                if len(batch_embeddings) < len(batch):
                    missing = len(batch) - len(batch_embeddings)
                    batch_embeddings = list(batch_embeddings) + ([[]] * missing)
                elif len(batch_embeddings) > len(batch):
                    batch_embeddings = list(batch_embeddings)[: len(batch)]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error("Failed to embed batch at index %d: %s", i, e)
                all_embeddings.extend([[] for _ in batch])

        return all_embeddings

    async def batch_add_to_vector_store_async(
        self,
        vector_store: QdrantVectorStore,
        documents: list[Document],
    ) -> list[str]:
        """Add documents to vector store asynchronously in batches.

        Args:
            vector_store: Vector store instance
            documents: Documents to add

        Returns:
            List of document IDs
        """
        if not documents:
            return []

        all_ids: list[str] = []

        for i in range(0, len(documents), self.embedding_batch_size):
            batch = documents[i : i + self.embedding_batch_size]
            try:
                batch_ids = await vector_store.aadd_documents(batch)
                all_ids.extend(batch_ids)
            except Exception as e:
                logger.error("Failed to add batch at index %d: %s", i, e)

        logger.info("Added %d documents async", len(all_ids))
        return all_ids
