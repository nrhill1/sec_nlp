"""Query ranking helpers for retrieve pipeline."""

from __future__ import annotations

from datetime import date

from sec_nlp.core.edgar.efts_models import EFTSHit

from ..models import RetrievalHit


def _sort_key(hit: RetrievalHit) -> tuple[float, date, str, str]:
    parsed_date = date.fromisoformat(hit.filed_date)
    return (hit.score, parsed_date, hit.query.casefold(), hit.accession_number)


def rank_retrieval_hits(
    *,
    symbol: str,
    candidates_by_query: dict[str, list[EFTSHit]],
    top_k: int,
) -> list[RetrievalHit]:
    """Rank flattened EFTS candidates and return top K rows."""

    ranked: list[RetrievalHit] = []
    seen: set[tuple[str, str]] = set()

    for query, hits in candidates_by_query.items():
        for hit in hits:
            key = (query.casefold(), hit.accession_number)
            if key in seen:
                continue
            seen.add(key)
            ranked.append(
                RetrievalHit(
                    symbol=symbol,
                    query=query,
                    accession_number=hit.accession_number,
                    form_type=hit.form_type,
                    filed_date=hit.filed_date.isoformat(),
                    company_name=hit.company_name,
                    cik=hit.cik,
                    score=float(hit.score),
                    edgar_url=hit.edgar_url,
                    snippet=hit.snippet or None,
                )
            )

    ranked.sort(key=_sort_key, reverse=True)
    return ranked[:top_k]
