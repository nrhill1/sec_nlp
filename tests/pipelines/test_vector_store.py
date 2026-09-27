# tests/pipelines/test_vector_store.py
"""Tests for QdrantVectorStore configuration and helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from langchain_ollama.embeddings import OllamaEmbeddings
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from sec_nlp.pipelines.vector import config as vector_config
from sec_nlp.pipelines.vector.client import create_qdrant_client
from sec_nlp.pipelines.vector.config import VectorConfig


@pytest.fixture(autouse=True)
def _clear_vector_runtime_caches() -> None:
    vector_config.clear_runtime_caches()


class TestVectorStoreCreation:
    """Tests around building the vector store and dependencies."""

    def test_create_vector_store_uses_provided_collection_name(self) -> None:
        """Ensure custom collection names are passed through."""
        config = VectorConfig(collection_name="custom_collection")
        fake_client: QdrantClient = Mock(spec=QdrantClient)
        fake_embedder: OllamaEmbeddings = Mock(spec=OllamaEmbeddings)

        mock_store = Mock()
        mock_store_cls = Mock(return_value=mock_store)
        with patch("langchain_qdrant.QdrantVectorStore", mock_store_cls):
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
        with patch("langchain_qdrant.QdrantVectorStore", mock_store_cls):
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
        with patch("langchain_qdrant.QdrantVectorStore", mock_store_cls):
            _store = config.create_vector_store(fake_client, fake_embedder)

        collection_name = mock_store_cls.call_args.kwargs["collection_name"]
        assert collection_name.startswith("sec_nlp_")
        assert len(collection_name) > len("sec_nlp_")

    def test_setup_embedding_model_uses_configured_model(self) -> None:
        """Validate embedding model wiring and initial probe call."""
        mock_embedder_cls = Mock(return_value=Mock())
        mock_instance = mock_embedder_cls.return_value
        mock_instance.embed_query.return_value = [0.1, 0.2]

        with patch(
            "langchain_ollama.embeddings.OllamaEmbeddings", mock_embedder_cls
        ):
            config = VectorConfig(embedding_model="custom-embedder")
            embedder, dim = config.setup_embedding_model()

        assert embedder is mock_instance
        assert dim == 2
        mock_embedder_cls.assert_called_once_with(
            model="custom-embedder",
            base_url="http://localhost:11434",
            validate_model_on_init=True,
        )
        mock_instance.embed_query.assert_called_once_with("test")

    def test_setup_embedding_model_reuses_process_cache(self) -> None:
        mock_embedder_cls = Mock(return_value=Mock())
        mock_instance = mock_embedder_cls.return_value
        mock_instance.embed_query.return_value = [0.1, 0.2]
        mock_instance.embed_documents.return_value = [[0.1, 0.2]]

        with patch(
            "langchain_ollama.embeddings.OllamaEmbeddings", mock_embedder_cls
        ):
            config = VectorConfig(embedding_model="cache-embedder")
            first_embedder, first_dim = config.setup_embedding_model()
            second_embedder, second_dim = config.setup_embedding_model()

        assert first_embedder is second_embedder
        assert first_dim == second_dim == 2
        mock_embedder_cls.assert_called_once()

    def test_setup_qdrant_client_uses_url_when_provided(self) -> None:
        """Ensure URL-based clients are initialized correctly."""
        mock_client = Mock()

        with patch(
            "sec_nlp.pipelines.vector.client.create_qdrant_client",
            return_value=mock_client,
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

        with patch(
            "sec_nlp.pipelines.vector.client.create_qdrant_client",
            return_value=mock_client,
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

        with patch(
            "sec_nlp.pipelines.vector.client.create_qdrant_client",
            return_value=mock_client,
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

    def test_setup_qdrant_client_reuses_process_cache(self) -> None:
        mock_client = Mock()

        with patch(
            "sec_nlp.pipelines.vector.client.create_qdrant_client",
            return_value=mock_client,
        ) as mock_factory:
            config = VectorConfig(qdrant_url="http://cached-qdrant:6333")
            first_client = config.setup_qdrant_client()
            second_client = config.setup_qdrant_client()

        assert first_client is second_client
        mock_factory.assert_called_once()

    def test_setup_qdrant_client_falls_back_to_disk(self) -> None:
        """Fallback to `.qdrant` when remote host endpoint is unavailable."""
        remote_client = Mock()
        remote_client.get_collections.side_effect = RuntimeError(
            "Connection refused"
        )
        disk_client = Mock()
        disk_client.get_collections.return_value = Mock(collections=[])
        calls: list[str | None] = []

        def _factory(
            *,
            location: str | None,
            url: str | None,
            host: str,
            port: int,
            grpc_port: int,
            api_key: str | None,
            timeout: int,
            prefer_grpc: bool,
            https: bool,
        ) -> Mock:
            _ = (
                url,
                host,
                port,
                grpc_port,
                api_key,
                timeout,
                prefer_grpc,
                https,
            )
            calls.append(location)
            if location is None:
                return remote_client
            if location == ".qdrant":
                return disk_client
            raise AssertionError(f"Unexpected location: {location}")

        with (
            patch(
                "sec_nlp.pipelines.vector.client.create_qdrant_client", _factory
            ),
            patch(
                "subprocess.run",
                return_value=False,
            ) as mock_bootstrap,
        ):
            config = VectorConfig(qdrant_location=None)
            client, target = config.setup_qdrant_client_with_target()

        assert client is disk_client
        assert target == ".qdrant"
        assert calls == [None, ".qdrant"]
        mock_bootstrap.assert_not_called()

    def test_setup_qdrant_client_falls_back_to_memory(self) -> None:
        """Fallback to `:memory:` when remote and disk targets both fail."""
        remote_client = Mock()
        remote_client.get_collections.side_effect = RuntimeError(
            "Connection refused"
        )
        disk_client = Mock()
        disk_client.get_collections.side_effect = RuntimeError("Wal lock")
        memory_client = Mock()
        memory_client.get_collections.return_value = Mock(collections=[])
        calls: list[str | None] = []

        def _factory(
            *,
            location: str | None,
            url: str | None,
            host: str,
            port: int,
            grpc_port: int,
            api_key: str | None,
            timeout: int,
            prefer_grpc: bool,
            https: bool,
        ) -> Mock:
            _ = (
                url,
                host,
                port,
                grpc_port,
                api_key,
                timeout,
                prefer_grpc,
                https,
            )
            calls.append(location)
            if location is None:
                return remote_client
            if location == ".qdrant":
                return disk_client
            if location == ":memory:":
                return memory_client
            raise AssertionError(f"Unexpected location: {location}")

        with (
            patch(
                "sec_nlp.pipelines.vector.client.create_qdrant_client", _factory
            ),
            patch(
                "subprocess.run",
                return_value=False,
            ) as mock_bootstrap,
        ):
            config = VectorConfig(qdrant_location=None)
            client, target = config.setup_qdrant_client_with_target()

        assert client is memory_client
        assert target == ":memory:"
        assert calls == [None, ".qdrant", ":memory:"]
        mock_bootstrap.assert_not_called()

    def test_persistent_qdrant_location_keeps_points_between_clients(
        self,
        tmp_path: Path,
    ) -> None:
        """Smoke test persistent local Qdrant storage survives client re-init."""
        collection_name = "persist_smoke"
        qdrant_path = tmp_path / "qdrant_store"
        config = VectorConfig(
            qdrant_location=str(qdrant_path),
            qdrant_url=None,
            collection_name=collection_name,
            qdrant_timeout=5,
        )

        first_client = config.setup_qdrant_client()
        if first_client.collection_exists(collection_name):
            first_client.delete_collection(collection_name)
        first_client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=4, distance=Distance.COSINE),
        )
        first_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=1,
                    vector=[0.1, 0.2, 0.3, 0.4],
                    payload={"symbol": "AAPL"},
                )
            ],
        )
        assert (
            first_client.count(
                collection_name=collection_name, exact=True
            ).count
            == 1
        )

        first_client.close()
        vector_config.clear_runtime_caches()
        second_client = config.setup_qdrant_client()
        assert (
            second_client.count(
                collection_name=collection_name, exact=True
            ).count
            == 1
        )
        retrieved = second_client.retrieve(
            collection_name=collection_name,
            ids=[1],
            with_payload=True,
            with_vectors=False,
        )
        assert len(retrieved) == 1
        assert retrieved[0].payload == {"symbol": "AAPL"}


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


class TestQdrantClientFactory:
    """Unit tests for shared Qdrant client constructor behavior."""

    def test_create_qdrant_client_uses_memory_location_mode(self) -> None:
        with patch(
            "sec_nlp.pipelines.vector.client.QdrantClient"
        ) as mock_client:
            create_qdrant_client(
                location=":memory:",
                url=None,
                host="localhost",
                port=6333,
                grpc_port=6334,
                api_key=None,
                timeout=5,
                prefer_grpc=True,
                https=False,
            )

        mock_client.assert_called_once_with(
            location=":memory:",
            timeout=5,
            prefer_grpc=False,
        )

    def test_create_qdrant_client_uses_path_for_persistent_location(
        self,
    ) -> None:
        with patch(
            "sec_nlp.pipelines.vector.client.QdrantClient"
        ) as mock_client:
            create_qdrant_client(
                location=".qdrant/rems",
                url=None,
                host="localhost",
                port=6333,
                grpc_port=6334,
                api_key=None,
                timeout=5,
                prefer_grpc=True,
                https=False,
            )

        mock_client.assert_called_once_with(
            path=".qdrant/rems",
            timeout=5,
            prefer_grpc=False,
        )
