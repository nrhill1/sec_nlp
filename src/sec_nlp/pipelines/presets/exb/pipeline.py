# src/sec_nlp/pipelines/presets/exb/pipeline.py
"""Pipeline for downloading and extracting exhibit content by category."""

from pathlib import Path
from typing import ClassVar, Literal, TypedDict

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from pydantic import PrivateAttr
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from tqdm import tqdm

from sec_nlp.core.infra.logger import log_divider, logger
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.core.text.keyword import KeywordMatcher
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.chunk_filters import limit_docs_per_accession
from sec_nlp.pipelines.metadata.exhibit import prepare_vector_docs
from sec_nlp.pipelines.observability.telemetry import (
    log_chunk_length_stats,
    log_filter_stats,
)
from sec_nlp.pipelines.output_io import write_json
from sec_nlp.pipelines.utils import slugify
from sec_nlp.pipelines.vector import upload_documents
from sec_nlp.pipelines.vector.query import scroll_exists
from sec_nlp.types import JsonValue, ResultDict

from .config import ExhibitConfig
from .io.exhibit_summary import write_exhibit_summary
from .io.outputs import write_exhibit_outputs
from .models import ExhibitResult
from .steps.extract.exhibits import collect_exhibit_documents
from .steps.search.payloads import (
    SearchManifestMetaPayload,
    SearchManifestPayload,
    SearchRecordPayload,
)
from .steps.search.search import ExhibitSearch


class SearchRecord(TypedDict):
    query: str
    query_slug: str
    output_file: str | None
    num_results: int
    top_symbols: list[str]


CONTRACT_KEYWORD_CATEGORY_TERMS = {
    "exclusivity": ["exclusive"],
    "cost": ["cost", "pricing", "cost-"],
    "aftermarket": [
        "aftermarket",
        "repair",
        "replacement",
        "maintenance",
        "service",
    ],
    "components": ["component", "engine", "part"],
    "supply": [
        "supplier",
        "supply",
        "offtake",
        "purchase",
        "distribution",
        "contract",
        "agreement",
        "schedule",
    ],
}


def _normalize_symbol(value: JsonValue) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool) or value is None:
        return "unknown"
    if isinstance(value, (int, float)):
        return str(value)
    return "unknown"


class ExhibitPipeline(BasePipeline):
    """Pipeline for extracting exhibit content by category."""

    # Class attributes
    pipeline_type: ClassVar[Literal["exhibit"]] = "exhibit"
    description: ClassVar[str] = (
        "Extract exhibit content across categories (contracts, subsidiaries, consents, financials, xbrl)"
    )

    requires_llm: ClassVar[bool] = False
    requires_vector_db: ClassVar[bool] = True

    config: ExhibitConfig

    # Filings
    _loader: Loader = PrivateAttr()

    # Vector Store
    _vector_store: QdrantVectorStore | None = PrivateAttr(default=None)
    _qdrant_client: QdrantClient | None = PrivateAttr(default=None)

    # Semantic Search
    _search: ExhibitSearch | None = PrivateAttr(default=None)

    @classmethod
    def config_model(cls) -> type[ExhibitConfig]:
        return ExhibitConfig

    @classmethod
    def result_model(cls) -> type[ExhibitResult]:
        return ExhibitResult

    def _build_components(self) -> None:
        """
        Build pipeline components that depend on config.

        This is called automatically by model_post_init after the
        config has been validated and assigned.

        Raises:
            ValueError: If components fail to initialize
            RuntimeError: If vector store cannot be initialized
        """
        try:
            self._loader = Loader(
                email=self.config.email,
                downloads_folder=self.config.dl_path,
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap,
            )
        except Exception as e:
            raise ValueError(
                f"Failed to initialize Loader: {e}\n"
                f"Downloads: {self.config.dl_path.resolve()}\n"
            ) from e

        if not self.config.dry_run:
            try:
                self._qdrant_client = self.config.vdb.setup_qdrant_client()
                embedder = self.config.vdb.setup_embedding_model()

                test_embedding = embedder.embed_query("test")
                embedding_dim = len(test_embedding)
                collection_name = self._collection_name()

                # Delete collection if fresh to avoid corrupted state
                self.config.vdb.recreate_collection_if_fresh(
                    self._qdrant_client, collection_name, self.config.fresh
                )

                # Ensure collection exists
                if not self._qdrant_client.collection_exists(collection_name):
                    self._qdrant_client.create_collection(
                        collection_name=collection_name,
                        vectors_config=VectorParams(
                            size=embedding_dim,
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
                    qdrant_client=self._qdrant_client,
                    embedder=embedder,
                    collection_name=collection_name,
                )

                logger.info("Embedding dimension: %d", embedding_dim)
            except Exception as e:
                raise RuntimeError(
                    f"{type(e).__name__}: Failed to initialize vector store: {e}\n"
                ) from e

    def _collection_name(self):
        collection_name = self.config.vdb.collection_name
        if isinstance(collection_name, str) and collection_name.strip():
            return collection_name
        return "exhibit"

    def run(self) -> ExhibitResult:
        """
        Execute the exhibit pipeline.

        Returns:
            ExhibitResult with outputs and metadata
        """
        try:
            self.config.setup_paths()

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

            # Skip chunking/indexing if search_only mode
            if not self.config.search_only:
                # Process symbols with progress bar
                with tqdm(
                    self.config.symbols,
                    desc="Processing symbols",
                    unit="symbol",
                    colour="green",
                    leave=True,
                    disable=not self.config.verbose,
                    bar_format="\n{n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
                ) as pbar:
                    for symbol in pbar:
                        pbar.set_description(f"Processing {symbol}")
                        symbol_outputs = self._process_symbol(symbol)
                        all_outputs.extend(symbol_outputs)
                        metadata[symbol] = len(symbol_outputs)
            else:
                logger.info("Skipping chunking/indexing (search_only mode)")

            # Run semantic search if queries are configured (or if search_only mode)
            if self.config.search.queries or self.config.search_only:
                search_outputs = self._run_semantic_search()
                all_outputs.extend(search_outputs)
                metadata["search_results"] = len(search_outputs)
                metadata["search_outputs"] = search_outputs
                metadata["search_queries"] = list(self.config.search.queries)

            self.config.complete_run(success=True)
            return ExhibitResult(
                success=True,
                outputs=all_outputs,
                metadata=metadata,
            )

        except Exception as e:
            logger.exception("Pipeline execution failed")
            self.config.complete_run(success=False)
            return ExhibitResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    def _process_symbol(self, symbol: str) -> list[Path]:
        """Process a single symbol."""
        log_divider(logger, color="cyan")
        logger.info("Processing symbol: %s \n", symbol)

        self._loader.add_symbol(symbol)
        keyword_terms = []
        if self.config.has_contract_exhibits():
            keyword_terms = [t.lower() for t in self.config.search_terms if t]
        keyword_categories = KeywordMatcher.build_keyword_categories(
            keyword_terms,
            category_terms=CONTRACT_KEYWORD_CATEGORY_TERMS,
        )

        exhibit_docs, stats = collect_exhibit_documents(
            loader=self._loader,
            symbol=symbol,
            config=self.config,
            keyword_terms=keyword_terms,
            keyword_categories=keyword_categories,
            adaptive_chunk_size=self._adaptive_chunk_size,
            skip_prefilter=False,
        )

        if not exhibit_docs:
            logger.warning("No exhibit sections found for %s", symbol)
            return []

        # Drop link-only reference stubs (e.g., “incorporated by reference” anchor lists)
        before_stub = len(exhibit_docs)
        exhibit_docs = [
            d for d in exhibit_docs if not self._is_reference_stub(d)
        ]
        if len(exhibit_docs) != before_stub:
            logger.info(
                "Dropped %d link-only reference chunks for %s",
                before_stub - len(exhibit_docs),
                symbol,
            )

        filtered_docs = self._filter_chunks(symbol, exhibit_docs)

        if not filtered_docs:
            logger.warning(
                "No exhibit chunks remaining after filtering for %s", symbol
            )
            summary_outputs = write_exhibit_summary(
                symbol=symbol,
                docs=exhibit_docs,
                config=self.config,
            )
            if summary_outputs:
                logger.info("Finished processing %s", symbol)
            return summary_outputs

        stats.log(symbol=symbol, filtered_chunk_count=len(filtered_docs))

        log_chunk_length_stats(
            label=None,
            symbol=symbol,
            accession=None,
            docs=filtered_docs,
            keyword_field="keyword_score",
        )

        # Filter out chunks from accessions already in the vector database
        if not self.config.dry_run and self._qdrant_client:
            filtered_docs, skipped_count = self._filter_indexed_accessions(
                filtered_docs
            )
            if skipped_count > 0:
                logger.info(
                    "Skipped %d chunks from already-indexed accessions for %s",
                    skipped_count,
                    symbol,
                )
            if not filtered_docs:
                logger.info("All exhibit chunks already indexed for %s", symbol)
                return []

        logger.info(
            "Indexing %d chunks for %s",
            len(filtered_docs),
            symbol,
        )

        # Store chunks in vector database
        if not self.config.dry_run and self._vector_store:
            vector_docs = prepare_vector_docs(
                filtered_docs,
                symbol=symbol,
            )

            if vector_docs:
                upload_documents(
                    vector_store=self._vector_store,
                    documents=vector_docs,
                    symbol=symbol,
                    batch_size=32,
                    desc=f"Uploading vectors for {symbol}",
                )
                logger.info(
                    "Stored %d chunks in vector database for %s",
                    len(vector_docs),
                    symbol,
                )

        # Write results to output files
        output_files = write_exhibit_outputs(
            symbol=symbol,
            docs=filtered_docs,
            config=self.config,
        )
        output_files.extend(
            write_exhibit_summary(
                symbol=symbol,
                docs=exhibit_docs,
                config=self.config,
            )
        )
        logger.info("Finished processing %s", symbol)

        return output_files

    def _run_semantic_search(self) -> list[Path]:
        """Run semantic search queries if configured.

        Returns:
            List of output files from search results
        """
        if not self.config.search.queries and not self.config.search_only:
            return []

        if not self.config.search.queries:
            logger.warning("Search not configured: no queries provided")
            return []

        if not self._vector_store:
            logger.warning(
                "Search queries configured but vector store not initialized (dry_run=True?)"
            )
            return []

        # Initialize search tool (analysis disabled for this pipeline)
        search_kwargs = dict(self.config.search.search_kwargs)
        if self.config.vdb.search_type == "mmr":
            search_kwargs.setdefault("fetch_k", self.config.search.mmr_fetch_k)
            search_kwargs.setdefault(
                "lambda_mult", self.config.search.mmr_lambda
            )

        self._search = ExhibitSearch(
            vector_store=self._vector_store,
            limit=self.config.search.limit,
            score_threshold=self.config.search.score_threshold,
            search_type=self.config.vdb.search_type,
            search_kwargs=search_kwargs,
        )

        search_outputs: list[Path] = []
        search_records: list[SearchRecord] = []

        # Create dedicated search output directory using run_id
        search_run_id = (
            str(self.config.run_id) if self.config.run_id else "run_unknown"
        )
        search_dir = self.config.out_path / "search" / search_run_id
        search_dir.mkdir(parents=True, exist_ok=True)

        log_divider(logger, color="yellow")
        logger.info(
            "Running %d semantic search queries",
            len(self.config.search.queries),
        )
        logger.info("Search output directory: %s", search_dir)

        for i, query in enumerate(self.config.search.queries, 1):
            try:
                logger.info(
                    "[%d/%d] Searching: %s",
                    i,
                    len(self.config.search.queries),
                    query,
                )

                results = self._search.search(
                    query=query,
                    symbols=self.config.symbols,
                )

                query_slug = slugify(query[:50])
                file_slug = f"{i:02d}_{query_slug}"
                output_file: Path | None = None
                if self.config.search.export_results and results:
                    # Generate safe filename from query
                    output_file = search_dir / f"{file_slug}.yaml"

                    self._search.export_results(
                        query=query,
                        results=results,
                        output_path=output_file,
                        search_type=self.config.vdb.search_type,
                        run_id=str(self.config.run_id),
                    )

                    search_outputs.append(output_file)

                top_symbols = list(
                    dict.fromkeys(
                        _normalize_symbol(r.metadata.get("symbol", "unknown"))
                        for r in results[:5]
                    )
                )
                record: SearchRecord = {
                    "query": query,
                    "query_slug": output_file.stem
                    if output_file
                    else file_slug,
                    "output_file": output_file.name if output_file else None,
                    "num_results": len(results),
                    "top_symbols": top_symbols,
                }
                search_records.append(record)

                logger.info("  → Found %d results", len(results))

            except Exception as e:
                logger.error("Search failed for query '%s': %s", query, e)
                continue

        # Write summary manifest
        if search_outputs:
            self._write_search_manifest(
                search_dir,
                search_records,
                queries=self.config.search.queries,
            )

        return search_outputs

    def _write_search_manifest(
        self,
        search_dir: Path,
        search_records: list[SearchRecord],
        queries: list[str] | None = None,
    ) -> None:
        """Write a summary manifest of all search results."""
        records_payload = [
            SearchRecordPayload.model_validate(record)
            for record in search_records
        ]

        meta_payload = SearchManifestMetaPayload(
            run_id=self.config.run_id,
            timestamp=self.config.run_timestamp.isoformat(),
            pipeline_type=self.config.pipeline_type,
            search_type=self.config.vdb.search_type,
            collection=self._collection_name(),
            total_queries=len(search_records),
            total_results=sum(
                record.get("num_results", 0) for record in search_records
            ),
        )

        manifest = SearchManifestPayload(
            meta=meta_payload,
            queries=records_payload,
        )

        manifest_path = search_dir / "_manifest.json"
        write_json(
            manifest_path,
            manifest,
            ensure_ascii=False,
            exclude_none=True,
        )

        logger.info("Search manifest written to %s", manifest_path)

    def _filter_chunks(
        self, symbol: str, docs: list[Document]
    ) -> list[Document]:
        """Filter exhibit chunks by length, duplication, and keyword hits."""
        if not docs:
            return []

        max_non_keyword_chunks = self.config.max_non_keyword_chunks
        if self.config.has_non_contract_exhibits():
            max_non_keyword_chunks = None

        keyword_terms = (
            self.config.search_terms
            if self.config.has_contract_exhibits()
            else []
        )
        filtered, stats = KeywordMatcher.filter_docs_by_keywords(
            docs,
            keyword_terms,
            min_chars=self.config.min_chunk_chars,
            dedupe=self.config.dedupe_chunks,
            max_non_keyword_chunks=max_non_keyword_chunks,
            max_chunks=None,
        )

        if self.config.max_chunks_per_filing and filtered:
            before = len(filtered)
            filtered, _kept, skipped = limit_docs_per_accession(
                filtered, self.config.max_chunks_per_filing
            )
            if skipped:
                logger.info(
                    "Per-filing cap: kept %d/%d chunks for %s",
                    len(filtered),
                    before,
                    symbol,
                )

        log_filter_stats(symbol=symbol, stats=stats)

        return filtered

    def _accession_exists_in_vectordb(self, accession_number: str) -> bool:
        """Check if chunks for an accession number already exist in the vector DB.

        Args:
            accession_number: SEC filing accession number

        Returns:
            True if at least one chunk with this accession exists
        """
        if not self._qdrant_client:
            return False

        found = scroll_exists(
            self._qdrant_client,
            self._collection_name(),
            {"accession_number": [accession_number]},
        )
        return found

    def _filter_indexed_accessions(
        self, docs: list[Document]
    ) -> tuple[list[Document], int]:
        """Filter out documents from accessions already in the vector database.

        Args:
            docs: List of document chunks

        Returns:
            Tuple of (filtered docs, count of skipped docs)
        """
        # Group docs by accession number
        accession_to_docs: dict[str, list[Document]] = {}
        for doc in docs:
            accession = (doc.metadata or {}).get("accession_number", "unknown")
            accession_to_docs.setdefault(accession, []).append(doc)

        # Check which accessions are already indexed
        indexed_accessions: set[str] = set()
        for accession in accession_to_docs:
            if accession != "unknown" and self._accession_exists_in_vectordb(
                accession
            ):
                indexed_accessions.add(accession)

        if indexed_accessions:
            logger.debug(
                "Found %d already-indexed accessions: %s",
                len(indexed_accessions),
                ", ".join(sorted(indexed_accessions)),
            )

        # Filter out docs from indexed accessions
        filtered_docs: list[Document] = []
        skipped_count = 0
        for accession, acc_docs in accession_to_docs.items():
            if accession in indexed_accessions:
                skipped_count += len(acc_docs)
            else:
                filtered_docs.extend(acc_docs)

        return filtered_docs, skipped_count

    def _adaptive_chunk_size(self, content_len: int) -> int:
        """Pick a chunk size based on content length to avoid massive chunks."""
        base = self._loader.chunk_size
        if content_len <= 0:
            return base
        # Smaller for huge exhibits, keep reasonable minimum
        scaled = max(2000, min(base, max(2500, content_len // 3)))
        return scaled

    @staticmethod
    def _is_reference_stub(doc: Document) -> bool:
        """
        Heuristic: skip link-only “incorporated by reference” stubs and tiny anchor lists.

        These often contain only exhibit filenames and no contract text.
        """
        text = (doc.page_content or "").strip().lower()
        if not text:
            return True

        # Count anchors and consider as stub if heavy on hrefs and short
        href_count = text.count("href=") + text.count("</a>")
        if href_count >= 3 and len(text) < 1500:
            return True

        if "incorporated by reference" in text and len(text) < 1800:
            return True

        # Very short fragments with no sentences
        if len(text) < 200 and text.count(".") < 1:
            return True

        return False
