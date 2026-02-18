# src/sec_nlp/pipelines/presets/analyze/builders.py
"""Factory helpers for analyze pipeline components."""

from __future__ import annotations

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.runnables import Runnable
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore

from sec_nlp import __version__ as sec_nlp_version
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.pipelines.presets.analyze.config import AnalyzeConfig
from sec_nlp.pipelines.presets.analyze.io.outputs import OutputFormatter
from sec_nlp.pipelines.presets.analyze.models import (
    AnalysisInput,
    AnalysisResult,
)
from sec_nlp.pipelines.presets.analyze.runnables.analysis import (
    AnalyzerRunnable,
)
from sec_nlp.pipelines.presets.analyze.runnables.search import SearchRunnable
from sec_nlp.pipelines.presets.analyze.steps.preprocess.preprocess import (
    ChunkPreprocessor,
)
from sec_nlp.pipelines.presets.analyze.steps.preprocess.topic_scoring import (
    build_topic_matcher,
)


def build_output_formatter(
    *,
    config: AnalyzeConfig,
    topics: list[str] | None = None,
) -> OutputFormatter:
    keyword_terms = topics or config.topics or config.keywords
    return OutputFormatter(
        export_format=config.export_format,
        confidence_threshold=config.confidence_threshold,
        topics=keyword_terms,
        include_raw_chunks=config.include_raw_chunks,
        run_id=config.run_id,
        model_name=config.llm.model_name,
        confidence_mode=config.confidence_mode,
        prompt_path=config.llm.prompt_path,
        pipeline_version=sec_nlp_version,
    )


def build_preprocessor(
    *,
    config: AnalyzeConfig,
    section_extractor: SectionExtractor | None,
    topics: list[str] | None,
    embedder: OllamaEmbeddings | None,
) -> ChunkPreprocessor:
    keyword_terms = topics or config.topics or config.keywords
    topic_matcher = build_topic_matcher(keyword_terms)
    return ChunkPreprocessor(
        config=config,
        section_extractor=section_extractor,
        topics=keyword_terms,
        topic_matcher=topic_matcher,
        min_topic_hits=config.min_topic_hits,
        prioritize_topics=config.prioritize_topics,
        embedder=embedder,
    )


def build_analysis_runner(
    *,
    config: AnalyzeConfig,
    graph: Runnable[AnalysisInput, AnalysisResult],
    callbacks: list[BaseCallbackHandler],
    analysis_instructions: str,
    ensemble_graphs: list[Runnable[AnalysisInput, AnalysisResult]]
    | None = None,
    ensemble_model_names: list[str] | None = None,
) -> AnalyzerRunnable:
    prompt_ref = (
        str(config.llm.prompt_file)
        if config.llm.prompt_file is not None
        else ""
    )
    cache_namespace = (
        f"{config.llm.model_name}|"
        f"{config.llm.temperature}|"
        f"{config.llm.require_json}|"
        f"{prompt_ref}"
    )
    return AnalyzerRunnable(
        graph=graph,
        callbacks=callbacks,
        analysis_instructions=analysis_instructions,
        symbols=config.symbols,
        llm_retry_attempts=config.llm_retry_attempts,
        llm_retry_backoff=config.llm_retry_backoff,
        confidence_mode=config.confidence_mode,
        analysis_fields=config.analysis_fields,
        compact_result_output=config.compact_result_output,
        include_raw_chunks=config.include_raw_chunks,
        batch_size=config.batch_size,
        query_term_min_len=config.search.query_term_min_len,
        run_id=config.run_id,
        llm_cache_enabled=config.llm_response_cache,
        llm_cache_file=(
            config.llm_response_cache_path()
            if config.llm_response_cache
            else None
        ),
        llm_cache_max_entries=config.llm_response_cache_max_entries,
        llm_cache_namespace=cache_namespace,
        ensemble_graphs=ensemble_graphs or [],
        ensemble_model_names=ensemble_model_names or [],
    )


def build_search_runner(
    *,
    config: AnalyzeConfig,
    vector_store: QdrantVectorStore | None,
) -> SearchRunnable:
    return SearchRunnable(
        vector_store=vector_store,
        symbols=config.symbols,
        vector_mode=config.vector_mode,
        search_limit=config.search.limit,
        score_threshold=config.search.score_threshold,
        metadata_filters=config.search.metadata_filters,
        query_term_min_hits=config.search.query_term_min_hits,
        query_term_min_ratio=config.search.query_term_min_ratio,
        query_term_min_len=config.search.query_term_min_len,
        search_analyze_limit=config.search.analyze_limit,
        search_analyze=config.search.analyze,
        export_results_enabled=config.search.export_results,
        distance_metric=config.vdb.qdrant_distance,
        search_type=config.vdb.search_type,
        output_root=config.out_path,
        pipeline_type=config.pipeline_type,
        run_dir=config.run_path_component(),
    )
