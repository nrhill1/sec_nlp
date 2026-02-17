"""EFTS candidate retrieval step."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import date

from sec_nlp.core.edgar.efts import EFTSAPIError, create_efts_client
from sec_nlp.core.edgar.efts_models import EFTSBatchResult, EFTSHit
from sec_nlp.core.infra.logger import logger

from ..config import RetrieveSettings


def _date_range(settings: RetrieveSettings) -> tuple[date, date]:
    return settings.date_range


async def _batch_search(
    *,
    symbol: str,
    queries: Sequence[str],
    settings: RetrieveSettings,
) -> list[EFTSBatchResult]:
    start_date, end_date = _date_range(settings)
    client = create_efts_client(
        email=settings.email,
        company_name="SEC NLP Tool",
    )
    return await client.batch_search(
        queries=list(queries),
        forms=settings.forms,
        tickers=[symbol],
        start_date=start_date,
        end_date=end_date,
        limit_per_query=settings.efts_candidates,
    )


def run_candidate_search(
    *,
    symbol: str,
    queries: Sequence[str],
    settings: RetrieveSettings,
) -> dict[str, list[EFTSHit]]:
    """Run EFTS candidate search for a symbol across queries."""

    if not queries:
        return {}

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        batch_results = loop.run_until_complete(
            _batch_search(
                symbol=symbol,
                queries=queries,
                settings=settings,
            )
        )
    except EFTSAPIError as exc:
        logger.warning("EFTS candidate search failed for %s: %s", symbol, exc)
        return {}
    except Exception as exc:
        logger.warning(
            "Unexpected EFTS candidate search failure for %s: %s",
            symbol,
            exc,
        )
        return {}
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    candidates: dict[str, list[EFTSHit]] = {}
    for result in batch_results:
        if not result.success:
            logger.debug(
                "EFTS batch query failed for %s query=%r: %s",
                symbol,
                result.query,
                result.error,
            )
            continue
        candidates[result.query] = list(result.hits)

    return candidates
