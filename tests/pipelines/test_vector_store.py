# tests/pipelines/test_vector_store.py
"""Tests for QdrantVectorStore configuration and helpers."""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

from langchain_ollama.embeddings import OllamaEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance

from sec_nlp.pipelines.vector import (
    VectorConfig,
    config as vector_config,
)


class TestVectorStoreCreation:
    """Tests around building the vector store and dependencies."""

    def test_create_vector_store_uses_provided_collection_name(self) -> None:
        """Ensure custom collection names are passed through."""
        config = VectorConfig(collection_name="custom_collection")
        fake_client: QdrantClient = Mock(spec=QdrantClient)
        fake_embedder: OllamaEmbeddings = Mock(spec=OllamaEmbeddings)

        mock_store = Mock()
        mock_store_cls = Mock(return_value=mock_store)
        with patch.object(vector_config, "QdrantVectorStore", mock_store_cls):
            store = config.create_vector_store(fake_client, fake_embedder)

        assert store is mock_store
        mock_store_cls.assert_called_once_with(
            client=fake_client,
            collection_name="custom_collection",
            embedding=fake_embedder,
            distance=Distance.COSINE,
        )

    def test_create_vector_store_accepts_override(self) -> None:
        """Override the configured collection name when provided."""
        config = VectorConfig(collection_name="config_default")
        fake_client: QdrantClient = Mock(spec=QdrantClient)
        fake_embedder: OllamaEmbeddings = Mock(spec=OllamaEmbeddings)

        mock_store = Mock()
        mock_store_cls = Mock(return_value=mock_store)
        with patch.object(vector_config, "QdrantVectorStore", mock_store_cls):
            store = config.create_vector_store(
                fake_client, fake_embedder, collection_name="override_name"
            )

        assert store is mock_store
        mock_store_cls.assert_called_once_with(
            client=fake_client,
            collection_name="override_name",
            embedding=fake_embedder,
            distance=Distance.COSINE,
        )

    def test_create_vector_store_generates_collection_prefix(self) -> None:
        """Generate a unique collection name when one is not provided."""
        config = VectorConfig(collection_name=None)
        fake_client: QdrantClient = Mock(spec=QdrantClient)
        fake_embedder: OllamaEmbeddings = Mock(spec=OllamaEmbeddings)

        mock_store_cls = Mock()
        with patch.object(vector_config, "QdrantVectorStore", mock_store_cls):
            _store = config.create_vector_store(fake_client, fake_embedder)

        collection_name = mock_store_cls.call_args.kwargs["collection_name"]
        assert collection_name.startswith("sec_nlp_")
        assert len(collection_name) > len("sec_nlp_")

    def test_setup_embedding_model_uses_configured_model(self) -> None:
        """Validate embedding model wiring and initial probe call."""
        mock_embedder_cls = Mock(return_value=Mock())
        mock_instance = mock_embedder_cls.return_value
        mock_instance.embed_query.return_value = [0.1, 0.2]

        with patch.object(vector_config, "OllamaEmbeddings", mock_embedder_cls):
            config = VectorConfig(embedding_model="custom-embedder")
            embedder, dim = config.setup_embedding_model()

        assert embedder is mock_instance
        assert dim == 2
        mock_embedder_cls.assert_called_once_with(
            model="custom-embedder", validate_model_on_init=True
        )
        mock_instance.embed_query.assert_called_once_with("test")

    def test_setup_qdrant_client_uses_url_when_provided(self) -> None:
        """Ensure URL-based clients are initialized correctly."""
        mock_client = Mock()

        with patch.object(
            vector_config, "create_qdrant_client", return_value=mock_client
        ) as mock_factory:
            config = VectorConfig(
                qdrant_url="http://qdrant.local:6333",
                qdrant_api_key="token",
                qdrant_timeout=15,
                qdrant_prefer_grpc=True,
            )

            client = config.setup_qdrant_client()

        assert client is mock_client
        mock_factory.assert_called_once_with(
            location=None,
            url="http://qdrant.local:6333",
            host="localhost",
            port=6333,
            grpc_port=6334,
            api_key="token",
            timeout=15,
            prefer_grpc=True,
            https=False,
        )

    def test_setup_qdrant_client_uses_host_settings(self) -> None:
        """Ensure host/port settings are used when URL is absent."""
        mock_client = Mock()

        with patch.object(
            vector_config, "create_qdrant_client", return_value=mock_client
        ) as mock_factory:
            config = VectorConfig(
                qdrant_url=None,
                qdrant_location=None,
                qdrant_host="example.host",
                qdrant_port=7000,
                qdrant_grpc_port=7001,
                qdrant_api_key="api-key",
                qdrant_timeout=25,
                qdrant_prefer_grpc=False,
                qdrant_https=True,
            )

            client = config.setup_qdrant_client()

        assert client is mock_client
        mock_factory.assert_called_once_with(
            location=None,
            url=None,
            host="example.host",
            port=7000,
            grpc_port=7001,
            api_key="api-key",
            timeout=25,
            prefer_grpc=False,
            https=True,
        )

    def test_setup_qdrant_client_uses_location_when_set(self) -> None:
        """Ensure embedded/location clients are initialized when provided."""
        mock_client = Mock()

        with patch.object(
            vector_config, "create_qdrant_client", return_value=mock_client
        ) as mock_factory:
            config = VectorConfig(
                qdrant_location=":memory:",
                qdrant_timeout=20,
                qdrant_prefer_grpc=True,
            )

            client = config.setup_qdrant_client()

        assert client is mock_client
        mock_factory.assert_called_once_with(
            location=":memory:",
            url=None,
            host="localhost",
            port=6333,
            grpc_port=6334,
            api_key=None,
            timeout=20,
            prefer_grpc=True,
            https=False,
        )


class TestEmbeddingAlignment:
    """Edge cases for embedding generation alignment."""

    def test_batch_embed_documents_pads_missing_embeddings(self) -> None:
        """Pad missing embeddings to keep alignment with inputs."""
        config = VectorConfig(embedding_batch_size=2)
        texts = ["a", "b", "c"]
        calls: list[list[str]] = []

        embedder = MagicMock(spec=OllamaEmbeddings)

        def embed_documents(batch: list[str]) -> list[list[float]]:
            calls.append(list(batch))
            if len(calls) == 1:
                return [[0.1]]
            return [[0.3]]

        embedder.embed_documents.side_effect = embed_documents
        embeddings = config.batch_embed_documents(
            embedder,
            texts,
            show_progress=False,
        )

        assert calls == [["a", "b"], ["c"]]
        assert embeddings == [[0.1], [], [0.3]]

    def test_batch_embed_documents_trims_extra_embeddings(self) -> None:
        """Trim extra embeddings to match the input batch length."""
        config = VectorConfig(embedding_batch_size=4)
        texts = ["only one"]
        calls: list[list[str]] = []

        embedder = MagicMock(spec=OllamaEmbeddings)

        def embed_documents(batch: list[str]) -> list[list[float]]:
            calls.append(list(batch))
            return [[0.1], [0.2]]

        embedder.embed_documents.side_effect = embed_documents
        embeddings = config.batch_embed_documents(
            embedder,
            texts,
            show_progress=False,
        )

        assert calls == [["only one"]]
        assert embeddings == [[0.1]]
