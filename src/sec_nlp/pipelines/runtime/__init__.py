# src/sec_nlp/pipelines/runtime/__init__.py
"""Shared runtime helpers for pipeline metadata handling and incremental state.

This package consolidates the previously split metadata and state helper
modules into one stable runtime namespace. Presets and shared pipeline
utilities import from here so the underlying implementation can stay smaller
and easier to evolve.
"""

from .metadata import (
    MetadataFilters,
    MetadataFilterValue,
    build_metadata_filter,
    build_rollups,
    coerce_meta_str,
    get_accession_from_metadata,
    get_meta_str,
    get_meta_str_any,
    group_results_by_accession,
    normalize_metadata_for_output,
    prepare_vector_docs,
)
from .state import (
    STATE_DIR_NAME,
    ProcessedAccession,
    ProcessingState,
    ProcessingStateData,
    ProcessingStateMetadata,
    get_state_dir,
    load_state,
)

__all__: tuple[str, ...] = (
    "MetadataFilters",
    "MetadataFilterValue",
    "ProcessedAccession",
    "ProcessingState",
    "ProcessingStateData",
    "ProcessingStateMetadata",
    "STATE_DIR_NAME",
    "build_metadata_filter",
    "build_rollups",
    "coerce_meta_str",
    "get_accession_from_metadata",
    "get_meta_str",
    "get_meta_str_any",
    "get_state_dir",
    "group_results_by_accession",
    "load_state",
    "normalize_metadata_for_output",
    "prepare_vector_docs",
)
