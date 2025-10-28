# sec_nlp/pipelines/summary.py
"""SEC filing summarization pipeline."""

from __future__ import annotations

import json
import re
import shutil
import traceback
from datetime import date, datetime, timedelta
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.loading import load_prompt
from langchain_core.runnables import Runnable
from pydantic import Field, PrivateAttr, SettingsConfigDict, field_validator, model_validator
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from sec_nlp.core import FilingManager, FilingMode, Preprocessor, get_logger, settings
from sec_nlp.core.llm.chains import (
    SummarizationInput,
    SummarizationOutput,
    build_summarization_runnable,
)
from sec_nlp.pipelines.base import BaseConfig, BasePipeline, BaseResult
from sec_nlp.pipelines.registry import PipelineRegistry

logger = get_logger(__name__)


def _slugify(s: str) -> str:
    """Convert string to URL-safe slug."""
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")


def _safe_name(s: str, allow: str = r"a-zA-Z0-9._-") -> str:
    """Sanitize string for use in filenames."""
    return re.sub(rf"[^{allow}]+", "_", s)[:120]


class SummaryConfig(BaseConfig):
    """Configuration for SEC filing summarization pipeline."""

    model_config = SettingsConfigDict(
        env_prefix="SUMMARY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    pipeline_type: Literal["summary"] = "summary"

    symbols: list[str] = Field(
        ...,
        description="Stock ticker symbols to process",
        min_length=1,
    )

    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Filing type: annual (10-K) or quarterly (10-Q)",
    )
    start_date: date | None = Field(
        default=None,
        description="Start date for filing search (YYYY-MM-DD)",
    )
    end_date: date | None = Field(
        default=None,
        description="End date for filing search (YYYY-MM-DD)",
    )
    keyword: str = Field(
        default="revenue",
        description="Keyword to filter filing chunks",
        min_length=1,
    )

    model_name: str = Field(
        default="google/flan-t5-base",
        description="LLM model name (HuggingFace or 'ollama:model-name')",
    )
    prompt_file: Path | None = Field(
        default=None,
        description="Path to custom prompt YAML file",
    )
    max_new_tokens: int = Field(
        default=1024,
        ge=1,
        le=8192,
        description="Maximum tokens for LLM generation",
    )
    require_json: bool = Field(
        default=True,
        description="Require JSON-formatted output from LLM",
    )

    limit: int | None = Field(
        default=1,
        ge=1,
        description="Maximum number of filings to process per symbol",
    )
    batch_size: int = Field(
        default=16,
        ge=1,
        le=128,
        description="Number of chunks to process in parallel",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed LLM calls",
    )

    fresh: bool = Field(
        default=False,
        description="Clear existing output and download folders",
    )
    cleanup: bool = Field(
        default=True,
        description="Clean up downloaded files after processing",
    )

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, v: list[str] | str) -> list[str]:
        """Normalize symbols to uppercase."""
        if isinstance(v, str):
            v = [v]
        return [s.strip().upper() for s in v]

    @field_validator("keyword")
    @classmethod
    def validate_keyword(cls, v: str) -> str:
        """Validate keyword is non-empty."""
        v = v.strip()
        if not v:
            raise ValueError("keyword must be non-empty")
        return v.lower()

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def parse_date(cls, v: str | date | None) -> date | None:
        """Parse date string to date object."""
        if v is None or isinstance(v, date):
            return v
        if isinstance(v, str):
            return date.fromisoformat(v)
        raise ValueError(f"Invalid date format: {v}")

    @model_validator(mode="after")
    def validate_date_range(self) -> None:
        """Validate date range is valid."""
        start, end = self.get_date_range()
        if start > end:
            raise ValueError("start_date cannot be after end_date")
        if start < date(1993, 1, 1):
            raise ValueError("start_date cannot be before 1993-01-01 (SEC EDGAR launch)")
        if end > date.today():
            raise ValueError("end_date cannot be in the future")

    @field_validator("prompt_file", mode="after")
    @classmethod
    def validate_prompt_file(cls, v: Path | None) -> Path | None:
        """Validate prompt file exists if provided."""
        if v is not None and not v.exists():
            raise ValueError(f"Prompt file not found: {v}")
        return v

    def validate_config(self) -> None:
        """Validate pipeline-specific configuration."""
        # All validation handled by Pydantic validators
        pass

    def get_date_range(self) -> tuple[date, date]:
        """Get computed date range with defaults."""
        today = datetime.today().date()
        one_year_ago = today - timedelta(days=365)
        start = self.start_date or one_year_ago
        end = self.end_date or today
        return start, end

    def get_prompt_path(self) -> Path | None:
        """Get resolved prompt file path."""
        return self.prompt_file

    def to_pipeline_kwargs(self) -> dict[str, Any]:
        """Convert config to pipeline constructor kwargs."""
        start, end = self.get_date_range()
        return {
            "mode": self.mode,
            "start_date": start,
            "end_date": end,
            "keyword": self.keyword,
            "prompt_file": self.get_prompt_path(),
            "model_name": self.model_name,
            "max_new_tokens": self.max_new_tokens,
            "require_json": self.require_json,
            "limit": self.limit,
            "batch_size": self.batch_size,
            "max_retries": self.max_retries,
            "dry_run": self.dry_run,
        }


class SummaryResult(BaseResult): ...


@PipelineRegistry.register("summary")
class SummaryPipeline(BasePipeline[SummaryConfig, SummaryResult]):
    """Pipeline for SEC filing summarization with LLM."""

    description = "Download, parse, and summarize SEC filings using LLMs"
    requires_model = True
    requires_vector_db = True

    out_path: Path
    dl_path: Path

    _prompt: BasePromptTemplate[Any] = PrivateAttr()
    _llm: BaseLanguageModel[Any] = PrivateAttr()
    _pre: Preprocessor | None = PrivateAttr(default=None)
    _qdrant: QdrantClient | None = PrivateAttr(default=None)
    _embedder: Any | None = PrivateAttr(default=None)
    _embedding_dim: int | None = PrivateAttr(default=None)
    _graph: Runnable[SummarizationInput, SummarizationOutput] | None = PrivateAttr(default=None)

    def __init__(
        self,
        config: SummaryConfig,
        out_path: Path | None = None,
        dl_path: Path | None = None,
    ) -> None:
        """Initialize summary pipeline."""
        # Use importlib.resources for default paths
        if out_path is None:
            data_pkg = files("sec_nlp") / "data"
            with as_file(data_pkg) as data_dir:
                out_path = Path(data_dir) / "output"
                out_path.mkdir(parents=True, exist_ok=True)

        if dl_path is None:
            data_pkg = files("sec_nlp") / "data"
            with as_file(data_pkg) as data_dir:
                dl_path = Path(data_dir) / "downloads"
                dl_path.mkdir(parents=True, exist_ok=True)

        self.out_path = out_path
        self.dl_path = dl_path

        super().__init__(config)

        # Load prompt
        try:
            self._prompt = load_prompt(str(config.get_prompt_path()))
            logger.info("Loaded prompt: %s", config.get_prompt_path())
        except Exception as e:
            raise ValueError(f"Failed to load prompt: {e}") from e

        # Initialize LLM
        try:
            if config.model_name.startswith("ollama:"):
                from sec_nlp.core.llm import build_ollama_llm

                model_id = config.model_name.split(":", 1)[1]
                self._llm = build_ollama_llm(model_name=model_id)
            else:
                from sec_nlp.core.llm import build_hf_pipeline

                self._llm = build_hf_pipeline(config.model_name)
        except Exception as e:
            raise RuntimeError(f"LLM failed to load: {e}") from e

    def validate_inputs(self) -> None:
        """Validate that all required inputs are available."""
        if not self.config.symbols:
            raise ValueError("No symbols provided")

        if not self.out_path.exists():
            raise ValueError(f"Output path does not exist: {self.out_path}")

        if not self.dl_path.exists():
            raise ValueError(f"Download path does not exist: {self.dl_path}")

    def run(self, **kwargs: Any) -> SummaryResult:
        """Execute the summary pipeline."""
        try:
            self.validate_inputs()

            all_outputs: list[Path] = []
            metadata: dict[str, Any] = {}

            for symbol in self.config.symbols:
                symbol_outputs = self._process_symbol(symbol)
                all_outputs.extend(symbol_outputs)
                metadata[symbol] = len(symbol_outputs)

            # Cleanup if requested
            if self.config.cleanup:
                self._cleanup_downloads()

            return SummaryResult(
                success=True,
                pipeline_type=self.pipeline_type,
                outputs=all_outputs,
                metadata=metadata,
            )

        except Exception as e:
            logger.exception("Pipeline execution failed")
            return SummaryResult(
                success=False,
                pipeline_type=self.pipeline_type,
                error=str(e),
            )

    def _process_symbol(self, symbol: str) -> list[Path]:
        """Process a single symbol."""
        logger.info("Processing symbol: %s", symbol)

        # Download filings
        downloader = FilingManager(
            email=settings.email,
            downloads_folder=self.dl_path,
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

            logger.info("Summarizing %d chunks from %s", len(relevant), html_path.name)

            inputs: list[SummarizationInput] = [
                SummarizationInput(
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
                    results: list[SummarizationOutput] = graph.batch(window)
                    summaries.extend(r.model_dump() for r in results)
                except Exception as e:
                    logger.error("Batch invocation failed: %s", e)
                    traceback.print_exc()
                    summaries.extend(
                        [{"error": f"Exception: {type(e).__name__}: {e}"} for _ in window]
                    )

            safe_kw = _slugify(self.config.keyword)
            safe_doc = _safe_name(html_path.stem)
            out_file = self.out_path / f"{symbol.lower()}_{safe_kw}_{safe_doc}.summary.json"

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
            self._pre = Preprocessor(downloads_folder=self.dl_path)
        return self._pre

    def _get_graph(self) -> Runnable[SummarizationInput, SummarizationOutput]:
        """Get or create LLM processing graph."""
        if self._graph is None:
            self._graph = build_summarization_runnable(
                prompt=self._prompt,
                llm=self._llm,
                require_json=self.config.require_json,
            )
            logger.info("Built summarization runnable graph")
        return self._graph

    def _collection_slug(self, symbol: str) -> str:
        """Generate Qdrant collection name."""
        base_name = _slugify(f"{symbol.upper()}-{self.config.keyword}")
        prefix = settings.qdrant_collection_prefix
        return f"{prefix}_{base_name}" if prefix else base_name

    def _ensure_qdrant(self) -> QdrantClient:
        """Initialize Qdrant client."""
        if self._qdrant is None:
            if self.config.dry_run:
                logger.info("Dry-run mode: skipping Qdrant")
                return None  # type: ignore

            if settings.qdrant_url:
                self._qdrant = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key,
                    timeout=settings.qdrant_timeout,
                    prefer_grpc=settings.qdrant_prefer_grpc,
                )
            else:
                self._qdrant = QdrantClient(
                    host=settings.qdrant_host,
                    port=settings.qdrant_port,
                    grpc_port=settings.qdrant_grpc_port,
                    api_key=settings.qdrant_api_key,
                    timeout=settings.qdrant_timeout,
                    prefer_grpc=settings.qdrant_prefer_grpc,
                    https=settings.qdrant_https,
                )

            logger.info("Connected to Qdrant")

        return self._qdrant

    def _ensure_embedder(self) -> Any:
        """Initialize sentence transformer embedder."""
        if self._embedder is None:
            from sentence_transformers import SentenceTransformer

            self._embedder = SentenceTransformer(
                settings.embedding_model,
                device=settings.embedding_device,
            )

            if self._embedding_dim is None:
                test_embedding = self._embedder.encode(["test"], show_progress_bar=False)
                self._embedding_dim = len(test_embedding[0])
                logger.info("Inferred embedding dimension: %d", self._embedding_dim)

        return self._embedder

    def _ensure_collection(self, collection_name: str) -> None:
        """Create Qdrant collection if it doesn't exist."""
        client = self._ensure_qdrant()
        self._embedder = self._ensure_embedder()

        collections = client.get_collections().collections
        if any(col.name == collection_name for col in collections):
            logger.info("Using existing collection: %s", collection_name)
            return

        vector_size = settings.qdrant_vector_size or self._embedding_dim
        if vector_size is None:
            raise RuntimeError("Could not determine embedding dimension")

        distance_map = {
            "Cosine": Distance.COSINE,
            "Euclid": Distance.EUCLID,
            "Dot": Distance.DOT,
        }
        distance = distance_map.get(settings.qdrant_distance, Distance.COSINE)

        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=distance),
            on_disk_payload=settings.qdrant_on_disk_payload,
            replication_factor=settings.qdrant_replication_factor,
            write_consistency_factor=settings.qdrant_write_consistency_factor,
        )

        logger.info("Created collection: %s", collection_name)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts."""
        if not texts:
            return []

        embedder = self._ensure_embedder()
        embeddings = embedder.encode(
            texts,
            batch_size=settings.embedding_batch_size,
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
            for point_id, vector, text, meta in zip(ids, vectors, texts, metadata, strict=True)
        ]

        client.upsert(collection_name=collection_name, points=points)
        logger.info("Upserted %d vectors", len(points))

        return ids

    def _cleanup_downloads(self) -> None:
        """Clean up downloaded files."""
        try:
            shutil.rmtree(self.dl_path / "sec-edgar-filings")
            logger.info("Cleaned up downloads")
        except Exception as e:
            logger.error("Cleanup failed: %s", e)
