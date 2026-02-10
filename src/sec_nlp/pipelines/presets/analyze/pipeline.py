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
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.ingest.filings import get_filing_date_from_dir
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.core.llm.chains import InputModelKeys, build_runnable
from sec_nlp.core.text.deduplication import SimHashConfig, SimHashDeduplicator
from sec_nlp.core.text.filters import SectionFilter
from sec_nlp.core.text.section_extractor import SectionExtractor
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.metadata.accession import get_accession_from_metadata
from sec_nlp.pipelines.observability.telemetry import log_chunk_length_stats
from sec_nlp.pipelines.state import ProcessingState, get_state_dir
from sec_nlp.pipelines.types import (
    AnalysisResultDict,
    MetadataRecord,
)
from sec_nlp.prompts import load_prompt_template
from sec_nlp.types import JsonDict, ResultDict

from . import (
    confidence as confidence_utils,
    efts as efts_utils,
)
from .builders import (
    build_analysis_runner,
    build_output_formatter,
    build_preprocessor,
    build_search_runner,
)
from .config import AnalyzeConfig
from .io.enhancements import (
    build_peer_comparison,
    build_symbol_profile,
    write_executive_comp_summary,
    write_peer_summary,
    write_symbol_summary,
)
from .io.outputs import OutputFormatter
from .io.result_writer import write_results
from .market import (
    MarketEnrichment,
    build_market_enrichment,
    format_market_context,
)
from .models import AnalysisInput, AnalysisResult, AnalyzeResult
from .runnables.analysis import AnalyzerRunnable
from .runnables.efts import EFTSSearchRunnable
from .runnables.market_correlation import (
    MarketCorrelationInput,
    MarketCorrelationRunnable,
)
from .runnables.search import SearchResultsByQuery, SearchRunnable
from .steps.analysis.callbacks import TracingCallbackHandler
from .steps.analysis.instructions import AnalysisInstructionBuilder
from .steps.indexing.vector_index import VectorIndexer
from .steps.preprocess.preprocess import ChunkPreprocessor
from .steps.search.efts_search import EFTSSearchResult
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
    _embedder: OllamaEmbeddings | None = PrivateAttr(default=None)

    # Deduplication
    _deduplicator: SimHashDeduplicator = PrivateAttr()

    # Output formatting
    _output_formatter: OutputFormatter = PrivateAttr()
    _analysis_instructions: str = PrivateAttr(default="")
    _relationship_graphs: JsonDict = PrivateAttr(default_factory=dict)

    # Modular helpers
    _preprocessor: ChunkPreprocessor = PrivateAttr()
    _vector_indexer: VectorIndexer = PrivateAttr()
    _analysis_runner: AnalyzerRunnable = PrivateAttr()
    _search_runner: SearchRunnable = PrivateAttr()
    _efts_runner: EFTSSearchRunnable | None = PrivateAttr(default=None)
    _market_correlation_runner: MarketCorrelationRunnable | None = PrivateAttr(
        default=None
    )
    _search_results_by_query: SearchResultsByQuery | None = PrivateAttr(
        default=None
    )
    _efts_results_by_symbol: dict[str, list[EFTSSearchResult]] = PrivateAttr(
        default_factory=dict
    )
    _market_context_by_symbol: dict[str, str] = PrivateAttr(
        default_factory=dict
    )
    _symbol_profiles: dict[str, JsonDict] = PrivateAttr(default_factory=dict)
    _processing_state: ProcessingState | None = PrivateAttr(default=None)

    @classmethod
    def config_model(cls) -> type[AnalyzeConfig]:
        return AnalyzeConfig

    @classmethod
    def result_model(cls) -> type[AnalyzeResult]:
        return AnalyzeResult

    def _build_components(self) -> None:
        """Build pipeline components from config."""
        keyword_terms = self.config.topics or self.config.keywords
        loader_keywords = self.config.keywords or None

        try:
            # Initialize loader
            self._loader = Loader(
                email=self.config.email,
                downloads_folder=self.config.dl_path,
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
                keywords=loader_keywords,
                keyword_mode=self.config.keyword_mode,
                use_async=self.config.loader_use_async,
                max_workers=self.config.loader_max_workers,
            )

            # Build section filter if section filtering is configured
            if self.config.section_type and (
                self.config.section_numbers
                or self.config.custom_section_pattern
            ):
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
                embedder, embedding_dim = (
                    self.config.vdb.setup_embedding_model()
                )
                self._embedder = embedder

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

        # Initialize output formatter and preprocessors
        self._output_formatter = build_output_formatter(
            config=self.config,
            topics=keyword_terms,
        )
        self._preprocessor = build_preprocessor(
            config=self.config,
            section_extractor=self._section_extractor,
            topics=keyword_terms,
            embedder=self._embedder,
        )
        self._vector_indexer = VectorIndexer(
            config=self.config,
            vector_store=self._vector_store,
            deduplicator=self._deduplicator,
        )
        self._analysis_runner = build_analysis_runner(
            config=self.config,
            graph=self._graph,
            callbacks=self._callbacks,
            analysis_instructions=self._analysis_instructions,
        )
        self._search_runner = build_search_runner(
            config=self.config,
            vector_store=self._vector_store,
        )
        self._efts_runner = EFTSSearchRunnable(
            efts_config=self.config.efts,
            forms=list(self.config.mode.forms),
            mode=self.config.mode,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            email=self.config.email,
        )
        self._market_correlation_runner = MarketCorrelationRunnable()

        # Initialize processing state for incremental mode
        if self.config.incremental:
            state_dir = get_state_dir(self.config.out_path)
            self._processing_state = ProcessingState(
                state_dir=state_dir,
                pipeline_type=self.pipeline_type,
            )
            # Clear state if fresh mode is enabled
            if self.config.fresh:
                self._processing_state.clear()

    def run(self) -> AnalyzeResult:
        """Execute the semantic search pipeline."""
        try:
            self.config.setup_paths()

            # Rich Panel for run header
            console = get_rich_console()
            run_info = Text()
            run_info.append("Run ", style="bold cyan")
            run_info.append(
                f"{self.config.short_id_display}", style="bold magenta"
            )
            run_info.append(" · ", style="dim")
            run_info.append(f"{self.config.run_id}", style="dim cyan")
            panel = Panel(
                run_info,
                title="[bold white]Pipeline Start[/bold white]",
                border_style="magenta",
                expand=False,
            )
            console.print(panel)
            logger.info(
                "Run %s (%s)",
                self.config.short_id_display,
                self.config.run_id,
            )

            output_set: set[Path] = set()
            metadata: ResultDict = {
                "run_id": str(self.config.run_id),
                "short_id": self.config.short_id,
                "run_path": self.config.run_path_component(),
            }
            total_analyzed_chunks = 0

            # Rich Progress bar for symbols
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(complete_style="green", finished_style="bold green"),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=False,
            ) as progress:
                task = progress.add_task(
                    "Processing symbols",
                    total=len(self.config.symbols),
                )
                last_index = len(self.config.symbols) - 1
                for index, symbol in enumerate(self.config.symbols):
                    progress.update(task, description=f"Processing {symbol}")
                    symbol_outputs, chunk_stats = self._process_symbol(symbol)
                    symbol_output_set = set(symbol_outputs)
                    output_set.update(symbol_output_set)
                    total_analyzed_chunks += int(
                        chunk_stats.get("analyzed_count", 0)
                    )
                    symbol_meta: SymbolRunMetadata = {
                        "outputs": len(symbol_output_set),
                        "chunk_stats": chunk_stats,
                    }
                    symbol_key = str(symbol)
                    # SymbolRunMetadata is a TypedDict compatible with ResultValue
                    metadata[symbol_key] = symbol_meta  # type: ignore[assignment]
                    progress.advance(task)
                    if index < last_index:
                        log_divider(logger, color="magenta")

            if len(self._symbol_profiles) > 1:
                run_component = self.config.run_path_component()
                peer_summary = build_peer_comparison(self._symbol_profiles)
                peer_dir = (
                    self.config.out_path / run_component / self.pipeline_type
                )
                peer_path = write_peer_summary(
                    output_dir=peer_dir,
                    summary=peer_summary,
                )
                if peer_path is not None:
                    output_set.add(peer_path)

            # Run semantic search if queries are configured
            search_queries = self.config.get_search_queries()
            if search_queries:
                if self._efts_results_by_symbol:
                    hybrid_results = efts_utils.build_hybrid_search_results(
                        config=self.config,
                        vector_results=self._search_results_by_query,
                        efts_results_by_symbol=self._efts_results_by_symbol,
                        market_context_by_symbol=self._market_context_by_symbol,
                    )
                    search_outputs = self._search_runner.export_results(
                        hybrid_results,
                        cached=True,
                        queries=search_queries,
                    )
                elif self._search_results_by_query is not None:
                    search_outputs = self._search_runner.export_results(
                        self._search_results_by_query,
                        cached=True,
                        queries=search_queries,
                    )
                else:
                    search_outputs = self._search_runner.run(
                        queries=search_queries,
                    )
                search_output_set = set(search_outputs)
                output_set.update(search_output_set)
                metadata["search_results"] = len(search_output_set)
                metadata["search_outputs"] = list(search_output_set)
                metadata["search_queries"] = list(search_queries)

            if self._relationship_graphs:
                metadata["relationships"] = dict(self._relationship_graphs)

            metadata["total_chunks_analyzed"] = total_analyzed_chunks

            self.config.complete_run(success=True)
            return AnalyzeResult(
                success=True,
                outputs=list(output_set),
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

    def _log_chunk_stats_by_accession(
        self,
        docs: list[Document],
        *,
        symbol: str | None,
        label: str | None,
    ) -> None:
        accession_docs: dict[str | None, list[Document]] = defaultdict(list)
        for doc in docs:
            accession = get_accession_from_metadata(doc.metadata)
            accession_docs[accession].append(doc)
        symbol_text = str(symbol) if symbol is not None else None
        label_text = str(label) if label is not None else None
        if len(accession_docs) == 1:
            only_accession = next(iter(accession_docs))
            log_chunk_length_stats(
                label=label_text,
                symbol=symbol_text,
                accession=str(only_accession) if only_accession else None,
                docs=docs,
                prefix_color="dim",
            )
            return
        for accession in sorted(
            accession_docs, key=lambda value: (value is None, value or "")
        ):
            log_chunk_length_stats(
                label=label_text,
                symbol=symbol_text,
                accession=str(accession) if accession else None,
                docs=accession_docs[accession],
                prefix_color="dim",
            )

    def _process_symbol(self, symbol: str) -> tuple[list[Path], ChunkStats]:
        """Process a single symbol through the full analysis pipeline."""
        log_divider(logger, color="cyan")
        logger.info("Processing symbol: %s \n", symbol)
        self._loader.add_symbol(symbol)
        timings: Timings = {}

        # Phase 1: EFTS discovery and document loading
        docs, allowed_accessions = self._run_efts_and_load_docs(symbol, timings)
        if not docs:
            return [], self._empty_chunk_stats(timings)

        # Phase 2: Preprocessing
        docs = self._preprocess_documents(symbol, docs, timings)
        if not docs:
            return [], self._empty_chunk_stats(timings)

        # Phase 3: Market enrichment and chunk stats
        stats, market_data, market_context = self._enrich_and_index(
            symbol, docs, timings
        )

        # Phase 4: Vector search and LLM analysis
        search_queries = self.config.get_search_queries()
        analysis_results, docs_for_analysis = self._run_search_and_analysis(
            symbol, search_queries, timings
        )
        stats["analyzed_count"] = len(analysis_results)

        # Phase 5: Post-processing (confidence, correlation)
        relevant_results, market_correlation = self._postprocess_results(
            symbol, analysis_results, market_data
        )

        # Phase 6: Write outputs
        output_files = self._write_symbol_outputs(
            symbol=symbol,
            docs=docs,
            analysis_results=analysis_results,
            relevant_results=relevant_results,
            search_queries=search_queries,
            timings=timings,
            market_data=market_data,
            market_context=market_context,
            market_correlation=market_correlation,
        )

        timings["total"] = sum(timings.values())

        # Mark accessions as processed for incremental mode
        if self._processing_state is not None and docs:
            processed_accessions = list(
                {
                    get_accession_from_metadata(doc.metadata)
                    for doc in docs
                    if get_accession_from_metadata(doc.metadata)
                }
            )
            if processed_accessions:
                self._processing_state.mark_processed_batch(
                    symbol=symbol,
                    accessions=processed_accessions,
                    run_id=self.config.run_id,
                    chunk_counts={
                        acc: len(
                            [
                                d
                                for d in docs
                                if get_accession_from_metadata(d.metadata)
                                == acc
                            ]
                        )
                        for acc in processed_accessions
                    },
                )

        return output_files, stats

    def _run_efts_and_load_docs(
        self,
        symbol: str,
        timings: Timings,
    ) -> tuple[list[Document], set[str] | None]:
        """Run EFTS discovery and load documents for a symbol."""
        start_date, end_date = self.config.date_range
        search_queries = self.config.get_search_queries()
        limit_per_symbol = self.config.limit
        perform_download = True
        allowed_accessions: set[str] | None = None

        if self.config.efts.enabled and search_queries:
            t0 = perf_counter()
            efts_results, new_accessions, efts_ok = (
                efts_utils.run_efts_for_symbol(
                    config=self.config,
                    efts_runner=self._efts_runner,
                    symbol=symbol,
                    queries=search_queries,
                    forms=self.config.effective_forms,
                )
            )
            timings["efts"] = perf_counter() - t0
            if efts_ok:
                self._efts_results_by_symbol[symbol] = efts_results
                allowed_accessions = efts_utils.efts_accessions(efts_results)
                total_hits = len(allowed_accessions)
                logger.info(
                    "EFTS search for %s: %d hits (%d new)",
                    symbol,
                    total_hits,
                    len(new_accessions),
                )
                if total_hits == 0:
                    allowed_accessions = None
                if not allowed_accessions:
                    perform_download = False
                    logger.info(
                        "EFTS returned no matching filings for %s", symbol
                    )
                if self.config.efts.auto_download:
                    limit_per_symbol, perform_download = (
                        self._handle_efts_download(
                            symbol,
                            efts_results,
                            new_accessions,
                            limit_per_symbol,
                            perform_download,
                            timings,
                        )
                    )

        t0 = perf_counter()
        docs = self._loader.load_documents(
            mode=self.config.mode,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            limit_per_symbol=limit_per_symbol,
            perform_download=perform_download,
            section_filter=self._section_filter,
            symbols=[symbol],
        )
        if allowed_accessions is not None:
            docs = efts_utils.filter_docs_by_accession(docs, allowed_accessions)

        # Apply incremental processing - filter out already-processed accessions
        if self._processing_state is not None and docs:
            all_accessions = {
                get_accession_from_metadata(doc.metadata)
                for doc in docs
                if get_accession_from_metadata(doc.metadata)
            }
            if all_accessions:
                pending = self._processing_state.get_pending_accessions(
                    symbol, all_accessions
                )
                if pending != all_accessions:
                    docs = [
                        doc
                        for doc in docs
                        if get_accession_from_metadata(doc.metadata) in pending
                    ]
                    if not docs:
                        logger.info(
                            "Incremental mode: all accessions already processed for %s",
                            symbol,
                        )
        relationships = self._loader.last_meta["relationships"]
        if relationships:
            self._relationship_graphs.update(relationships)
        timings["load"] = perf_counter() - t0

        if not docs:
            logger.warning("No documents found for %s", symbol)
        return docs, allowed_accessions

    def _handle_efts_download(
        self,
        symbol: str,
        efts_results: list[EFTSSearchResult],
        new_accessions: list[str],
        limit_per_symbol: int | None,
        perform_download: bool,
        timings: Timings,
    ) -> tuple[int | None, bool]:
        """Handle EFTS auto-download logic."""
        limit_per_symbol = efts_utils.cap_efts_download_limit(
            self.config, limit_per_symbol
        )
        if limit_per_symbol == 0:
            logger.info("EFTS auto-download disabled for %s", symbol)
            return limit_per_symbol, False

        accessions_to_download = efts_utils.select_efts_accessions(
            efts_results,
            new_accessions,
            limit_per_symbol,
        )
        if accessions_to_download:
            t_download = perf_counter()
            downloaded = efts_utils.download_efts_accessions(
                config=self.config,
                company_name=self._loader.company_name,
                symbol=symbol,
                accessions=accessions_to_download,
                results=efts_results,
            )
            timings["efts_download"] = perf_counter() - t_download
            if downloaded:
                logger.info(
                    "EFTS auto-download for %s: %d accessions",
                    symbol,
                    downloaded,
                )
                return limit_per_symbol, False
            logger.info(
                "EFTS auto-download for %s: no accessions downloaded", symbol
            )
        elif not new_accessions:
            logger.info(
                "EFTS auto-download skipped for %s (no new accessions)", symbol
            )
            return limit_per_symbol, False

        return limit_per_symbol, perform_download

    def _preprocess_documents(
        self,
        symbol: str,
        docs: list[Document],
        timings: Timings,
    ) -> list[Document]:
        """Preprocess and chunk documents."""
        t0 = perf_counter()
        docs = self._preprocessor.chunk_and_prepare(docs)
        self._ensure_filing_dates(docs)
        timings["prepare"] = perf_counter() - t0

        if not docs:
            logger.warning(
                "No documents remaining after filtering for %s", symbol
            )
        return docs

    def _enrich_and_index(
        self,
        symbol: str,
        docs: list[Document],
        timings: Timings,
    ) -> tuple[ChunkStats, MarketEnrichment | None, str | None]:
        """Enrich documents with market data and index them."""
        self._update_efts_keywords_from_docs(symbol, docs)

        chunk_lengths = [len((doc.page_content or "").strip()) for doc in docs]
        stats: ChunkStats = {
            "count": float(len(chunk_lengths)),
            "min_value": float(min(chunk_lengths)),
            "max_value": float(max(chunk_lengths)),
            "median": float(median(chunk_lengths)),
            "mean": float(mean(chunk_lengths)),
            "analyzed_count": 0,
            "timings": timings,
        }

        market_data = self._build_market_enrichment(symbol, docs)
        market_context = self._format_market_context(market_data)
        if market_context:
            self._market_context_by_symbol[symbol] = market_context
            for doc in docs:
                metadata = dict(doc.metadata or {})
                metadata["market_enrichment_context"] = market_context
                doc.metadata = metadata

        self._log_chunk_stats_by_accession(docs, symbol=symbol, label=None)
        self._vector_indexer.index(symbol, docs, timings)

        return stats, market_data, market_context

    def _run_search_and_analysis(
        self,
        symbol: str,
        search_queries: list[str] | None,
        timings: Timings,
    ) -> tuple[list[AnalysisResultDict], list[Document]]:
        """Run vector search and LLM analysis."""
        if not search_queries or not self._vector_store:
            logger.info(
                "Search not configured (no queries/topics) or vector store unavailable; skipping analysis"
            )
            return [], []

        # Vector search
        per_symbol_filters = dict(self.config.search.metadata_filters)
        per_symbol_filters["symbol"] = [symbol]
        search_runner = self._search_runner
        if search_runner.metadata_filters != per_symbol_filters:
            search_runner = search_runner.model_copy(
                update={"metadata_filters": per_symbol_filters}
            )
        docs_for_analysis, search_results = (
            search_runner.retrieve_hits_with_results(queries=search_queries)
        )
        self._search_results_by_query = search_results

        if not docs_for_analysis:
            logger.info(
                "No vector search hits for %s; skipping analysis step", symbol
            )
            return [], []

        logger.info(
            "Analyzing %d retrieved chunks for %s (from vector search)",
            len(docs_for_analysis),
            symbol,
        )
        self._log_chunk_stats_by_accession(
            docs_for_analysis, symbol=symbol, label="vector"
        )

        # LLM analysis with status spinner
        t0 = perf_counter()
        console = get_rich_console()
        with console.status(
            f"[bold green]Running LLM analysis for {symbol}...[/bold green]",
            spinner="dots",
        ):
            analysis_results = self._analysis_runner.analyze_chunks(
                symbol, docs_for_analysis
            )
        timings["analyze"] = perf_counter() - t0

        return analysis_results, docs_for_analysis

    def _postprocess_results(
        self,
        symbol: str,
        analysis_results: list[AnalysisResultDict],
        market_data: MarketEnrichment | None,
    ) -> tuple[list[AnalysisResultDict], JsonDict | None]:
        """Filter relevant results and run market correlation."""
        relevant_results = [
            result
            for result in analysis_results
            if self._output_formatter.is_relevant_result(result)
        ]
        error_results = [
            r for r in analysis_results if r.get("error") or r.get("exception")
        ]

        # Market correlation
        market_correlation = None
        if self.config.market_correlation_enabled:
            runner = (
                self._market_correlation_runner or MarketCorrelationRunnable()
            )
            try:
                market_correlation = runner.invoke(
                    MarketCorrelationInput(
                        market_data=market_data,
                        relevant_results=relevant_results,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "Market correlation failed for %s: %s", symbol, exc
                )

        # Confidence calibration
        if self.config.confidence_mode == "calibrated":
            confidence_utils.apply_confidence_derivation(
                analysis_results, market_correlation
            )

        # Log summary
        self._log_analysis_summary(
            symbol, analysis_results, relevant_results, error_results
        )

        return relevant_results, market_correlation

    def _log_analysis_summary(
        self,
        symbol: str,
        analysis_results: list[AnalysisResultDict],
        relevant_results: list[AnalysisResultDict],
        error_results: list[AnalysisResultDict],
    ) -> None:
        """Log analysis summary statistics."""
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

        # Rich Table for analysis summary
        console = get_rich_console()
        table = Table(
            title=f"[bold cyan]Analysis Summary: {symbol}[/bold cyan]",
            show_header=False,
            box=None,
        )
        table.add_column("Label", style="dim cyan", justify="right")
        table.add_column("Value", style="bold white")
        table.add_row("Total Chunks", str(total_hits))
        table.add_row("Relevant", f"[green]{relevant_hits}[/green]")
        table.add_row("Avg Confidence", avg_conf_display)
        table.add_row("Threshold", f"{self.config.confidence_threshold:.2f}")
        if error_results:
            table.add_row("Errors", f"[red]{len(error_results)}[/red]")
        console.print(table)

        # Keep log for file output
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

    def _write_symbol_outputs(
        self,
        *,
        symbol: str,
        docs: list[Document],
        analysis_results: list[AnalysisResultDict],
        relevant_results: list[AnalysisResultDict],
        search_queries: list[str] | None,
        timings: Timings,
        market_data: MarketEnrichment | None,
        market_context: str | None,
        market_correlation: JsonDict | None,
    ) -> list[Path]:
        """Write all output files for a symbol."""
        t_write_start = perf_counter()
        fallback_meta = docs[0].metadata or {}

        output_files = self._write_results(
            symbol,
            fallback_meta,
            analysis_results,
            relevant_results=relevant_results,
            search_queries=search_queries,
            timings=timings,
            market_data=market_data,
            market_context=market_context,
            market_correlation=market_correlation,
        )

        self._symbol_profiles[symbol] = build_symbol_profile(
            symbol=symbol,
            results=relevant_results,
        )

        summary_path = write_symbol_summary(
            output_dir=self.config.get_symbol_output_dir(symbol),
            symbol=symbol,
            run_id=self.config.run_id,
            analysis_results=analysis_results,
            relevant_results=relevant_results,
            fallback_meta=fallback_meta,
        )
        if summary_path is not None:
            output_files.append(summary_path)

        if self.config.mode == FilingMode.proxy:
            exec_comp_path = write_executive_comp_summary(
                output_dir=self.config.get_symbol_output_dir(symbol),
                symbol=symbol,
                run_id=self.config.run_id,
                analysis_results=analysis_results,
                relevant_results=relevant_results,
                fallback_meta=fallback_meta,
            )
            if exec_comp_path is not None:
                output_files.append(exec_comp_path)

        if output_files:
            output_dir = self.config.get_symbol_output_dir(symbol)
            # Rich-styled path output
            console = get_rich_console()
            console.print(
                f"[dim cyan]→[/dim cyan] Wrote [bold magenta]{len(output_files)}[/bold magenta] files for [bold cyan]{symbol}[/bold cyan] → [link=file://{output_dir.resolve()}][blue]{output_dir.resolve()}[/blue][/link]"
            )
            logger.info(
                "Wrote %d analysis files for %s -> %s",
                len(output_files),
                symbol,
                output_dir.resolve(),
            )
        timings["write_outputs"] = perf_counter() - t_write_start
        return output_files

    @staticmethod
    def _empty_chunk_stats(timings: Timings) -> ChunkStats:
        """Return empty chunk stats for early returns."""
        return {
            "count": 0.0,
            "min_value": 0.0,
            "max_value": 0.0,
            "mean": 0.0,
            "analyzed_count": 0,
            "timings": timings,
        }

    @staticmethod
    def _ensure_filing_dates(docs: list[Document]) -> None:
        for doc in docs:
            metadata = dict(doc.metadata or {})
            if metadata.get("filing_date") or metadata.get("acceptance_date"):
                continue
            filed_date = metadata.get("filed_date")
            if isinstance(filed_date, str) and filed_date.strip():
                metadata.setdefault("filing_date", filed_date)
                metadata.setdefault("acceptance_date", filed_date)
                doc.metadata = metadata
                continue
            source = metadata.get("file_path") or metadata.get("source")
            if isinstance(source, str) and source.strip():
                try:
                    filing_date = get_filing_date_from_dir(Path(source).parent)
                except Exception:
                    filing_date = None
                if filing_date is not None:
                    iso_date = filing_date.isoformat()
                    metadata.setdefault("filing_date", iso_date)
                    metadata.setdefault("acceptance_date", iso_date)
                    doc.metadata = metadata

    def _prepare_documents(self, docs: list[Document]) -> list[Document]:
        """Expose preprocessing for tests and standalone use."""
        return self._preprocessor.prepare_documents(docs)

    def _process_batch(
        self, batch: list[AnalysisInput], docs: list[Document]
    ) -> list[AnalysisResultDict]:
        """Expose batch processing for tests and retries."""
        return self._analysis_runner._process_batch(batch, docs)

    def _retrieve_search_hits(self) -> list[Document]:
        """Expose vector search retrieval for tests."""
        return self._search_runner.retrieve_hits(
            queries=self.config.get_search_queries()
        )

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
        return format_market_context(enrichment)

    def _update_efts_keywords_from_docs(
        self, symbol: str, docs: list[Document]
    ) -> None:
        efts_utils.update_efts_keywords_from_docs(
            symbol=symbol,
            docs=docs,
            results_by_symbol=self._efts_results_by_symbol,
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
        market_correlation: JsonDict | None = None,
    ) -> list[Path]:
        """Expose result writing for tests and downstream usage."""
        return write_results(
            config=self.config,
            formatter=self._output_formatter,
            symbol=symbol,
            filing_meta=filing_meta,
            analysis_results=analysis_results,
            relevant_results=relevant_results,
            search_queries=search_queries,
            timings=timings,
            market_data=market_data,
            market_context=market_context,
            market_correlation=market_correlation,
        )
