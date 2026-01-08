# src/sec_nlp/pipelines/presets/warranty/pipeline.py
"""Pipeline for extracting warranty statistics (liabilities, payouts, etc.) from 10-K documents."""

from datetime import date
from pathlib import Path
from typing import ClassVar, Literal

from langchain_core.documents import Document
from pydantic import PrivateAttr
from tqdm import tqdm

from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.core.text.filters import SectionFilter, create_item_filter
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.observability.telemetry import log_chunk_length_stats
from sec_nlp.pipelines.output_io import (
    build_accession_file_stem,
    build_run_file_stem,
    write_json,
)
from sec_nlp.pipelines.types import FilingMetadata, WarrantyExtractionDict
from sec_nlp.types import ResultDict

from .config import WarrantyConfig
from .io.payloads import (
    WarrantyOutputPayload,
    WarrantyPeriodPayload,
    WarrantyProcessingPayload,
    WarrantySummaryPayload,
)
from .models import WarrantyResult
from .steps.aggregate.deduplication import (
    aggregate_period_records,
    dedupe_period_records,
)
from .steps.extract.xbrl import extract_from_xbrl_docs, load_xbrl_for_filing
from .types import WarrantyPeriodRecord


class WarrantyPipeline(BasePipeline):
    """Warranty data extraction pipeline."""

    pipeline_type: ClassVar[Literal["warranty"]] = "warranty"
    description: ClassVar[str] = (
        "Extract warranty and revenue data from SEC 10-K filings"
    )

    requires_llm: ClassVar[bool] = False

    config: WarrantyConfig

    _loader: Loader = PrivateAttr()
    _section_filter: SectionFilter | None = PrivateAttr(default=None)

    @classmethod
    def config_model(cls) -> type[WarrantyConfig]:
        return WarrantyConfig

    @classmethod
    def result_model(cls) -> type[WarrantyResult]:
        return WarrantyResult

    def _build_components(self) -> None:
        """
        Build pipeline components that depend on config.

        This pipeline now runs purely on deterministic XBRL extraction.
        """
        try:
            if self.config.use_item_8_filter:
                self._section_filter = create_item_filter(
                    item_numbers=self.config.item_filter_numbers,
                    search_window=self.config.item_filter_search_window,
                    filter_indices=self.config.item_filter_exclude_indices,
                )
                logger.info(
                    "Item filter enabled: numbers=%s, search_window=%d, exclude_indices=%s",
                    self.config.item_filter_numbers,
                    self.config.item_filter_search_window,
                    self.config.item_filter_exclude_indices,
                )
            else:
                self._section_filter = None

            self._loader = Loader(
                email=self.config.email,
                downloads_folder=self.config.dl_path,
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
                keywords=self.config.keywords if self.config.keywords else None,
                section_filter=self._section_filter,
            )

            if not self.config.xbrl_only:
                logger.warning(
                    "LLM analysis disabled for warranty pipeline; config.xbrl_only should be True"
                )

        except Exception as e:
            raise ValueError(
                f"Failed to initialize Loader: {e}\n"
                f"Downloads: {self.config.dl_path.resolve()}\n"
            ) from e
        logger.info("Warranty pipeline configured for XBRL-only extraction")

    def run(self) -> WarrantyResult:
        """Execute the warranty pipeline."""
        try:
            try:
                setup_paths = self.config.setup_paths
            except AttributeError:
                setup_paths = None
            if setup_paths:
                setup_paths()

            all_outputs: list[Path] = []
            metadata: ResultDict = {}

            with tqdm(
                self.config.symbols,
                desc="Processing symbols",
                unit="symbol",
                colour="green",
            ) as pbar:
                for _idx, symbol in enumerate(pbar):
                    # Add clear separators between symbols
                    log_divider(logger, color="cyan")
                    pbar.set_description(f"Processing {symbol}")
                    symbol_outputs = self._process_symbol(symbol)
                    all_outputs.extend(symbol_outputs)
                    metadata[symbol] = len(symbol_outputs)

            return WarrantyResult(
                success=True,
                outputs=all_outputs,
                metadata=metadata,
            )

        except Exception as e:
            logger.exception("Pipeline execution failed")
            return WarrantyResult(
                success=False,
                error=str(e),
            )

    def _process_symbol(self, symbol: str) -> list[Path]:
        """
        Download and process all filings for a symbol.

        Responsible for locating HTML/XBRL files for the ticker inside the
        configured date window, then delegating to `_process_filing` for each.
        """
        from sec_edgar_downloader import (  # type: ignore[attr-defined]
            Downloader,
        )

        logger.info("Processing symbol: %s", symbol)

        self._loader.add_symbol(symbol)

        start_date, end_date = self.config.date_range

        # Download filings if needed
        downloader = Downloader(
            "SEC NLP Tool",
            self.config.email,
            str(self.config.dl_path),
        )
        try:
            n = downloader.get(
                self.config.mode.form,
                symbol,
                after=start_date,
                before=end_date,
                limit=self.config.limit,
                download_details=True,
            )
            if n:
                logger.info("Downloaded %d filings for %s", n, symbol)
        except Exception as e:
            logger.warning("Download failed for %s: %s", symbol, e)

        # Get HTML filing paths from base download folder
        # (sec_edgar_downloader creates sec-edgar-filings/SYMBOL/FORM inside dl_path)
        try:
            html_paths = self._loader.html_paths_for_symbol(
                symbol=symbol,
                mode=self.config.mode,
                base=self.config.dl_path,
                limit=self.config.limit,
                start_date=start_date,
                end_date=end_date,
            )
        except FileNotFoundError:
            logger.warning(
                "No filings found for %s in %s", symbol, self.config.dl_path
            )
            return []

        if not html_paths:
            logger.warning("No filings found for %s", symbol)
            return []

        logger.info("Found %d filings for %s", len(html_paths), symbol)

        # Process each filing separately
        output_files: list[Path] = []
        for html_path in html_paths:
            filing_outputs = self._process_filing(
                symbol, html_path, start_date, end_date
            )
            output_files.extend(filing_outputs)

        return output_files

    def _process_filing(
        self,
        symbol: str,
        html_path: Path,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Path]:
        """
        Process a single filing end to end.

        Steps:
            1) Chunk HTML (unless xbrl_only is set).
            2) Parse inline/embedded XBRL.
            3) Run LLM on text chunks (unless xbrl_only).
            4) Aggregate periods and write outputs.
        """
        import re

        # Extract accession number from path
        accession_match = re.search(
            r"/([0-9]{10}-[0-9]{2}-[0-9]{6})/", str(html_path)
        )
        accession_number = (
            accession_match.group(1) if accession_match else "unknown"
        )

        filing_dir = html_path.parent
        filing_date = self._loader._get_filing_date_from_dir(filing_dir)
        filing_year = filing_date.year if filing_date else None

        logger.info(
            "Processing filing %s for %s (filing_date=%s period=%s)",
            accession_number,
            symbol,
            filing_date.isoformat() if filing_date else "unknown",
            filing_year,
        )

        docs: list[Document] = []

        # Load XBRL facts for this specific filing
        xbrl_docs = load_xbrl_for_filing(
            symbol=symbol,
            filing_dir=filing_dir,
            accession_number=accession_number,
        )

        if xbrl_docs:
            logger.info(
                "Loaded %d XBRL warranty facts for %s/%s",
                len(xbrl_docs),
                symbol,
                accession_number,
            )
            docs = list(xbrl_docs)

        if not docs:
            logger.warning(
                "No documents found for %s/%s", symbol, accession_number
            )
            # Emit an empty-but-present output so older filings are not skipped
            fallback_result: list[WarrantyExtractionDict] = [
                {
                    "period": filing_year,
                    "confidence": 0.0,
                    "source_metadata": {
                        "method": "fallback_no_docs",
                        "accession_number": accession_number,
                        "period": filing_year,
                    },
                }
            ]
            fallback_meta: FilingMetadata = {
                "accession_number": accession_number,
                "form_type": self.config.mode.form,
                "filing_date": filing_date.isoformat() if filing_date else None,
                "filing_year": filing_year,
            }
            output_file = self._write_results(
                symbol,
                fallback_meta,
                fallback_result,
            )
            return [output_file] if output_file else []

        logger.info(
            "Extracting warranty data from %d chunks for %s/%s",
            len(docs),
            symbol,
            accession_number,
        )

        # Log chunk length statistics by type
        text_docs = [
            d
            for d in docs
            if str((d.metadata or {}).get("category", "")).lower() != "xbrl"
        ]
        xbrl_docs = [
            d
            for d in docs
            if str((d.metadata or {}).get("category", "")).lower() == "xbrl"
        ]
        self._log_length_stats("Text", symbol, accession_number, text_docs)
        self._log_length_stats("XBRL", symbol, accession_number, xbrl_docs)

        extraction_results = self._extract_warranty_data(symbol, list(docs))

        # Build filing metadata
        filing_meta: FilingMetadata = {
            "accession_number": accession_number,
            "form_type": self.config.mode.form,
            "filing_date": filing_date.isoformat() if filing_date else None,
            "filing_year": filing_year,
        }

        output_file = self._write_results(
            symbol, filing_meta, extraction_results
        )

        return [output_file] if output_file else []

    def _load_xbrl_for_filing(
        self, symbol: str, filing_dir: Path, accession_number: str
    ) -> list[Document]:
        """
        Load XBRL facts for a specific filing directory.

        Parses inline XBRL (ix:nonFraction) or legacy raw tags and returns them
        as Documents so the deterministic extractor can operate without the LLM.
        """
        import re

        # Find HTML file in this filing directory
        html_files = list(filing_dir.glob("*.html"))
        html_path = html_files[0] if html_files else None

        text = ""
        if html_path:
            try:
                text = html_path.read_text(errors="ignore")
            except Exception as e:
                logger.error("Failed to read %s: %s", html_path.name, e)

        tags = [
            # Warranty liability/accrual tags
            "us-gaap:StandardProductWarrantyAccrual",
            "us-gaap:ProductWarrantyAccrual",
            "us-gaap:WarrantyAccrual",
            "us-gaap:StandardProductWarrantyAccrualCurrent",
            "us-gaap:ProductWarrantyAccrualCurrent",
            "us-gaap:WarrantyAccrualCurrent",
            "us-gaap:StandardProductWarrantyAccrualNoncurrent",
            "us-gaap:ProductWarrantyAccrualNoncurrent",
            "us-gaap:WarrantyAccrualNoncurrent",
            "us-gaap:ProductWarrantyObligation",
            # Warranty payout/payments tags
            "us-gaap:StandardProductWarrantyAccrualPayments",
            "us-gaap:ProductWarrantyAccrualPayments",
            "us-gaap:StandardProductWarrantyAccrualWarrantyClaimsPaid",
            "us-gaap:ProductWarrantyAccrualWarrantyClaimsPaid",
            # Revenue tags
            "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
            "us-gaap:Revenues",
            "us-gaap:SalesRevenueNet",
        ]

        facts: list[Document] = []
        seen: set[tuple[str, str | None, str | None, float]] = set()

        def build_document(
            *,
            element: str,
            raw_val: str,
            tag: str,
            source: str,
        ) -> Document | None:
            """Parse a single XBRL element into a Document."""
            scale = 0
            scale_match = re.search(r'scale="(-?\d+)"', element)
            if scale_match:
                try:
                    scale = int(scale_match.group(1))
                except ValueError:
                    scale = 0

            try:
                val = float(raw_val.replace(",", ""))
                if scale:
                    val *= 10**scale
            except ValueError:
                return None

            # Extract contextRef for period info
            context_ref = None
            period_end = None
            fiscal_year = None
            context_match = re.search(r'contextRef="([^"]+)"', element)
            if context_match:
                context_ref = context_match.group(1)
                # Parse date from contextRef like "As_Of_11_1_2020_..."
                date_match = re.search(
                    r"As_Of_(\d{1,2})_(\d{1,2})_(\d{4})", context_ref
                )
                if date_match:
                    month, day, year = date_match.groups()
                    period_end = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    fiscal_year = year
                else:
                    # Fallback: grab YYYY-MM-DD or YYYYMMDD anywhere in the contextRef
                    ymd_match = re.search(
                        r"(\d{4})[-_]?(\d{2})[-_]?(\d{2})", context_ref
                    )
                    if ymd_match:
                        year, month, day = ymd_match.groups()
                        period_end = f"{year}-{month}-{day}"
                        fiscal_year = year
                    else:
                        year_match = re.search(
                            r"(20\d{2}|19\d{2})", context_ref
                        )
                        if year_match:
                            fiscal_year = year_match.group(1)

            key = (tag.lower(), context_ref, period_end, val)
            if key in seen:
                return None
            seen.add(key)

            meta = {
                "tag": tag,
                "source": source,
                "scale": scale,
                "raw_value": raw_val,
                "category": "xbrl",
                "symbol": symbol,
                "accession_number": accession_number,
                "context_ref": context_ref,
                "period_end": period_end,
                "fiscal_year": fiscal_year,
            }
            return Document(
                # Store plain numeric value so downstream float() parsing works
                page_content=str(val),
                metadata=meta,
            )

        def parse_facts_from_text(text: str, source: str) -> list[Document]:
            """Parse both inline ix:nonFraction and raw tags from a text blob."""
            docs: list[Document] = []
            for tag in tags:
                # Inline XBRL (common post-2020)
                for m in re.finditer(
                    rf'<ix:nonFraction[^>]*name="{re.escape(tag)}"[^>]*>([-+]?\d[\d,\.]*)</ix:nonFraction>',
                    text,
                    flags=re.IGNORECASE,
                ):
                    doc = build_document(
                        element=m.group(0),
                        raw_val=m.group(1),
                        tag=tag,
                        source=source,
                    )
                    if doc:
                        docs.append(doc)

                # Raw tag (older pre-inline filings)
                for m in re.finditer(
                    rf"<{re.escape(tag)}[^>]*>([-+]?\d[\d,\.]*)</{re.escape(tag)}>",
                    text,
                    flags=re.IGNORECASE,
                ):
                    doc = build_document(
                        element=m.group(0),
                        raw_val=m.group(1),
                        tag=tag,
                        source=source,
                    )
                    if doc:
                        docs.append(doc)
            return docs

        if text:
            facts.extend(parse_facts_from_text(text, str(html_path)))

        # Fallback: parse full-submission (or other XBRL) when inline HTML has no facts
        if not facts:
            full_submission = filing_dir / "full-submission.txt"
            if full_submission.exists():
                try:
                    fs_text = full_submission.read_text(errors="ignore")
                    facts.extend(
                        parse_facts_from_text(fs_text, str(full_submission))
                    )
                    if facts:
                        logger.info(
                            "Parsed %d XBRL facts from full-submission.txt for %s/%s",
                            len(facts),
                            symbol,
                            accession_number,
                        )
                except Exception as e:
                    logger.debug(
                        "Failed to parse full-submission.txt for %s/%s: %s",
                        symbol,
                        accession_number,
                        e,
                    )

        return facts

    def _extract_warranty_data(
        self, symbol: str, docs: list[Document]
    ) -> list[WarrantyExtractionDict]:
        """
        Extract warranty data from document chunks.

        Runs a deterministic XBRL-first pass, then falls back to the LLM on text
        chunks when enabled. Each chunk produces a raw record with metadata.
        """
        results: list[WarrantyExtractionDict] = []

        # Deterministic pass: harvest numbers from XBRL fact docs (category = xbrl)
        xbrl_docs = [
            d
            for d in docs
            if str((d.metadata or {}).get("category", "")).lower() == "xbrl"
        ]
        non_xbrl_docs = [d for d in docs if d not in xbrl_docs]
        logger.info(
            "Chunk stats for %s: total=%d xbrl=%d text=%d",
            symbol,
            len(docs),
            len(xbrl_docs),
            len(non_xbrl_docs),
        )
        xbrl_results = extract_from_xbrl_docs(symbol, xbrl_docs)
        results.extend(xbrl_results)

        return results

    def _period_matches(
        self,
        target_period: str | None,
        target_period_end: str | None,
        candidate_period: str | int | None,
        candidate_period_end: str | int | None,
    ) -> bool:
        """Helper to match periods across records/chunks."""
        target_period_str = (
            str(target_period).strip() if target_period is not None else None
        )
        candidate_period_str = (
            str(candidate_period).strip()
            if candidate_period is not None
            else None
        )
        if target_period_str and candidate_period_str:
            return target_period_str == candidate_period_str

        target_end_str = (
            str(target_period_end).strip()
            if target_period_end is not None
            else None
        )
        candidate_end_str = (
            str(candidate_period_end).strip()
            if candidate_period_end is not None
            else None
        )
        if target_end_str and candidate_end_str:
            return target_end_str == candidate_end_str

        if target_period_str and candidate_end_str:
            return candidate_end_str.startswith(target_period_str)
        if target_end_str and candidate_period_str:
            return target_end_str.startswith(candidate_period_str)
        return False

    def _select_docs_for_period(
        self,
        docs: list[Document],
        target_period: str | None,
        target_period_end: str | None,
        limit: int = 5,
    ) -> list[Document]:
        """
        Select text docs that mention the target period and match warranty keywords.

        Falls back to keyword-only matches, then to the first N text docs to
        avoid missing data when the period is absent in text.
        """
        text_docs = [
            d
            for d in docs
            if str((d.metadata or {}).get("category", "")).lower() != "xbrl"
        ]
        if not text_docs:
            return []

        tokens: set[str] = set()
        if target_period:
            tokens.add(str(target_period))
        if target_period_end:
            target_end_str = str(target_period_end)
            tokens.update(
                {
                    target_end_str,
                    target_end_str.replace("-", ""),
                    target_end_str[:4],
                }
            )

        keywords = [kw.lower() for kw in (self.config.keywords or [])]

        def _matches_keywords(text: str) -> bool:
            if not keywords:
                return True
            lower = text.lower()
            return any(kw in lower for kw in keywords)

        matched: list[Document] = []
        for doc in text_docs:
            content = doc.page_content or ""
            if tokens and not any(
                token and token in content for token in tokens
            ):
                continue
            if not _matches_keywords(content):
                continue
            matched.append(doc)
            if len(matched) >= limit:
                break

        if not matched:
            # Relax to keyword-only matches
            for doc in text_docs:
                content = doc.page_content or ""
                if _matches_keywords(content):
                    matched.append(doc)
                if len(matched) >= limit:
                    break

        return matched or text_docs[:limit]

    def _has_llm_value_for_fields(
        self,
        extraction_results: list[WarrantyExtractionDict],
        target_period: str | None,
        target_period_end: str | None,
        fields: list[str],
    ) -> bool:
        """Check if any LLM result already provided numeric values for fields."""
        for rec in extraction_results:
            meta = rec.get("source_metadata", {}) or {}
            if meta.get("method") == "xbrl_facts":
                continue
            res_period = rec.get("period") or meta.get("period")
            res_period_end = rec.get("period_end") or meta.get("period_end")
            if not self._period_matches(
                target_period, target_period_end, res_period, res_period_end
            ):
                continue
            if any(
                isinstance(rec.get(field), (int, float)) for field in fields
            ):
                return True
        return False

    def _extract_from_xbrl_docs(
        self, symbol: str, docs: list[Document]
    ) -> list[WarrantyExtractionDict]:
        """Delegate to the shared XBRL extractor."""
        return extract_from_xbrl_docs(symbol, docs)

    def _write_results(
        self,
        symbol: str,
        filing_meta: FilingMetadata,
        extraction_results: list[WarrantyExtractionDict],
    ) -> Path | None:
        """
        Write warranty extraction results to disk.

        Produces a per-filing JSON (optional) plus a symbol-level combined CSV.
        Records are deduped before writing so downstream consumers see the
        latest/strongest values only.
        """
        # Write to per-symbol subdirectory
        get_symbol_output_dir = getattr(
            self.config, "get_symbol_output_dir", None
        )
        if get_symbol_output_dir:
            symbol_out_path = get_symbol_output_dir(symbol)
        else:  # Fallback for older/dummy configs in tests
            symbol_out_path = self.config.out_path / symbol.upper()
            symbol_out_path.mkdir(parents=True, exist_ok=True)
        base_name = build_accession_file_stem(
            symbol,
            "warranty",
            filing_meta.get("accession_number"),
            self.config.run_id,
        )
        out_file = symbol_out_path / f"{base_name}.json"

        def _has_numeric(rec: WarrantyExtractionDict) -> bool:
            return any(
                isinstance(rec.get(f), (int, float))
                for f in (
                    "warranty_liability",
                    "warranty_payout",
                    "net_revenue",
                )
            )

        def _is_xbrl(rec: WarrantyExtractionDict) -> bool:
            method = rec.get("source_metadata", {}).get("method")
            return bool(method == "xbrl_facts")

        valid_results = [
            r
            for r in extraction_results
            if "error" not in r
            and (_has_numeric(r) or r.get("confidence") is not None)
        ]

        logger.debug(
            "Validation results for %s: total=%d, errors=%d, valid=%d",
            symbol,
            len(extraction_results),
            sum(1 for r in extraction_results if "error" in r),
            len(valid_results),
        )

        if not valid_results:
            logger.warning(
                "Skipping file write for %s - no valid extraction result found. "
                "Total results: %d, with errors: %d",
                symbol,
                len(extraction_results),
                sum(1 for r in extraction_results if "error" in r),
            )
            for i, r in enumerate(extraction_results[:3]):
                logger.debug(
                    "Sample result %d: %s",
                    i,
                    {k: v for k, v in r.items() if k != "source_metadata"},
                )
            return None

        xbrl_count = sum(
            1 for r in extraction_results if _is_xbrl(r) and _has_numeric(r)
        )

        # Separate XBRL and LLM results (for processing stats only)
        llm_results = [r for r in valid_results if not _is_xbrl(r)]
        llm_with_data = [r for r in llm_results if _has_numeric(r)]

        period_records: list[WarrantyPeriodRecord] = aggregate_period_records(
            symbol=symbol,
            filing_meta=filing_meta,
            valid_results=valid_results,
        )

        # Sort by period descending
        period_records.sort(
            key=lambda r: r.get("period") or "0000", reverse=True
        )

        period_records = dedupe_period_records(period_records)

        # Get best result for backward compatibility
        best_result = period_records[0] if period_records else None

        logger.info(
            "Warranty periods for %s/%s: %s",
            symbol,
            filing_meta.get("accession_number"),
            ", ".join(
                [
                    str(rec.get("period") or rec.get("period_end") or "?")
                    for rec in period_records
                ]
            )
            or "none",
        )

        periods_payload = [
            WarrantyPeriodPayload.model_validate(record)
            for record in period_records
        ]

        summary_payload = WarrantySummaryPayload(
            periods_found=len(period_records),
            xbrl_periods=sum(
                1
                for r in period_records
                if str(r.get("source", "")).lower() in ("xbrl", "mixed")
            ),
            llm_periods=sum(
                1
                for r in period_records
                if str(r.get("source", "")).lower() in ("llm", "mixed")
            ),
            latest_period=best_result.get("period") if best_result else None,
            latest_liability=best_result.get("warranty_liability")
            if best_result
            else None,
        )

        processing_payload = WarrantyProcessingPayload(
            chunks_analyzed=len(extraction_results),
            xbrl_facts_found=xbrl_count,
            llm_extractions=len(llm_results),
            llm_with_data=len(llm_with_data),
            errors=sum(1 for r in extraction_results if "error" in r),
        )

        output_data = WarrantyOutputPayload(
            symbol=symbol,
            form_type=filing_meta.get("form_type") or self.config.mode.form,
            periods=periods_payload,
            summary=summary_payload,
            processing=processing_payload,
        )

        if self.config.export_format in ("json", "both"):
            write_json(out_file, output_data, exclude_none=True)

        # CSV export - append to per-symbol combined CSV (no per-filing CSVs)
        if self.config.export_format in ("csv", "both"):
            import csv

            fieldnames = [
                "symbol",
                "period",
                "warranty_liability",
                "warranty_payout",
                "net_revenue",
                "liability_to_revenue_ratio",
                "confidence",
                "source",
                "accession_number",
            ]

            # Write/append to per-symbol combined CSV
            combined_csv = self.config.combined_csv or (
                symbol_out_path
                / f"{build_run_file_stem(symbol, 'warranty_combined', self.config.run_id)}.csv"
            )

            combined_csv.parent.mkdir(parents=True, exist_ok=True)

            existing_rows: list[WarrantyPeriodRecord] = []
            if combined_csv.exists() and combined_csv.stat().st_size > 0:
                with open(combined_csv, newline="", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        record: WarrantyPeriodRecord = {}
                        symbol_val = row.get("symbol")
                        if symbol_val:
                            record["symbol"] = symbol_val
                        period_val = row.get("period")
                        if period_val:
                            record["period"] = period_val
                        liability_val = row.get("warranty_liability")
                        payout_val = row.get("warranty_payout")
                        revenue_val = row.get("net_revenue")
                        confidence_val = row.get("confidence")
                        source_val = row.get("source")
                        accession_val = row.get("accession_number")

                        def _as_float(raw: str | None) -> float | None:
                            if raw in (None, "", "None"):
                                return None
                            try:
                                return float(raw)
                            except ValueError:
                                return None

                        liability = _as_float(liability_val)
                        if liability is not None:
                            record["warranty_liability"] = liability
                        payout = _as_float(payout_val)
                        if payout is not None:
                            record["warranty_payout"] = payout
                        revenue = _as_float(revenue_val)
                        if revenue is not None:
                            record["net_revenue"] = revenue
                        confidence = _as_float(confidence_val)
                        if confidence is not None:
                            record["confidence"] = confidence
                        if source_val:
                            record["source"] = source_val
                        if accession_val:
                            record["accession_number"] = accession_val

                        existing_rows.append(record)

            combined_rows = dedupe_period_records(
                existing_rows + period_records
            )

            with open(combined_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                for row in combined_rows:
                    # Compute ratio if possible
                    ratio = None
                    try:
                        liab_val = row.get("warranty_liability")
                        rev_val = row.get("net_revenue")
                        liab = float(liab_val) if liab_val is not None else None
                        rev = float(rev_val) if rev_val is not None else None
                        if liab is not None and rev is not None and rev != 0:
                            ratio = liab / rev
                    except Exception:
                        ratio = None
                    row_out = {k: row.get(k) for k in fieldnames}
                    row_out["liability_to_revenue_ratio"] = ratio
                    writer.writerow(row_out)
            logger.info(
                "Wrote %d unique period(s) to combined CSV: %s",
                len(combined_rows),
                combined_csv,
            )

        # Informative logging for JSON
        if self.config.export_format in ("json", "both"):
            logger.info("Warranty JSON written to %s", out_file)
        return out_file

    def _log_length_stats(
        self,
        label: str,
        symbol: str,
        accession_number: str,
        docs: list[Document],
    ) -> None:
        """Log min/max/mean/median chunk length stats for a filing."""
        log_chunk_length_stats(
            label=label,
            symbol=symbol,
            accession=accession_number,
            docs=docs,
        )
