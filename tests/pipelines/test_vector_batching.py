# tests/pipelines/test_vector_batching.py
"""Test vector database batching optimizations."""

from unittest.mock import Mock

import pytest

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.pipelines.vector.config import VectorConfig
from tests.utils.typing import Benchmark


class TestVectorBatching:
    """Test vector database batching."""

    @pytest.fixture
    def vector_config(self) -> VectorConfig:
        """Create vector config with batching settings."""
        return VectorConfig(
            embedding_batch_size=32,
        )

    def test_batch_embed_documents_respects_batch_size(
        self, vector_config: VectorConfig
    ) -> None:
        """Test that batching respects configured size."""
        mock_embedder = Mock()
        mock_embedder.embed_documents.return_value = [[0.1] * 1024] * 10

        texts = [f"Text {i}" for i in range(100)]

        embeddings = vector_config.batch_embed_documents(
            mock_embedder,
            texts,
            show_progress=False,
        )

        # Should make ceil(100/32) = 4 calls
        assert mock_embedder.embed_documents.call_count == 4
        assert len(embeddings) == 100

    def test_batch_embed_documents_empty_list(
        self, vector_config: VectorConfig
    ) -> None:
        """Test handling of empty text list."""
        mock_embedder = Mock()

        embeddings = vector_config.batch_embed_documents(
            mock_embedder,
            [],
            show_progress=False,
        )

        assert len(embeddings) == 0
        mock_embedder.embed_documents.assert_not_called()

    def test_batch_embed_documents_handles_errors(
        self, vector_config: VectorConfig
    ) -> None:
        """Test error handling during embedding."""
        mock_embedder = Mock()
        mock_embedder.embed_documents.side_effect = [
            [[0.1] * 1024] * 32,  # First batch succeeds
            Exception("Embedding failed"),  # Second batch fails
            [[0.1] * 1024] * 32,  # Third batch succeeds
        ]

        texts = [f"Text {i}" for i in range(96)]  # 3 batches of 32

        embeddings = vector_config.batch_embed_documents(
            mock_embedder,
            texts,
            show_progress=False,
        )

        # Should have embeddings from successful batches + empty from failed
        assert mock_embedder.embed_documents.call_count == 3
        assert len(embeddings) == 96
        assert embeddings[32:64] == [[]] * 32

    def test_batch_add_to_vector_store(
        self, vector_config: VectorConfig
    ) -> None:
        """Test batched vector store operations."""
        mock_vector_store = Mock()
        mock_vector_store.add_documents.return_value = ["id1", "id2"]

        mock_docs = [Document(page_content=f"text {i}") for i in range(50)]

        ids = vector_config.batch_add_to_vector_store(
            mock_vector_store,
            mock_docs,
            show_progress=False,
        )

        # Should batch the operations
        assert (
            mock_vector_store.add_documents.call_count == 2
        )  # 50/32 = 2 batches
        assert len(ids) > 0

    def test_batch_add_to_vector_store_empty_list(
        self, vector_config: VectorConfig
    ) -> None:
        """Test handling of empty document list."""
        mock_vector_store = Mock()

        ids = vector_config.batch_add_to_vector_store(
            mock_vector_store,
            [],
            show_progress=False,
        )

        assert len(ids) == 0
        mock_vector_store.add_documents.assert_not_called()

    def test_batch_add_to_vector_store_handles_errors(
        self, vector_config: VectorConfig
    ) -> None:
        """Test error handling during vector store operations."""
        mock_vector_store = Mock()
        mock_vector_store.add_documents.side_effect = [
            ["id1", "id2"],  # First batch succeeds
            Exception("Add failed"),  # Second batch fails
        ]

        mock_docs = [
            Document(page_content=f"text {i}") for i in range(64)
        ]  # 2 batches of 32

        ids = vector_config.batch_add_to_vector_store(
            mock_vector_store,
            mock_docs,
            show_progress=False,
        )

        # Should have IDs from successful batch
        assert len(ids) == 2
        assert mock_vector_store.add_documents.call_count == 2

    def test_batch_size_validation(self) -> None:
        """Test that batch size is validated."""
        config = VectorConfig(embedding_batch_size=1)
        assert config.embedding_batch_size == 1

        config = VectorConfig(embedding_batch_size=100)
        assert config.embedding_batch_size == 100

    def test_single_batch_not_split(self, vector_config: VectorConfig) -> None:
        """Test that small lists use single batch."""
        mock_embedder = Mock()
        mock_embedder.embed_documents.return_value = [[0.1] * 1024] * 10

        texts = [f"Text {i}" for i in range(10)]  # Less than batch size

        embeddings = vector_config.batch_embed_documents(
            mock_embedder,
            texts,
            show_progress=False,
        )

        assert mock_embedder.embed_documents.call_count == 1
        assert len(embeddings) == 10

    def test_batching_performance(
        self, vector_config: VectorConfig, benchmark: Benchmark
    ) -> None:
        """Benchmark batching vs unbatched."""
        mock_embedder = Mock()
        mock_embedder.embed_documents.return_value = [[0.1] * 1024] * 32

        texts = [f"Text {i}" for i in range(128)]

        result = benchmark(
            vector_config.batch_embed_documents,
            mock_embedder,
            texts,
            show_progress=False,
        )

        assert len(result) == 128


class TestVectorConfigSetup:
    """Test VectorConfig setup methods."""

    def test_config_defaults(self) -> None:
        """Test default configuration values."""
        config = VectorConfig()

        assert config.embedding_batch_size == 32
        assert config.embedding_model == "granite-embedding:30m"
        assert config.qdrant_port == 6333

    def test_config_custom_values(self) -> None:
        """Test custom configuration values."""
        config = VectorConfig(
            embedding_batch_size=64,
            embedding_model="custom-model",
            qdrant_port=7000,
        )

        assert config.embedding_batch_size == 64
        assert config.embedding_model == "custom-model"
        assert config.qdrant_port == 7000
