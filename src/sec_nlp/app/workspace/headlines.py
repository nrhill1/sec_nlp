# src/sec_nlp/app/workspace/headlines.py
"""Relate cached headlines to filing entities with explicit, inspectable reasons.

Matching uses declared entity names and user-authored watchlist aliases. It
never derives an issuer from an accession number or performs a background
lookup when the reader is opened.
"""

import re
from collections.abc import Sequence

from sec_nlp.app.pulse.models import Headline, WatchItem
from sec_nlp.core.edgar.filing_models import FilingRecord
from sec_nlp.core.news.normalization import title_key


def related_headlines(
    filing: FilingRecord,
    headlines: Sequence[Headline],
    watchlist: Sequence[WatchItem],
) -> tuple[tuple[Headline, str], ...]:
    """Return cached mentions with their declared-name or watchlist match reason.

    Args:
        filing: Filing with source-declared entity associations.
        headlines: Previously acquired headline records.
        watchlist: User-authored names and aliases for matching ticker context.

    Returns:
        Pairs of cached headlines and human-readable match explanations.
    """
    names = {
        title_key(entity.name) for entity in filing.entities if entity.name
    }
    names.update(
        re.sub(
            r"\s+(?:inc|incorporated|corp|corporation|ltd|limited|llc|plc)$",
            "",
            name,
        )
        for name in tuple(names)
    )
    names = {name for name in names if len(name) >= 3}
    symbols: set[str] = set()
    for watched in watchlist:
        aliases = {
            title_key(value)
            for value in (watched.name, *watched.aliases)
            if value
        }
        if names.intersection(aliases):
            symbols.add(watched.symbol)
    result: list[tuple[Headline, str]] = []
    for headline in headlines:
        matched_symbols = symbols.intersection(headline.symbols)
        if matched_symbols:
            result.append(
                (
                    headline,
                    "Watchlist match: " + ", ".join(sorted(matched_symbols)),
                )
            )
            continue
        title = " " + title_key(headline.title) + " "
        matched = next(
            (
                name
                for name in sorted(names, key=len, reverse=True)
                if f" {name} " in title
            ),
            None,
        )
        if matched:
            result.append(
                (headline, f"Headline mentions filing entity: {matched}")
            )
    return tuple(result)
