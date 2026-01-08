from collections import Counter
from collections.abc import Callable as Callable

from langchain_core.documents import Document as Document

from sec_nlp.core.infra.logger import logger as logger
from sec_nlp.core.ingest.exhibit_downloader import (
    ExhibitDownloader as ExhibitDownloader,
)
from sec_nlp.core.ingest.loader import Loader as Loader
from sec_nlp.core.text.filters import (
    create_exhibit_filter as create_exhibit_filter,
)
from sec_nlp.core.text.keyword import KeywordMatcher as KeywordMatcher
from sec_nlp.core.text.section_extractor import (
    create_section_extractor as create_section_extractor,
)
from sec_nlp.pipelines.observability.telemetry import (
    log_document_metadata as log_document_metadata,
    log_exhibit_stats as log_exhibit_stats,
)
from sec_nlp.pipelines.presets.exb_10.config import (
    Exhibit10Config as Exhibit10Config,
)

class ExhibitStats:
    chunk_count: int
    sections_found: set[str]
    exhibit_docs: int
    html_files: int
    accession_numbers: set[str]
    prefilter_skips: Counter[str]
    def log(
        self, symbol: str, filtered_chunk_count: int | None = None
    ) -> None: ...

def collect_exhibit_documents(
    *,
    loader: Loader,
    symbol: str,
    config: Exhibit10Config,
    keyword_terms: list[str],
    keyword_categories: KeywordMatcher.KeywordCategories,
    adaptive_chunk_size: Callable[[int], int],
    skip_prefilter: bool = False,
) -> tuple[list[Document], ExhibitStats]: ...
