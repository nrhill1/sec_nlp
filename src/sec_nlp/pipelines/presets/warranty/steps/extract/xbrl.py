# src/sec_nlp/pipelines/presets/warranty/steps/extract/xbrl.py
"""XBRL fact extraction for warranty pipeline."""

import re
from pathlib import Path
from typing import TypedDict

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.types import SourceMetadata, WarrantyExtractionDict

# XBRL tags to search for warranty-related data
WARRANTY_XBRL_TAGS: list[str] = [
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


class XbrlValueEntry(TypedDict):
    """Extracted XBRL fact value with tag and context metadata."""

    value: float
    tag: str
    context_ref: str | None
    period_end: str | None


type XbrlValueSets = dict[str, list[XbrlValueEntry]]


class XbrlYearBucket(TypedDict, total=False):
    """Year bucket for normalized warranty-related XBRL totals."""

    warranty_liability: float | None
    warranty_payout: float | None
    net_revenue: float | None
    period: str | int | None
    period_end: str | None
    accession_number: str | None
    confidence: float
    source_metadata: SourceMetadata
    _value_sets: XbrlValueSets
    _conflicts: set[str]


def load_xbrl_for_filing(
    symbol: str,
    filing_dir: Path,
    accession_number: str,
) -> list[Document]:
    """Load XBRL facts for a specific filing directory.

    Parses inline XBRL (ix:nonFraction) or legacy raw tags and returns them
    as Documents so the deterministic extractor can operate without the LLM.

    Args:
        symbol: Ticker symbol
        filing_dir: Path to filing directory
        accession_number: SEC accession number

    Returns:
        List of Documents containing XBRL facts
    """
    # Find HTML file in this filing directory
    html_files = list(filing_dir.glob("*.html"))
    html_path = html_files[0] if html_files else None

    text = ""
    if html_path:
        try:
            text = html_path.read_text(errors="ignore")
        except Exception as e:
            logger.error("Failed to read %s: %s", html_path.name, e)

    facts: list[Document] = []
    raw_docs: list[Document] = []
    seen: set[tuple[str, str | None, str | None, float]] = set()

    if text:
        # Preserve raw XBRL/HTML for optional LLM extraction
        raw_docs.append(
            Document(
                page_content=text,
                metadata={
                    "category": "xbrl_raw",
                    "symbol": symbol,
                    "accession_number": accession_number,
                    "source": str(html_path) if html_path else str(filing_dir),
                },
            )
        )
        facts.extend(
            _parse_facts_from_text(
                text, str(html_path), symbol, accession_number, seen
            )
        )

    # Fallback: parse full-submission when inline HTML has no facts
    if not facts:
        full_submission = filing_dir / "full-submission.txt"
        if full_submission.exists():
            try:
                fs_text = full_submission.read_text(errors="ignore")
                facts.extend(
                    _parse_facts_from_text(
                        fs_text,
                        str(full_submission),
                        symbol,
                        accession_number,
                        seen,
                    )
                )
                if facts:
                    logger.info(
                        "Parsed %d XBRL facts from full-submission.txt for %s/%s",
                        len(facts),
                        symbol,
                        accession_number,
                    )
                    # Also keep raw full-submission for LLM path
                    raw_docs.append(
                        Document(
                            page_content=fs_text,
                            metadata={
                                "category": "xbrl_raw",
                                "symbol": symbol,
                                "accession_number": accession_number,
                                "source": str(full_submission),
                            },
                        )
                    )
            except Exception as e:
                logger.debug(
                    "Failed to parse full-submission.txt for %s/%s: %s",
                    symbol,
                    accession_number,
                    e,
                )

    return raw_docs + facts


def _parse_facts_from_text(
    text: str,
    source: str,
    symbol: str,
    accession_number: str,
    seen: set[tuple[str, str | None, str | None, float]],
) -> list[Document]:
    """Parse both inline ix:nonFraction and raw tags from a text blob."""
    docs: list[Document] = []

    for tag in WARRANTY_XBRL_TAGS:
        # Inline XBRL (common post-2020)
        for m in re.finditer(
            rf'<ix:nonFraction[^>]*name="{re.escape(tag)}"[^>]*>([-+]?\d[\d,\.]*)</ix:nonFraction>',
            text,
            flags=re.IGNORECASE,
        ):
            doc = _build_document(
                element=m.group(0),
                raw_val=m.group(1),
                tag=tag,
                source=source,
                symbol=symbol,
                accession_number=accession_number,
                seen=seen,
            )
            if doc:
                docs.append(doc)

        # Raw tag (older pre-inline filings)
        for m in re.finditer(
            rf"<{re.escape(tag)}[^>]*>([-+]?\d[\d,\.]*)</{re.escape(tag)}>",
            text,
            flags=re.IGNORECASE,
        ):
            doc = _build_document(
                element=m.group(0),
                raw_val=m.group(1),
                tag=tag,
                source=source,
                symbol=symbol,
                accession_number=accession_number,
                seen=seen,
            )
            if doc:
                docs.append(doc)

    return docs


def _build_document(
    *,
    element: str,
    raw_val: str,
    tag: str,
    source: str,
    symbol: str,
    accession_number: str,
    seen: set[tuple[str, str | None, str | None, float]],
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
                year_match = re.search(r"(20\d{2}|19\d{2})", context_ref)
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


def extract_from_xbrl_docs(
    symbol: str, docs: list[Document]
) -> list[WarrantyExtractionDict]:
    """Build deterministic results from XBRL facts, grouped by fiscal year.

    Keeps only one row per fiscal year and prefers the first seen value per
    tag family to avoid double-counting contexts.

    Args:
        symbol: Ticker symbol
        docs: List of XBRL Documents

    Returns:
        List of extraction results grouped by fiscal year
    """
    if not docs:
        return []

    def _track_value(
        bucket: XbrlYearBucket,
        field: str,
        val: float,
        tag: str,
        context_ref: str | None,
        period_end: str | None,
    ) -> None:
        """Track all XBRL values per field to surface conflicts."""
        values = bucket.setdefault("_value_sets", {}).setdefault(field, [])
        values.append(
            {
                "value": val,
                "tag": tag,
                "context_ref": context_ref,
                "period_end": period_end,
            }
        )
        rounded_vals = {
            round(entry["value"], 6)
            for entry in values
            if entry.get("value") is not None
        }
        if len(rounded_vals) > 1:
            bucket.setdefault("_conflicts", set()).add(field)

    # Group facts by fiscal year
    by_year: dict[str, XbrlYearBucket] = {}

    for d in docs:
        meta = d.metadata or {}
        tag = str(meta.get("tag", "")).lower()
        fiscal_year = meta.get("fiscal_year")
        period_end = meta.get("period_end")
        accession_number = meta.get("accession_number")

        try:
            val = float(d.page_content)
        except (TypeError, ValueError):
            continue

        # Use fiscal_year as key, fallback to "unknown"
        if fiscal_year is None:
            year_key = "unknown"
        else:
            year_key = str(fiscal_year)

        if year_key not in by_year:
            period_end_val = str(period_end) if period_end is not None else None
            bucket: XbrlYearBucket = {
                "warranty_liability": None,
                "warranty_payout": None,
                "net_revenue": None,
                "period": fiscal_year
                if isinstance(fiscal_year, (str, int))
                else None,
                "period_end": period_end_val,
                "accession_number": str(accession_number)
                if accession_number is not None
                else None,
                "confidence": 1.0,
                "source_metadata": {
                    "method": "xbrl_facts",
                    "symbol": symbol,
                },
                "_value_sets": {},
                "_conflicts": set(),
            }
            by_year[year_key] = bucket

        period_end_str = str(period_end) if period_end is not None else None
        # Update with period_end if we have a better one
        if period_end_str and not by_year[year_key].get("period_end"):
            by_year[year_key]["period_end"] = period_end_str
            if accession_number and not by_year[year_key].get(
                "accession_number"
            ):
                by_year[year_key]["accession_number"] = str(accession_number)

        # Assign values based on tag
        field_key = _classify_tag(tag, by_year[year_key], val)

        context_ref = meta.get("context_ref")
        period_end = meta.get("period_end")
        if field_key:
            _track_value(
                by_year[year_key],
                field_key,
                val,
                str(meta.get("tag") or tag),
                str(context_ref) if context_ref is not None else None,
                str(period_end) if period_end is not None else None,
            )

    # Filter out entries with no numeric data and attach conflict metadata
    results: list[WarrantyExtractionDict] = []
    for year_data in by_year.values():
        if (
            year_data.get("warranty_liability") is None
            and year_data.get("warranty_payout") is None
        ):
            continue

        conflicts = sorted(year_data.get("_conflicts", set()))
        value_sets = year_data.get("_value_sets", {})

        meta: SourceMetadata = {}
        source_meta = year_data.get("source_metadata")
        if isinstance(source_meta, dict):
            method = source_meta.get("method")
            if isinstance(method, str):
                meta["method"] = method
            symbol_val = source_meta.get("symbol")
            if isinstance(symbol_val, str):
                meta["symbol"] = symbol_val
            accession_val = source_meta.get("accession_number")
            if isinstance(accession_val, str):
                meta["accession_number"] = accession_val
            period_val = source_meta.get("period")
            if isinstance(period_val, (str, int)) or period_val is None:
                meta["period"] = period_val
            period_end_val = source_meta.get("period_end")
            if isinstance(period_end_val, str) or period_end_val is None:
                meta["period_end"] = period_end_val
            fiscal_year_val = source_meta.get("fiscal_year")
            if (
                isinstance(fiscal_year_val, (str, int))
                or fiscal_year_val is None
            ):
                meta["fiscal_year"] = fiscal_year_val
        if conflicts:
            meta["xbrl_conflicts"] = conflicts
        if value_sets:
            meta["xbrl_values_seen"] = {
                field: [
                    {
                        "value": entry.get("value"),
                        "tag": entry.get("tag"),
                        "context_ref": entry.get("context_ref"),
                        "period_end": entry.get("period_end"),
                    }
                    for entry in entries
                ]
                for field, entries in value_sets.items()
            }

        record: WarrantyExtractionDict = {
            "warranty_liability": year_data.get("warranty_liability"),
            "warranty_payout": year_data.get("warranty_payout"),
            "net_revenue": year_data.get("net_revenue"),
            "period": year_data.get("period"),
            "period_end": year_data.get("period_end"),
            "confidence": year_data.get("confidence"),
            "source_metadata": meta,
        }
        accession = year_data.get("accession_number")
        if accession is not None:
            record["accession_number"] = accession
        results.append(record)

    # Sort by period descending (most recent first)
    results.sort(key=lambda r: r.get("period") or "0000", reverse=True)

    if results:
        _log_xbrl_stats(symbol, docs, results)
    else:
        logger.info(
            "XBRL stats for %s: no usable facts (input facts=%d)",
            symbol,
            len(docs),
        )

    return results


def _classify_tag(
    tag: str, year_data: XbrlYearBucket, val: float
) -> str | None:
    """Classify XBRL tag and assign value to appropriate field."""
    # Check for payments/payouts first (most specific patterns)
    if "payment" in tag and "accrual" in tag:
        # Tags like StandardProductWarrantyAccrualPayments
        if year_data["warranty_payout"] is None:
            year_data["warranty_payout"] = val
        return "warranty_payout"
    if "warrantyclaimspaid" in tag:
        # Tags like StandardProductWarrantyAccrualWarrantyClaimsPaid
        if year_data["warranty_payout"] is None:
            year_data["warranty_payout"] = val
        return "warranty_payout"
    # Now handle liability/accrual tags (only if not a payment tag)
    if "standardproductwarrantyaccrual" in tag:
        # StandardProductWarrantyAccrual = warranty liability
        if year_data["warranty_liability"] is None:
            year_data["warranty_liability"] = val
        return "warranty_liability"
    if "productwarrantyaccrual" in tag:
        # ProductWarrantyAccrual = warranty liability
        if year_data["warranty_liability"] is None:
            year_data["warranty_liability"] = val
        return "warranty_liability"
    if "warrantyaccrual" in tag:
        # WarrantyAccrual = warranty liability
        if year_data["warranty_liability"] is None:
            year_data["warranty_liability"] = val
        return "warranty_liability"
    # Revenue tags
    if (
        "revenuefromcontractwithcustomer" in tag
        or tag in ("us-gaap:revenues", "revenues")
        or "salesrevenuenet" in tag
    ):
        if year_data["net_revenue"] is None:
            year_data["net_revenue"] = val
        return "net_revenue"
    return None


def _log_xbrl_stats(
    symbol: str, docs: list[Document], results: list[WarrantyExtractionDict]
) -> None:
    """Log XBRL extraction statistics."""

    def _fmt_period(r: WarrantyExtractionDict) -> str:
        """Format period values into canonical period labels."""
        val = r.get("period") or r.get("period_end")
        if val is None:
            return "?"
        s = str(val).strip()
        if s.isdigit() and len(s) == 4:
            try:
                year = int(s)
                if 1900 <= year <= 2100:
                    return s
            except ValueError:
                pass
        return "?"

    logger.info(
        "XBRL stats for %s: facts=%d periods=%d [%s] liabilities=%d payouts=%d revenues=%d",
        symbol,
        len(docs),
        len(results),
        ", ".join({_fmt_period(r) for r in results}),
        sum(1 for r in results if r.get("warranty_liability") is not None),
        sum(1 for r in results if r.get("warranty_payout") is not None),
        sum(1 for r in results if r.get("net_revenue") is not None),
    )
