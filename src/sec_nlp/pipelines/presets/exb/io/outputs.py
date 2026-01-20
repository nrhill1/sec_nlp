# src/sec_nlp/pipelines/presets/exb/io/outputs.py
"""Output generation for the exhibit pipeline."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.output_io import (
    build_run_file_stem,
    write_json,
    write_yaml,
)
from sec_nlp.types import JsonDict, JsonObject, JsonValue

from ..config import ExhibitConfig


class AccessionRecord(TypedDict):
    accession_number: str
    form_type: str | None
    filing_date: str | None
    chunk_count: int
    exhibit_numbers: list[str]
    exhibit_categories: list[JsonValue]
    filenames: list[str]
    sources: list[str]
    descriptions: list[str]
    keyword_hits: list[str]


@dataclass
class AccessionAccumulator:
    accession_number: str
    form_type: str | None
    filing_date: str | None
    chunk_count: int = 0
    exhibit_numbers: set[str] = field(default_factory=set)
    exhibit_categories: set[JsonValue] = field(default_factory=set)
    filenames: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    descriptions: set[str] = field(default_factory=set)
    keyword_hits: set[str] = field(default_factory=set)


def write_exhibit_outputs(
    *,
    symbol: str,
    docs: list[Document],
    config: ExhibitConfig,
) -> list[Path]:
    """Write exhibit indexing results to output files.

    Args:
        symbol: Ticker symbol
        docs: Analyzed document chunks
        config: Pipeline configuration

    Returns:
        List of output file paths created
    """
    if not docs:
        logger.warning("No exhibit documents to write for %s", symbol)
        return []

    output_files: list[Path] = []

    # Write into a run-scoped directory and postfix filenames with run_id
    symbol_out_path = config.get_symbol_output_dir(symbol)
    symbol_out_path.mkdir(parents=True, exist_ok=True)
    base_name = build_run_file_stem(symbol, "exhibit_index", config.run_id)

    # Build output data structure
    output_data = _build_output_data(
        symbol=symbol,
        docs=docs,
        config=config,
    )

    # Export based on format
    if config.export_format in ("yaml", "both"):
        yaml_file = symbol_out_path / f"{base_name}.yaml"
        output = _prepare_output(output_data, config.verbose_output)
        write_yaml(yaml_file, output, sort_keys=False, allow_unicode=True)
        output_files.append(yaml_file)
        logger.info("Manifest written to %s", yaml_file)

    if config.export_format in ("json",):
        json_file = symbol_out_path / f"{base_name}.json"
        output = _prepare_output(output_data, config.verbose_output)
        write_json(json_file, output)
        output_files.append(json_file)
        logger.info("Analysis written to %s", json_file)

    if config.export_format in ("csv", "both"):
        csv_file = symbol_out_path / f"{base_name}.csv"
        _write_csv(csv_file, output_data)
        output_files.append(csv_file)
        logger.info("Contracts CSV written to %s", csv_file)

    return output_files


def _as_str(value: JsonValue | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        cleaned = str(value).strip()
        return cleaned if cleaned else None
    return None


def _sort_accession_records(
    records: list[AccessionRecord],
) -> list[AccessionRecord]:
    def _sort_key(record: AccessionRecord) -> tuple[str, str]:
        date_key = record.get("filing_date") or ""
        accession_key = record.get("accession_number") or ""
        return (date_key, accession_key)

    return sorted(records, key=_sort_key, reverse=True)


def _build_accession_records(
    docs: list[Document],
) -> list[AccessionRecord]:
    accessions: dict[str, AccessionAccumulator] = {}
    for doc in docs:
        meta = doc.metadata or {}
        accession = _as_str(meta.get("accession_number")) or "unknown"
        entry = accessions.get(accession)
        if entry is None:
            entry = AccessionAccumulator(
                accession_number=accession,
                form_type=_as_str(meta.get("form_type")),
                filing_date=_as_str(meta.get("filing_date")),
            )
            accessions[accession] = entry

        entry.chunk_count += 1

        exhibit_number = _as_str(meta.get("exhibit_number"))
        if exhibit_number:
            entry.exhibit_numbers.add(exhibit_number)

        exhibit_category = _as_str(meta.get("exhibit_category"))
        if exhibit_category:
            entry.exhibit_categories.add(exhibit_category)

        filename = _as_str(meta.get("filename")) or _as_str(
            meta.get("source_file")
        )
        if filename:
            entry.filenames.add(filename)

        source = _as_str(meta.get("source"))
        if source:
            entry.sources.add(source)

        description = _as_str(meta.get("description"))
        if description:
            entry.descriptions.add(description)

        for hit in _as_str_list(meta.get("keyword_hits")):
            entry.keyword_hits.add(hit)

    records: list[AccessionRecord] = []
    for entry in accessions.values():
        record: AccessionRecord = {
            "accession_number": entry.accession_number,
            "form_type": entry.form_type,
            "filing_date": entry.filing_date,
            "chunk_count": entry.chunk_count,
            "exhibit_numbers": sorted(entry.exhibit_numbers),
            "exhibit_categories": sorted(
                entry.exhibit_categories, key=lambda value: str(value)
            ),
            "filenames": sorted(entry.filenames),
            "sources": sorted(entry.sources),
            "descriptions": sorted(entry.descriptions),
            "keyword_hits": sorted(entry.keyword_hits),
        }
        records.append(record)

    return _sort_accession_records(records)


def _collect_accession_numbers(
    records: list[AccessionRecord],
) -> list[str]:
    accessions: list[str] = []
    for record in records:
        accession = record.get("accession_number")
        if accession and accession != "unknown":
            accessions.append(accession)
    return accessions


def _accession_record_payload(record: AccessionRecord) -> JsonDict:
    return {
        "accession_number": record["accession_number"],
        "form_type": record["form_type"],
        "filing_date": record["filing_date"],
        "chunk_count": record["chunk_count"],
        "exhibit_numbers": record["exhibit_numbers"],
        "exhibit_categories": record["exhibit_categories"],
        "filenames": record["filenames"],
        "sources": record["sources"],
        "descriptions": record["descriptions"],
        "keyword_hits": record["keyword_hits"],
    }


def _build_output_data(
    *,
    symbol: str,
    docs: list[Document],
    config: ExhibitConfig,
) -> JsonObject:
    """Build structured output data from indexed chunks."""
    docs_with_hits = [
        doc for doc in docs if (doc.metadata or {}).get("keyword_hits")
    ]
    hit_accessions: set[str] = set()
    for doc in docs_with_hits:
        accession = _as_str((doc.metadata or {}).get("accession_number"))
        if accession and accession != "unknown":
            hit_accessions.add(accession)

    accession_records_all = _build_accession_records(docs)
    accession_records_hits = [
        record
        for record in accession_records_all
        if record.get("accession_number") in hit_accessions
    ]
    accession_payloads = [
        _accession_record_payload(record) for record in accession_records_hits
    ]
    accessions_indexed = _collect_accession_numbers(accession_records_all)
    accessions_with_hits = _collect_accession_numbers(accession_records_hits)
    return {
        "symbol": symbol,
        "analysis_enabled": False,
        "summary": {
            "chunks_indexed": len(docs),
            "chunks_with_search_term_hits": len(docs_with_hits),
            "accessions_indexed": accessions_indexed,
            "accessions_with_search_term_hits": accessions_with_hits,
            "exhibit_categories": config.get_exhibit_categories(),
            "contract_categories": config.contract_categories,
        },
        "accessions": accession_payloads,
    }


def _prepare_output(data: JsonObject, verbose: bool) -> JsonObject:
    """Prepare output data by filtering verbose-only fields."""
    output: JsonDict = {
        k: v for k, v in data.items() if not k.startswith("_") or verbose
    }
    if verbose and "_all_analyses" in data:
        output["all_analyses"] = data["_all_analyses"]
    return output


def _as_str_list(value: JsonValue | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, Sequence) and not isinstance(value, str):
        items: list[str] = []
        for item in value:
            if isinstance(item, (str, int, float)):
                items.append(str(item))
        return items
    return []


# CSV fieldnames constant to avoid duplication
_CSV_FIELDNAMES: list[str] = [
    "accession",
    "contract_type",
    "category",
    "relevance_score",
    "parties",
    "suppliers",
    "has_exclusivity",
    "has_aftermarket",
    "has_at_cost_pricing",
    "summary",
]


def _write_csv(path: Path, data: JsonObject) -> None:
    """Write contracts as CSV table."""
    contracts_value = data.get("contracts")
    contracts: list[Mapping[str, JsonValue]] = []
    if isinstance(contracts_value, Sequence) and not isinstance(
        contracts_value, str
    ):
        for contract in contracts_value:
            if isinstance(contract, Mapping):
                contract_obj: dict[str, JsonValue] = {}
                for key, value in contract.items():
                    if not isinstance(key, str):
                        continue
                    if (
                        isinstance(value, (str, int, float, bool))
                        or value is None
                    ):
                        contract_obj[key] = value
                        continue
                    if isinstance(value, Sequence) and not isinstance(
                        value, str
                    ):
                        items: list[JsonValue] = []
                        ok = True
                        for item in value:
                            if (
                                isinstance(item, (str, int, float, bool))
                                or item is None
                            ):
                                items.append(item)
                            else:
                                ok = False
                                break
                        if ok:
                            contract_obj[key] = items
                contracts.append(contract_obj)

    with open(path, "w", newline="", encoding="utf-8") as f:
        dict_writer = csv.DictWriter(
            f, fieldnames=_CSV_FIELDNAMES, extrasaction="ignore"
        )
        dict_writer.writeheader()

        for contract in contracts:
            contract_obj = {str(k): v for k, v in contract.items()}
            row = {
                **contract_obj,
                "parties": "; ".join(_as_str_list(contract_obj.get("parties"))),
                "suppliers": "; ".join(
                    _as_str_list(contract_obj.get("suppliers"))
                ),
            }
            dict_writer.writerow(row)


def write_indexing_manifest(
    *,
    symbol: str,
    docs: list[Document],
    config: ExhibitConfig,
) -> Path | None:
    """Write a simple manifest for indexing-only runs (no analysis)."""
    if not docs:
        return None

    symbol_out_path = config.get_symbol_output_dir(symbol)
    symbol_out_path.mkdir(parents=True, exist_ok=True)
    out_file = (
        symbol_out_path
        / f"{build_run_file_stem(symbol, 'exhibit_index', config.run_id)}.yaml"
    )

    manifest = _build_output_data(
        symbol=symbol,
        docs=docs,
        config=config,
    )

    write_yaml(out_file, manifest, sort_keys=False)

    logger.info(
        "Indexing manifest written to %s (chunks=%d)",
        out_file,
        len(docs),
    )
    return out_file
