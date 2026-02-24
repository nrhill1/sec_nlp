# src/sec_nlp/pipelines/presets/exb/bridge.py
"""Bridge helpers for converting EXB outputs into flow contract evidence."""

from langchain_core.documents import Document

from sec_nlp.app.flows.contracts import (
    ContractEvidenceBundle,
    ContractEvidenceChunk,
)
from sec_nlp.types import JsonValue


def _coerce_str(value: JsonValue) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _coerce_score(value: JsonValue) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _snippet(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max(0, max_chars - 3)].rstrip()}..."


def build_contract_evidence_bundle(
    *,
    symbol: str,
    docs: list[Document],
    run_id: str,
    run_short_id: int | None,
    queries: list[str] | None = None,
    max_chunks: int = 200,
    snippet_chars: int = 500,
) -> ContractEvidenceBundle:
    """Convert EXB documents into a typed flow contract evidence bundle."""
    chunks: list[ContractEvidenceChunk] = []
    for doc in docs:
        if len(chunks) >= max_chunks:
            break
        snippet = _snippet(doc.page_content, snippet_chars)
        if not snippet:
            continue
        metadata = doc.metadata or {}
        chunks.append(
            ContractEvidenceChunk(
                symbol=_coerce_str(metadata.get("ticker")) or symbol,
                accession_number=_coerce_str(metadata.get("accession_number")),
                form_type=_coerce_str(metadata.get("form_type")),
                filed_date=_coerce_str(metadata.get("filing_date")),
                exhibit_number=_coerce_str(metadata.get("exhibit_number")),
                exhibit_category=_coerce_str(metadata.get("exhibit_category")),
                section_number=_coerce_str(metadata.get("section_number")),
                source=_coerce_str(metadata.get("source_file"))
                or _coerce_str(metadata.get("source")),
                score=_coerce_score(metadata.get("keyword_score")),
                snippet=snippet,
            )
        )
    return ContractEvidenceBundle(
        upstream_pipeline="exhibit",
        upstream_run_id=run_id,
        upstream_short_id=run_short_id,
        symbols=[symbol],
        queries=list(queries or []),
        chunks=chunks,
    )
