from collections.abc import Iterable

from langchain_core.documents import Document as Document
from langchain_qdrant import QdrantVectorStore as QdrantVectorStore

def upload_documents(
    *,
    vector_store: QdrantVectorStore,
    documents: Iterable[Document],
    symbol: str | None = None,
    batch_size: int = 32,
    bar_color: str = "magenta",
    desc: str | None = None,
) -> None: ...
