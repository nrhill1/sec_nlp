"""Scan 8-K filings and detect event mentions."""

from __future__ import annotations

import re
from pathlib import Path

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.downloader import download_filings
from sec_nlp.core.ingest.filings import (
    get_filing_date_from_dir,
    html_paths_for_symbol,
)
from sec_nlp.core.text.entity_extraction import (
    EntityExtensionError,
    detect_events,
)

from ..config import EventsSettings
from ..models import DetectedEvent

_ACCESSION_RE = re.compile(r"(\d{10}-\d{2}-\d{6})")
_ITEM_RE = re.compile(
    r"\bitem\s+(\d{1,2}\.\d{2})\b",
    flags=re.IGNORECASE,
)
_ITEM_EVENT_MAP: dict[str, str] = {
    "1.01": "material_agreement",
    "2.01": "acquisition",
    "2.02": "earnings",
    "4.02": "restatement",
    "5.02": "executive_change",
    "8.01": "other",
}


def _extract_accession(path: Path) -> str | None:
    match = _ACCESSION_RE.search(str(path))
    return match.group(1) if match else None


def _extract_item_numbers(text: str) -> list[str]:
    items = [match.group(1) for match in _ITEM_RE.finditer(text)]
    return list(dict.fromkeys(items))


def _normalize_event_type(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_event_type(
    item_numbers: list[str], text: str
) -> tuple[str, list[str], str | None]:
    mentions: list[str] = []
    snippet: str | None = None

    try:
        raw_mentions = detect_events(text[:120_000])
    except EntityExtensionError:
        raw_mentions = []
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.debug("Event detection failed: %s", exc)
        raw_mentions = []

    if raw_mentions:
        best = max(raw_mentions, key=lambda current: current.confidence)
        mentions = list(
            dict.fromkeys(
                mention.text.strip()
                for mention in raw_mentions
                if mention.text.strip()
            )
        )
        snippet = best.text.strip() or None
        return _normalize_event_type(best.event_type), mentions, snippet

    for item in item_numbers:
        mapped = _ITEM_EVENT_MAP.get(item)
        if mapped:
            return mapped, mentions, snippet

    return "other", mentions, snippet


def scan_events_for_symbol(
    *,
    symbol: str,
    settings: EventsSettings,
) -> tuple[list[DetectedEvent], int, int]:
    """Download and scan 8-K filings for a symbol."""

    start_date, end_date = settings.effective_event_date_range
    download_results = download_filings(
        symbols=[symbol],
        mode=FilingMode.current,
        work_folder=settings.dl_path,
        company_name="SEC NLP Tool",
        email=settings.email,
        after_date=start_date,
        before_date=end_date,
        limit_per_symbol=settings.limit,
    )
    downloaded = int(download_results.get(symbol, {}).get("downloaded", 0))

    try:
        html_paths = html_paths_for_symbol(
            symbol=symbol,
            mode=FilingMode.current,
            base=settings.dl_path,
            limit=settings.limit,
            start_date=start_date,
            end_date=end_date,
        )
    except FileNotFoundError:
        return [], downloaded, 0

    detected: list[DetectedEvent] = []
    for html_path in html_paths:
        filing_date = get_filing_date_from_dir(html_path.parent)
        if filing_date is None:
            continue

        try:
            text = html_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:  # pragma: no cover - file read failure
            logger.debug("Failed reading %s: %s", html_path, exc)
            continue

        accession = _extract_accession(html_path) or html_path.parent.name
        item_numbers = _extract_item_numbers(text)
        event_type, entity_mentions, snippet = _resolve_event_type(
            item_numbers,
            text,
        )

        if settings.event_types and event_type not in settings.event_types:
            continue

        if snippet is None and item_numbers:
            snippet = f"8-K item {'/'.join(item_numbers[:3])}"

        detected.append(
            DetectedEvent(
                symbol=symbol,
                event_type=event_type,
                event_date=filing_date.isoformat(),
                filing_accession=accession,
                filing_form="8-K",
                filing_items=item_numbers,
                entity_mentions=entity_mentions,
                text_snippet=snippet,
                source_file=str(html_path),
            )
        )

    detected.sort(
        key=lambda current: (
            current.event_date,
            current.filing_accession,
        ),
        reverse=True,
    )
    return detected, downloaded, len(html_paths)
