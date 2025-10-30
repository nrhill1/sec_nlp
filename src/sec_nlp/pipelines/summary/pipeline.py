# src/sec_nlp/pipelines/summary/pipeline.py
"""SEC filing summarization pipeline."""

from __future__ import annotations

import json
import re
import shutil
import traceback
from pathlib import Path
from typing import Any, ClassVar
from uuid import uuid4

from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.loading import load_prompt
from langchain_core.runnables import Runnable
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
)
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from sec_nlp.core import (
    FilingManager,
    Preprocessor,
    get_logger,
)
from sec_nlp.core.llm.chains import build_runnable
from sec_nlp.pipelines.base import BasePipeline, BaseResult
from sec_nlp.pipelines.registry import PipelineRegistry
from sec_nlp.pipelines.summary.config import SummaryConfig

logger = get_logger(__name__)


def _slugify(s: str) -> str:
    """Convert string to URL-safe slug."""
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")


def _safe_name(s: str, allow: str = r"a-zA-Z0-9._-") -> str:
    """Sanitize string for use in filenames."""
    return re.sub(rf"[^{allow}]+", "_", s)[:120]


class SummaryInput(BaseModel):
    """Input schema for the SEC summarization chain."""

    chunk: str
    symbol: str
    search_term: str


class SummaryResult(BaseResult):
    """Pydantic dataclass representing a validated LLM summary payload."""

    pipeline_type: ClassVar[str] = "summary"

    summary: str | None = Field(default=None)
    points: list[str] | None = Field(default=None)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


@PipelineRegistry.register("summary")
class SummaryPipeline(BasePipeline[SummaryConfig, SummaryInput, SummaryResult]):
    """Pipeline for SEC filing summarization with LLM."""

    pipeline_type: ClassVar[str] = "summary"
    description: ClassVar[str] = (
        "Download, parse, and summarize SEC filings using LLMs"
    )
    requires_llm: ClassVar[bool] = True
    requires_vector_db: ClassVar[bool] = True

    _prompt: BasePromptTemplate[Any] = PrivateAttr()
    _llm: BaseLanguageModel[Any] = PrivateAttr()
    _graph: Runnable[SummaryInput, SummaryResult] | None = PrivateAttr(
        default=None
    )

    _pre: Preprocessor | None = PrivateAttr(default=None)
    _qdrant: QdrantClient | None = PrivateAttr(default=None)
    _embedder: Any | None = PrivateAttr(default=None)
    _embedding_dim: int | None = PrivateAttr(default=None)

    def _build_components(self) -> None:
        """
        Build pipeline components that depend on config.

        This is called automatically by model_post_init after the
        config has been validated and assigned.

        Raises:
            ValueError: If prompt cannot be loaded
            RuntimeError: If LLM cannot be initialized
        """
        try:
            prompt_path = self.config.get_prompt_path()
            self._prompt = load_prompt(str(prompt_path))
            logger.info("Loaded prompt: %s", prompt_path)
        except Exception as e:
            raise ValueError(f"Failed to load prompt: {e}") from e

        try:
            if self.config.llm.model_name.startswith("ollama:"):
                from sec_nlp.core.llm import build_ollama_llm

                model_id = self.config.llm.model_name.split(":", 1)[1]
                self._llm = build_ollama_llm(model_name=model_id)
            else:
                from sec_nlp.core.llm import build_hf_pipeline

                self._llm = build_hf_pipeline(self.config.llm.model_name)

            logger.info("Initialized LLM: %s", self.config.llm.model_name)
        except Exception as e:
            raise RuntimeError(f"LLM failed to load: {e}") from e

        try:
            self._graph = build_runnable(
                prompt=self._prompt,
                llm=self._llm,
                input_model=SummaryInput,
                output_model=SummaryResult,
                require_json=self.config.llm.require_json,
            )
            logger.info("Built LLM processing graph")
        except Exception as e:
            logger.warning("Failed to build graph during init: %s", e)
            self._graph = None

    def validate_inputs(self, input_data: SummaryInput) -> None:
        """Validate that all required inputs are available."""
        if not input_data.chunk:
            raise ValueError("Chunk text is required")
        if not input_data.symbol:
            raise ValueError("Symbol is required")
        if not input_data.search_term:
            raise ValueError("Search term is required")

    def _validate_config(self) -> None:
        """Validate configuration settings."""
        if not self.config.symbols:
            raise ValueError("No symbols provided")

        if not self.config.out_path.exists():
            raise ValueError(
                f"Output path does not exist: {self.config.out_path}"
            )

        if not self.config.dl_path.exists():
            raise ValueError(
                f"Download path does not exist: {self.config.dl_path}"
            )

    def run(self, input_data: SummaryInput | None = None) -> SummaryResult:
        """
        Execute the summary pipeline.

        Args:
            input_data: Optional input data. If not provided, processes all configured symbols.

        Returns:
            SummaryResult with outputs and metadata
        """
        try:
            self._validate_config()

            all_outputs: list[Path] = []
            metadata: dict[str, Any] = {}

            for symbol in self.config.symbols:
                symbol_outputs = self._process_symbol(symbol)
                all_outputs.extend(symbol_outputs)
                metadata[symbol] = len(symbol_outputs)

            if self.config.cleanup:
                self._cleanup_downloads()

            return SummaryResult(
                success=True,
                outputs=all_outputs,
                metadata=metadata,
            )

        except Exception as e:
            logger.exception("Pipeline execution failed")
            return SummaryResult(
                success=False,
                error=str(e),
            )

    def _process_symbol(self, symbol: str) -> list[Path]:
        """Process a single symbol."""
        logger.info("Processing symbol: %s", symbol)

        downloader = FilingManager(
            email=self.config.email,
            downloads_folder=self.config.dl_path,
        )
        downloader.add_symbol(symbol)
        downloader.download_filings(
            start_date=self.config.get_date_range()[0],
            end_date=self.config.get_date_range()[1],
            mode=self.config.mode,
        )

        pre = self._get_preprocessor()
        html_paths = pre.html_paths_for_symbol(
            symbol,
            mode=self.config.mode,
            limit=self.config.limit,
        )

        if not html_paths:
            logger.warning("No filings found for %s", symbol)
            return []

        collection_name = self._collection_slug(symbol)
        if not self.config.dry_run:
            self._ensure_collection(collection_name)

        graph = self._get_graph()
        output_files: list[Path] = []

        for html_path in html_paths:
            chunks = pre.transform_html(html_path)
            relevant = [
                c.page_content
                for c in chunks
                if self.config.keyword.lower() in c.page_content.lower()
            ]

            if not relevant:
                logger.warning(
                    "No chunks matched keyword %r in %s",
                    self.config.keyword,
                    html_path.name,
                )
                continue

            metas = [
                {
                    "source": html_path.name,
                    "symbol": symbol,
                    "keyword": self.config.keyword,
                }
                for _ in relevant
            ]
            self._upsert_texts(collection_name, relevant, metadata=metas)

            logger.info(
                "Summarizing %d chunks from %s", len(relevant), html_path.name
            )

            inputs: list[SummaryInput] = [
                SummaryInput(
                    symbol=symbol,
                    chunk=chunk,
                    search_term=self.config.keyword,
                )
                for chunk in relevant
            ]

            summaries: list[dict[str, Any]] = []

            for i in range(0, len(inputs), self.config.batch_size):
                window = inputs[i : i + self.config.batch_size]
                try:
                    results: list[SummaryResult] = graph.batch(window)
                    summaries.extend(r.model_dump() for r in results)
                except Exception as e:
                    logger.error("Batch invocation failed: %s", e)
                    traceback.print_exc()
                    summaries.extend(
                        [
                            {"error": f"Exception: {type(e).__name__}: {e}"}
                            for _ in window
                        ]
                    )

            safe_kw = _slugify(self.config.keyword)
            safe_doc = _safe_name(html_path.stem)
            out_file = (
                self.config.out_path
                / f"{symbol.lower()}_{safe_kw}_{safe_doc}.summary.json"
            )

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "symbol": symbol,
                        "document": html_path.name,
                        "collection": collection_name,
                        "summaries": summaries,
                    },
                    f,
                    indent=2,
                )

            logger.info("Summary written to %s", out_file)
            output_files.append(out_file)

        return output_files

    def _get_preprocessor(self) -> Preprocessor:
        """Get or create preprocessor instance."""
        if self._pre is None:
            self._pre = Preprocessor(downloads_folder=self.config.dl_path)
        return self._pre

    def _get_graph(self) -> Runnable[SummaryInput, SummaryResult]:
        """Get or create LLM processing graph."""
        if self._graph is None:
            self._graph = build_runnable(
                prompt=self._prompt,
                llm=self._llm,
                output_model=SummaryResult,
                input_model=SummaryInput,
                require_json=self.config.llm.require_json,
            )
            logger.info("Built summarization runnable graph (lazy)")
        return self._graph

    def _collection_slug(self, symbol: str) -> str:
        """Generate Qdrant collection name."""
        base_name = _slugify(f"{symbol.upper()}-{self.config.keyword}")
        prefix = self.config.vdb.collection_name
        return f"{prefix}_{base_name}" if prefix else base_name

    def _ensure_qdrant(self) -> QdrantClient:
        """Initialize Qdrant client."""
        if self._qdrant is None:
            if self.config.dry_run:
                logger.info("Dry-run mode: skipping Qdrant")
                return None  # type: ignore

            if self.config.vdb.qdrant_url:
                self._qdrant = QdrantClient(
                    url=self.config.vdb.qdrant_url,
                    api_key=self.config.vdb.qdrant_api_key,
                    timeout=self.config.vdb.qdrant_timeout,
                    prefer_grpc=self.config.vdb.qdrant_prefer_grpc,
                )
            else:
                self._qdrant = QdrantClient(
                    host=self.config.vdb.qdrant_host,
                    port=self.config.vdb.qdrant_port,
                    grpc_port=self.config.vdb.qdrant_grpc_port,
                    api_key=self.config.vdb.qdrant_api_key,
                    timeout=self.config.vdb.qdrant_timeout,
                    prefer_grpc=self.config.vdb.qdrant_prefer_grpc,
                    https=self.config.vdb.qdrant_https,
                )

            logger.info("Connected to Qdrant")

        return self._qdrant

    def _ensure_embedder(self) -> Any:
        """Initialize sentence transformer embedder."""
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            # Use config instead of settings
            self._embedder = SentenceTransformer(
                self.config.vdb.embedding_model,
                device=self.config.vdb.embedding_device,
            )

            if self._embedding_dim is None:
                test_embedding = self._embedder.encode(
                    ["test"], show_progress_bar=False
                )
                self._embedding_dim = len(test_embedding[0])
                logger.info(
                    "Inferred embedding dimension: %d", self._embedding_dim
                )

        return self._embedder

    def _ensure_collection(self, collection_name: str) -> None:
        """Create Qdrant collection if it doesn't exist."""
        client = self._ensure_qdrant()
        self._embedder = self._ensure_embedder()

        collections = client.get_collections().collections
        if any(col.name == collection_name for col in collections):
            logger.info("Using existing collection: %s", collection_name)
            return

        # Use config instead of settings
        vector_size = self.config.vdb.vector_size or self._embedding_dim
        if vector_size is None:
            raise RuntimeError("Could not determine embedding dimension")

        distance_map = {
            "Cosine": Distance.COSINE,
            "Euclid": Distance.EUCLID,
            "Dot": Distance.DOT,
        }
        distance = distance_map.get(
            self.config.vdb.qdrant_distance, Distance.COSINE
        )

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
            on_disk_payload=self.config.vdb.qdrant_on_disk_payload,
            replication_factor=self.config.vdb.qdrant_replication_factor,
            write_consistency_factor=self.config.vdb.qdrant_write_consistency_factor,
        )

        logger.info("Created collection: %s", collection_name)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        if not texts:
            return []

        embedder = self._ensure_embedder()

        embeddings = embedder.encode(
            texts,
            batch_size=self.config.vdb.embedding_batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        return [emb.tolist() for emb in embeddings]

    def _upsert_texts(
        self,
        collection_name: str,
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        """Upsert texts with embeddings into Qdrant."""
        if not texts:
            return []

        if self.config.dry_run:
            logger.info("Dry-run: would upsert %d texts", len(texts))
            return [str(uuid4()) for _ in texts]

        client = self._ensure_qdrant()
        vectors = self._embed_texts(texts)

        if ids is None:
            ids = [str(uuid4()) for _ in texts]
        if metadata is None:
            metadata = [{} for _ in texts]

        points = [
            PointStruct(
                id=point_id,
                vector=vector,
                payload={**meta, "text": text},
            )
            for point_id, vector, text, meta in zip(
                ids, vectors, texts, metadata, strict=True
            )
        ]

        client.upsert(collection_name=collection_name, points=points)
        logger.info("Upserted %d vectors", len(points))

        return ids

    def _cleanup_downloads(self) -> None:
        """Clean up downloaded files."""
        try:
            shutil.rmtree(self.config.dl_path / "sec-edgar-filings")
            logger.info("Cleaned up downloads")
        except Exception as e:
            logger.error("Cleanup failed: %s", e)
