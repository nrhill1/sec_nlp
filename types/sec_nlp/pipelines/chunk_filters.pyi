from langchain_core.documents import Document as Document

from sec_nlp.pipelines.runtime import (
    get_accession_from_metadata as get_accession_from_metadata,
)

type AccessionCounts = dict[str, int]

def limit_docs_per_accession(
    docs: list[Document], max_chunks: int
) -> tuple[list[Document], AccessionCounts, AccessionCounts]: ...
