from pathlib import Path

from _typeshed import Incomplete
from langchain_qdrant import QdrantVectorStore as QdrantVectorStore
from pydantic import BaseModel

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.pipelines.utils import slugify as slugify
from sec_nlp.types import (
    JsonObject as JsonObject,
    JsonValue as JsonValue,
)

class SearchResult(BaseModel):
    model_config: Incomplete
    text: str
    score: float
    metadata: dict[str, JsonValue]

class Exhibit10Search(BaseModel):
    model_config: Incomplete
    vector_store: QdrantVectorStore
    limit: int
    score_threshold: float
    search_kwargs: dict[str, JsonValue]
    search_type: str
    def search(
        self,
        query: str,
        symbols: list[str] | None = None,
        limit: int | None = None,
        score_threshold: float | None = 0.9,
        search_kwargs: dict[str, JsonValue] | None = None,
    ) -> list[SearchResult]: ...
    def export_results(
        self,
        query: str,
        results: list[SearchResult],
        output_path: Path,
        search_type: str = "similarity",
        run_id: str | None = None,
    ) -> None: ...
