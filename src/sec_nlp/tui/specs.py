"""Pipeline specs and segment patterns for the TUI."""

from __future__ import annotations

from dataclasses import dataclass

from sec_nlp.types import ConfigScalar

type PatternList = tuple[ConfigScalar, ...]


@dataclass(frozen=True)
class SegmentSpec:
    key: ConfigScalar
    label: ConfigScalar
    patterns: PatternList


@dataclass(frozen=True)
class PipelineSpec:
    key: ConfigScalar
    label: ConfigScalar
    description: ConfigScalar
    command: ConfigScalar
    segments: tuple[SegmentSpec, ...]
    preview_fields: tuple[ConfigScalar, ...]


ANALYZE_SEGMENTS: tuple[SegmentSpec, ...] = (
    SegmentSpec(
        key="validate",
        label="Validate config",
        patterns=("Validation Report",),
    ),
    SegmentSpec(
        key="load",
        label="Load filings",
        patterns=(
            "Processing symbol",
            "Found .* filings",
            "Downloaded .* filings",
        ),
    ),
    SegmentSpec(
        key="preprocess",
        label="Preprocess chunks",
        patterns=(
            "Prepared .* chunks",
            "Topic scoring",
            "Chunking",
        ),
    ),
    SegmentSpec(
        key="index",
        label="Index vectors",
        patterns=(
            "Prepared .* for indexing",
            "Indexed .* chunks",
            "Created Qdrant collection",
        ),
    ),
    SegmentSpec(
        key="search",
        label="Vector search",
        patterns=(
            "Vector search",
            "Search '",
            "Exporting results for",
        ),
    ),
    SegmentSpec(
        key="analyze",
        label="LLM analysis",
        patterns=(
            "Analyzing .* retrieved chunks",
            "Ready to analyze",
            "LLM start",
        ),
    ),
    SegmentSpec(
        key="export",
        label="Write outputs",
        patterns=(
            "Analysis summary written",
            "Exported consolidated search results",
            "Analysis complete",
        ),
    ),
)

EXB_SEGMENTS: tuple[SegmentSpec, ...] = (
    SegmentSpec(
        key="validate",
        label="Validate config",
        patterns=("Validation Report",),
    ),
    SegmentSpec(
        key="load",
        label="Load filings",
        patterns=("Processing symbol", "Found .* filings"),
    ),
    SegmentSpec(
        key="extract",
        label="Extract exhibits",
        patterns=("Extracted", "Exhibit", "Contract"),
    ),
    SegmentSpec(
        key="index",
        label="Index vectors",
        patterns=(
            "Prepared .* for indexing",
            "Embedding dimension",
            "Indexed .* chunks",
        ),
    ),
    SegmentSpec(
        key="search",
        label="Search exhibits",
        patterns=("Search output directory", "Found .* results"),
    ),
    SegmentSpec(
        key="export",
        label="Write outputs",
        patterns=(
            "Manifest written",
            "Exhibit summary written",
            "Contracts CSV written",
        ),
    ),
)

WARRANTY_SEGMENTS: tuple[SegmentSpec, ...] = (
    SegmentSpec(
        key="validate",
        label="Validate config",
        patterns=("Validation Report",),
    ),
    SegmentSpec(
        key="load",
        label="Load filings",
        patterns=("Downloaded .* filings", "Found .* filings"),
    ),
    SegmentSpec(
        key="extract",
        label="Extract warranty data",
        patterns=("XBRL", "Warranty"),
    ),
    SegmentSpec(
        key="summarize",
        label="Summarize results",
        patterns=("Aggregated", "Summarized"),
    ),
    SegmentSpec(
        key="export",
        label="Write outputs",
        patterns=("Warranty JSON written", "CSV written"),
    ),
)


PIPELINE_SPECS: tuple[PipelineSpec, ...] = (
    PipelineSpec(
        key="analyze",
        label="Analyze",
        description="LLM-assisted analysis with vector search and market context.",
        command="analyze",
        segments=ANALYZE_SEGMENTS,
        preview_fields=(
            "symbols",
            "preset",
            "mode",
            "limit",
            "topics",
            "keywords",
            "vector_mode",
            "batch_size",
            "top_k_chunks",
            "max_chunk_length",
        ),
    ),
    PipelineSpec(
        key="exb",
        label="Exhibit",
        description="Download and extract exhibit documents by category.",
        command="exb",
        segments=EXB_SEGMENTS,
        preview_fields=(
            "symbols",
            "mode",
            "limit",
            "exhibit_categories",
            "exhibit_numbers",
            "search_only",
            "batch_size",
        ),
    ),
    PipelineSpec(
        key="warranty",
        label="Warranty",
        description="XBRL-focused warranty extraction without LLM calls.",
        command="warranty",
        segments=WARRANTY_SEGMENTS,
        preview_fields=(
            "symbols",
            "mode",
            "limit",
            "keywords",
            "xbrl_only",
            "export_format",
        ),
    ),
)


def get_pipeline_specs() -> tuple[PipelineSpec, ...]:
    return PIPELINE_SPECS


def find_pipeline_spec(key: ConfigScalar) -> PipelineSpec | None:
    for spec in PIPELINE_SPECS:
        if spec.key == key:
            return spec
    return None
