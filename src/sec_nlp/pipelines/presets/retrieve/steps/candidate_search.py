# src/sec_nlp/pipelines/presets/retrieve/steps/candidate_search.py
"""EFTS candidate retrieval step."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from datetime import date
from functools import lru_cache
from types import TracebackType

from sec_nlp.core.edgar.efts import EFTSAPIError, create_efts_client
from sec_nlp.core.edgar.efts_models import EFTSBatchResult, EFTSHit
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.filings import get_cik_for_ticker

from ..config import RetrieveSettings

_TICKER_TOKEN = re.compile(r"^[A-Z][A-Z0-9\.-]{0,9}$")


def _date_range(settings: RetrieveSettings) -> tuple[date, date]:
    return settings.date_range


def _normalize_symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    normalized = symbol.strip().upper()
    return normalized or None


def _normalize_cik(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    return digits.zfill(10)


def _scope_query_to_symbol(*, query: str, symbol: str) -> str:
    """Prefix query with symbol ticker when not already present."""
    cleaned = query.strip()
    if not cleaned:
        return symbol
    token = symbol.upper()
    pattern = rf"\b{re.escape(token)}\b"
    if re.search(pattern, cleaned, flags=re.IGNORECASE):
        return cleaned
    return f"{token} {cleaned}"


def _scope_queries_for_symbol(
    *,
    queries: Sequence[str],
    symbol: str,
) -> tuple[list[str], dict[str, str]]:
    """Build symbol-scoped EFTS queries and reverse map to originals."""
    scoped_queries: list[str] = []
    reverse_map: dict[str, str] = {}
    for original in queries:
        scoped = _scope_query_to_symbol(query=original, symbol=symbol)
        scoped_queries.append(scoped)
        reverse_map[scoped] = original
    return scoped_queries, reverse_map


@lru_cache(maxsize=4096)
def _company_name_tickers(company_name: str) -> frozenset[str]:
    if "(" not in company_name:
        return frozenset()
    matches = re.findall(r"\(([^)]+)\)", company_name.upper())
    tickers: set[str] = set()
    for group in matches:
        if "CIK" in group:
            continue
        for part in group.split(","):
            token = part.strip()
            if _TICKER_TOKEN.match(token):
                tickers.add(token)
    return frozenset(tickers)


def _hit_matches_symbol(
    *,
    hit: EFTSHit,
    symbol: str,
    symbol_cik: str | None,
) -> bool:
    target = symbol.upper()
    hit_tickers = {ticker.strip().upper() for ticker in hit.tickers if ticker}
    if target in hit_tickers:
        return True

    # When EFTS already returns explicit tickers, avoid slower company-name
    # parsing for non-matches and use CIK as the only fallback path.
    if hit_tickers:
        if symbol_cik is None:
            return False
        return _normalize_cik(hit.cik) == symbol_cik

    if symbol_cik is not None and _normalize_cik(hit.cik) == symbol_cik:
        return True

    return target in _company_name_tickers(hit.company_name)


def _resolve_symbol_cik(
    *,
    symbol: str,
    settings: RetrieveSettings,
) -> str | None:
    try:
        cik = get_cik_for_ticker(
            ticker=symbol,
            company_name="SEC NLP Tool",
            email=settings.email,
        )
        return _normalize_cik(cik)
    except Exception as exc:
        logger.debug("Failed to resolve CIK for %s: %s", symbol, exc)
        return None


def _filter_hits_for_symbol(
    *,
    hits: list[EFTSHit],
    symbol: str,
    symbol_cik: str | None,
) -> list[EFTSHit]:
    if not symbol.strip():
        return list(hits)

    filtered = [
        hit
        for hit in hits
        if _hit_matches_symbol(
            hit=hit,
            symbol=symbol,
            symbol_cik=symbol_cik,
        )
    ]
    return filtered


class RetrieveCandidateSearcher:
    """Run-scoped EFTS candidate searcher that reuses client + event loop."""

    def __init__(self, settings: RetrieveSettings) -> None:
        self._settings = settings
        self._start_date, self._end_date = _date_range(settings)
        self._client = create_efts_client(
            email=settings.email,
            company_name="SEC NLP Tool",
        )
        self._loop = asyncio.new_event_loop()
        self._symbol_cik_cache: dict[str, str | None] = {}

    async def _batch_search_async(
        self,
        *,
        symbol: str | None,
        queries: Sequence[str],
    ) -> list[EFTSBatchResult]:
        normalized_symbol = _normalize_symbol(symbol)
        return await self._client.batch_search(
            queries=list(queries),
            forms=self._settings.forms,
            tickers=[normalized_symbol] if normalized_symbol else None,
            start_date=self._start_date,
            end_date=self._end_date,
            limit_per_query=self._settings.efts_candidates,
        )

    def _resolve_symbol_cik_cached(self, symbol: str) -> str | None:
        cached = self._symbol_cik_cache.get(symbol)
        if symbol in self._symbol_cik_cache:
            return cached
        resolved = _resolve_symbol_cik(symbol=symbol, settings=self._settings)
        self._symbol_cik_cache[symbol] = resolved
        return resolved

    def _candidates_from_batch_results(
        self,
        *,
        normalized_symbol: str | None,
        queries: Sequence[str],
        batch_results: list[EFTSBatchResult],
    ) -> dict[str, list[EFTSHit]]:
        symbol_display = normalized_symbol or "<all>"
        symbol_cik: str | None = None

        candidates: dict[str, list[EFTSHit]] = {query: [] for query in queries}
        for result in batch_results:
            if not result.success:
                logger.debug(
                    "EFTS batch query failed for %s query=%r: %s",
                    symbol_display,
                    result.query,
                    result.error,
                )
                continue

            raw_hits = list(result.hits)
            if normalized_symbol is None:
                candidates[result.query] = raw_hits
                logger.debug(
                    "EFTS hits for %s query=%r: %d",
                    symbol_display,
                    result.query,
                    len(raw_hits),
                )
                continue

            filtered_hits = _filter_hits_for_symbol(
                hits=raw_hits,
                symbol=normalized_symbol,
                symbol_cik=None,
            )
            if len(filtered_hits) != len(raw_hits):
                # Avoid extra SEC ticker-registry lookups unless the fast
                # ticker/company-name pass produced no symbol matches.
                if not filtered_hits and any(
                    _normalize_cik(hit.cik) is not None for hit in raw_hits
                ):
                    if symbol_cik is None:
                        symbol_cik = self._resolve_symbol_cik_cached(
                            normalized_symbol
                        )
                    if symbol_cik:
                        filtered_hits = _filter_hits_for_symbol(
                            hits=raw_hits,
                            symbol=normalized_symbol,
                            symbol_cik=symbol_cik,
                        )
                logger.debug(
                    "Filtered %d/%d cross-symbol EFTS hits for %s query=%r",
                    len(raw_hits) - len(filtered_hits),
                    len(raw_hits),
                    normalized_symbol,
                    result.query,
                )
            logger.debug(
                "EFTS hits for %s query=%r: %d",
                normalized_symbol,
                result.query,
                len(filtered_hits),
            )
            candidates[result.query] = filtered_hits

        return candidates

    @staticmethod
    def _truncate_query(query: str, *, max_chars: int = 56) -> str:
        """Truncate query text for compact console summaries."""
        normalized = " ".join(query.split())
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[: max_chars - 1].rstrip()}…"

    @classmethod
    def _log_query_hit_summary(
        cls,
        *,
        symbol: str,
        candidates_by_query: dict[str, list[EFTSHit]],
        max_queries: int = 5,
    ) -> None:
        """Emit a compact one-line summary of EFTS hits per symbol."""
        total_hits = sum(len(hits) for hits in candidates_by_query.values())
        query_count = len(candidates_by_query)
        if query_count == 0:
            logger.info("EFTS summary for %s: 0 hits across 0 queries", symbol)
            return

        ranked = sorted(
            candidates_by_query.items(),
            key=lambda item: len(item[1]),
            reverse=True,
        )
        snippets: list[str] = []
        for query, hits in ranked[:max_queries]:
            snippets.append(
                f"{len(hits)}:{cls._truncate_query(query, max_chars=44)}"
            )
        remaining = max(0, len(ranked) - max_queries)
        if remaining > 0:
            snippets.append(f"+{remaining} more")

        logger.info(
            "EFTS summary for %s: %d hits across %d queries [%s]",
            symbol,
            total_hits,
            query_count,
            "; ".join(snippets),
        )

    def search(
        self,
        *,
        symbol: str | None,
        queries: Sequence[str],
    ) -> dict[str, list[EFTSHit]]:
        if not queries:
            return {}

        normalized_symbol = _normalize_symbol(symbol)
        symbol_display = normalized_symbol or "<all>"
        effective_queries = list(queries)
        reverse_query_map: dict[str, str] = {}
        if normalized_symbol is not None:
            (
                effective_queries,
                reverse_query_map,
            ) = _scope_queries_for_symbol(
                queries=queries,
                symbol=normalized_symbol,
            )

        try:
            asyncio.set_event_loop(self._loop)
            batch_results = self._loop.run_until_complete(
                self._batch_search_async(
                    symbol=normalized_symbol,
                    queries=effective_queries,
                )
            )
        except EFTSAPIError as exc:
            logger.warning(
                "EFTS candidate search failed for %s: %s",
                symbol_display,
                exc,
            )
            return {}
        except Exception as exc:
            logger.warning(
                "Unexpected EFTS candidate search failure for %s: %s",
                symbol_display,
                exc,
            )
            return {}
        finally:
            asyncio.set_event_loop(None)

        candidates = self._candidates_from_batch_results(
            normalized_symbol=normalized_symbol,
            queries=effective_queries,
            batch_results=batch_results,
        )
        if normalized_symbol is None:
            self._log_query_hit_summary(
                symbol=symbol_display,
                candidates_by_query=candidates,
            )
            return candidates

        remapped: dict[str, list[EFTSHit]] = {query: [] for query in queries}
        for scoped_query, hits in candidates.items():
            original_query = reverse_query_map.get(scoped_query, scoped_query)
            remapped[original_query] = hits
        self._log_query_hit_summary(
            symbol=normalized_symbol,
            candidates_by_query=remapped,
        )
        return remapped

    def search_many(
        self,
        *,
        symbols: Sequence[str | None],
        queries: Sequence[str],
    ) -> dict[str, dict[str, list[EFTSHit]]]:
        if not queries:
            return {}

        normalized_symbols: list[str] = []
        seen: set[str] = set()
        for raw_symbol in symbols:
            normalized = _normalize_symbol(raw_symbol)
            if normalized is None:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            normalized_symbols.append(normalized)
        if not normalized_symbols:
            return {}

        scoped_queries_by_symbol: dict[str, list[str]] = {}
        reverse_query_maps: dict[str, dict[str, str]] = {}
        for symbol in normalized_symbols:
            (
                scoped_queries,
                reverse_map,
            ) = _scope_queries_for_symbol(
                queries=queries,
                symbol=symbol,
            )
            scoped_queries_by_symbol[symbol] = scoped_queries
            reverse_query_maps[symbol] = reverse_map

        async def _search_many_async() -> list[object]:
            tasks = [
                self._batch_search_async(
                    symbol=symbol,
                    queries=scoped_queries_by_symbol[symbol],
                )
                for symbol in normalized_symbols
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        try:
            asyncio.set_event_loop(self._loop)
            gathered = self._loop.run_until_complete(_search_many_async())
        finally:
            asyncio.set_event_loop(None)

        results: dict[str, dict[str, list[EFTSHit]]] = {}
        for symbol, current in zip(normalized_symbols, gathered, strict=False):
            if isinstance(current, EFTSAPIError):
                logger.warning(
                    "EFTS candidate search failed for %s: %s",
                    symbol,
                    current,
                )
                results[symbol] = {query: [] for query in queries}
                continue
            if isinstance(current, Exception):
                logger.warning(
                    "Unexpected EFTS candidate search failure for %s: %s",
                    symbol,
                    current,
                )
                results[symbol] = {query: [] for query in queries}
                continue
            candidates = self._candidates_from_batch_results(
                normalized_symbol=symbol,
                queries=scoped_queries_by_symbol[symbol],
                batch_results=current,
            )
            reverse_map = reverse_query_maps[symbol]
            remapped: dict[str, list[EFTSHit]] = {
                query: [] for query in queries
            }
            for scoped_query, hits in candidates.items():
                original_query = reverse_map.get(scoped_query, scoped_query)
                remapped[original_query] = hits
            self._log_query_hit_summary(
                symbol=symbol,
                candidates_by_query=remapped,
            )
            results[symbol] = remapped
        return results

    def close(self) -> None:
        if self._loop.is_closed():
            return
        self._loop.close()

    def __enter__(self) -> RetrieveCandidateSearcher:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()


def run_candidate_search(
    *,
    symbol: str | None,
    queries: Sequence[str],
    settings: RetrieveSettings,
) -> dict[str, list[EFTSHit]]:
    """Run EFTS candidate search for a symbol across queries."""

    with RetrieveCandidateSearcher(settings) as searcher:
        return searcher.search(symbol=symbol, queries=queries)
