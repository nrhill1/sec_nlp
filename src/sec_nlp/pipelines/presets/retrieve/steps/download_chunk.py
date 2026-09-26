# src/sec_nlp/pipelines/presets/retrieve/steps/download_chunk.py
"""Download/chunk stage for retrieve pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.downloader import download_accessions
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.core.text.filters import create_item_filter
from sec_nlp.core.types import coerce_json_value
from sec_nlp.types import JsonValue

from ..config import RetrieveSettings
from ..models import RetrievalHit
from .tokenization import DEFAULT_QUERY_STOPWORDS, extract_query_terms


@dataclass(slots=True, frozen=True)
class _ChunkCandidate:
    """Internal model for ChunkCandidate."""

    text: str
    section_type: str | None
    section_number: str | None
    chunk_index: int | None


def _mode_for_form(form_type: str, fallback: FilingMode) -> FilingMode:
    """Resolve filing mode from the filing form type."""
    normalized = form_type.strip().upper()
    if normalized.startswith("10-K"):
        return FilingMode.annual
    if normalized.startswith("10-Q"):
        return FilingMode.quarterly
    if normalized.startswith(("8-K", "6-K", "6K")):
        return FilingMode.current
    if normalized.startswith("DEF 14A"):
        return FilingMode.proxy
    if normalized.startswith("13F-HR"):
        return FilingMode.holdings
    if normalized in {"3", "4", "5"}:
        return FilingMode.insider
    if normalized.startswith("S-1"):
        return FilingMode.registration
    if normalized.startswith("S-3"):
        return FilingMode.shelf_registration
    return fallback


def _best_html_file(accession_dir: Path) -> Path | None:
    """Select the most relevant HTML file for chunk extraction."""
    best_path: Path | None = None
    best_size = -1
    for path in accession_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".htm", ".html", ".xhtml"}:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > best_size:
            best_path = path
            best_size = size
    return best_path


def _find_html_for_accession(
    *,
    dl_path: Path,
    symbol: str,
    accession: str,
    preferred_form: str | None,
) -> Path | None:
    """Find html for accession."""
    symbol_root = dl_path / "sec-edgar-filings" / symbol.upper()
    if not symbol_root.exists():
        return None

    accession_dirs: list[Path] = []
    if preferred_form:
        preferred = symbol_root / preferred_form / accession
        if preferred.exists():
            accession_dirs.append(preferred)

    for form_dir in sorted(symbol_root.iterdir()):
        if not form_dir.is_dir():
            continue
        candidate = form_dir / accession
        if candidate.exists() and candidate not in accession_dirs:
            accession_dirs.append(candidate)

    for accession_dir in accession_dirs:
        html_path = _best_html_file(accession_dir)
        if html_path is not None:
            return html_path
    return None


def _coerce_str(value: JsonValue) -> str | None:
    """Coerce scalar metadata values to strings when possible."""
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


def _coerce_int(value: JsonValue) -> int | None:
    """Coerce scalar metadata values to integers when possible."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _clip_snippet(text: str, max_chars: int) -> str:
    """Trim snippet windows to a bounded character span."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max(0, max_chars - 3)].rstrip()}..."


def _has_snippet(value: str | None) -> bool:
    """Return whether snippet."""
    if value is None:
        return False
    return bool(value.strip())


def _choose_chunk(
    *,
    candidates: list[_ChunkCandidate],
    query: str,
    max_chars: int,
    remove_stopwords: bool,
) -> _ChunkCandidate | None:
    """Select the best chunk candidate for a matched snippet."""
    if not candidates:
        return None

    stopwords = DEFAULT_QUERY_STOPWORDS if remove_stopwords else None
    tokens = extract_query_terms(query, stopwords=stopwords)
    if not tokens:
        first = candidates[0]
        return _ChunkCandidate(
            text=_clip_snippet(first.text, max_chars),
            section_type=first.section_type,
            section_number=first.section_number,
            chunk_index=first.chunk_index,
        )

    best: _ChunkCandidate | None = None
    best_score = -1
    best_len = -1
    for candidate in candidates:
        haystack = candidate.text.casefold()
        score = sum(1 for token in tokens if token in haystack)
        candidate_len = len(candidate.text)
        if score > best_score or (
            score == best_score and candidate_len > best_len
        ):
            best = candidate
            best_score = score
            best_len = candidate_len

    if best is None:
        return None
    return _ChunkCandidate(
        text=_clip_snippet(best.text, max_chars),
        section_type=best.section_type,
        section_number=best.section_number,
        chunk_index=best.chunk_index,
    )


def _build_section_filter(settings: RetrieveSettings):
    """Build section filter."""
    if not settings.sections:
        return None
    return create_item_filter(settings.sections)


def _hydration_keywords(
    *,
    hits: list[RetrievalHit],
    remove_stopwords: bool,
) -> list[str] | None:
    """Build query-derived keywords for pre-chunk hydration filtering."""
    ordered_terms: list[str] = []
    seen: set[str] = set()
    stopwords = DEFAULT_QUERY_STOPWORDS if remove_stopwords else None
    for hit in hits:
        for term in sorted(extract_query_terms(hit.query, stopwords=stopwords)):
            if term in seen:
                continue
            seen.add(term)
            ordered_terms.append(term)
    if not ordered_terms:
        return None
    return ordered_terms


def _load_chunk_candidates(
    *,
    html_path: Path,
    loader: Loader,
    settings: RetrieveSettings,
    hits: list[RetrievalHit],
) -> list[_ChunkCandidate]:
    """Load chunk candidates."""
    keywords = _hydration_keywords(
        hits=hits,
        remove_stopwords=settings.stopword_aware_lexical,
    )
    docs = loader.transform_html(
        html_path,
        keywords=keywords,
        section_filter=_build_section_filter(settings),
    )
    candidates: list[_ChunkCandidate] = []
    for doc in docs:
        if len(candidates) >= settings.max_chunks_per_accession:
            break
        if not isinstance(doc, Document):
            continue
        text = doc.page_content.strip()
        if not text:
            continue
        metadata: dict[str, JsonValue] = {}
        for raw_key, raw_value in (doc.metadata or {}).items():
            if not isinstance(raw_key, str):
                continue
            normalized = coerce_json_value(raw_value)
            if normalized is not None:
                metadata[raw_key] = normalized
        candidates.append(
            _ChunkCandidate(
                text=text,
                section_type=_coerce_str(metadata.get("section_type")),
                section_number=_coerce_str(metadata.get("section_number")),
                chunk_index=_coerce_int(metadata.get("chunk_index")),
            )
        )

    return candidates


def _download_missing_accessions(
    *,
    symbol: str,
    missing_accessions: set[str],
    hits_by_accession: dict[str, RetrievalHit],
    settings: RetrieveSettings,
) -> None:
    """Download missing accession files required for hydration."""
    if not missing_accessions or not settings.download_missing:
        return

    accession_cik_map = {
        accession: hits_by_accession[accession].cik
        for accession in sorted(missing_accessions)
        if accession in hits_by_accession
    }
    by_mode: dict[FilingMode, list[str]] = {}
    for accession in sorted(missing_accessions):
        hit = hits_by_accession.get(accession)
        if hit is None:
            continue
        mode = _mode_for_form(hit.form_type, settings.mode)
        by_mode.setdefault(mode, []).append(accession)

    for mode, accessions in by_mode.items():
        try:
            download_accessions(
                symbol=symbol,
                accessions=accessions,
                accession_cik_map=accession_cik_map,
                mode=mode,
                work_folder=settings.dl_path,
                company_name="SEC NLP Tool",
                email=settings.email,
            )
        except Exception as exc:
            logger.warning(
                "Retrieve download failed for %s mode=%s: %s",
                symbol,
                mode.value,
                exc,
            )


def download_and_chunk_hits(
    *,
    symbol: str,
    hits: list[RetrievalHit],
    settings: RetrieveSettings,
) -> list[RetrievalHit]:
    """Load filing chunks and enrich retrieval hits with chunk snippets."""

    if not hits:
        return hits

    target_accessions: set[str] | None = None
    if not settings.sections:
        if not settings.hydrate_missing_snippets:
            logger.debug(
                "Hydration skipped for %s: no sections requested and "
                "hydrate_missing_snippets disabled",
                symbol,
            )
            return hits
        target_accessions = {
            hit.accession_number
            for hit in hits
            if not _has_snippet(hit.snippet)
        }
        # EFTS snippets are usually present; skip expensive chunk extraction
        # unless section targeting is requested or snippet hydration is needed.
        if not target_accessions:
            logger.debug(
                "Hydration skipped for %s: all ranked hits already contain snippets",
                symbol,
            )
            return hits

    logger.debug(
        "Hydration start for %s: hits=%d section_filter=%s target_accessions=%s",
        symbol,
        len(hits),
        bool(settings.sections),
        ("all" if target_accessions is None else str(len(target_accessions))),
    )

    hits_by_accession = {hit.accession_number: hit for hit in hits}
    html_paths: dict[str, Path] = {}
    missing: set[str] = set()
    for hit in hits:
        if (
            target_accessions is not None
            and hit.accession_number not in target_accessions
        ):
            logger.debug(
                "Hydration skip for %s accession=%s: snippet already present",
                symbol,
                hit.accession_number,
            )
            continue
        html_path = _find_html_for_accession(
            dl_path=settings.dl_path,
            symbol=symbol,
            accession=hit.accession_number,
            preferred_form=hit.form_type,
        )
        if html_path is None:
            missing.add(hit.accession_number)
            logger.debug(
                "Hydration needs download for %s accession=%s",
                symbol,
                hit.accession_number,
            )
            continue
        html_paths[hit.accession_number] = html_path
        logger.debug(
            "Hydration source resolved for %s accession=%s path=%s",
            symbol,
            hit.accession_number,
            html_path,
        )

    if missing:
        _download_missing_accessions(
            symbol=symbol,
            missing_accessions=missing,
            hits_by_accession=hits_by_accession,
            settings=settings,
        )
        resolved_after_download = 0
        for accession in sorted(missing):
            hit = hits_by_accession.get(accession)
            if hit is None:
                continue
            html_path = _find_html_for_accession(
                dl_path=settings.dl_path,
                symbol=symbol,
                accession=accession,
                preferred_form=hit.form_type,
            )
            if html_path is not None:
                html_paths[accession] = html_path
                resolved_after_download += 1
                logger.debug(
                    "Hydration source resolved after download for %s accession=%s path=%s",
                    symbol,
                    accession,
                    html_path,
                )
            else:
                logger.debug(
                    "Hydration source unresolved after download for %s accession=%s",
                    symbol,
                    accession,
                )
        if settings.download_missing and not resolved_after_download:
            logger.warning(
                "Retrieve hydration warning for %s: no accessions downloaded for %d missing accession(s)",
                symbol,
                len(missing),
            )

    loader = Loader(
        email=settings.email,
        downloads_folder=settings.dl_path,
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        semantic_chunking=settings.semantic_chunking,
    )

    chunk_candidates: dict[str, list[_ChunkCandidate]] = {}
    for accession, path in html_paths.items():
        try:
            accession_hits = [
                hit for hit in hits if hit.accession_number == accession
            ]
            candidates = _load_chunk_candidates(
                html_path=path,
                loader=loader,
                settings=settings,
                hits=accession_hits,
            )
            if candidates:
                chunk_candidates[accession] = candidates
                logger.debug(
                    "Hydration chunk candidates for %s accession=%s count=%d",
                    symbol,
                    accession,
                    len(candidates),
                )
            else:
                logger.debug(
                    "Hydration no chunk candidates for %s accession=%s",
                    symbol,
                    accession,
                )
        except Exception as exc:
            logger.debug(
                "Chunk extraction failed for %s (%s): %s",
                symbol,
                accession,
                exc,
            )

    enriched_hits: list[RetrievalHit] = []
    for hit in hits:
        candidates = chunk_candidates.get(hit.accession_number, [])
        selected = _choose_chunk(
            candidates=candidates,
            query=hit.query,
            max_chars=settings.snippet_chars,
            remove_stopwords=settings.stopword_aware_lexical,
        )
        if selected is None:
            enriched_hits.append(hit)
            logger.debug(
                "Hydration unchanged for %s accession=%s: no matching chunk found",
                symbol,
                hit.accession_number,
            )
            continue

        logger.debug(
            "Hydration selected chunk for %s accession=%s section=%s item=%s chunk_index=%s",
            symbol,
            hit.accession_number,
            selected.section_type,
            selected.section_number,
            selected.chunk_index,
        )
        enriched_hits.append(
            hit.model_copy(
                update={
                    "snippet": selected.text,
                    "section_type": selected.section_type,
                    "section_number": selected.section_number,
                    "chunk_index": selected.chunk_index,
                }
            )
        )

    return enriched_hits
