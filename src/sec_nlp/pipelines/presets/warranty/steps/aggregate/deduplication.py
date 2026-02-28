# src/sec_nlp/pipelines/presets/warranty/steps/aggregate/deduplication.py
"""Period record deduplication and aggregation for warranty pipeline."""

from collections.abc import Hashable
from datetime import datetime
from typing import Literal

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.types import (
    FilingMetadata,
    WarrantyAggregateDict,
    WarrantyExtractionDict,
)
from sec_nlp.types import JsonValue

from ...types import WarrantyMergeBucket, WarrantyPeriodRecord

FieldName = Literal["warranty_liability", "warranty_payout", "net_revenue"]


def aggregate_period_records(
    symbol: str,
    filing_meta: FilingMetadata,
    valid_results: list[WarrantyExtractionDict],
) -> list[WarrantyPeriodRecord]:
    """Merge XBRL/LLM results across filings and periods into flat records.

    Keeps provenance (source flags/accessions) while preferring XBRL values
    and highest confidence. This is the primary place where per-filing
    records are collapsed into per-period rows.

    Args:
        symbol: Ticker symbol
        filing_meta: Filing metadata (accession_number, form_type, etc.)
        valid_results: List of valid extraction results

    Returns:
        List of aggregated period records
    """

    def _get_accession(rec: WarrantyExtractionDict) -> str | None:
        """Extract accession number from a period record."""
        return (
            rec.get("accession_number")
            or rec.get("source_metadata", {}).get("accession_number")
            or filing_meta.get("accession_number")
        )

    def _get_method(rec: WarrantyExtractionDict) -> str:
        """Extract method value from a period record."""
        return str(rec.get("source_metadata", {}).get("method", "llm"))

    def _extract_period_info(
        rec: WarrantyExtractionDict,
    ) -> tuple[str | None, str | None]:
        """Extract normalized period metadata for aggregation."""
        meta = rec.get("source_metadata", {}) or {}
        period_val = (
            rec.get("period") or meta.get("period") or meta.get("fiscal_year")
        )
        period_end = rec.get("period_end") or meta.get("period_end")
        period_end_str = None
        if isinstance(period_end, int):
            period_end_str = str(period_end)
        elif isinstance(period_end, str):
            period_end_str = period_end
        if period_val is None and period_end_str:
            period_val = period_end_str[:4]

        return _clean_year(period_val), period_end_str

    def _init_agg(
        period: str | None, period_end: str | None, acc: str | None = None
    ) -> WarrantyAggregateDict:
        """Initialize an aggregation bucket for one period key."""
        agg: WarrantyAggregateDict = {
            "symbol": symbol,
            "period": period,
            "period_end": period_end,
            "warranty_liability": None,
            "warranty_payout": None,
            "net_revenue": None,
            "confidence": 0.0,
            "accessions": {acc} if acc else set(),
            "source_flags": set(),
            "warranty_liability_from_xbrl": False,
            "warranty_payout_from_xbrl": False,
            "net_revenue_from_xbrl": False,
            "xbrl_conflicted_fields": set(),
        }
        return agg

    def _merge_value(
        agg: WarrantyAggregateDict,
        field: FieldName,
        new_val: float | None,
        new_is_xbrl: bool,
    ) -> None:
        """Merge two values using source-priority rules."""
        if new_val is None:
            return
        if field == "warranty_liability":
            has_xbrl = bool(agg.get("warranty_liability_from_xbrl"))
            current = agg.get("warranty_liability")
            if new_is_xbrl:
                if current is None or not has_xbrl:
                    agg["warranty_liability"] = new_val
                    agg["warranty_liability_from_xbrl"] = True
            elif current is None:
                agg["warranty_liability"] = new_val
            return
        if field == "warranty_payout":
            has_xbrl = bool(agg.get("warranty_payout_from_xbrl"))
            current = agg.get("warranty_payout")
            if new_is_xbrl:
                if current is None or not has_xbrl:
                    agg["warranty_payout"] = new_val
                    agg["warranty_payout_from_xbrl"] = True
            elif current is None:
                agg["warranty_payout"] = new_val
            return
        has_xbrl = bool(agg.get("net_revenue_from_xbrl"))
        current = agg.get("net_revenue")
        if new_is_xbrl:
            if current is None or not has_xbrl:
                agg["net_revenue"] = new_val
                agg["net_revenue_from_xbrl"] = True
        elif current is None:
            agg["net_revenue"] = new_val

    def _merge_agg(
        target: WarrantyAggregateDict, source: WarrantyAggregateDict
    ) -> None:
        """Merge source aggregates into one combined aggregate."""
        target["accessions"].update(source.get("accessions", set()))
        target["source_flags"].update(source.get("source_flags", set()))
        target["xbrl_conflicted_fields"].update(
            source.get("xbrl_conflicted_fields", set())
        )
        src_period_end = source.get("period_end")
        if src_period_end and (
            not target.get("period_end")
            or str(src_period_end) > str(target["period_end"])
        ):
            target["period_end"] = src_period_end

        for field in (
            "warranty_liability",
            "warranty_payout",
            "net_revenue",
        ):
            if field == "warranty_liability":
                flag = bool(source.get("warranty_liability_from_xbrl"))
            elif field == "warranty_payout":
                flag = bool(source.get("warranty_payout_from_xbrl"))
            else:
                flag = bool(source.get("net_revenue_from_xbrl"))
            _merge_value(
                target,
                field,
                source.get(field),
                flag,
            )

        if source.get("confidence", 0.0) > target.get("confidence", 0.0):
            target["confidence"] = source["confidence"]

    def _source_label(flags: set[str]) -> str:
        """Build a stable source label for diagnostics."""
        if "xbrl" in flags and "llm" in flags:
            return "mixed"
        if "xbrl" in flags:
            return "xbrl"
        if "llm" in flags:
            return "llm"
        return "unknown"

    def _normalize_period(rec: WarrantyPeriodRecord) -> str | None:
        """Normalize period labels for deterministic grouping."""
        if rec.get("period"):
            cleaned = _clean_year(rec.get("period"))
            if cleaned:
                return cleaned
        period_end = rec.get("period_end")
        if period_end:
            cleaned = _clean_year(str(period_end)[:4])
            if cleaned:
                return cleaned
        return None

    # First, bucket by (accession, period) to merge within each filing
    accession_period_buckets: dict[
        tuple[str | None, str | None], WarrantyAggregateDict
    ] = {}
    unknown_period_buckets: list[WarrantyAggregateDict] = []

    for rec in valid_results:
        acc = _get_accession(rec)
        is_xbrl = _get_method(rec) == "xbrl_facts"
        conflict_fields = set(
            rec.get("source_metadata", {}).get("xbrl_conflicts") or []
        )
        period_key, period_end = _extract_period_info(rec)
        bucket_key = (acc, period_key)

        agg = accession_period_buckets.get(bucket_key)
        if agg is None:
            agg = _init_agg(period_key, period_end, acc)
            accession_period_buckets[bucket_key] = agg

        if period_key is None:
            unknown_period_buckets.append(agg)

        agg["accessions"].update([acc] if acc else [])
        agg["source_flags"].add("xbrl" if is_xbrl else "llm")
        if conflict_fields:
            agg["xbrl_conflicted_fields"].update(conflict_fields)
        if period_end and not agg.get("period_end"):
            agg["period_end"] = period_end

        _merge_value(
            agg,
            "warranty_liability",
            rec.get("warranty_liability"),
            is_xbrl,
        )
        _merge_value(
            agg, "warranty_payout", rec.get("warranty_payout"), is_xbrl
        )
        _merge_value(agg, "net_revenue", rec.get("net_revenue"), is_xbrl)

        conf = rec.get("confidence")
        if conf is None:
            conf = 1.0 if is_xbrl else 0.0
        if conf is not None and conf > agg["confidence"]:
            agg["confidence"] = conf

    # Then merge across accessions by period to fill gaps
    merged_by_period: dict[str, WarrantyAggregateDict] = {}
    for (_acc, period_key), bucket in accession_period_buckets.items():
        if period_key is None:
            continue
        if period_key not in merged_by_period:
            merged_by_period[period_key] = _init_agg(
                period_key, bucket.get("period_end")
            )
        _merge_agg(merged_by_period[period_key], bucket)

    period_records: list[WarrantyPeriodRecord] = []

    # Period-keyed records
    for period_key, agg in merged_by_period.items():
        source_label = _source_label(agg.get("source_flags", set()))
        record: WarrantyPeriodRecord = {
            "symbol": symbol,
            "period": period_key,
            "period_end": agg.get("period_end"),
            "warranty_liability": agg.get("warranty_liability"),
            "warranty_payout": agg.get("warranty_payout"),
            "net_revenue": agg.get("net_revenue"),
            "confidence": agg.get("confidence", 0.0),
            "source": source_label,
            "accession_number": ";".join(
                sorted(a for a in agg.get("accessions", set()) if a)
            )
            or filing_meta.get("accession_number"),
            "xbrl_conflicted_fields": sorted(
                agg.get("xbrl_conflicted_fields", set())
            )
            or None,
        }
        period_records.append(record)

    # Period-less records (keep period=None)
    for agg in {id(b): b for b in unknown_period_buckets}.values():
        source_label = _source_label(agg.get("source_flags", set()))
        record: WarrantyPeriodRecord = {
            "symbol": symbol,
            "period": None,
            "period_end": agg.get("period_end"),
            "warranty_liability": agg.get("warranty_liability"),
            "warranty_payout": agg.get("warranty_payout"),
            "net_revenue": agg.get("net_revenue"),
            "confidence": agg.get("confidence", 0.0),
            "source": source_label,
            "accession_number": ";".join(
                sorted(a for a in agg.get("accessions", set()) if a)
            )
            or filing_meta.get("accession_number"),
            "xbrl_conflicted_fields": sorted(
                agg.get("xbrl_conflicted_fields", set())
            )
            or None,
        }
        period_records.append(record)

    # Normalize period from period_end where possible
    for rec in period_records:
        rec["period"] = _normalize_period(rec)

    # Fallback: if no records have a period, use filing_year as a last resort
    if period_records and all(
        rec.get("period") is None for rec in period_records
    ):
        fallback_period = filing_meta.get("filing_year")
        if fallback_period is not None:
            for rec in period_records:
                rec["period"] = str(fallback_period)

    return period_records


def dedupe_period_records(
    records: list[WarrantyPeriodRecord],
) -> list[WarrantyPeriodRecord]:
    """Merge duplicate period records (e.g., from multiple documents/filings).

    Prefers XBRL/mixed sources, higher confidence, and rows with more data,
    while allowing fields to be filled from different accessions. Periods are
    merged on the fiscal year to collapse rows that only differ by period_end
    formatting.

    Args:
        records: List of period records to deduplicate

    Returns:
        Deduplicated list of period records
    """

    def _norm_period_end(val: JsonValue) -> str | None:
        """Normalize period-end values to ISO date strings."""
        if val in (None, "", "None"):
            return None
        s = str(val).strip()
        try:
            return datetime.fromisoformat(s).date().isoformat()
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%m/%d/%y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(s, fmt).date().isoformat()
            except ValueError:
                continue
        return s  # leave as-is if unparseable

    def _conflict_fields(rec: WarrantyPeriodRecord) -> set[str]:
        """Return field names considered for conflict tracking."""
        raw = rec.get("xbrl_conflicted_fields")
        if isinstance(raw, str):
            return {f for f in raw.split(";") if f}
        if isinstance(raw, (list, set, tuple)):
            return {str(f) for f in raw if f}
        return set()

    def _normalize(rec: WarrantyPeriodRecord) -> WarrantyPeriodRecord:
        """Normalize scalar values for equality comparisons."""
        normalized: WarrantyPeriodRecord = {}
        symbol = rec.get("symbol")
        if isinstance(symbol, str):
            normalized["symbol"] = symbol

        period = rec.get("period")
        if period is not None:
            normalized["period"] = str(period)

        period_end = rec.get("period_end")
        if period_end is not None:
            normalized["period_end"] = _norm_period_end(period_end)

        for field in (
            "warranty_liability",
            "warranty_payout",
            "net_revenue",
            "confidence",
        ):
            value = _safe_float(rec.get(field))
            if value is not None:
                normalized[field] = value

        source = rec.get("source")
        if isinstance(source, str):
            normalized["source"] = source

        accession = rec.get("accession_number")
        if isinstance(accession, str) and accession:
            normalized["accession_number"] = accession

        conflicts = rec.get("xbrl_conflicted_fields")
        if isinstance(conflicts, str):
            normalized["xbrl_conflicted_fields"] = [
                f for f in conflicts.split(";") if f
            ]
        elif isinstance(conflicts, (list, set, tuple)):
            normalized["xbrl_conflicted_fields"] = [
                str(f) for f in conflicts if f
            ]

        for key in (
            "warranty_liability_sources",
            "warranty_payout_sources",
            "net_revenue_sources",
        ):
            value = rec.get(key)
            if isinstance(value, str):
                normalized[key] = value

        return normalized

    def _period_key(rec: WarrantyPeriodRecord) -> tuple[str | None, str | None]:
        """Build normalized period/year and period_end values for grouping."""
        period = _clean_year(rec.get("period"))
        period_end = _norm_period_end(rec.get("period_end"))
        if period is None and period_end:
            year_part = period_end[:4]
            period = _clean_year(year_part)
        return period, period_end

    def _source_rank(
        source: str | None, field: str, conflict_fields: set[str] | None
    ) -> float:
        """Compute source precedence rank for merge decisions."""
        s = str(source or "").lower()
        rank = 0.0
        if s == "xbrl":
            rank = 3.0
        elif s == "mixed":
            rank = 2.5
        elif s == "llm":
            rank = 2.0
        if conflict_fields and field in conflict_fields:
            rank -= 1.25
        return max(rank, 0.0)

    def _field_value(
        rec: WarrantyPeriodRecord, field: FieldName
    ) -> float | None:
        """Read a field value from a period record."""
        if field == "warranty_liability":
            return rec.get("warranty_liability")
        if field == "warranty_payout":
            return rec.get("warranty_payout")
        return rec.get("net_revenue")

    def _bucket_value(
        bucket: WarrantyMergeBucket, field: FieldName
    ) -> float | None:
        """Read a field value from an aggregate bucket."""
        if field == "warranty_liability":
            return bucket.get("warranty_liability")
        if field == "warranty_payout":
            return bucket.get("warranty_payout")
        return bucket.get("net_revenue")

    def _set_bucket_value(
        bucket: WarrantyMergeBucket, field: FieldName, value: float
    ) -> None:
        """Write a field value into an aggregate bucket."""
        if field == "warranty_liability":
            bucket["warranty_liability"] = value
        elif field == "warranty_payout":
            bucket["warranty_payout"] = value
        else:
            bucket["net_revenue"] = value

    def _bucket_rank(bucket: WarrantyMergeBucket, field: FieldName) -> float:
        """Read the source rank for a bucket field."""
        if field == "warranty_liability":
            return bucket.get("_warranty_liability_rank", -1.0)
        if field == "warranty_payout":
            return bucket.get("_warranty_payout_rank", -1.0)
        return bucket.get("_net_revenue_rank", -1.0)

    def _set_bucket_rank(
        bucket: WarrantyMergeBucket, field: FieldName, rank: float
    ) -> None:
        """Set the source rank for a bucket field."""
        if field == "warranty_liability":
            bucket["_warranty_liability_rank"] = rank
        elif field == "warranty_payout":
            bucket["_warranty_payout_rank"] = rank
        else:
            bucket["_net_revenue_rank"] = rank

    def _bucket_sources(
        bucket: WarrantyMergeBucket, field: FieldName
    ) -> set[str]:
        """Read source labels attached to a bucket field."""
        if field == "warranty_liability":
            return bucket.get("warranty_liability_sources", set())
        if field == "warranty_payout":
            return bucket.get("warranty_payout_sources", set())
        return bucket.get("net_revenue_sources", set())

    def _set_bucket_sources(
        bucket: WarrantyMergeBucket, field: FieldName, sources: set[str]
    ) -> None:
        """Set source labels for a bucket field."""
        if field == "warranty_liability":
            bucket["warranty_liability_sources"] = sources
        elif field == "warranty_payout":
            bucket["warranty_payout_sources"] = sources
        else:
            bucket["net_revenue_sources"] = sources

    def _merge_field(
        target: WarrantyMergeBucket,
        source_rec: WarrantyPeriodRecord,
        field: FieldName,
        accs: set[str],
    ) -> None:
        """Merge one field into a bucket using rank-aware rules."""
        conflict_fields = _conflict_fields(source_rec)
        src_rank = _source_rank(
            source_rec.get("source"), field, conflict_fields
        )
        new_val = _field_value(source_rec, field)
        if new_val in (None, "", "None"):
            return
        if not isinstance(new_val, (int, float)):
            return
        cur_val = _bucket_value(target, field)
        cur_rank = _bucket_rank(target, field)
        # Prefer higher rank; if equal and current missing, replace
        if cur_val is None or src_rank > cur_rank:
            _set_bucket_value(target, field, new_val)
            _set_bucket_rank(target, field, src_rank)
            _set_bucket_sources(target, field, set(accs))
        elif src_rank == cur_rank and cur_val is None:
            _set_bucket_value(target, field, new_val)
            _set_bucket_sources(target, field, set(accs))
        elif src_rank == cur_rank and cur_val is not None:
            sources = _bucket_sources(target, field)
            sources.update(accs)
            _set_bucket_sources(target, field, sources)

    def _safe_float(val: JsonValue | None) -> float | None:
        """Coerce numeric inputs to float when possible."""
        if val in (None, "", "None"):
            return None
        if isinstance(val, bool):
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except ValueError:
                return None
        return None

    grouped: dict[tuple[Hashable, Hashable], WarrantyMergeBucket] = {}
    for rec in map(_normalize, records):
        period_key, period_end_val = _period_key(rec)
        # When period is known, ignore period_end in the grouping key so
        # variants like 2019 vs 2019-12-31 merge into one row.
        key = (period_key, None if period_key else period_end_val)
        bucket = grouped.setdefault(
            key,
            {
                "symbol": rec.get("symbol"),
                "period": period_key,
                "period_end": period_end_val,
                "warranty_liability": None,
                "warranty_payout": None,
                "net_revenue": None,
                "confidence": rec.get("confidence") or 0.0,
                "source": rec.get("source"),
                "accession_number": "",
                "warranty_liability_sources": set(),
                "warranty_payout_sources": set(),
                "net_revenue_sources": set(),
                "xbrl_conflicted_fields": set(),
                "_warranty_liability_rank": -1.0,
                "_warranty_payout_rank": -1.0,
                "_net_revenue_rank": -1.0,
            },
        )

        accs = {
            a.strip()
            for a in str(rec.get("accession_number") or "").split(";")
            if a.strip()
        }
        # Merge accession list regardless of field-level choices
        if accs:
            if bucket["accession_number"]:
                bucket["accession_number"] += ";" + ";".join(sorted(accs))
            else:
                bucket["accession_number"] = ";".join(sorted(accs))

        # Track highest confidence seen
        rec_conf = _safe_float(rec.get("confidence", 0.0))
        if rec_conf is not None:
            current_conf = _safe_float(bucket.get("confidence")) or 0.0
            if rec_conf > current_conf:
                bucket["confidence"] = rec_conf

        bucket_conflicts = bucket.setdefault("xbrl_conflicted_fields", set())
        bucket_conflicts.update(_conflict_fields(rec))

        # Ensure the most specific period_end survives while merging rows by year
        if period_end_val and not bucket.get("period_end"):
            bucket["period_end"] = period_end_val
        elif period_end_val and bucket.get("period_end"):
            # Prefer the lexicographically later end date (usually the more recent)
            bucket["period_end"] = max(
                str(bucket["period_end"]), str(period_end_val)
            )

        # Field-level merging with provenance
        _merge_field(bucket, rec, "warranty_liability", accs)
        _merge_field(bucket, rec, "warranty_payout", accs)
        _merge_field(bucket, rec, "net_revenue", accs)

        # Promote highest-ranked source label
        cur_source_rank = _source_rank(
            bucket.get("source"), "", bucket_conflicts
        )
        src_source_rank = _source_rank(
            rec.get("source"), "", _conflict_fields(rec)
        )
        if src_source_rank > cur_source_rank:
            bucket["source"] = rec.get("source")

    # Finalize output records
    deduped: list[WarrantyPeriodRecord] = []
    for (_period, _period_end), bucket in grouped.items():
        rec: WarrantyPeriodRecord = {}
        symbol = bucket.get("symbol")
        if isinstance(symbol, str):
            rec["symbol"] = symbol
        period = bucket.get("period")
        if period is not None:
            rec["period"] = period
        period_end = bucket.get("period_end")
        if period_end is not None:
            rec["period_end"] = period_end
        liability = bucket.get("warranty_liability")
        if liability is not None:
            rec["warranty_liability"] = liability
        payout = bucket.get("warranty_payout")
        if payout is not None:
            rec["warranty_payout"] = payout
        revenue = bucket.get("net_revenue")
        if revenue is not None:
            rec["net_revenue"] = revenue
        confidence = bucket.get("confidence")
        if confidence is not None:
            rec["confidence"] = confidence
        source = bucket.get("source")
        if isinstance(source, str):
            rec["source"] = source
        accession = bucket.get("accession_number")
        if isinstance(accession, str) and accession:
            rec["accession_number"] = accession

        conflicts = bucket.get("xbrl_conflicted_fields", set())
        rec["xbrl_conflicted_fields"] = sorted(conflicts) if conflicts else []

        for field in (
            "warranty_liability_sources",
            "warranty_payout_sources",
            "net_revenue_sources",
        ):
            sources = bucket.get(field, set())
            rec[field] = ";".join(sorted(sources)) if sources else ""

        # Clean accession_number duplicates
        accession_number = rec.get("accession_number")
        if isinstance(accession_number, str) and accession_number:
            rec["accession_number"] = ";".join(
                sorted({a for a in accession_number.split(";") if a})
            )

        # Log provenance per period for visibility (not persisted to CSV)
        logger.debug(
            "Provenance for %s period %s: liability from [%s]; payout from [%s]; revenue from [%s]",
            rec.get("symbol"),
            rec.get("period") or rec.get("period_end") or "unknown",
            rec.get("warranty_liability_sources") or "n/a",
            rec.get("warranty_payout_sources") or "n/a",
            rec.get("net_revenue_sources") or "n/a",
        )

        deduped.append(rec)

    deduped.sort(key=lambda r: r.get("period") or "0000", reverse=True)
    return deduped


def _clean_year(val: JsonValue) -> str | None:
    """Clean and validate a year value."""
    try:
        s = str(val).strip()
    except Exception:
        return None
    if not s or s in {"None", "0000"}:
        return None
    if len(s) == 4 and s.isdigit():
        year_int = int(s)
        if 1900 <= year_int <= 2100:
            return f"{year_int:04d}"
    return None
