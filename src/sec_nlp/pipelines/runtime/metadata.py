# src/sec_nlp/pipelines/runtime/metadata.py
"""Runtime metadata helpers for accession lookup, filtering, and output shaping.

This module consolidates the shared metadata utilities that presets use during
vector search, result export, and exhibit rollups. Keeping these helpers in one
runtime module reduces import sprawl and makes the shared metadata contract
explicit across analyze and EXB flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qdrant_client.models import (
        FieldCondition,
        Filter,
    )


import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TypedDict

from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.core.types import is_json_array, is_json_object
from sec_nlp.pipelines.serialization import is_score_key, round_score
from sec_nlp.pipelines.types import (
    AnalysisResultDict,
    MetadataMap,
    MetadataValue,
)
from sec_nlp.types import JsonDict, JsonObject, JsonValue

type MetadataFilterValue = str | int | bool
type MetadataFilterInput = MetadataFilterValue | Sequence[MetadataFilterValue]
type MetadataFilters = Mapping[str, MetadataFilterInput]

_QDRANT_METADATA_PREFIX = "metadata"
_OMIT_METADATA_KEYS: set[str] = {
    "raw_chunk",
    "page_content",
}


class RollupWorkItem(TypedDict):
    """Mutable aggregation row for exhibit rollup construction.

    Attributes:
        accession_number: Filing accession used as the rollup key.
        filing_date: Filing or acceptance date for the exhibit source.
        form_type: SEC form type associated with the exhibit.
        exhibit_number: Exhibit identifier reported in source metadata.
        filename: Best-effort source filename for output display.
        chunk_count: Number of contributing chunks aggregated into the rollup.
        parties: Distinct parties collected from chunk analysis results.
        suppliers: Distinct supplier names collected from results.
        key_terms: Unique extracted key terms for the accession.
        obligations: Unique obligation phrases for the accession.
        summaries: Per-chunk summaries preserved for later output.
    """

    accession_number: str
    filing_date: str | None
    form_type: str | None
    exhibit_number: str | None
    filename: str | None
    chunk_count: int
    parties: set[str]
    suppliers: set[str]
    key_terms: set[str]
    obligations: set[str]
    summaries: list[str]


class RollupRecord(TypedDict):
    """Normalized exhibit rollup payload emitted to outputs.

    Attributes:
        accession_number: Filing accession used as the record identifier.
        filing_date: Filing or acceptance date associated with the exhibit.
        form_type: SEC form type associated with the exhibit.
        exhibit_number: Exhibit identifier reported in source metadata.
        filename: Best-effort source filename for output display.
        chunk_count: Number of contributing chunks aggregated into the record.
        parties: Sorted list of parties collected from chunk results.
        suppliers: Sorted list of supplier names collected from results.
        key_terms: Sorted list of extracted key terms for the accession.
        obligations: Sorted list of obligation phrases for the accession.
        summaries: Ordered list of chunk summaries for the accession.
    """

    accession_number: str
    filing_date: str | None
    form_type: str | None
    exhibit_number: str | None
    filename: str | None
    chunk_count: int
    parties: list[str]
    suppliers: list[str]
    key_terms: list[str]
    obligations: list[str]
    summaries: list[str]


def get_accession_from_metadata(metadata: MetadataMap | None) -> str:
    """Extract an accession number or fallback identifier from metadata."""
    if not metadata:
        return "unknown"

    for key in ("accession_number", "accession", "accessionNumber"):
        if metadata.get(key):
            return str(metadata[key])

    source = metadata.get("source") or metadata.get("file_path")
    if isinstance(source, str):
        match = re.search(r"(\d{10}-\d{2}-\d{6})", source)
        if match:
            return match.group(1)

    return "unknown"


def group_results_by_accession(
    results: list[AnalysisResultDict],
    fallback_meta: MetadataMap | None,
) -> dict[str, list[AnalysisResultDict]]:
    """Group analysis results by accession, falling back to parent metadata."""
    grouped: dict[str, list[AnalysisResultDict]] = defaultdict(list)
    fallback_accession = get_accession_from_metadata(fallback_meta)

    for result in results:
        metadata = result.get("source_metadata") or {}
        accession = get_accession_from_metadata(metadata)
        if accession == "unknown":
            accession = fallback_accession
        grouped[accession].append(result)

    return grouped


def build_metadata_filter(raw_filters: MetadataFilters) -> Filter | None:
    """Construct a Qdrant metadata filter from config-style mappings."""
    conditions: list[FieldCondition] = []

    for key, raw_value in raw_filters.items():
        values = _normalize_filter_values(raw_value)
        cleaned = [value for value in values if value != ""]
        if not cleaned:
            continue

        field_key = _prefixed_key(key)

        if len(cleaned) == 1:
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                MatchAny,
                MatchValue,
            )

            conditions.append(
                FieldCondition(
                    key=field_key,
                    match=MatchValue(value=cleaned[0]),
                )
            )
            continue

        str_values: list[str] = []
        int_values: list[int] = []
        bool_values: list[bool] = []
        for value in cleaned:
            if isinstance(value, str):
                str_values.append(value)
            elif isinstance(value, bool):
                bool_values.append(value)
            else:
                int_values.append(value)

        if len(str_values) == len(cleaned):
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                MatchAny,
                MatchValue,
            )

            conditions.append(
                FieldCondition(key=field_key, match=MatchAny(any=str_values))
            )
            continue

        if len(int_values) == len(cleaned):
            from qdrant_client.models import (
                FieldCondition,
                Filter,
                MatchAny,
                MatchValue,
            )

            conditions.append(
                FieldCondition(key=field_key, match=MatchAny(any=int_values))
            )
            continue

        if len(bool_values) == len(cleaned):
            unique_bools = list(dict.fromkeys(bool_values))
            if len(unique_bools) == 1:
                from qdrant_client.models import (
                    FieldCondition,
                    Filter,
                    MatchAny,
                    MatchValue,
                )

                conditions.append(
                    FieldCondition(
                        key=field_key,
                        match=MatchValue(value=unique_bools[0]),
                    )
                )
            continue

        coerced_values = [str(value) for value in cleaned]
        from qdrant_client.models import (
            FieldCondition,
            Filter,
            MatchAny,
            MatchValue,
        )

        conditions.append(
            FieldCondition(key=field_key, match=MatchAny(any=coerced_values))
        )

    if not conditions:
        return None

    from qdrant_client.models import FieldCondition, MatchAny, MatchValue

    return Filter(must=list(conditions))


def coerce_meta_str(value: MetadataValue) -> str | None:
    """Normalize a metadata scalar to a string value."""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return None


def get_meta_str(meta: MetadataMap, key: str) -> str | None:
    """Return one metadata value as a normalized string."""
    value = meta.get(key)
    if value is None:
        return None
    return coerce_meta_str(value)


def get_meta_str_any(
    meta: MetadataMap,
    keys: Iterable[str],
    *,
    include_source_meta: bool = True,
) -> str | None:
    """Return the first matching metadata value across candidate keys."""
    for key in keys:
        value = meta.get(key)
        if value is None:
            continue
        coerced = coerce_meta_str(value)
        if coerced is not None:
            return coerced
    if include_source_meta:
        source_meta = meta.get("source_metadata")
        if is_json_object(source_meta):
            for key in keys:
                value = source_meta.get(key)
                if value is None:
                    continue
                coerced = coerce_meta_str(value)
                if coerced is not None:
                    return coerced
    return None


def normalize_metadata_for_output(metadata: MetadataMap | None) -> JsonDict:
    """Convert internal metadata to a stable JSON-safe output payload."""
    if not metadata:
        return {}

    payload: JsonDict = {}
    for key, raw_value in metadata.items():
        if not isinstance(key, str):
            continue
        if key in _OMIT_METADATA_KEYS:
            continue
        normalized = _normalize_metadata_value(key, raw_value)
        if normalized is not None:
            payload[key] = normalized
    return payload


def prepare_vector_docs(
    docs: list[Document],
    *,
    symbol: str,
) -> list[Document]:
    """Attach consistent vector metadata for indexed exhibit chunks."""
    vector_docs: list[Document] = []

    for doc in docs:
        base_meta = doc.metadata or {}
        doc.metadata.update(
            {
                **base_meta,
                "symbol": symbol,
                "text": doc.page_content,
                "relevance_score": None,
            }
        )
        vector_docs.append(doc)

    return vector_docs


def build_rollups(
    relevant_results: list[JsonObject],
) -> tuple[list[RollupRecord], set[str], set[str]]:
    """Aggregate per-accession exhibit rollups and unique parties/suppliers."""
    all_suppliers: set[str] = set()
    all_parties: set[str] = set()
    rollups: dict[str, RollupWorkItem] = {}

    for result in relevant_results:
        all_suppliers.update(_as_str_list(result.get("supplier_names")))
        all_parties.update(_as_str_list(result.get("parties")))

        metadata = _as_metadata(result.get("source_metadata"))
        accession = _as_str(metadata.get("accession_number")) or _as_str(
            metadata.get("source_file")
        )
        accession = accession or "unknown"
        if accession not in rollups:
            rollups[accession] = RollupWorkItem(
                accession_number=accession,
                filing_date=_as_str(metadata.get("filing_date")),
                form_type=_as_str(metadata.get("form_type")),
                exhibit_number=_as_str(metadata.get("exhibit_number")),
                filename=_as_str(metadata.get("filename"))
                or _as_str(metadata.get("source_file")),
                chunk_count=0,
                parties=set(),
                suppliers=set(),
                key_terms=set(),
                obligations=set(),
                summaries=[],
            )

        entry = rollups[accession]
        entry["chunk_count"] += 1
        entry["parties"].update(_as_str_list(result.get("parties")))
        entry["suppliers"].update(_as_str_list(result.get("supplier_names")))
        entry["key_terms"].update(_as_str_list(result.get("key_terms")))
        entry["obligations"].update(_as_str_list(result.get("obligations")))
        summary_text = _as_str(result.get("summary")) or _as_str(
            result.get("reasoning")
        )
        if summary_text:
            entry["summaries"].append(summary_text)

    rollup_list: list[RollupRecord] = []
    for entry in rollups.values():
        rollup: RollupRecord = {
            "accession_number": entry["accession_number"],
            "filing_date": entry["filing_date"],
            "form_type": entry["form_type"],
            "exhibit_number": entry["exhibit_number"],
            "filename": entry["filename"],
            "chunk_count": entry["chunk_count"],
            "parties": sorted(entry["parties"]),
            "suppliers": sorted(entry["suppliers"]),
            "key_terms": sorted(entry["key_terms"]),
            "obligations": sorted(entry["obligations"]),
            "summaries": list(entry["summaries"]),
        }
        rollup_list.append(rollup)

    return rollup_list, all_suppliers, all_parties


def _prefixed_key(key: str) -> str:
    """Prefix a metadata key for the Qdrant payload path."""
    if key.startswith(f"{_QDRANT_METADATA_PREFIX}."):
        return key
    return f"{_QDRANT_METADATA_PREFIX}.{key}"


def _normalize_filter_values(
    raw_value: MetadataFilterInput,
) -> list[MetadataFilterValue]:
    """Normalize scalar or sequence filter values into a concrete list."""
    if isinstance(raw_value, (str, bool, int)):
        return [raw_value]
    return list(raw_value)


def _normalize_metadata_value(
    key: str,
    value: MetadataValue | Path,
) -> JsonValue | None:
    """Normalize one metadata value for output serialization."""
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (int, float)) and is_score_key(key):
        return round_score(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if is_json_object(value):
        nested: JsonDict = {}
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                continue
            if nested_key in _OMIT_METADATA_KEYS:
                continue
            normalized = _normalize_metadata_value(nested_key, nested_value)
            if normalized is not None:
                nested[nested_key] = normalized
        return nested or None
    if is_json_array(value):
        items: list[JsonValue] = []
        for item in value:
            normalized = _normalize_metadata_value(key, item)
            if normalized is not None:
                items.append(normalized)
        return items or None
    return None


def _as_str(value: JsonValue | None) -> str | None:
    """Coerce one JSON value into a string when safe."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def _as_str_list(value: JsonValue | None) -> list[str]:
    """Coerce one JSON value into a list of strings when safe."""
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if is_json_array(value) and not isinstance(value, str):
        items: list[str] = []
        for item in value:
            if isinstance(item, bool):
                continue
            if isinstance(item, (str, int, float)):
                items.append(str(item))
        return items
    return []


def _as_metadata(value: JsonValue | None) -> JsonObject:
    """Coerce one JSON value into a metadata object when safe."""
    if is_json_object(value):
        cleaned: dict[str, JsonValue] = {}
        for key, raw in value.items():
            if not isinstance(key, str):
                continue
            if isinstance(raw, (str, int, float, bool)) or raw is None:
                cleaned[key] = raw
                continue
            if isinstance(raw, Sequence) and not isinstance(raw, str):
                items: list[JsonValue] = []
                ok = True
                for item in raw:
                    if (
                        isinstance(item, (str, int, float, bool))
                        or item is None
                    ):
                        items.append(item)
                    else:
                        ok = False
                        break
                if ok:
                    cleaned[key] = items
                continue
            if isinstance(raw, Mapping):
                nested: dict[str, JsonValue] = {}
                ok = True
                for nested_key, nested_value in raw.items():
                    if not isinstance(nested_key, str):
                        ok = False
                        break
                    if (
                        isinstance(nested_value, (str, int, float, bool))
                        or nested_value is None
                    ):
                        nested[nested_key] = nested_value
                    else:
                        ok = False
                        break
                if ok:
                    cleaned[key] = nested
        return cleaned
    return {}
