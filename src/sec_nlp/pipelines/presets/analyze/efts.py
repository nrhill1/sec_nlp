# src/sec_nlp/pipelines/presets/analyze/efts.py
"""EFTS search helpers for the analyze pipeline."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from langchain_core.documents import Document

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.downloader import download_accessions
from sec_nlp.core.ingest.filings import get_filing_date_from_dir
from sec_nlp.core.text.ranking import KeywordExtractor, RankingAlgorithm
from sec_nlp.pipelines.presets.analyze.config import AnalyzeConfig
from sec_nlp.pipelines.presets.analyze.runnables.efts import (
    EFTSSearchInput,
    EFTSSearchRunnable,
)
from sec_nlp.pipelines.presets.analyze.runnables.search import (
    SearchQueryResults,
    SearchResultsByQuery,
)
from sec_nlp.pipelines.presets.analyze.steps.search.efts_search import (
    EFTSSearchResult,
)
from sec_nlp.pipelines.runtime import get_accession_from_metadata
from sec_nlp.pipelines.types import MetadataScalar, MetadataValue


def cap_efts_download_limit(
    config: AnalyzeConfig,
    limit_per_symbol: int | None,
) -> int | None:
    """Clamp per-symbol EFTS downloads to configured hard limits."""
    if limit_per_symbol is not None:
        return limit_per_symbol
    auto_limit = config.efts.auto_download_limit
    if auto_limit <= 0:
        return 0
    return auto_limit


def efts_date_range(
    config: AnalyzeConfig,
) -> tuple[date | None, date | None]:
    """Resolve the EFTS date window for the current analyze run."""
    if config.efts.expand_date_range:
        end_date = date.today()
        start_date = end_date - timedelta(
            days=365 * config.efts.date_range_years
        )
        return start_date, end_date
    return config.start_date, config.end_date


def local_accessions(config: AnalyzeConfig, symbol: str) -> set[str]:
    """Collect local accession directories for a symbol within the date window."""
    start_date, end_date = efts_date_range(config)
    accession_set = set()
    for form_type in config.mode.forms:
        filing_dir = (
            config.dl_path / "sec-edgar-filings" / symbol.upper() / form_type
        )
        if not filing_dir.exists():
            continue
        for path in filing_dir.iterdir():
            if not path.is_dir():
                continue
            filing_date = get_filing_date_from_dir(path)
            if start_date or end_date:
                if filing_date is None:
                    accession_set.add(path.name)
                    continue
                if start_date and filing_date < start_date:
                    continue
                if end_date and filing_date > end_date:
                    continue
            accession_set.add(path.name)
    return accession_set


def select_efts_accessions(
    results: list[EFTSSearchResult],
    accessions: list[str],
    limit: int | None,
) -> list[str]:
    """Select highest-scoring accession candidates, capped by limit when set."""
    if not accessions:
        return []
    allowed = {accession for accession in accessions if accession}
    if not allowed:
        return []
    best_scores: dict[str, float] = {}
    for result in results:
        for hit in result.hits:
            accession = hit.accession_number
            if accession not in allowed:
                continue
            score = float(hit.score)
            best = best_scores.get(accession)
            if best is None or score > best:
                best_scores[accession] = score
    ordered = sorted(
        best_scores.items(),
        key=lambda item: (-item[1], item[0]),
    )
    ranked = [accession for accession, _ in ordered]
    if limit is None:
        return ranked
    return ranked[:limit]


def download_efts_accessions(
    *,
    config: AnalyzeConfig,
    company_name: str | None,
    symbol: str,
    accessions: list[str],
    results: list[EFTSSearchResult],
) -> int:
    """Download selected accessions and return count of successful downloads."""
    if not accessions:
        return 0

    accession_set = set(accessions)
    hits_by_accession: dict[str, EFTSHit] = {}
    for result in results:
        for hit in result.hits:
            accession = hit.accession_number
            if (
                accession in accession_set
                and accession not in hits_by_accession
            ):
                hits_by_accession[accession] = hit
    if not hits_by_accession:
        return 0

    accession_cik_map = {
        accession: hit.cik for accession, hit in hits_by_accession.items()
    }

    safe_company_name = company_name or symbol
    download_results = download_accessions(
        symbol=symbol,
        accessions=accessions,
        accession_cik_map=accession_cik_map,
        mode=config.mode,
        work_folder=config.dl_path,
        company_name=safe_company_name,
        email=config.email,
    )

    downloaded = 0
    for result in download_results.values():
        if not result.get("success"):
            continue
        count = result.get("downloaded")
        if isinstance(count, int) and count > 0:
            downloaded += 1
    return downloaded


def run_efts_for_symbol(
    *,
    config: AnalyzeConfig,
    efts_runner: EFTSSearchRunnable | None,
    symbol: str,
    queries: list[str],
    forms: list[str] | None = None,
) -> tuple[list[EFTSSearchResult], list[str], bool]:
    """Run EFTS search for one symbol and optionally identify new accessions."""
    if not queries or not config.efts.enabled:
        return [], [], False

    local = local_accessions(config, symbol)
    runner = efts_runner
    if runner is None:
        effective_forms = forms if forms is not None else config.effective_forms
        runner = EFTSSearchRunnable(
            efts_config=config.efts,
            forms=effective_forms,
            mode=config.mode,
            start_date=config.start_date,
            end_date=config.end_date,
            email=config.email,
        )
    try:
        results = runner.invoke(
            EFTSSearchInput(
                symbol=symbol,
                queries=queries,
                local_accessions=local,
            )
        )
    except Exception as exc:
        logger.warning("EFTS search failed for %s: %s", symbol, exc)
        return [], [], False

    new_accessions: set[str] = set()
    for result in results:
        for accession in result.new_accessions:
            new_accessions.add(accession)

    return results, sorted(new_accessions), True


def collect_efts_hits(
    *,
    config: AnalyzeConfig,
    results_by_symbol: dict[str, list[EFTSSearchResult]],
    market_context_by_symbol: dict[str, str],
) -> tuple[
    dict[str, list[tuple[Document, float]]],
    dict[str, int],
]:
    """Group EFTS hits by query and collect per-query totals."""
    hits_by_query: dict[str, list[tuple[Document, float]]] = defaultdict(list)
    totals_by_query: dict[str, int] = defaultdict(int)

    for symbol, results in results_by_symbol.items():
        if not results:
            continue
        local = local_accessions(config, symbol)
        market_context = market_context_by_symbol.get(symbol)
        for result in results:
            query = result.query
            if not query:
                continue
            totals_by_query[query] += result.total
            seen_accessions: set[str] = set()
            for hit in result.hits:
                accession = hit.accession_number
                if accession in seen_accessions:
                    continue
                seen_accessions.add(accession)
                tickers: list[MetadataScalar] = [
                    ticker
                    for ticker in hit.tickers
                    if isinstance(ticker, str) and ticker
                ]
                hit_symbol = hit.ticker or (tickers[0] if tickers else symbol)
                yake_keywords: list[MetadataScalar] = list(hit.yake_keywords)
                metadata: dict[str, MetadataValue] = {
                    "source": "efts",
                    "search_source": "efts",
                    "symbol": str(hit_symbol).upper(),
                    "accession_number": accession,
                    "cik": hit.cik,
                    "company_name": hit.company_name,
                    "tickers": tickers,
                    "form_type": hit.form_type,
                    "filed_date": hit.filed_date.isoformat(),
                    "efts_score": float(hit.score),
                    "efts_query": query,
                    "yake_keywords": yake_keywords,
                    "edgar_url": hit.edgar_url,
                    "is_local": accession in local,
                }
                if market_context:
                    metadata["market_enrichment_context"] = market_context
                doc = Document(
                    page_content=hit.snippet,
                    metadata=metadata,
                )
                hits_by_query[query].append((doc, float(hit.score)))

    return dict(hits_by_query), dict(totals_by_query)


def normalize_scores(scores: list[float]) -> list[float]:
    """Scale score values into a 0..1 range with min-max normalization."""
    if not scores:
        return []
    low = min(scores)
    high = max(scores)
    if high <= low:
        return [1.0 for _ in scores]
    return [(score - low) / (high - low) for score in scores]


def adjust_efts_score(
    normalized_score: float,
    *,
    vector_scores: list[float],
    prefers_lower: bool,
) -> float:
    """Project normalized EFTS scores into the vector scoring scale."""
    if not vector_scores:
        return 1.0 - normalized_score if prefers_lower else normalized_score
    best = min(vector_scores) if prefers_lower else max(vector_scores)
    worst = max(vector_scores) if prefers_lower else min(vector_scores)
    if best == worst:
        return best
    if prefers_lower:
        return best + (1.0 - normalized_score) * (worst - best)
    return worst + normalized_score * (best - worst)


def update_search_sources(
    metadata: dict[str, MetadataValue],
    source: str,
) -> None:
    """Add a search source label to metadata without duplicates."""
    existing = metadata.get("search_sources")
    sources: list[MetadataScalar] = []
    if isinstance(existing, list):
        for item in existing:
            if isinstance(item, str) and item not in sources:
                sources.append(item)
    elif isinstance(existing, str):
        sources.append(existing)
    if source not in sources:
        sources.append(source)
    metadata["search_sources"] = sources


def annotate_efts_match(
    docs: list[Document],
    *,
    query: str,
    score: float,
) -> None:
    """Attach EFTS query match metadata to each overlapping document."""
    for doc in docs:
        metadata: dict[str, MetadataValue] = dict(doc.metadata or {})
        matches = metadata.get("efts_matches")
        cleaned: list[dict[str, MetadataScalar]] = []
        if isinstance(matches, list):
            for item in matches:
                if isinstance(item, dict):
                    filtered: dict[str, MetadataScalar] = {}
                    for key, value in item.items():
                        if (
                            isinstance(key, str)
                            and isinstance(value, (str, int, float, bool))
                            or isinstance(key, str)
                            and value is None
                        ):
                            filtered[key] = value
                    if filtered:
                        cleaned.append(filtered)
        already_present = False
        for item in cleaned:
            if item.get("query") == query:
                already_present = True
                break
        if not already_present:
            cleaned.append({"query": query, "score": float(score)})
        metadata["efts_matches"] = cleaned
        update_search_sources(metadata, "efts")
        doc.metadata = metadata


def build_hybrid_search_results(
    *,
    config: AnalyzeConfig,
    vector_results: SearchResultsByQuery | None,
    efts_results_by_symbol: dict[str, list[EFTSSearchResult]],
    market_context_by_symbol: dict[str, str],
) -> SearchResultsByQuery:
    """Merge vector and EFTS results into one ranked query result map."""
    base_results = vector_results or {}
    efts_hits_by_query, efts_totals = collect_efts_hits(
        config=config,
        results_by_symbol=efts_results_by_symbol,
        market_context_by_symbol=market_context_by_symbol,
    )
    if not efts_hits_by_query:
        return base_results

    distance_metric = config.vdb.qdrant_distance
    prefers_lower = distance_metric in ("Cosine", "Euclid")

    hybrid_results: SearchResultsByQuery = {}
    all_queries = set(base_results) | set(efts_hits_by_query)
    for query in all_queries:
        vector_entry = base_results.get(query)
        vector_filtered = list(vector_entry.filtered) if vector_entry else []
        vector_total = vector_entry.total if vector_entry else 0
        vector_scores = [float(score) for _, score in vector_filtered]
        vector_accessions: dict[str, list[Document]] = defaultdict(list)
        for doc, _ in vector_filtered:
            metadata: dict[str, MetadataValue] = dict(doc.metadata or {})
            update_search_sources(metadata, "vector")
            doc.metadata = metadata
            accession = get_accession_from_metadata(doc.metadata)
            if accession:
                vector_accessions[accession].append(doc)

        efts_hits = efts_hits_by_query.get(query, [])
        efts_filtered: list[tuple[Document, float]] = []
        for doc, raw_score in efts_hits:
            accession = get_accession_from_metadata(doc.metadata)
            if accession and accession in vector_accessions:
                annotate_efts_match(
                    vector_accessions[accession],
                    query=query,
                    score=raw_score,
                )
                continue
            efts_filtered.append((doc, raw_score))

        normalized = normalize_scores(
            [float(score) for _, score in efts_filtered]
        )
        combined = list(vector_filtered)
        for (doc, raw_score), norm in zip(
            efts_filtered, normalized, strict=True
        ):
            metadata: dict[str, MetadataValue] = dict(doc.metadata or {})
            if "efts_score" not in metadata:
                metadata["efts_score"] = float(raw_score)
            update_search_sources(metadata, "efts")
            doc.metadata = metadata
            adjusted_score = adjust_efts_score(
                norm,
                vector_scores=vector_scores,
                prefers_lower=prefers_lower,
            )
            combined.append((doc, adjusted_score))

        total_hits = vector_total + efts_totals.get(query, 0)
        hybrid_results[query] = SearchQueryResults(
            filtered=combined,
            total=total_hits,
        )

    return hybrid_results


def efts_accessions(results: list[EFTSSearchResult]) -> set[str]:
    """Extract unique accession numbers from EFTS results."""
    accessions: set[str] = set()
    for result in results:
        for hit in result.hits:
            accessions.add(hit.accession_number)
    return accessions


def filter_docs_by_accession(
    docs: list[Document],
    accessions: set[str],
) -> list[Document]:
    """Filter documents to those whose accession appears in the allowed set."""
    if not accessions:
        return []
    filtered: list[Document] = []
    for doc in docs:
        accession = get_accession_from_metadata(doc.metadata or {})
        if accession in accessions:
            filtered.append(doc)
    return filtered


def update_efts_keywords_from_docs(
    *,
    symbol: str,
    docs: list[Document],
    results_by_symbol: dict[str, list[EFTSSearchResult]],
) -> None:
    """Populate EFTS hit keywords from downloaded document content."""
    results = results_by_symbol.get(symbol)
    if not results:
        return

    try:
        extractor = KeywordExtractor(
            algorithm=RankingAlgorithm.YAKE,
            ngram_size=3,
        )
    except Exception as exc:
        logger.warning("YAKE extractor unavailable: %s", exc)
        return

    accession_sources: dict[str, str] = {}
    for doc in docs:
        accession = get_accession_from_metadata(doc.metadata)
        if not accession or accession in accession_sources:
            continue
        content = (doc.page_content or "").strip()
        if not content:
            continue
        accession_sources[accession] = content

    if not accession_sources:
        return

    for result in results:
        updated_hits: list[EFTSHit] = []
        for hit in result.hits:
            source_text = accession_sources.get(hit.accession_number, "")
            if source_text:
                keywords = [
                    kw.keyword for kw in extractor.extract(source_text, top_n=5)
                ]
                updated_hits.append(
                    hit.model_copy(update={"yake_keywords": keywords})
                )
            else:
                updated_hits.append(hit)
        result.hits = updated_hits
