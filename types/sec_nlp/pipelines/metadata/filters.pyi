from collections.abc import Mapping, Sequence

from qdrant_client.models import Filter

type MetadataFilterValue = str | int | bool
type MetadataFilters = Mapping[str, Sequence[MetadataFilterValue]]

def build_metadata_filter(raw_filters: MetadataFilters) -> Filter | None: ...
