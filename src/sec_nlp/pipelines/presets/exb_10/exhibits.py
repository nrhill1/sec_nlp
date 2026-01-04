"""Exhibit parsing helpers for the Exhibit 10 pipeline."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from langchain_core.documents import Document
from pydantic import Field
from pydantic.dataclasses import dataclass

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.exhibit_downloader import ExhibitDownloader
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.core.text.filters import create_exhibit_filter
from sec_nlp.core.text.keyword import KeywordMatcher
from sec_nlp.core.text.section_extractor import create_section_extractor
from sec_nlp.pipelines.observability.telemetry import (
    log_document_metadata,
    log_exhibit_stats,
)
from sec_nlp.pipelines.presets.exb_10.config import Exhibit10Config


@dataclass
class ExhibitStats:
    """Lightweight stats for exhibit parsing."""

    chunk_count: int = 0
    sections_found: set[str] = Field(default_factory=set)
    exhibit_docs: int = 0
    html_files: int = 0
    accession_numbers: set[str] = Field(default_factory=set)
    prefilter_skips: Counter[str] = Field(default_factory=Counter)

    def log(self, symbol: str, filtered_chunk_count: int | None = None) -> None:
        log_exhibit_stats(
            symbol=symbol,
            chunk_count=self.chunk_count,
            sections_found=len(self.sections_found),
            exhibit_docs=self.exhibit_docs,
            html_files=self.html_files,
            accession_count=len(self.accession_numbers),
            filtered_chunk_count=filtered_chunk_count,
            prefilter_skips=dict(self.prefilter_skips),
        )


def collect_exhibit_documents(
    *,
    loader: Loader,
    symbol: str,
    config: Exhibit10Config,
    keyword_terms: list[str],
    keyword_categories: KeywordMatcher.KeywordCategories,
    adaptive_chunk_size: Callable[[int], int],
    skip_prefilter: bool = False,
) -> tuple[list[Document], ExhibitStats]:
    """Parse Exhibit 10 content (full submissions + downloaded HTML) into chunks."""
    start_date, end_date = config.date_range

    # Use disk-based downloader which fetches ALL files including separate exhibits
    from sec_edgar_downloader import Downloader  # type: ignore[attr-defined]

    work_folder = loader.downloads_folder
    downloader = Downloader(loader.company_name, loader.email, str(work_folder))

    try:
        n = downloader.get(
            config.mode.form,
            symbol,
            after=start_date if start_date else None,
            before=end_date if end_date else None,
            download_details=True,
            limit=config.limit,
        )
        logger.info(
            "Downloaded %d %s filing(s) for %s (including exhibits)",
            n or 0,
            config.mode.form,
            symbol,
        )
    except Exception as e:
        logger.error("Failed to download filings for %s: %s", symbol, e)
        return [], ExhibitStats()

    filing_dir = (
        work_folder / "sec-edgar-filings" / symbol.upper() / config.mode.form
    )
    if not filing_dir.exists():
        logger.warning("No filings directory found for %s", symbol)
        return [], ExhibitStats()

    exhibit_downloader = ExhibitDownloader(
        company_name=loader.company_name,
        email=loader.email,
        rate_limit=0.1,
    )

    html_files = list(filing_dir.rglob("*.html"))
    logger.info(
        "Found %d HTML files (including exhibits) for %s",
        len(html_files),
        symbol,
    )

    full_submission_files = list(filing_dir.rglob("full-submission.txt"))
    all_exhibit_documents = []
    for full_sub_file in full_submission_files:
        exhibits = exhibit_downloader.parse_full_submission(
            full_sub_file, accession_number=full_sub_file.parent.name
        )
        all_exhibit_documents.extend(exhibits)

    for accession_dir in filing_dir.iterdir():
        if not accession_dir.is_dir():
            continue

        accession_number = accession_dir.name
        try:
            cik = loader._symbol_to_cik.get(symbol)
            if not cik:
                cik = loader._get_cik_for_ticker(symbol)
                loader._symbol_to_cik[symbol] = cik

            downloaded_exhibits = (
                exhibit_downloader.download_exhibits_from_index(
                    accession_number=accession_number,
                    cik=cik,
                    exhibit_numbers=["10"],
                    output_dir=accession_dir,
                )
            )
            if downloaded_exhibits:
                all_exhibit_documents.extend(downloaded_exhibits)
                logger.info(
                    "Downloaded %d Exhibit 10 files from SEC for %s",
                    len(downloaded_exhibits),
                    accession_number,
                )
        except Exception as e:
            logger.debug(
                "Could not download exhibits for %s: %s", accession_number, e
            )

    exhibit_filter = create_exhibit_filter(
        exhibit_numbers=["10"],
        search_window=3000,
        filter_indices=True,
    )
    section_extractor = create_section_extractor(
        section_filter=exhibit_filter,
        max_section_length=500000,
        detect_boundaries=True,
    )

    stats = ExhibitStats()
    exhibit10_docs: list[Document] = []
    allowed_no_kw_remaining = config.prefilter_allow_no_keyword
    use_keyword_prefilter = (
        False if skip_prefilter else config.prefilter_keywords
    )
    use_section_prefilter = (
        False if skip_prefilter else config.prefilter_section_terms
    )

    for exhibit_doc in all_exhibit_documents:
        try:
            if not exhibit_doc.content:
                continue

            doc_accession_number = exhibit_doc.accession_number
            doc_exhibit_number = exhibit_doc.exhibit_number

            log_document_metadata(
                symbol=symbol,
                accession_number=doc_accession_number,
                filename=exhibit_doc.filename,
                filing_date=None,
                source="downloaded" if exhibit_doc.url else "full_submission",
                exhibit_number=doc_exhibit_number,
            )

            if (
                use_keyword_prefilter
                and keyword_terms
                and not KeywordMatcher.has_keyword_hit(
                    exhibit_doc.content,
                    keyword_terms,
                    keyword_categories,
                    min_categories=config.require_keyword_categories,
                )
            ):
                stats.prefilter_skips["no_keyword_terms"] += 1
                if allowed_no_kw_remaining > 0:
                    allowed_no_kw_remaining -= 1
                    logger.debug(
                        "Passing exhibit without keyword hit (fallback slot remaining=%d): %s",
                        allowed_no_kw_remaining,
                        exhibit_doc.filename,
                    )
                else:
                    continue

            if use_section_prefilter:
                should_process, reason = exhibit_filter.should_process_html(
                    exhibit_doc.content,
                    check_window=config.chunk_prefilter_window,
                    min_content_length=config.chunk_prefilter_min_length,
                )
                if not should_process:
                    stats.prefilter_skips[reason] += 1
                    continue

            filing_metadata = {
                "ticker": symbol,
                "form_type": config.mode.form,
                "exhibit_number": doc_exhibit_number,
                "filename": exhibit_doc.filename,
                "description": exhibit_doc.description,
                "source": "full_submission"
                if not exhibit_doc.url
                else "downloaded",
                "accession_number": doc_accession_number,
            }

            effective_chunk_size = adaptive_chunk_size(len(exhibit_doc.content))
            section_chunks = section_extractor.extract_and_chunk(
                exhibit_doc.content,
                metadata=filing_metadata,
                chunk_size=effective_chunk_size,
                chunk_overlap=loader.chunk_overlap,
            )

            if section_chunks:
                exhibit10_docs.extend(section_chunks)
                section_numbers = {
                    chunk.metadata.get("section_number", "unknown")
                    for chunk in section_chunks
                }
                stats.sections_found.update(str(s) for s in section_numbers)
                stats.chunk_count += len(section_chunks)
            stats.exhibit_docs += 1
        except Exception as e:
            logger.error(
                "Failed to process exhibit %s: %s", exhibit_doc.filename, e
            )
            continue

    for html_file in html_files:
        try:
            with open(html_file, encoding="utf-8", errors="ignore") as f:
                html_content = f.read()

            logger.debug("Scanning file for Exhibit 10: %s", html_file.name)

            if (
                use_keyword_prefilter
                and keyword_terms
                and not KeywordMatcher.has_keyword_hit(
                    html_content,
                    keyword_terms,
                    keyword_categories,
                    min_categories=config.require_keyword_categories,
                )
            ):
                stats.prefilter_skips["no_keyword_terms"] += 1
                if allowed_no_kw_remaining > 0:
                    allowed_no_kw_remaining -= 1
                    logger.debug(
                        "Passing HTML without keyword hit (fallback slot remaining=%d): %s",
                        allowed_no_kw_remaining,
                        html_file.name,
                    )
                else:
                    continue

            if use_section_prefilter:
                should_process, reason = exhibit_filter.should_process_html(
                    html_content,
                    check_window=config.chunk_prefilter_window,
                    min_content_length=config.chunk_prefilter_min_length,
                )
                if not should_process:
                    stats.prefilter_skips[reason] += 1
                    continue

            accession_number = html_file.parent.name
            filing_date = loader._get_filing_date_from_dir(html_file.parent)
            stats.accession_numbers.add(accession_number)

            logger.debug(
                "Exhibit 10 candidate: symbol=%s accession=%s filing_date=%s file=%s",
                symbol,
                accession_number,
                filing_date.isoformat() if filing_date else "unknown",
                html_file.name,
            )

            filing_metadata = {
                "ticker": symbol,
                "form_type": config.mode.form,
                "accession_number": accession_number,
                "source_file": str(html_file),
                "filename": html_file.name,
                "filing_date": filing_date.isoformat() if filing_date else None,
            }

            log_document_metadata(
                symbol=symbol,
                accession_number=accession_number,
                filename=html_file.name,
                filing_date=filing_date.isoformat() if filing_date else None,
                source="html_file",
                exhibit_number=None,
            )

            effective_chunk_size = adaptive_chunk_size(len(html_content))
            section_chunks = section_extractor.extract_and_chunk(
                html_content,
                metadata=filing_metadata,
                chunk_size=effective_chunk_size,
                chunk_overlap=loader.chunk_overlap,
            )

            if section_chunks:
                exhibit10_docs.extend(section_chunks)
                section_numbers = {
                    chunk.metadata.get("section_number", "unknown")
                    for chunk in section_chunks
                }
                stats.sections_found.update(str(s) for s in section_numbers)
                stats.chunk_count += len(section_chunks)
            stats.html_files += 1
        except Exception as e:
            logger.error("Failed to process %s: %s", html_file.name, e)
            continue

    stats.log(symbol)
    return exhibit10_docs, stats
