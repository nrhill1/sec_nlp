# tests/benchmarks/test_runtime_offline_perf.py
"""Offline benchmarks for consolidated runtime metadata and state helpers.

These cases exercise the shared runtime helpers now imported by analyze and
EXB. The inputs stay fully local by using synthetic ``Document`` payloads and
``tmp_path``-backed state files instead of SEC downloads, Qdrant, or LLM
dependencies.
"""

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from langchain_core.documents import Document

from sec_nlp.pipelines.runtime import (
    ProcessingState,
    build_metadata_filter,
    get_state_dir,
    group_results_by_accession,
    load_state,
    normalize_metadata_for_output,
    prepare_vector_docs,
)
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord
from tests.utils.performance import measure_duration
from tests.utils.typing import Benchmark, MemoryTracker


def _make_accession(index: int) -> str:
    """Build one deterministic synthetic accession number."""
    issuer_id = 1_000_000_000 + index
    filing_year = 20 + (index % 10)
    filing_sequence = index % 1_000_000
    return f"{issuer_id:010d}-{filing_year:02d}-{filing_sequence:06d}"


def _build_filter_payload() -> dict[
    str, str | int | bool | list[str] | list[int] | list[bool]
]:
    """Build a mixed metadata-filter payload for Qdrant filter benchmarks."""
    return {
        "symbol": ["AAPL", "MSFT", "NVDA", "AMD"],
        "form_type": ["10-K", "10-Q"],
        "filing_year": [2022, 2023, 2024],
        "chunk_index": [0, 1, 2, 3],
        "section_number": "1A",
        "is_chunked": True,
        "accession_number": [_make_accession(index) for index in range(6)],
    }


def _build_analysis_results(
    *,
    accession_count: int,
    results_per_accession: int,
) -> list[AnalysisResultDict]:
    """Build synthetic analysis results that mimic analyze output grouping."""
    results: list[AnalysisResultDict] = []

    for accession_index in range(accession_count):
        accession = _make_accession(accession_index)
        for chunk_index in range(results_per_accession):
            source_metadata: MetadataRecord = {
                "symbol": "AAPL",
                "accession_number": accession,
                "form_type": "10-K",
                "filing_date": "2025-02-14",
                "chunk_index": chunk_index,
            }
            result: AnalysisResultDict = {
                "rank": chunk_index + 1,
                "is_relevant": (chunk_index % 4) != 0,
                "confidence_score": 0.95 - ((chunk_index % 5) * 0.05),
                "summary": (
                    f"Accession {accession} summary for chunk {chunk_index}"
                ),
                "query_match_terms": ["liquidity", "risk"],
                "source_metadata": source_metadata,
            }
            results.append(result)

    return results


def _build_output_metadata() -> MetadataRecord:
    """Build nested metadata for output-normalization benchmarks."""
    return {
        "symbol": "AAPL",
        "accession_number": _make_accession(7),
        "form_type": "10-K",
        "filing_year": 2025,
        "confidence_score": 0.912345,
        "relevance_score": 0.66789,
        "topic_hits": ["risk factors", "liquidity"],
        "matched_queries": [
            {"query": "risk", "score": 0.91},
            {"query": "liquidity", "score": 0.88},
        ],
        "source_metadata": {
            "source": "synthetic-filings/AAPL/10-K/primary.html",
            "chunk_index": 4,
        },
        "xbrl_values_seen": {
            "revenue": [{"period": "2025", "value": 123.4}],
            "warranty": [{"period": "2025", "value": 45.0}],
        },
        "raw_chunk": "This raw chunk should be omitted from serialized output.",
        "page_content": "This page content should also be omitted.",
    }


def _build_documents(doc_count: int) -> list[Document]:
    """Build deterministic documents for vector-metadata preparation."""
    docs: list[Document] = []
    for index in range(doc_count):
        docs.append(
            Document(
                page_content=(
                    "Synthetic chunk body for offline runtime benchmarks "
                    f"{index}"
                ),
                metadata={
                    "accession_number": _make_accession(index % 64),
                    "form_type": "10-K",
                    "chunk_index": index,
                },
            )
        )
    return docs


def _build_accessions(count: int) -> list[str]:
    """Build a deterministic accession batch for state persistence tests."""
    return [_make_accession(index) for index in range(count)]


def _persist_state_snapshot(
    out_path: Path,
    accessions: list[str],
    *,
    run_id: UUID,
) -> int:
    """Write one synthetic processing-state snapshot and return its size."""
    state_dir = get_state_dir(out_path)
    state = ProcessingState(
        state_dir=state_dir,
        pipeline_type="analyze",
        auto_save=False,
    )
    if state.state_file.exists():
        state.state_file.unlink()

    chunk_counts = {
        accession: (index % 7) + 1 for index, accession in enumerate(accessions)
    }
    state.mark_processed_batch(
        "AAPL",
        accessions,
        run_id=run_id,
        chunk_counts=chunk_counts,
    )
    state.save()
    return len(state.data.get_processed_accession_numbers("AAPL"))


def _load_state_snapshot(out_path: Path) -> int:
    """Load one synthetic processing-state snapshot and return its size."""
    state = load_state(out_path, "analyze")
    return len(state.data.get_processed_accession_numbers("AAPL"))


@pytest.mark.benchmark
def test_build_metadata_filter_offline_benchmark(
    benchmark: Benchmark,
) -> None:
    """Benchmark mixed metadata-filter construction without vector services."""
    raw_filters = _build_filter_payload()

    qdrant_filter = benchmark(build_metadata_filter, raw_filters)

    assert qdrant_filter is not None
    must_raw = qdrant_filter.must
    if must_raw is None:
        must_conditions: list[object] = []
    elif isinstance(must_raw, list):
        must_conditions = must_raw
    else:
        must_conditions = [must_raw]
    assert len(must_conditions) == len(raw_filters)


@pytest.mark.benchmark
def test_group_results_by_accession_offline_benchmark(
    benchmark: Benchmark,
) -> None:
    """Benchmark accession grouping for synthetic analyze outputs."""
    results = _build_analysis_results(
        accession_count=80,
        results_per_accession=24,
    )
    fallback_meta: MetadataRecord = {
        "symbol": "AAPL",
        "accession_number": _make_accession(999),
    }

    grouped = benchmark(group_results_by_accession, results, fallback_meta)

    assert len(grouped) == 80
    assert sum(len(group) for group in grouped.values()) == len(results)


@pytest.mark.benchmark
def test_normalize_metadata_for_output_offline_benchmark(
    benchmark: Benchmark,
) -> None:
    """Benchmark nested metadata normalization for export paths."""
    metadata = _build_output_metadata()

    normalized = benchmark(normalize_metadata_for_output, metadata)

    assert "raw_chunk" not in normalized
    assert "page_content" not in normalized
    assert normalized.get("symbol") == "AAPL"


@pytest.mark.benchmark
def test_prepare_vector_docs_offline_benchmark(
    benchmark: Benchmark,
) -> None:
    """Benchmark vector metadata shaping for EXB chunk uploads."""
    docs = _build_documents(2_048)

    vector_docs = benchmark(prepare_vector_docs, docs, symbol="AAPL")

    assert len(vector_docs) == len(docs)
    assert vector_docs[0].metadata.get("symbol") == "AAPL"
    assert vector_docs[0].metadata.get("text") == vector_docs[0].page_content


@pytest.mark.benchmark
def test_processing_state_load_offline_benchmark(
    tmp_path: Path,
    benchmark: Benchmark,
) -> None:
    """Benchmark loading a persisted processing-state snapshot from disk."""
    accessions = _build_accessions(750)
    stored = _persist_state_snapshot(tmp_path, accessions, run_id=uuid4())
    assert stored == len(accessions)

    loaded = benchmark(_load_state_snapshot, tmp_path)

    assert loaded == len(accessions)


def test_processing_state_roundtrip_offline_memory(
    tmp_path: Path,
    track_memory: MemoryTracker,
) -> None:
    """Track memory for one offline processing-state write/load roundtrip."""
    accessions = _build_accessions(750)

    with track_memory() as metrics:
        stored = _persist_state_snapshot(tmp_path, accessions, run_id=uuid4())
        loaded, elapsed = measure_duration(_load_state_snapshot, tmp_path)

    assert stored == len(accessions)
    assert loaded == len(accessions)
    assert elapsed >= 0.0
    assert metrics["peak"] >= 0
