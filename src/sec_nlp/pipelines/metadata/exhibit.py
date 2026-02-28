# src/sec_nlp/pipelines/metadata/exhibit.py
"""Metadata helpers for the exhibit pipeline."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypedDict

from langchain_core.documents import Document

from sec_nlp.types import JsonObject, JsonValue


class RollupWorkItem(TypedDict):
    """Input row used while building exhibit rollups."""

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
    """Normalized exhibit rollup record emitted to outputs."""

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


def _as_str(value: JsonValue | None) -> str | None:
    """Coerce str."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        return str(value)
    return None


def _as_str_list(value: JsonValue | None) -> list[str]:
    """Coerce str list."""
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, str):
        items: list[str] = []
        for item in value:
            if isinstance(item, bool):
                continue
            if isinstance(item, (str, int, float)):
                items.append(str(item))
        return items
    return []


def _as_metadata(value: JsonValue | None) -> JsonObject:
    """Coerce metadata."""
    if isinstance(value, Mapping):
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
                for nk, nv in raw.items():
                    if not isinstance(nk, str):
                        ok = False
                        break
                    if isinstance(nv, (str, int, float, bool)) or nv is None:
                        nested[nk] = nv
                    else:
                        ok = False
                        break
                if ok:
                    cleaned[key] = nested
        return cleaned
    return {}


def prepare_vector_docs(
    docs: list[Document],
    *,
    symbol: str,
) -> list[Document]:
    """Attach consistent vector metadata for indexed chunks."""
    vector_docs: list[Document] = []

    for doc in docs:
        base_meta = doc.metadata or {}
        doc.metadata = {
            **base_meta,
            "symbol": symbol,
            "text": doc.page_content,
            "relevance_score": None,
        }
        vector_docs.append(doc)

    return vector_docs


def build_rollups(
    relevant_results: list[JsonObject],
) -> tuple[list[RollupRecord], set[str], set[str]]:
    """Aggregate per-accession rollups and unique parties/suppliers."""
    all_suppliers: set[str] = set()
    all_parties: set[str] = set()
    rollups: dict[str, RollupWorkItem] = {}

    for r in relevant_results:
        all_suppliers.update(_as_str_list(r.get("supplier_names")))
        all_parties.update(_as_str_list(r.get("parties")))

        meta = _as_metadata(r.get("source_metadata"))
        accession = _as_str(meta.get("accession_number")) or _as_str(
            meta.get("source_file")
        )
        accession = accession or "unknown"
        if accession not in rollups:
            rollups[accession] = RollupWorkItem(
                accession_number=accession,
                filing_date=_as_str(meta.get("filing_date")),
                form_type=_as_str(meta.get("form_type")),
                exhibit_number=_as_str(meta.get("exhibit_number")),
                filename=_as_str(meta.get("filename"))
                or _as_str(meta.get("source_file")),
                chunk_count=0,
                parties=set(),
                suppliers=set(),
                key_terms=set(),
                obligations=set(),
                summaries=[],
            )

        entry = rollups[accession]
        entry["chunk_count"] += 1
        entry["parties"].update(_as_str_list(r.get("parties")))
        entry["suppliers"].update(_as_str_list(r.get("supplier_names")))
        entry["key_terms"].update(_as_str_list(r.get("key_terms")))
        entry["obligations"].update(_as_str_list(r.get("obligations")))
        summary_text = _as_str(r.get("summary")) or _as_str(r.get("reasoning"))
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
