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
) -> AnalyzerRunnable:
    return AnalyzerRunnable(
        graph=graph,
        callbacks=callbacks,
        analysis_instructions=analysis_instructions,
        symbols=config.symbols,
        llm_retry_attempts=config.llm_retry_attempts,
        llm_retry_backoff=config.llm_retry_backoff,
        confidence_mode=config.confidence_mode,
        include_raw_chunks=config.include_raw_chunks,
        batch_size=config.batch_size,
        query_term_min_len=config.search.query_term_min_len,
        run_id=config.run_id,
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
        search_analyze=config.search.analyze,
        export_results_enabled=config.search.export_results,
        distance_metric=config.vdb.qdrant_distance,
        search_type=config.vdb.search_type,
        output_root=config.out_path,
        pipeline_type=config.pipeline_type,
        run_dir=config.run_path_component(),
    )
