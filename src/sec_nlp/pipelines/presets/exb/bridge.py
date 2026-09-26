# src/sec_nlp/pipelines/presets/exb/bridge.py
"""Bridge helpers for converting EXB outputs into flow contract evidence."""

from dataclasses import dataclass

from sec_nlp.app.workspace.evidence import (
    ContractEvidenceBundle,
    ContractEvidenceChunk,
    FlowRetrievedChunk,
)
from sec_nlp.core.documents import DocumentRecord as Document
from sec_nlp.types import JsonValue


def _coerce_str(value: JsonValue) -> str | None:
    """Coerce scalar values to strings when possible."""
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _coerce_score(value: JsonValue) -> float:
    """Coerce score-like values to bounded floats."""
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
    """Build bounded snippet text for EXB flow handoff chunks."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[: max(0, max_chars - 3)].rstrip()}..."


@dataclass(slots=True, frozen=True)
class _ContractChunkValues:
    """Normalized chunk fields shared by EXB flow handoff outputs."""

    symbol: str
    accession_number: str | None
    form_type: str | None
    filed_date: str | None
    exhibit_number: str | None
    exhibit_category: str | None
    section_number: str | None
    source: str | None
    score: float
    snippet: str


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
    chunks = [
        ContractEvidenceChunk(
            symbol=chunk.symbol,
            accession_number=chunk.accession_number,
            form_type=chunk.form_type,
            filed_date=chunk.filed_date,
            exhibit_number=chunk.exhibit_number,
            exhibit_category=chunk.exhibit_category,
            section_number=chunk.section_number,
            source=chunk.source,
            score=chunk.score,
            snippet=chunk.snippet,
        )
        for chunk in _contract_chunk_values(
            symbol=symbol,
            docs=docs,
            max_chunks=max_chunks,
            snippet_chars=snippet_chars,
        )
    ]
    return ContractEvidenceBundle(
        upstream_pipeline="exhibit",
        upstream_run_id=run_id,
        upstream_short_id=run_short_id,
        symbols=[symbol],
        queries=list(queries or []),
        chunks=chunks,
    )


def build_contract_seed_chunks(
    *,
    symbol: str,
    docs: list[Document],
    max_chunks: int = 200,
    snippet_chars: int = 500,
) -> tuple[FlowRetrievedChunk, ...]:
    """Convert EXB documents into prebuilt chat chunks for flow handoff."""
    return tuple(
        FlowRetrievedChunk(
            collection="exhibit",
            score=chunk.score,
            symbol=chunk.symbol,
            accession_number=chunk.accession_number,
            form_type=chunk.form_type,
            filed_date=chunk.filed_date,
            source=chunk.source,
            snippet=chunk.snippet,
            vector=None,
        )
        for chunk in _contract_chunk_values(
            symbol=symbol,
            docs=docs,
            max_chunks=max_chunks,
            snippet_chars=snippet_chars,
        )
    )


def _contract_chunk_values(
    *,
    symbol: str,
    docs: list[Document],
    max_chunks: int,
    snippet_chars: int,
) -> list[_ContractChunkValues]:
    """Return normalized EXB chunk values reused by flow handoff builders."""
    chunks: list[_ContractChunkValues] = []
    for doc in docs:
        if len(chunks) >= max_chunks:
            break
        snippet = _snippet(doc.page_content, snippet_chars)
        if not snippet:
            continue
        metadata = doc.metadata or {}
        chunks.append(
            _ContractChunkValues(
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
    return chunks
