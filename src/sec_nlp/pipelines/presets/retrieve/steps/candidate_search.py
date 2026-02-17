"""EFTS candidate retrieval step."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from datetime import date

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


def _company_name_tickers(company_name: str) -> set[str]:
    matches = re.findall(r"\(([^)]+)\)", company_name.upper())
    tickers: set[str] = set()
    for group in matches:
        if "CIK" in group:
            continue
        for part in group.split(","):
            token = part.strip()
            if _TICKER_TOKEN.match(token):
                tickers.add(token)
    return tickers


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

    if target in _company_name_tickers(hit.company_name):
        return True

    if symbol_cik is None:
        return False
    return _normalize_cik(hit.cik) == symbol_cik


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


async def _batch_search(
    *,
    symbol: str | None,
    queries: Sequence[str],
    settings: RetrieveSettings,
) -> list[EFTSBatchResult]:
    start_date, end_date = _date_range(settings)
    normalized_symbol = _normalize_symbol(symbol)
    client = create_efts_client(
        email=settings.email,
        company_name="SEC NLP Tool",
    )
    return await client.batch_search(
        queries=list(queries),
        forms=settings.forms,
        tickers=[normalized_symbol] if normalized_symbol else None,
        start_date=start_date,
        end_date=end_date,
        limit_per_query=settings.efts_candidates,
    )


def run_candidate_search(
    *,
    symbol: str | None,
    queries: Sequence[str],
    settings: RetrieveSettings,
) -> dict[str, list[EFTSHit]]:
    """Run EFTS candidate search for a symbol across queries."""

    if not queries:
        return {}

    normalized_symbol = _normalize_symbol(symbol)
    symbol_display = normalized_symbol or "<all>"

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        batch_results = loop.run_until_complete(
            _batch_search(
                symbol=normalized_symbol,
                queries=queries,
                settings=settings,
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
        loop.close()

    symbol_cik = (
        _resolve_symbol_cik(
            symbol=normalized_symbol,
            settings=settings,
        )
        if normalized_symbol
        else None
    )

    candidates: dict[str, list[EFTSHit]] = {}
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
            continue
        filtered_hits = _filter_hits_for_symbol(
            hits=raw_hits,
            symbol=normalized_symbol,
            symbol_cik=symbol_cik,
        )
        if len(filtered_hits) != len(raw_hits):
            logger.info(
                "Filtered %d/%d cross-symbol EFTS hits for %s query=%r",
                len(raw_hits) - len(filtered_hits),
                len(raw_hits),
                normalized_symbol,
                result.query,
            )
        candidates[result.query] = filtered_hits

    return candidates
