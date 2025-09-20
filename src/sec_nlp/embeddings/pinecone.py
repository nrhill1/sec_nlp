import logging
import os

from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec


logger = logging.getLogger(__name__)


class PineconeEmbedder:

    def __init__(self, pinecone_api_key: str = os.getenv("PINECONE_API_KEY")):
        self._pc = Pinecone(api_key=pinecone_api_key)
        self._current_index = None
        self._vector_store = None

    def add_index(self, index_name: str):
        """
        Create a new Pinecone index if it doesn't already exist.

        Args:
            index_name (str): Name of the Pinecone index to create
        """
        if not self._pc.has_index(index_name):
            pc.create_index(
                name=index_name,
                embed={
                    "model": "llama-text-embed-v2",
                }
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            self._current_index = self._pc.get_index(index_name)
            logger.info(f"Created Pinecone index: {index_name}")
        else:
            logger.info(f"Pinecone index already exists: {index_name}")

    def set_index(self, index_name: str):
        if not self._pc.has_index(index_name):
            raise ValueError(f"Pinecone index does not exist: {index_name}")
        self._current_index = self._pc.get_index(index_name)
        logger.info(f"Current Pinecone index: {index_name}")
