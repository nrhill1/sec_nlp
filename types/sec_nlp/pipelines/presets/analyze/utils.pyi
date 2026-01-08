from sec_nlp.pipelines.types import MetadataMap as MetadataMap

def resolve_symbol_for_output(
    fallback_symbol: str, *metas: MetadataMap | None
) -> str: ...

DEFAULT_QUERY_STOPWORDS: set[str]

def normalize_query_terms(
    query: str | None, *, min_len: int = 3, stopwords: set[str] | None = None
) -> list[str]: ...
def query_term_overlap(
    query: str | None,
    content: str | None,
    *,
    min_len: int = 3,
    stopwords: set[str] | None = None,
) -> tuple[list[str], list[str], float]: ...
