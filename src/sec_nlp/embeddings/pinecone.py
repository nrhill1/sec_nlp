import logging
import os

from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec
from uuid import uuid4

logger = logging.getLogger(__name__)


class PineconeEmbedder:

    def __init__(self, pinecone_api_key: str, initial_index: str):
        self._pc = Pinecone(api_key=pinecone_api_key)
        self._current_index = initial_index

        if not self._pc.has_index(initial_index):
            self.add_index(initial_index)

        self._vector_store = self._create_vector_store()
        logger.info("Initialized Pinecone client.")

    def add_documents(self, documents: list[Document]):
        """
        Add documents to the Pinecone vector store.

        Args:
            documents (list[Document]): List of documents to add.

        Raises:
            ValueError: If the vector store is not initialized.
        """
        if self._vector_store is None:
            raise ValueError(
                "Vector store not initialized. Please initialize the vector store before adding documents.")
        uuids = [str(uuid4()) for _ in documents]
        self._vector_store.add_documents(documents=documents, ids=uuids)
        logger.info(
            f"Added {len(documents)} documents to Pinecone vector store.")

    def add_index(self, index_name: str):
        """
        Create a new Pinecone index if it doesn't already exist.

        Args:
            index_name (str): Name of the Pinecone index to create
        """
        if not self._pc.has_index(index_name):
            self._pc.create_index(
                name=index_name,
                dimension=384,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )

            self._current_index = index_name
            logger.info(f"Created Pinecone index: {index_name}")
        else:
            logger.info(f"Pinecone index already exists: {index_name}")

    def _create_vector_store(self):
        """
        Initialize the Pinecone vector store.

        Raises:
            ValueError: If no Pinecone index is set.
        """
        if self._current_index is None:
            raise ValueError(
                "No Pinecone index set. Please set/add an index before initializing the vector store.")
        embeddings_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2")
        index = self._pc.Index(self._current_index)

        logger.info("Initialized Pinecone vector store.")
        return PineconeVectorStore(
            index=index, embedding=embeddings_model)

    def query(self, query: str, top_k: int = 5):
        """
        Query the Pinecone vector store.

        Args:
            query (str): Query string.
            top_k (int, optional): Number of top results to return. Defaults to 5.

        Raises:
            ValueError: If the vector store is not initialized.

        Returns:
            list[Document]: List of retrieved documents.
        """
        results = self._vector_store.similarity_search(
            query=query, k=top_k)
        logger.info(f"Queried Pinecone vector store with query: {query}")
        return results

    def set_index(self, index_name: str):
        """
        Set the current Pinecone index.

        Args:
            index_name (str): Name of the Pinecone index to set

        Raises:
            ValueError: If the specified Pinecone index does not exist.
        """
        if not self._pc.has_index(index_name):
            raise ValueError(f"Pinecone index does not exist: {index_name}")
        self._current_index = index_name
        logger.info(f"Current Pinecone index: {index_name}")
