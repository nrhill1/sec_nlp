from _typeshed import Incomplete
from pydantic import BaseModel

from sec_nlp.types import JsonValue as JsonValue

class SearchRecordPayload(BaseModel):
    model_config: Incomplete
    query: JsonValue | None
    query_slug: JsonValue | None
    output_file: JsonValue | None
    num_results: int | None
    top_symbols: list[JsonValue] | None

class SearchManifestMetaPayload(BaseModel):
    model_config: Incomplete
    run_id: JsonValue
    timestamp: JsonValue
    pipeline_type: JsonValue
    search_type: JsonValue
    collection: JsonValue
    total_queries: int
    total_results: int

class SearchManifestPayload(BaseModel):
    model_config: Incomplete
    meta: SearchManifestMetaPayload
    queries: list[SearchRecordPayload]
