import logging

from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone

logger = logging.getLogger(__name__)


class PineconeManager:

    def __init__(self, api_key: str):
        self._pc = Pinecone(api_key=api_key)
