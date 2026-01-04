"""Shared metadata helpers for accession identification."""

from __future__ import annotations

import re
from collections import defaultdict

from sec_nlp.pipelines.types import AnalysisResultDict, MetadataMap


def get_accession_from_metadata(metadata: MetadataMap | None) -> str:
    """Extract accession number or fallback identifier from metadata."""
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
    """Group results by accession, falling back to provided metadata."""
    grouped: dict[str, list[AnalysisResultDict]] = defaultdict(list)
    fallback_accession = get_accession_from_metadata(fallback_meta)

    for result in results:
        metadata = result.get("source_metadata") or {}
        accession = get_accession_from_metadata(metadata)
        if accession == "unknown":
            accession = fallback_accession
        grouped[accession].append(result)

    return grouped
