# src/sec_nlp/pipelines/presets/analyze/steps/search/efts_search.py
"""EFTS search integration for the analyze pipeline.

Combines SEC EDGAR Full-Text Search (EFTS) with local vector search
for broader filing discovery.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, timedelta

from langchain_core.documents import Document
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.edgar.efts import EFTSAPIError, EFTSClient, create_efts_client
from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.text.ranking import KeywordExtractor, RankingAlgorithm

from ...config import EFTSConfig


@dataclass
class EFTSSearchResult:
    """Result from an EFTS search operation."""

    query: str
    hits: list[EFTSHit] = field(default_factory=list)
    total: int = 0
    new_accessions: list[str] = field(default_factory=list)
    downloaded_accessions: list[str] = field(default_factory=list)


@dataclass
class HybridSearchResult:
    """Combined results from local vector search and EFTS."""

    local_docs: list[Document] = field(default_factory=list)
    efts_results: list[EFTSSearchResult] = field(default_factory=list)
    discovered_filings: int = 0
    downloaded_filings: int = 0


class EFTSSearchRunnable(BaseModel):
    """Run EFTS searches and optionally download discovered filings.

    Example:
        runner = EFTSSearchRunnable(
            efts_config=analyze_config.efts,
            symbols=analyze_config.symbols,
            forms=list(analyze_config.mode.forms),
            start_date=analyze_config.start_date,
            end_date=analyze_config.end_date,
            email="user@example.com",
        )
        results = await runner.search_queries(["warranty accrual", "recall"])
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    efts_config: EFTSConfig = Field(description="EFTS configuration")
    symbols: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    mode: FilingMode | None = None
    start_date: date | None = None
    end_date: date | None = None
    email: str = Field(
        description="Contact email for SEC API requests",
    )
    local_accessions: set[str] = Field(
        default_factory=set,
        description="Set of accession numbers already downloaded locally",
    )

    def _get_efts_config(self) -> EFTSConfig:
        """Get EFTS configuration from analyze config."""
        return self.efts_config

    def _create_client(self) -> EFTSClient:
        """Create an EFTS client with proper user agent."""
        return create_efts_client(
            email=self.email,
            company_name="SEC NLP Tool",
        )

    def _get_date_range(self) -> tuple[date | None, date | None]:
        """Calculate date range for EFTS search."""
        efts_config = self._get_efts_config()

        if efts_config.expand_date_range:
            end_date = date.today()
            start_date = end_date - timedelta(
                days=365 * efts_config.date_range_years
            )
            return start_date, end_date

        # Use pipeline date range if configured
        return self.start_date, self.end_date

    def _get_form_types(self) -> list[str]:
        """Get form types to search."""
        efts_config = self._get_efts_config()

        if efts_config.forms:
            return list(efts_config.forms)

        if self.forms:
            return list(self.forms)

        if self.mode is not None:
            return list(self.mode.forms)

        return []

    def _get_ciks(self) -> list[str]:
        """Get CIKs for configured symbols."""
        # This would need CIK lookup - for now return empty
        # The EFTS API can also filter by ticker directly
        return []

    def _get_tickers(self) -> list[str]:
        """Get tickers to filter EFTS results."""
        return [s.strip().upper() for s in self.symbols if s.strip()]

    @staticmethod
    def _filter_hits_by_ticker(
        hits: list[EFTSHit],
        tickers: list[str],
    ) -> list[EFTSHit]:
        """Filter EFTS hits to only include filings from specified tickers.

        Args:
            hits: List of EFTS search hits
            tickers: List of ticker symbols to keep (case-insensitive)

        Returns:
            Filtered list containing only hits matching the specified tickers
        """
        if not tickers:
            return hits

        ticker_set = {t.upper() for t in tickers}

        filtered: list[EFTSHit] = []
        for hit in hits:
            # Check if any of the hit's tickers match our filter
            hit_tickers = {t.upper() for t in hit.tickers if t}
            if hit_tickers & ticker_set:
                filtered.append(hit)

        return filtered

    async def search_queries(
        self, queries: list[str]
    ) -> list[EFTSSearchResult]:
        """Execute EFTS searches for all queries using batch search.

        Uses the Rust batch_search_async for efficient parallel execution
        with built-in rate limiting.

        Args:
            queries: List of search queries

        Returns:
            List of EFTSSearchResult for each query
        """
        efts_config = self._get_efts_config()

        if not efts_config.enabled:
            logger.debug("EFTS search disabled")
            return []

        if not queries:
            logger.debug("No queries provided for EFTS search")
            return []

        client = self._create_client()
        start_date, end_date = self._get_date_range()
        form_types = self._get_form_types()
        tickers = self._get_tickers()

        logger.info(
            "EFTS batch search: %d queries (forms=%s, tickers=%s)",
            len(queries),
            form_types,
            tickers,
        )

        try:
            batch_results = await client.batch_search(
                queries,
                forms=form_types,
                tickers=tickers if tickers else None,
                start_date=start_date,
                end_date=end_date,
                limit_per_query=efts_config.limit,
            )
        except EFTSAPIError as e:
            logger.error("EFTS batch search failed: %s", e)
            return [EFTSSearchResult(query=q) for q in queries]
        except Exception as e:
            logger.error("Unexpected error in EFTS batch search: %s", e)
            return [EFTSSearchResult(query=q) for q in queries]

        extractor: KeywordExtractor | None = None
        try:
            extractor = KeywordExtractor(
                algorithm=RankingAlgorithm.YAKE,
                ngram_size=3,
            )
        except Exception as exc:
            logger.warning("YAKE extractor unavailable: %s", exc)

        results: list[EFTSSearchResult] = []
        for batch_result in batch_results:
            if batch_result.error:
                logger.error(
                    "EFTS search failed for query '%s': %s",
                    batch_result.query,
                    batch_result.error,
                )
                results.append(EFTSSearchResult(query=batch_result.query))
                continue

            # Filter by score threshold
            hits = batch_result.hits
            if efts_config.score_threshold > 0:
                hits = [
                    h for h in hits if h.score >= efts_config.score_threshold
                ]

            # Filter by ticker scope
            scoped_hits = self._filter_hits_by_ticker(hits, tickers)
            if len(scoped_hits) != len(hits):
                logger.info(
                    "EFTS ticker scope '%s': kept %d/%d hits",
                    batch_result.query,
                    len(scoped_hits),
                    len(hits),
                )

            if extractor is not None:
                enriched_hits: list[EFTSHit] = []
                for hit in scoped_hits:
                    snippet = hit.snippet or ""
                    keyword_source = (
                        snippet if snippet.strip() else batch_result.query
                    )
                    keywords = (
                        [
                            kw.keyword
                            for kw in extractor.extract(keyword_source, top_n=5)
                        ]
                        if keyword_source.strip()
                        else []
                    )
                    enriched_hits.append(
                        hit.model_copy(update={"yake_keywords": keywords})
                    )
                scoped_hits = enriched_hits

            # Identify new accessions
            scoped_new_accessions = [
                hit.accession_number
                for hit in scoped_hits
                if hit.accession_number not in self.local_accessions
            ]

            logger.info(
                "EFTS search '%s': %d hits, %d new accessions",
                batch_result.query,
                len(scoped_hits),
                len(scoped_new_accessions),
            )

            results.append(
                EFTSSearchResult(
                    query=batch_result.query,
                    hits=scoped_hits,
                    total=batch_result.total,
                    new_accessions=scoped_new_accessions,
                )
            )

        return results

    def get_accessions_to_download(
        self, results: list[EFTSSearchResult]
    ) -> list[str]:
        """Get unique accessions to download from EFTS results.

        Respects auto_download_limit from config.
        """
        efts_config = self._get_efts_config()

        if (
            not efts_config.auto_download
            or efts_config.auto_download_limit <= 0
        ):
            return []

        # Collect unique new accessions ordered by relevance (score)
        seen: set[str] = set()
        to_download: list[str] = []

        for result in results:
            for hit in result.hits:
                if (
                    hit.accession_number not in seen
                    and hit.accession_number not in self.local_accessions
                ):
                    seen.add(hit.accession_number)
                    to_download.append(hit.accession_number)

                    if len(to_download) >= efts_config.auto_download_limit:
                        return to_download

        return to_download

    def hits_to_documents(
        self, results: list[EFTSSearchResult]
    ) -> list[Document]:
        """Convert EFTS hits to Document objects for downstream processing.

        These documents contain metadata about discovered filings but no content
        until the filings are downloaded.
        """
        docs: list[Document] = []
        seen: set[str] = set()

        for result in results:
            for hit in result.hits:
                if hit.accession_number in seen:
                    continue
                seen.add(hit.accession_number)

                doc = Document(
                    page_content=hit.snippet,
                    metadata={
                        "source": "efts",
                        "accession_number": hit.accession_number,
                        "cik": hit.cik,
                        "company_name": hit.company_name,
                        "tickers": hit.tickers,
                        "form_type": hit.form_type,
                        "filed_date": hit.filed_date.isoformat(),
                        "efts_score": hit.score,
                        "efts_query": result.query,
                        "yake_keywords": hit.yake_keywords,
                        "edgar_url": hit.edgar_url,
                        "is_local": hit.accession_number
                        in self.local_accessions,
                    },
                )
                docs.append(doc)

        return docs


def run_efts_search(
    efts_config: EFTSConfig,
    symbols: list[str],
    forms: list[str],
    mode: FilingMode | None,
    start_date: date | None,
    end_date: date | None,
    queries: list[str],
    email: str,
    local_accessions: set[str] | None = None,
) -> list[EFTSSearchResult]:
    """Synchronous wrapper for EFTS search.

    Args:
        efts_config: EFTS configuration
        symbols: Symbols to scope the EFTS searches
        forms: Filing form types to include
        mode: Filing mode used for default forms
        start_date: Optional pipeline start date
        end_date: Optional pipeline end date
        queries: Search queries to execute
        email: Contact email for SEC API
        local_accessions: Set of already-downloaded accession numbers

    Returns:
        List of EFTS search results
    """
    runner = EFTSSearchRunnable(
        efts_config=efts_config,
        symbols=symbols,
        forms=forms,
        mode=mode,
        start_date=start_date,
        end_date=end_date,
        email=email,
        local_accessions=local_accessions or set(),
    )

    return asyncio.run(runner.search_queries(queries))
