import logging
import os

from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone


logger = logging.getLogger(__name__)


class PineconeDBManager:

    def __init__(self, pinecone_api_key: str = os.getenv("PINECONE_API_KEY")):
        self._pc = Pinecone(api_key=pinecone_api_key)

    def add_index(self, index_name: str):
        if not self._pc.has_index(index_name):
            pass
