from qdrant_client import QdrantClient as QdrantClient

from sec_nlp.pipelines.runtime import (
    MetadataFilters as MetadataFilters,
    build_metadata_filter as build_metadata_filter,
)

def scroll_exists(
    client: QdrantClient, collection_name: str, filters: MetadataFilters
) -> bool: ...
