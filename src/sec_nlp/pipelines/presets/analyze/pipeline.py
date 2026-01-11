# src/sec_nlp/pipelines/presets/analyze/pipeline.py
"""Generalized semantic search and confidence analysis pipeline for SEC filings."""

from collections import defaultdict
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from typing import ClassVar, Literal

from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.documents import Document
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.runnables import Runnable
from langchain_ollama.embeddings import OllamaEmbeddings
from langchain_qdrant import QdrantVectorStore
from pydantic import PrivateAttr
from qdrant_client.models import Distance, VectorParams
from tqdm import tqdm

from sec_nlp import __version__ as sec_nlp_version
from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.core.llm.chains import InputModelKeys, build_runnable
from sec_nlp.core.text.deduplication import SimHashConfig, SimHashDeduplicator
from sec_nlp.core.text.filters import SectionFilter
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.metadata.accession import get_accession_from_metadata
from sec_nlp.pipelines.observability.telemetry import log_chunk_length_stats
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord
from sec_nlp.prompts import load_prompt_template
from sec_nlp.types import ResultDict

from .config import AnalyzeConfig
from .io.outputs import OutputFormatter
from .io.result_writer import write_results
from .market import MarketEnrichment, build_market_enrichment
from .models import AnalysisInput, AnalysisResult, AnalyzeResult
from .steps.analysis.analysis_runner import AnalyzerRunnable
from .steps.analysis.callbacks import TracingCallbackHandler
from .steps.analysis.instructions import AnalysisInstructionBuilder
from .steps.indexing.vector_index import VectorIndexer
from .steps.preprocess.preprocess import ChunkPreprocessor
from .steps.preprocess.topic_scoring import build_topic_matcher
from .steps.search.vector_search import SearchResultsByQuery, SearchRunnable
from .types import ChunkStats, SymbolRunMetadata, Timings

type PromptInput = dict[
    str,
    InputModelKeys | list[InputModelKeys] | dict[str, InputModelKeys],
]


class AnalyzePipeline(BasePipeline):
    """Generalized pipeline for semantic search and confidence analysis."""

    # Class attributes
    pipeline_type: ClassVar[Literal["analyze"]] = "analyze"
    description: ClassVar[str] = (
        "Generalized semantic search and confidence analysis for SEC filings"
    )

    requires_llm: ClassVar[bool] = True
    requires_vector_db: ClassVar[bool] = True

    config: AnalyzeConfig

    # LLM & Runnable
    _prompt: BasePromptTemplate[PromptInput] = PrivateAttr()
    _llm: BaseLanguageModel[str] = PrivateAttr()
    _graph: Runnable[AnalysisInput, AnalysisResult] = PrivateAttr()
    _callbacks: list[BaseCallbackHandler] = PrivateAttr(default_factory=list)

    # Filings
    _loader: Loader = PrivateAttr()

    # Section filter
    _section_filter: SectionFilter | None = PrivateAttr(default=None)
    _section_extractor: SectionExtractor | None = PrivateAttr(default=None)

    # Vector Store
    _vector_store: QdrantVectorStore = PrivateAttr()
    _embedder: OllamaEmbeddings = PrivateAttr()

    # Deduplication
    _deduplicator: SimHashDeduplicator = PrivateAttr()

    # Output formatting
    _output_formatter: OutputFormatter = PrivateAttr()
    _analysis_instructions: str = PrivateAttr(default="")

    # Modular helpers
    _preprocessor: ChunkPreprocessor = PrivateAttr()
    _vector_indexer: VectorIndexer = PrivateAttr()
    _analysis_runner: AnalyzerRunnable = PrivateAttr()
    _search_runner: SearchRunnable = PrivateAttr()
    _search_results_by_query: SearchResultsByQuery | None = PrivateAttr(
        default=None
    )

    @classmethod
    def config_model(cls) -> type[AnalyzeConfig]:
        return AnalyzeConfig

    @classmethod
    def result_model(cls) -> type[AnalyzeResult]:
        return AnalyzeResult

    def _build_components(self) -> None:
        """Build pipeline components from config."""
        keyword_terms = self.config.topics or self.config.keywords

        try:
            # Initialize loader
            self._loader = Loader(
                email=self.config.email,
                downloads_folder=self.config.dl_path,
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
                keywords=keyword_terms if keyword_terms else None,
                keyword_mode=self.config.keyword_mode,
                use_async=self.config.loader_use_async,
                max_workers=self.config.loader_max_workers,
            )

            # Build section filter if section filtering is configured
            if self.config.section_type and self.config.section_numbers:
                section_pattern = self.config.get_section_pattern()
                if section_pattern is not None:
                    self._section_filter = SectionFilter(
                        patterns=[section_pattern],
                        search_window=self.config.search_window,
                        filter_indices=self.config.filter_indices,
                    )
                    self._section_extractor = SectionExtractor(
                        section_filter=self._section_filter,
                        max_section_length=self.config.max_chunk_length
                        or 500000,
                        detect_boundaries=True,
                    )
                    logger.info(
                        "Created section filter: type=%s, numbers=%s",
                        self.config.section_type,
                        self.config.section_numbers,
                    )

            # Load prompt
            prompt_path = self.config.llm.prompt_path
            self._prompt = load_prompt_template(prompt_path)
            self._analysis_instructions = AnalysisInstructionBuilder(
                analysis_fields=self.config.analysis_fields
            ).build()

        except Exception as e:
            raise ValueError(
                f"Failed to initialize components: {e}\n"
                f"Prompt path: {self.config.llm.prompt_path.resolve()}\n"
                f"Downloads: {self.config.dl_path.resolve()}\n"
            ) from e

        # Initialize LLM
        self._llm = self.config.llm.setup_ollama_model()

        # Configure tracing callbacks
        if self.config.enable_tracing:
            self._callbacks = [
                TracingCallbackHandler(
                    log_prompts=self.config.trace_log_prompts
                )
            ]
            logger.info("LangChain tracing enabled")
        else:
            self._callbacks = []

        # Initialize vector store
        has_search_queries = bool(self.config.get_search_queries())
        if has_search_queries and self.config.vector_mode == "off":
            logger.warning(
                "search queries configured -- vector_mode should be 'read' or 'write'"
            )

        should_init_vector = (
            has_search_queries or self.config.vector_mode != "off"
        )

        if should_init_vector:
            try:
                qdrant_client = self.config.vdb.setup_qdrant_client()
                embedder = self.config.vdb.setup_embedding_model()
                self._embedder = embedder

                test_embedding = embedder.embed_query("test")
                embedding_dim = len(test_embedding)
                target_dim = self.config.vdb.vector_size or embedding_dim
                if embedding_dim != target_dim:
                    logger.warning(
                        "Embedding dimension %d does not match configured vector_size %d; "
                        "using embedding dimension for collection.",
                        embedding_dim,
                        target_dim,
                    )
                    target_dim = embedding_dim

                collection_name = self.config.vdb.collection_name or "analyze"

                # Delete collection if fresh to avoid corrupted state
                self.config.vdb.recreate_collection_if_fresh(
                    qdrant_client,
                    collection_name,
                    self.config.fresh,
                )

                # Ensure collection exists
                needs_recreate = False
                if qdrant_client.collection_exists(collection_name):
                    try:
                        info = qdrant_client.get_collection(collection_name)
                        vector_params = info.config.params.vectors
                        current_dim: int | None = None
                        if isinstance(vector_params, VectorParams):
                            current_dim = vector_params.size
                        elif isinstance(vector_params, dict):
                            first_params = next(
                                iter(vector_params.values()), None
                            )
                            if isinstance(first_params, VectorParams):
                                current_dim = first_params.size
                        if current_dim and current_dim != target_dim:
                            logger.warning(
                                "Collection %s has dimension %s, expected %s. Recreating collection.",
                                collection_name,
                                current_dim,
                                target_dim,
                            )
                            qdrant_client.delete_collection(collection_name)
                            needs_recreate = True
                    except Exception:
                        needs_recreate = True
                if (
                    not qdrant_client.collection_exists(collection_name)
                    or needs_recreate
                ):
                    qdrant_client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=target_dim,
                            distance=Distance.COSINE,
                        ),
                        replication_factor=self.config.vdb.qdrant_replication_factor,
                        write_consistency_factor=self.config.vdb.qdrant_write_consistency_factor,
                        on_disk_payload=self.config.vdb.qdrant_on_disk_payload,
                    )
                    logger.info(
                        "Created Qdrant collection: %s", collection_name
                    )

                self._vector_store = self.config.vdb.create_vector_store(
                    qdrant_client=qdrant_client,
                    embedder=embedder,
                    collection_name=collection_name,
                )

                logger.info("Embedding/vector dimension: %d", target_dim)
            except Exception as e:
                raise RuntimeError(
                    f"{type(e).__name__}: Failed to initialize vector store: {e}\n"
                ) from e

        # Build LLM graph
        try:
            self._graph = build_runnable(
                prompt=self._prompt,
                llm=self._llm,
                input_model=AnalysisInput,
                output_model=AnalysisResult,
                require_json=self.config.llm.require_json,
            )
            logger.info("Built LLM processing graph")

        except Exception as e:
            raise RuntimeError(
                f"{type(e).__name__}: Failed to build LLM graph: {e}\n"
                "Check prompt format and LLM compatibility."
            ) from e

        # Initialize deduplicator with efficient SimHash indexing
        self._deduplicator = SimHashDeduplicator(
            config=SimHashConfig(
                num_bits=self.config.simhash_bits,
                max_distance=self.config.simhash_max_distance,
            )
        )

        # Initialize output formatter
        self._output_formatter = OutputFormatter(
            export_format=self.config.export_format,
            confidence_threshold=self.config.confidence_threshold,
            topics=keyword_terms,
            include_raw_chunks=self.config.include_raw_chunks,
            run_id=str(self.config.run_id),
            model_name=self.config.llm.model_name,
            confidence_mode=self.config.confidence_mode,
            prompt_path=self.config.llm.prompt_path,
            pipeline_version=sec_nlp_version,
        )

        topic_matcher = build_topic_matcher(keyword_terms)

        self._preprocessor = ChunkPreprocessor(
            config=self.config,
            section_extractor=self._section_extractor,
            topics=keyword_terms,
            topic_matcher=topic_matcher,
            min_topic_hits=self.config.min_topic_hits,
            prioritize_topics=self.config.prioritize_topics,
            embedder=self._embedder,
        )
        self._vector_indexer = VectorIndexer(
            config=self.config,
            vector_store=self._vector_store,
            deduplicator=self._deduplicator,
        )
        self._analysis_runner = AnalyzerRunnable(
            config=self.config,
            graph=self._graph,
            callbacks=self._callbacks,
            analysis_instructions=self._analysis_instructions,
        )
        self._search_runner = SearchRunnable(
            config=self.config,
            vector_store=self._vector_store,
        )

    def run(self) -> AnalyzeResult:
        """Execute the semantic search pipeline."""
        try:
            self.config.setup_paths()

            log_divider(logger, color="magenta")
            logger.info(
                "Run %s (%s)",
                self.config.short_id_display,
                self.config.run_id,
            )

            all_outputs: list[Path] = []
            metadata: ResultDict = {
                "run_id": self.config.run_id,
                "short_id": self.config.short_id,
            }

            bar_format = "\n{n_fmt}/{total_fmt} [{elapsed}<{remaining}]"

            # Process symbols sequentially with progress bar
            with tqdm(
                self.config.symbols,
                desc="Processing symbols",
                unit="symbol",
                colour="green",
                leave=True,
                disable=not self.config.verbose,
                bar_format=bar_format,
            ) as pbar:
                last_index = len(self.config.symbols) - 1
                for index, symbol in enumerate(pbar):
                    pbar.set_description(f"Processing {symbol}")
                    symbol_outputs, chunk_stats = self._process_symbol(symbol)
                    all_outputs.extend(symbol_outputs)
                    symbol_meta: SymbolRunMetadata = {
                        "outputs": len(symbol_outputs),
                        "chunk_stats": chunk_stats,
                    }
                    metadata[symbol] = symbol_meta
                    if index < last_index:
                        log_divider(logger, color="magenta")

            # Run semantic search if queries are configured
            if self.config.get_search_queries():
                if self._search_results_by_query is not None:
                    search_outputs = self._search_runner.export_results(
                        self._search_results_by_query,
                        cached=True,
                        queries=self.config.get_search_queries(),
                    )
                else:
                    search_outputs = self._search_runner.run(
                        queries=self.config.get_search_queries(),
                    )
                all_outputs.extend(search_outputs)
                metadata["search_results"] = len(search_outputs)
                metadata["search_outputs"] = search_outputs
                metadata["search_queries"] = list(
                    self.config.get_search_queries()
                )

            self.config.complete_run(success=True)
            return AnalyzeResult(
                success=True,
                outputs=all_outputs,
                metadata=metadata,
            )

        except Exception as e:
            logger.exception("Pipeline execution failed")
            self.config.complete_run(success=False)
            return AnalyzeResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
            )
        finally:
            log_divider(logger, color="green")

    def _process_symbol(self, symbol: str) -> tuple[list[Path], ChunkStats]:
        """Process a single symbol."""
        log_divider(logger, color="cyan")
        logger.info("Processing symbol: %s \n", symbol)

        self._loader.add_symbol(symbol)
        timings: Timings = {}

        start_date, end_date = self.config.date_range

        t0 = perf_counter()
        docs = self._loader.load_documents(
            mode=self.config.mode,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            limit_per_symbol=self.config.limit,
            perform_download=True,
            section_filter=self._section_filter,
        )
        timings["load"] = perf_counter() - t0

        if not docs:
            logger.warning("No documents found for %s", symbol)
            return [], {
                "count": 0.0,
                "min_value": 0.0,
                "max_value": 0.0,
                "mean": 0.0,
                "timings": timings,
            }

        t0 = perf_counter()
        docs = self._preprocessor.chunk_and_prepare(docs)
        timings["prepare"] = perf_counter() - t0

        if not docs:
            logger.warning(
                "No documents remaining after filtering for %s", symbol
            )
            return [], {
                "count": 0,
                "min_value": 0.0,
                "max_value": 0.0,
                "mean": 0.0,
                "timings": timings,
            }

        chunk_lengths = [len((doc.page_content or "").strip()) for doc in docs]
        stats: ChunkStats = {
            "count": float(len(chunk_lengths)),
            "min_value": float(min(chunk_lengths)),
            "max_value": float(max(chunk_lengths)),
            "median": float(median(chunk_lengths)),
            "mean": float(mean(chunk_lengths)),
            "timings": timings,
        }
        market_data = self._build_market_enrichment(symbol, docs)
        market_context = self._format_market_context(market_data)
        if market_context:
            for doc in docs:
                metadata = dict(doc.metadata or {})
                metadata["market_enrichment_context"] = market_context
                doc.metadata = metadata
        accession_docs: dict[str, list[Document]] = defaultdict(list)
        for doc in docs:
            accession = get_accession_from_metadata(doc.metadata)
            accession_docs[accession].append(doc)

        if len(accession_docs) == 1:
            only_accession = next(iter(accession_docs))
            log_chunk_length_stats(
                label=None,
                symbol=symbol,
                accession=only_accession,
                docs=docs,
                prefix_color="dim",
            )
        else:
            for accession in sorted(accession_docs):
                log_chunk_length_stats(
                    label=None,
                    symbol=symbol,
                    accession=accession,
                    docs=accession_docs[accession],
                    prefix_color="dim",
                )

        # Index chunks before analysis
        self._vector_indexer.index(symbol, docs, timings)

        # Retrieve relevant chunks via vector search (if enabled)
        search_queries = self.config.get_search_queries()
        if search_queries and self._vector_store:
            (
                docs_for_analysis,
                search_results,
            ) = self._search_runner.retrieve_hits_with_results(
                queries=search_queries
            )
            self._search_results_by_query = search_results
            if not docs_for_analysis:
                logger.info(
                    "No vector search hits for %s; skipping analysis step",
                    symbol,
                )
            else:
                logger.info(
                    "Analyzing %d retrieved chunks for %s (from vector search)",
                    len(docs_for_analysis),
                    symbol,
                )
        else:
            logger.info(
                "Search not configured (no queries/topics) or vector store unavailable; skipping analysis"
            )
            docs_for_analysis = []

        # Analyze chunks with LLM (only if we have search hits)
        if docs_for_analysis:
            t0 = perf_counter()
            logger.info(
                "Ready to analyze %d chunks for %s",
                len(docs_for_analysis),
                symbol,
            )
            analysis_results = self._analysis_runner.analyze_chunks(
                symbol, docs_for_analysis
            )
            timings["analyze"] = perf_counter() - t0
        else:
            analysis_results = []
            timings["analyze"] = 0.0

        # Filter relevant items once to keep storage/output in sync
        formatter = self._output_formatter
        relevant_pairs = [
            (doc, result)
            for doc, result in zip(
                docs_for_analysis, analysis_results, strict=False
            )
            if formatter.is_relevant_result(result)
        ]
        relevant_results = [r for _, r in relevant_pairs]
        error_results = [
            r for r in analysis_results if r.get("error") or r.get("exception")
        ]
        total_hits = len(analysis_results)
        relevant_hits = len(relevant_results)
        confidence_scores = [
            float(r.get("confidence_score", 0) or 0) for r in relevant_results
        ]
        avg_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else None
        )
        avg_conf_display = (
            f"{avg_confidence:.2f}" if avg_confidence is not None else "n/a"
        )
        logger.info(
            "Analysis hits for %s: %d total, %d relevant (avg confidence=%s, threshold=%.2f)",
            symbol,
            total_hits,
            relevant_hits,
            avg_conf_display,
            self.config.confidence_threshold,
        )
        if error_results:
            sample_error = error_results[0]
            logger.warning(
                "Analysis errors for %s: %d (sample=%s)",
                symbol,
                len(error_results),
                sample_error.get("error") or sample_error.get("exception"),
            )

        # Write results to output file
        t_write_start = perf_counter()
        output_files = self._write_results(
            symbol,
            docs[0].metadata or {},
            analysis_results,
            relevant_results=relevant_results,
            search_queries=search_queries,
            timings=timings,
            market_data=market_data,
            market_context=market_context,
        )
        if output_files:
            run_id = self.config.run_id
            logger.info(
                "Wrote %d analysis files for %s -> %s",
                len(output_files),
                symbol,
                (self.config.out_path / symbol / str(run_id)).resolve(),
            )
        timings["write_outputs"] = perf_counter() - t_write_start
        timings["total"] = sum(timings.values())

        return output_files, stats

    def _prepare_documents(self, docs: list[Document]) -> list[Document]:
        """Expose preprocessing for tests and standalone use."""
        preprocessor = getattr(self, "_preprocessor", None)
        if preprocessor is None:
            topics = self.config.topics or self.config.keywords
            preprocessor = ChunkPreprocessor(
                config=self.config,
                section_extractor=getattr(self, "_section_extractor", None),
                topics=topics,
                topic_matcher=build_topic_matcher(topics),
                min_topic_hits=self.config.min_topic_hits,
                prioritize_topics=self.config.prioritize_topics,
                embedder=self._embedder,
            )
        return preprocessor.prepare_documents(docs)

    def _process_batch(
        self, batch: list[AnalysisInput], docs: list[Document]
    ) -> list[AnalysisResultDict]:
        """Expose batch processing for tests and retries."""
        runner = getattr(self, "_analysis_runner", None)
        if runner is None:
            runner = AnalyzerRunnable(
                config=self.config,
                graph=self._graph,
                callbacks=self._callbacks,
                analysis_instructions=self._analysis_instructions,
            )
        return runner._process_batch(batch, docs)

    def _retrieve_search_hits(self) -> list[Document]:
        """Expose vector search retrieval for tests."""
        runner = getattr(self, "_search_runner", None)
        if runner is None:
            runner = SearchRunnable(
                config=self.config,
                vector_store=self._vector_store,
            )
        return runner.retrieve_hits(queries=self.config.get_search_queries())

    def _build_market_enrichment(
        self,
        symbol: str,
        docs: list[Document],
    ) -> MarketEnrichment | None:
        """Return market enrichment metadata for the given docs."""
        return build_market_enrichment(
            config=self.config.market,
            symbol=symbol,
            docs=docs,
            default_range=self.config.date_range,
        )

    def _format_market_context(
        self,
        enrichment: MarketEnrichment | None,
    ) -> str | None:
        """Summarize market data for inclusion in the LLM context."""
        if enrichment is None or not enrichment.quotes:
            return None

        rows: list[str] = []
        for summary in enrichment.quotes[:3]:
            rows.append(
                f"{summary.start_date.isoformat()}..{summary.end_date.isoformat()} "
                f"close={summary.average_close:.2f}"
            )
        suffix = ""
        extra = len(enrichment.quotes) - len(rows)
        if extra > 0:
            suffix = f" (+{extra} more)"

        filing_hint = (
            f"filing {enrichment.filing_date.isoformat()}"
            if enrichment.filing_date
            else "filing date unknown"
        )
        window = (
            f"{enrichment.window_start.isoformat()}.."
            f"{enrichment.window_end.isoformat()}"
        )

        return (
            f"{filing_hint} | market {enrichment.ticker} "
            f"{enrichment.granularity.value} window {window}: "
            f"{'; '.join(rows)}{suffix}"
        )

    def _write_results(
        self,
        symbol: str,
        filing_meta: MetadataRecord,
        analysis_results: list[AnalysisResultDict],
        *,
        relevant_results: list[AnalysisResultDict] | None = None,
        search_queries: list[str] | None = None,
        timings: Timings | None = None,
        market_data: MarketEnrichment | None = None,
        market_context: str | None = None,
    ) -> list[Path]:
        """Expose result writing for tests and downstream usage."""
        formatter = getattr(self, "_output_formatter", None)
        if formatter is None:
            formatter = OutputFormatter(
                export_format=self.config.export_format,
                confidence_threshold=self.config.confidence_threshold,
                topics=self.config.topics or self.config.keywords,
                include_raw_chunks=self.config.include_raw_chunks,
                run_id=str(self.config.run_id),
                model_name=self.config.llm.model_name,
                confidence_mode=self.config.confidence_mode,
                prompt_path=self.config.llm.prompt_path,
                pipeline_version=sec_nlp_version,
            )
        return write_results(
            config=self.config,
            formatter=formatter,
            symbol=symbol,
            filing_meta=filing_meta,
            analysis_results=analysis_results,
            relevant_results=relevant_results,
            search_queries=search_queries,
            timings=timings,
            market_data=market_data,
            market_context=market_context,
        )
