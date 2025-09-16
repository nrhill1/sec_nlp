import logging
import os

from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone


logger = logging.getLogger(__name__)


class PineconeDBManager:

    def __init__(self, pinecone_api_key: str):
        self._pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
