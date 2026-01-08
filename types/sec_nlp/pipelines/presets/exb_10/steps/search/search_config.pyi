from _typeshed import Incomplete
from pydantic_settings import BaseSettings

from sec_nlp.types import JsonValue as JsonValue

class SearchConfig(BaseSettings):
    model_config: Incomplete
    queries: list[str]
    search_kwargs: dict[str, JsonValue]
    limit: int
    score_threshold: float
    export_results: bool
    mmr_fetch_k: int
    mmr_lambda: float
    @classmethod
    def normalize_queries(cls, v: list[str] | str) -> list[str]: ...
