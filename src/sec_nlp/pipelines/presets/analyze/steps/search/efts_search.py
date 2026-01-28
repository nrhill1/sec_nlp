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
from sec_nlp.core.infra.logger import logger

from ...config import AnalyzeConfig, EFTSConfig


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


class EFTSSearchRunner(BaseModel):
    """Run EFTS searches and optionally download discovered filings.

    Example:
        runner = EFTSSearchRunner(
            config=analyze_config,
            email="user@example.com",
        )
        results = await runner.search_queries(["warranty accrual", "recall"])
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="forbid",
    )

    config: AnalyzeConfig = Field(
        description="Analyze pipeline configuration",
    )
    email: str = Field(
        description="Contact email for SEC API requests",
    )
    local_accessions: set[str] = Field(
        default_factory=set,
        description="Set of accession numbers already downloaded locally",
    )

    def _get_efts_config(self) -> EFTSConfig:
        """Get EFTS configuration from analyze config."""
        return self.config.efts

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
        return self.config.start_date, self.config.end_date

    def _get_form_types(self) -> list[str]:
        """Get form types to search."""
        efts_config = self._get_efts_config()

        if efts_config.forms:
            return list(efts_config.forms)

        # Fall back to pipeline mode
        return list(self.config.mode.forms)

    def _get_ciks(self) -> list[str]:
        """Get CIKs for configured symbols."""
        # This would need CIK lookup - for now return empty
        # The EFTS API can also filter by ticker directly
        return []

    def _get_tickers(self) -> list[str]:
        """Get tickers to filter EFTS results."""
        return [s.strip().upper() for s in self.config.symbols if s.strip()]

    @staticmethod
    def _filter_hits_by_ticker(
        hits: list[EFTSHit],
        tickers: list[str],
    ) -> list[EFTSHit]:
        _ = tickers
        return hits

    async def search_queries(
        self, queries: list[str]
    ) -> list[EFTSSearchResult]:
        """Execute EFTS searches for all queries.

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

        results: list[EFTSSearchResult] = []

        for query in queries:
            try:
                result = await self._search_single_query(
                    client=client,
                    query=query,
                    forms=form_types,
                    tickers=tickers,
                    start_date=start_date,
                    end_date=end_date,
                    limit=efts_config.limit,
                    score_threshold=efts_config.score_threshold,
                )
                scoped_hits = self._filter_hits_by_ticker(
                    result.hits,
                    tickers,
                )
                if len(scoped_hits) != len(result.hits):
                    logger.info(
                        "EFTS ticker scope '%s': kept %d/%d hits",
                        query,
                        len(scoped_hits),
                        len(result.hits),
                    )
                scoped_new_accessions = [
                    hit.accession_number
                    for hit in scoped_hits
                    if hit.accession_number not in self.local_accessions
                ]
                results.append(
                    EFTSSearchResult(
                        query=query,
                        hits=scoped_hits,
                        total=len(scoped_hits),
                        new_accessions=scoped_new_accessions,
                    )
                )
            except EFTSAPIError as e:
                logger.error("EFTS search failed for query '%s': %s", query, e)
                results.append(EFTSSearchResult(query=query))
            except Exception as e:
                logger.error(
                    "Unexpected error in EFTS search for query '%s': %s",
                    query,
                    e,
                )
                results.append(EFTSSearchResult(query=query))

        return results

    async def _search_single_query(
        self,
        *,
        client: EFTSClient,
        query: str,
        forms: list[str],
        tickers: list[str],
        start_date: date | None,
        end_date: date | None,
        limit: int,
        score_threshold: float,
    ) -> EFTSSearchResult:
        """Execute a single EFTS search."""
        logger.info(
            "EFTS search: '%s' (forms=%s, tickers=%s)", query, forms, tickers
        )

        response = await client.search(
            query,
            forms=forms,
            tickers=tickers if tickers else None,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )

        # Filter by score threshold if configured
        hits = response.hits
        if score_threshold > 0:
            hits = [h for h in hits if h.score >= score_threshold]

        # Identify new accessions not in local storage
        new_accessions = [
            h.accession_number
            for h in hits
            if h.accession_number not in self.local_accessions
        ]

        logger.info(
            "EFTS search '%s': %d hits, %d new accessions",
            query,
            len(hits),
            len(new_accessions),
        )

        return EFTSSearchResult(
            query=query,
            hits=hits,
            total=response.total,
            new_accessions=new_accessions,
        )

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
                        "edgar_url": hit.edgar_url,
                        "is_local": hit.accession_number
                        in self.local_accessions,
                    },
                )
                docs.append(doc)

        return docs


def run_efts_search(
    config: AnalyzeConfig,
    queries: list[str],
    email: str,
    local_accessions: set[str] | None = None,
) -> list[EFTSSearchResult]:
    """Synchronous wrapper for EFTS search.

    Args:
        config: Analyze pipeline configuration
        queries: Search queries to execute
        email: Contact email for SEC API
        local_accessions: Set of already-downloaded accession numbers

    Returns:
        List of EFTS search results
    """
    runner = EFTSSearchRunner(
        config=config,
        email=email,
        local_accessions=local_accessions or set(),
    )

    return asyncio.run(runner.search_queries(queries))
