from typing import Literal

from _typeshed import Incomplete
from langchain_core.documents import Document as Document
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel
from qdrant_client import QdrantClient as QdrantClient

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.vector.client import (
    create_qdrant_client as create_qdrant_client,
)

class VectorConfig(BaseModel):
    model_config: Incomplete
    collection_name: str | None
    embedding_model: str
    embedding_device: str
    embedding_batch_size: int
    vector_size: int
    qdrant_location: str | None
    qdrant_url: str | None
    qdrant_host: str
    qdrant_port: int
    qdrant_grpc_port: int
    qdrant_api_key: str | None
    qdrant_https: bool
    qdrant_prefer_grpc: bool
    qdrant_timeout: int
    qdrant_distance: Literal["Cosine", "Euclid", "Dot"]
    qdrant_on_disk_payload: bool
    qdrant_replication_factor: int
    qdrant_write_consistency_factor: int
    search_type: str
    def setup_qdrant_client(self) -> QdrantClient: ...
    @staticmethod
    def recreate_collection_if_fresh(
        qdrant_client: QdrantClient, collection_name: str, fresh: bool
    ) -> None: ...
    def setup_embedding_model(self) -> OllamaEmbeddings: ...
    def create_vector_store(
        self,
        qdrant_client: QdrantClient,
        embedder: OllamaEmbeddings,
        collection_name: str | None = None,
    ) -> QdrantVectorStore: ...
    def batch_embed_documents(
        self,
        embedder: OllamaEmbeddings,
        texts: list[str],
        show_progress: bool = True,
    ) -> list[list[float]]: ...
    def batch_add_to_vector_store(
        self,
        vector_store: QdrantVectorStore,
        documents: list[Document],
        show_progress: bool = True,
    ) -> list[str]: ...
