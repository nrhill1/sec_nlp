import logging
import os

from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec


logger = logging.getLogger(__name__)


class PineconeVectorStore:

    def __init__(self, pinecone_api_key: str = os.getenv("PINECONE_API_KEY")):
        self._pc = Pinecone(api_key=pinecone_api_key)

    def add_index(self, index_name: str):
        if not self._pc.has_index(index_name):
            pc.create_index(
                name=index_name,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                )
            )
            logger.info(f"Created Pinecone index: {index_name}")
        else:
            logger.info(f"Pinecone index already exists: {index_name}")
