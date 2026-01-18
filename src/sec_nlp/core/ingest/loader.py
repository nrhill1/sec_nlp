# src/sec_nlp/core/loader.py
"""Unified Loader that downloads and preprocesses SEC filings.

Self-contained implementation using sec_edgar_downloader for fetching and
unstructured.io + LangChain for parsing/splitting.

Fetch mode:
- "download": download files via sec_edgar_downloader (default)

Primary method returns LangChain Documents directly.
"""

import asyncio
from collections.abc import Coroutine, Generator, Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Protocol, TypedDict

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator
from unstructured.documents.elements import Element

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.edgar.holdings_parser import HoldingsParser
from sec_nlp.core.edgar.insider_parser import InsiderParser
from sec_nlp.core.edgar.relationship_resolver import (
    RelationshipResolver,
    build_related_filings_map,
    serialize_relationship_graph,
)
from sec_nlp.core.infra.logger import format_size, logger
from sec_nlp.core.ingest import filings
from sec_nlp.core.ingest.downloader import download_filings
from sec_nlp.core.ingest.parser import HtmlProcessor
from sec_nlp.core.ingest.types import DownloadResults
from sec_nlp.core.text.filters import SectionFilter
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.types import JsonDict


class LoaderRunMetadata(TypedDict):
    work_folder: str
    download_results: DownloadResults
    per_symbol_doc_counts: dict[str, int]
    total_documents: int
    relationships: JsonDict


class FilingRecord(Protocol):
    acceptance_date: str


def _default_meta() -> LoaderRunMetadata:
    return {
        "work_folder": "",
        "download_results": {},
        "per_symbol_doc_counts": {},
        "total_documents": 0,
        "relationships": {},
    }


class Loader(BaseModel):
    """Download + preprocess filings into LangChain Documents.

    Example:
        loader = Loader(email="you@example.com")
        loader.add_symbols(["AAPL", "MSFT"])
        docs = loader.load_documents(
            mode=FilingMode.annual,
            keywords=["warranty"]
        )
        print(len(docs))
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
    )

    email: str
    downloads_folder: Path = Path("downloads")
    company_name: str = "SEC NLP Tool"
    fetch_mode: Literal["download"] = "download"

    # Preprocessing controls (sentence-based chunking)
    chunk_size: int = Field(
        default=10,
        ge=1,
        description="Max sentences per chunk (sentence-based splitting)",
    )
    chunk_overlap: int = Field(
        default=2,
        ge=0,
        description="Sentences to overlap between chunks",
    )

    section_chunking: bool = Field(
        default=True,
        description="Split filings into sections before sentence chunking",
    )
    section_chunk_max_length: int = Field(
        default=500000,
        ge=1000,
        description="Maximum characters to keep per section before truncation",
    )

    # Content filtering
    keywords: list[str] | None = None
    keyword_mode: Literal["any", "all"] = "any"
    keyword_boundary: bool = Field(
        default=False,
        description="Match whole words only (vs substrings)",
    )
    section_filter: SectionFilter | None = None

    # Async processing controls
    use_async: bool = Field(
        default=True,
        description="Enable async HTML processing",
    )
    max_workers: int = Field(
        default=2,
        ge=1,
        le=16,
        description="Maximum concurrent workers for async processing",
    )

    _symbols: set[str] = PrivateAttr(default_factory=set)
    _symbol_to_cik: dict[str, str] = PrivateAttr(default_factory=dict)
    _last_meta: LoaderRunMetadata = PrivateAttr(default_factory=_default_meta)
    _parser: HtmlProcessor = PrivateAttr()

    @field_validator("downloads_folder", mode="before")
    @classmethod
    def _ensure_path(cls, v: str | Path) -> Path:
        if isinstance(v, str):
            return Path(v)
        if isinstance(v, Path):
            return v
        raise ValueError(f"Expected str or Path, got {type(v)}")

    @field_validator("chunk_size", "chunk_overlap")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    def model_post_init(self, __ctx: None) -> None:
        self._parser = HtmlProcessor(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            section_chunking=self.section_chunking,
            section_chunk_max_length=self.section_chunk_max_length,
            keyword_mode=self.keyword_mode,
        )
        logger.debug("Loader initialized with %s", self._parser)
        self.downloads_folder.mkdir(parents=True, exist_ok=True)

    def add_symbol(self, symbol: str) -> None:
        """Add a ticker symbol to process.

        Args:
            symbol: Ticker symbol (CIK will be auto-fetched from SEC)
        """
        sym = symbol.strip().upper()
        self._symbols.add(sym)
        logger.info("Loader: added symbol %s", sym)
        logger.debug("Current symbols: %s", sorted(self._symbols))

    def add_symbols(self, symbols: Iterable[str]) -> None:
        """Add multiple ticker symbols.

        Args:
            symbols: List of ticker symbols (CIKs will be auto-fetched)
        """
        for s in symbols:
            self.add_symbol(s)

    def load_documents(
        self,
        mode: FilingMode = FilingMode.annual,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> list[Document]:
        """Download filings and return preprocessed LangChain Documents.

        Args:
            mode: FilingMode.annual -> 10-K, .quarterly -> 10-Q
            start_date: YYYY-MM-DD (inclusive)
            end_date: YYYY-MM-DD (inclusive)
            limit_per_symbol: limit number of HTML files per symbol (newest first)
            perform_download: whether to download filings before processing
            keywords: Optional list of keywords to filter content (case-insensitive).
                Overrides instance-level keywords if provided.
            section_filter: Optional SectionFilter to filter for specific sections.
                Overrides instance-level section_filter if provided.
        """
        if not self._symbols:
            raise ValueError("No symbols added; call add_symbol(s) first")

        if self.fetch_mode != "download":
            raise ValueError(
                f"fetch_mode '{self.fetch_mode}' is not supported. Only 'download' is available."
            )

        # Use provided keywords or fall back to instance keywords
        filter_keywords = keywords if keywords is not None else self.keywords

        # Use provided section_filter or fall back to instance section_filter
        active_section_filter = (
            section_filter
            if section_filter is not None
            else self.section_filter
        )

        work_folder = self.downloads_folder
        after_date = date.fromisoformat(start_date) if start_date else None
        before_date = date.fromisoformat(end_date) if end_date else None

        download_results: DownloadResults = {}
        if perform_download:
            download_results = download_filings(
                symbols=self._symbols,
                mode=mode,
                work_folder=work_folder,
                company_name=self.company_name,
                email=self.email,
                after_date=after_date,
                before_date=before_date,
                limit_per_symbol=limit_per_symbol,
            )

        # Gather and preprocess
        all_docs: list[Document] = []
        per_symbol_counts: dict[str, int] = {}
        relationships_by_symbol: JsonDict = {}

        for symbol in sorted(self._symbols):
            try:
                related_map, graph_payload = (
                    self._build_relationships_for_symbol(symbol)
                )
                relationships_by_symbol[symbol] = graph_payload
                if mode == FilingMode.holdings:
                    filing_dir = self._filing_dir(symbol, mode, work_folder)
                    docs = self._load_holdings_documents(
                        filing_dir=filing_dir,
                        limit=limit_per_symbol,
                        start_date=after_date,
                        end_date=before_date,
                    )
                elif mode == FilingMode.insider:
                    docs = self._load_insider_documents(
                        symbol=symbol,
                        base=work_folder,
                        limit=limit_per_symbol,
                        start_date=after_date,
                        end_date=before_date,
                    )
                else:
                    html_paths = self.html_paths_for_symbol(
                        symbol=symbol,
                        mode=mode,
                        base=work_folder,
                        limit=limit_per_symbol,
                        start_date=after_date,
                        end_date=before_date,
                    )
                    if html_paths:
                        total_size = 0
                        per_accession: dict[str, int] = {}
                        for html_path in html_paths:
                            try:
                                sz = html_path.stat().st_size
                                total_size += sz
                                accession = html_path.parent.name
                                per_accession[accession] = (
                                    per_accession.get(accession, 0) + sz
                                )
                                logger.debug(
                                    "File size [%s/%s]: %.1f KB",
                                    accession,
                                    html_path.name,
                                    sz / 1024.0,
                                )
                            except OSError:
                                logger.debug("Could not stat %s", html_path)
                        for acc, sz in per_accession.items():
                            logger.debug(
                                "Total size for %s (%s accession %s): %s",
                                symbol,
                                mode.form,
                                acc,
                                format_size(sz),
                            )
                        logger.info(
                            "Total size for %s (%s): %s across %d files",
                            symbol,
                            mode.form,
                            format_size(total_size),
                            len(html_paths),
                        )
                    docs = self.batch_transform_html(
                        list(html_paths),
                        keywords=filter_keywords,
                        section_filter=active_section_filter,
                    )
                self._attach_related_filings(docs, related_map)
                all_docs.extend(docs)
                per_symbol_counts[symbol] = len(docs)
            except FileNotFoundError:
                logger.warning(
                    "No filings found on disk for %s (%s)",
                    symbol,
                    mode.value,
                )
                per_symbol_counts[symbol] = 0

        meta: LoaderRunMetadata = {
            "work_folder": str(work_folder),
            "download_results": download_results,
            "per_symbol_doc_counts": per_symbol_counts,
            "total_documents": len(all_docs),
            "relationships": relationships_by_symbol,
        }
        self._last_meta = meta

        return all_docs

    def load_texts(
        self,
        mode: FilingMode = FilingMode.annual,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> list[str]:
        """Convenience helper: return only text chunks from the Documents."""
        docs = self.load_documents(
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            limit_per_symbol=limit_per_symbol,
            perform_download=perform_download,
            keywords=keywords,
            section_filter=section_filter,
        )
        return [d.page_content for d in docs]

    def _filing_dir(self, symbol: str, mode: FilingMode, base: Path) -> Path:
        return filings.filing_dir(base, symbol, mode)

    def _get_filing_date_from_dir(self, filing_dir: Path) -> date | None:
        """Extract filing date from full-submission.txt in filing directory.

        Args:
            filing_dir: Path to filing directory (e.g., .../0001558370-20-014436)

        Returns:
            Filing date or None if not found
        """
        return filings.get_filing_date_from_dir(filing_dir)

    def _build_relationships_for_symbol(
        self, symbol: str
    ) -> tuple[dict[str, list[JsonDict]], JsonDict]:
        resolver = RelationshipResolver(self.downloads_folder)
        graph = resolver.resolve_symbol(symbol)
        related_map = build_related_filings_map(graph)
        return related_map, serialize_relationship_graph(graph)

    def _accession_dirs_for_filing_dir(
        self,
        filing_dir: Path,
        limit: int | None,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Path]:
        if not filing_dir.exists():
            raise FileNotFoundError(f"No filings found at {filing_dir}")

        accession_dirs = [
            path for path in filing_dir.iterdir() if path.is_dir()
        ]
        dirs_with_dates: list[tuple[Path, date | None]] = []
        for accession_dir in accession_dirs:
            filing_date = filings.get_filing_date_from_dir(accession_dir)
            if start_date or end_date:
                if filing_date is None:
                    dirs_with_dates.append((accession_dir, filing_date))
                    continue
                if start_date and filing_date < start_date:
                    continue
                if end_date and filing_date > end_date:
                    continue
            dirs_with_dates.append((accession_dir, filing_date))

        def sort_key(item: tuple[Path, date | None]) -> tuple[date, float]:
            path, filing_date = item
            if filing_date:
                return (filing_date, 0.0)
            return (date.min, -path.stat().st_mtime)

        dirs_with_dates.sort(key=sort_key, reverse=True)
        sorted_dirs = [path for path, _ in dirs_with_dates]
        return sorted_dirs[:limit] if limit else sorted_dirs

    def _accession_dirs_for_filing_dirs(
        self,
        filing_dirs: Sequence[Path],
        limit: int | None,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Path]:
        existing_dirs = [path for path in filing_dirs if path.exists()]
        if not existing_dirs:
            raise FileNotFoundError("No filings found in configured folders")

        dirs_with_dates: list[tuple[Path, date | None]] = []
        for filing_dir in existing_dirs:
            for accession_dir in filing_dir.iterdir():
                if not accession_dir.is_dir():
                    continue
                filing_date = filings.get_filing_date_from_dir(accession_dir)
                if start_date or end_date:
                    if filing_date is None:
                        dirs_with_dates.append((accession_dir, filing_date))
                        continue
                    if start_date and filing_date < start_date:
                        continue
                    if end_date and filing_date > end_date:
                        continue
                dirs_with_dates.append((accession_dir, filing_date))

        def sort_key(item: tuple[Path, date | None]) -> tuple[date, float]:
            path, filing_date = item
            if filing_date:
                return (filing_date, 0.0)
            return (date.min, -path.stat().st_mtime)

        dirs_with_dates.sort(key=sort_key, reverse=True)
        sorted_dirs = [path for path, _ in dirs_with_dates]
        return sorted_dirs[:limit] if limit else sorted_dirs

    def _load_holdings_documents(
        self,
        filing_dir: Path,
        limit: int | None,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Document]:
        accession_dirs = self._accession_dirs_for_filing_dir(
            filing_dir=filing_dir,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        parser = HoldingsParser()
        docs: list[Document] = []
        for accession_dir in accession_dirs:
            docs.extend(parser.parse_accession_dir(accession_dir))
        return docs

    def _load_insider_documents(
        self,
        *,
        symbol: str,
        base: Path,
        limit: int | None,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Document]:
        form_dirs = [
            base / "sec-edgar-filings" / symbol.upper() / form_type
            for form_type in FilingMode.insider.forms
        ]
        accession_dirs = self._accession_dirs_for_filing_dirs(
            filing_dirs=form_dirs,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )
        parser = InsiderParser()
        docs: list[Document] = []
        for accession_dir in accession_dirs:
            docs.extend(parser.parse_accession_dir(accession_dir))
        return docs

    @staticmethod
    def _attach_related_filings(
        docs: Sequence[Document],
        related_map: dict[str, list[JsonDict]],
    ) -> None:
        if not docs or not related_map:
            return

        for doc in docs:
            metadata = doc.metadata or {}
            accession = Loader._extract_accession(metadata)
            if not accession:
                continue
            related = related_map.get(accession)
            if not related:
                continue
            updated = dict(metadata)
            if not updated.get("accession_number"):
                updated["accession_number"] = accession
            updated["related_filings"] = related
            doc.metadata = updated

    @staticmethod
    def _extract_accession(metadata: JsonDict) -> str | None:
        accession_value = metadata.get("accession_number") or metadata.get(
            "accession"
        )
        if isinstance(accession_value, str) and accession_value.strip():
            return accession_value.strip()
        source = metadata.get("source") or metadata.get("file_path")
        if isinstance(source, str) and source.strip():
            parts = Path(source).parts
            if "sec-edgar-filings" in parts:
                idx = parts.index("sec-edgar-filings")
                if idx + 3 < len(parts):
                    return parts[idx + 3]
        return None

    def html_paths_for_symbol(
        self,
        symbol: str,
        mode: FilingMode,
        base: Path,
        limit: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Path]:
        """Get HTML file paths for a symbol, optionally filtered by date range.

        Args:
            symbol: Ticker symbol
            mode: Filing mode (annual/quarterly)
            base: Base download directory
            limit: Maximum number of files to return (applied after date filtering)
            start_date: Optional start date filter (inclusive)
            end_date: Optional end date filter (inclusive)

        Returns:
            List of HTML file paths, sorted by filing date (newest first)
        """
        return filings.html_paths_for_symbol(
            symbol=symbol,
            mode=mode,
            base=base,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
        )

    def _build_section_extractor(
        self, section_filter: SectionFilter | None
    ) -> SectionExtractor | None:
        return self._parser._build_section_extractor(section_filter)

    def _log_section_chunk_summary(
        self, section_chunks: list[Document]
    ) -> None:
        self._parser._log_section_chunk_summary(section_chunks)

    def _chunk_text(
        self,
        text_content: str,
        metadata: JsonDict | None,
        section_filter: SectionFilter | None,
    ) -> list[Document]:
        return self._parser._chunk_text(
            text_content,
            metadata,
            section_filter,
        )

    def transform_html(
        self,
        html_path: Path,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        """Transform HTML file into chunked documents.

        Args:
            html_path: Path to HTML file
            keywords: Optional keywords to filter content
            section_filter: Optional section filter to apply
        """
        active_filter = (
            section_filter
            if section_filter is not None
            else self.section_filter
        )
        return self._parser.transform_html(
            html_path,
            keywords=keywords,
            section_filter=active_filter,
        )

    def transform_html_string(
        self,
        html: str,
        metadata: dict[str, str | int | float] | None = None,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        """Transform HTML string into chunked documents.

        Args:
            html: HTML content as string
            metadata: Optional metadata to attach to documents
            keywords: Optional keywords to filter content before chunking
            section_filter: Optional section filter to apply

        Returns:
            List of chunked Document objects
        """
        active_filter = (
            section_filter
            if section_filter is not None
            else self.section_filter
        )
        return self._parser.transform_html_string(
            html,
            metadata=metadata,
            keywords=keywords,
            section_filter=active_filter,
        )

    async def transform_html_async(
        self,
        html_path: Path,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Sequence[Document]:
        """Async wrapper for transform_html.

        Args:
            html_path: Path to HTML file
            keywords: Optional keywords to filter content
            section_filter: Optional section filter to apply

        Returns:
            List of chunked Document objects
        """
        active_filter = (
            section_filter
            if section_filter is not None
            else self.section_filter
        )
        return await self._parser.transform_html_async(
            html_path,
            keywords=keywords,
            section_filter=active_filter,
        )

    async def _batch_transform_async(
        self,
        html_paths: list[Path],
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> list[Document]:
        """Process files concurrently with semaphore for rate limiting.

        Args:
            html_paths: List of paths to HTML files
            keywords: Optional keywords to filter content
            section_filter: Optional section filter to apply

        Returns:
            Flattened list of all documents from all files
        """
        semaphore = asyncio.Semaphore(self.max_workers)

        async def process_with_semaphore(path: Path) -> list[Document]:
            async with semaphore:
                try:
                    return list(
                        await self.transform_html_async(
                            path, keywords, section_filter
                        )
                    )
                except FileNotFoundError as e:
                    logger.error("Missing HTML file %s: %s", path.name, e)
                    return []
                except (OSError, ValueError) as e:
                    logger.error("Failed to transform %s: %s", path.name, e)
                    return []

        results = await asyncio.gather(
            *[process_with_semaphore(p) for p in html_paths]
        )
        return [doc for result in results for doc in result]  # Flatten

    def _batch_transform_sequential(
        self,
        html_paths: list[Path],
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> list[Document]:
        """Process files sequentially (fallback/baseline).

        Args:
            html_paths: List of paths to HTML files
            keywords: Optional keywords to filter content
            section_filter: Optional section filter to apply

        Returns:
            Flattened list of all documents from all files
        """
        all_docs: list[Document] = []
        for p in html_paths:
            try:
                all_docs.extend(
                    self.transform_html(
                        p, keywords=keywords, section_filter=section_filter
                    )
                )
            except FileNotFoundError as e:
                logger.error("Missing HTML file %s: %s", p.name, e)
            except (OSError, ValueError) as e:
                logger.error("Failed to transform %s: %s", p.name, e)
        return all_docs

    def batch_transform_html(
        self,
        html_paths: list[Path],
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
        concurrent: bool = True,
    ) -> list[Document]:
        """Transform multiple HTML files with optional concurrency.

        Args:
            html_paths: List of paths to HTML files
            keywords: Optional keywords to filter content
            section_filter: Optional section filter to apply
            concurrent: Enable concurrent processing (uses use_async setting)

        Returns:
            Flattened list of all documents from all files
        """
        # Use sequential processing if:
        # - concurrent is disabled
        # - use_async is disabled
        # - only one file (no benefit from async)
        if not concurrent or not self.use_async or len(html_paths) <= 1:
            return self._batch_transform_sequential(
                html_paths, keywords, section_filter
            )

        # Try async processing with fallback to sequential
        coro: Coroutine[None, None, list[Document]] | None = None
        try:
            coro = self._batch_transform_async(
                html_paths, keywords, section_filter
            )
            return self._run_async(coro)
        except (RuntimeError, OSError, ValueError) as e:
            if coro is not None:
                try:
                    coro.close()  # Avoid unawaited coroutine warnings on failure
                except RuntimeError:
                    pass
            logger.warning(
                "Async processing failed: %s. Falling back to sequential.", e
            )
            return self._batch_transform_sequential(
                html_paths, keywords, section_filter
            )

    @staticmethod
    def _run_async(
        coro: Coroutine[None, None, list[Document]],
    ) -> list[Document]:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(coro)
            finally:
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except (RuntimeError, ValueError):
                    pass
                shutdown_default_executor = getattr(
                    loop, "shutdown_default_executor", None
                )
                if callable(shutdown_default_executor):
                    try:
                        loop.run_until_complete(shutdown_default_executor())
                    except (RuntimeError, ValueError):
                        pass
        finally:
            asyncio.set_event_loop(None)
            if not loop.is_closed():
                loop.close()

    def _filter_filings_by_date(
        self,
        filings: list[FilingRecord],
        start: date | None,
        end: date | None,
    ) -> list[FilingRecord]:
        """Filter filings by date range.

        Note: filings are external objects from sec_edgar_downloader.
        """
        filtered = []
        for filing in filings:
            filing_date = datetime.fromisoformat(filing.acceptance_date).date()

            if start and filing_date < start:
                continue
            if end and filing_date > end:
                continue
            if end and filing_date > end:
                continue

            filtered.append(filing)

        return filtered

    def _get_cik_for_ticker(self, ticker: str) -> str:
        """Look up CIK for a ticker symbol from SEC.

        Uses the SEC company tickers JSON endpoint.
        Results are cached for efficiency.
        """
        return filings.get_cik_for_ticker(
            ticker=ticker,
            company_name=self.company_name,
            email=self.email,
        )

    def _filter_elements_by_keywords(
        self,
        elements: list[Element],
        keywords: list[str],
    ) -> list[Element]:
        """Filter unstructured elements by keywords using Aho-Corasick ranking.

        This is the most efficient filtering point - before combining elements
        into text and before chunking.

        Args:
            elements: Unstructured elements from partition_html
            keywords: List of keywords (case-insensitive)

        Returns:
            Filtered list of elements
        """
        return self._parser._filter_elements_by_keywords(elements, keywords)

    def _filter_documents_by_keywords(
        self,
        documents: list[Document],
        keywords: list[str],
    ) -> list[Document]:
        """Filter documents by keywords using Aho-Corasick ranking.

        Args:
            documents: List of Document objects
            keywords: List of keywords (case-insensitive)

        Returns:
            Filtered list of documents
        """
        return self._parser._filter_documents_by_keywords(documents, keywords)

    def load_documents_stream(
        self,
        mode: FilingMode = FilingMode.annual,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Generator[Document, None, LoaderRunMetadata]:
        """Stream documents as they're processed.

        Yields documents one at a time for memory-efficient processing.
        Returns metadata dictionary after all documents processed.

        Args:
            mode: FilingMode.annual -> 10-K, .quarterly -> 10-Q
            start_date: YYYY-MM-DD (inclusive)
            end_date: YYYY-MM-DD (inclusive)
            limit_per_symbol: limit number of HTML files per symbol
            perform_download: whether to download filings before processing
            keywords: Optional keywords to filter content
            section_filter: Optional section filter

        Yields:
            Document objects one at a time

        Returns:
            Metadata dictionary after all documents processed
        """
        if not self._symbols:
            raise ValueError("No symbols added; call add_symbol(s) first")

        filter_keywords = keywords if keywords is not None else self.keywords
        active_section_filter = (
            section_filter
            if section_filter is not None
            else self.section_filter
        )

        work_folder = self.downloads_folder
        after_date = date.fromisoformat(start_date) if start_date else None
        before_date = date.fromisoformat(end_date) if end_date else None

        download_results: DownloadResults = {}
        if perform_download:
            download_results = download_filings(
                symbols=self._symbols,
                mode=mode,
                work_folder=work_folder,
                company_name=self.company_name,
                email=self.email,
                after_date=after_date,
                before_date=before_date,
                limit_per_symbol=limit_per_symbol,
            )

        # Stream documents
        total_docs = 0
        per_symbol_counts: dict[str, int] = {}
        relationships_by_symbol: JsonDict = {}

        for symbol in sorted(self._symbols):
            try:
                related_map, graph_payload = (
                    self._build_relationships_for_symbol(symbol)
                )
                relationships_by_symbol[symbol] = graph_payload
                symbol_count = 0
                if mode == FilingMode.holdings:
                    filing_dir = self._filing_dir(symbol, mode, work_folder)
                    accession_dirs = self._accession_dirs_for_filing_dir(
                        filing_dir=filing_dir,
                        limit=limit_per_symbol,
                        start_date=after_date,
                        end_date=before_date,
                    )
                    parser = HoldingsParser()
                    for accession_dir in accession_dirs:
                        docs = parser.parse_accession_dir(accession_dir)
                        self._attach_related_filings(docs, related_map)
                        for doc in docs:
                            yield doc
                            symbol_count += 1
                            total_docs += 1
                elif mode == FilingMode.insider:
                    form_dirs = [
                        work_folder
                        / "sec-edgar-filings"
                        / symbol.upper()
                        / form_type
                        for form_type in FilingMode.insider.forms
                    ]
                    accession_dirs = self._accession_dirs_for_filing_dirs(
                        filing_dirs=form_dirs,
                        limit=limit_per_symbol,
                        start_date=after_date,
                        end_date=before_date,
                    )
                    parser = InsiderParser()
                    for accession_dir in accession_dirs:
                        docs = parser.parse_accession_dir(accession_dir)
                        self._attach_related_filings(docs, related_map)
                        for doc in docs:
                            yield doc
                            symbol_count += 1
                            total_docs += 1
                else:
                    html_paths = self.html_paths_for_symbol(
                        symbol=symbol,
                        mode=mode,
                        base=work_folder,
                        limit=limit_per_symbol,
                        start_date=after_date,
                        end_date=before_date,
                    )
                    for html_path in html_paths:
                        try:
                            docs = self.transform_html(
                                html_path,
                                keywords=filter_keywords,
                                section_filter=active_section_filter,
                            )
                            self._attach_related_filings(docs, related_map)
                            for doc in docs:
                                yield doc
                                symbol_count += 1
                                total_docs += 1
                        except Exception as e:
                            logger.error(
                                "Failed to transform %s: %s",
                                html_path.name,
                                e,
                            )

                per_symbol_counts[symbol] = symbol_count

            except FileNotFoundError:
                logger.warning(
                    "No filings found on disk for %s (%s)",
                    symbol,
                    mode.value,
                )
                per_symbol_counts[symbol] = 0

        # Update metadata
        meta: LoaderRunMetadata = {
            "work_folder": str(work_folder),
            "download_results": download_results,
            "per_symbol_doc_counts": per_symbol_counts,
            "total_documents": total_docs,
            "relationships": relationships_by_symbol,
        }
        self._last_meta = meta

        # Return metadata
        return meta

    def load_texts_stream(
        self,
        mode: FilingMode = FilingMode.annual,
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_symbol: int | None = None,
        perform_download: bool = True,
        keywords: list[str] | None = None,
        section_filter: SectionFilter | None = None,
    ) -> Generator[str, None, LoaderRunMetadata]:
        """Stream text chunks from documents.

        Convenience helper that yields only text content from documents.

        Args:
            mode: FilingMode.annual -> 10-K, .quarterly -> 10-Q
            start_date: YYYY-MM-DD (inclusive)
            end_date: YYYY-MM-DD (inclusive)
            limit_per_symbol: limit number of HTML files per symbol
            perform_download: whether to download filings before processing
            keywords: Optional keywords to filter content
            section_filter: Optional section filter

        Yields:
            Text content from documents

        Returns:
            Metadata dictionary after all documents processed
        """
        doc_gen = self.load_documents_stream(
            mode=mode,
            start_date=start_date,
            end_date=end_date,
            limit_per_symbol=limit_per_symbol,
            perform_download=perform_download,
            keywords=keywords,
            section_filter=section_filter,
        )

        try:
            while True:
                doc = next(doc_gen)
                yield doc.page_content
        except StopIteration:
            return self.last_meta

    @property
    def last_meta(self) -> LoaderRunMetadata:
        """Metadata from the last load_documents call (download counts, etc.)."""
        return self._last_meta

    def load_xbrl_facts(
        self,
        tags: list[str],
        mode: FilingMode,
        limit_per_symbol: int | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Document]:
        """
        Minimal Inline XBRL fact extractor.

        Scans downloaded filing HTML/XML files for ix:nonFraction facts matching
        the provided tags and returns them as Documents so downstream pipelines
        (e.g., warranty) can use deterministic numeric values.
        """
        return filings.load_xbrl_facts(
            symbols=self._symbols,
            tags=tags,
            mode=mode,
            downloads_folder=self.downloads_folder,
            limit_per_symbol=limit_per_symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def __repr__(self) -> str:
        symbols = ",".join(sorted(self._symbols)) or "<none>"
        return (
            f"<Loader company_name={self.company_name} symbols=[{symbols}] "
            f"fetch_mode={self.fetch_mode} "
            f"downloads_folder={self.downloads_folder!r}>"
        )

    def __str__(self) -> str:
        mode_str = self.fetch_mode
        return f"Loader({mode_str}) with {len(self._symbols)} symbol(s)"
