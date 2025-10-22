# sec_nlp/core/pipeline.py
from __future__ import annotations

import json
import os
import re
import sys
import traceback
from datetime import date
from importlib.metadata import PackageNotFoundError, version
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.loading import load_prompt
from langchain_core.runnables import Runnable
from platformdirs import user_cache_dir, user_data_dir
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    computed_field,
    field_validator,
    model_validator,
)
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from sec_nlp.core.config import get_logger, settings
from sec_nlp.core.downloader import FilingManager
from sec_nlp.core.enums import FilingMode
from sec_nlp.core.llm.chains import (
    SummarizationInput,
    SummarizationOutput,
    SummarizationResult,
    build_summarization_runnable,
)
from sec_nlp.core.preprocessor import Preprocessor

logger = get_logger(__name__)


def _get_version() -> str:
    """Get package version using importlib.metadata."""
    try:
        return version("sec_nlp")
    except PackageNotFoundError:
        return "0.0.0.dev"


def _slugify(s: str) -> str:
    """Convert string to URL-safe slug."""
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")


def _safe_name(s: str, allow: str = r"a-zA-Z0-9._-") -> str:
    """Sanitize string for use in filenames."""
    return re.sub(rf"[^{allow}]+", "_", s)[:120]


def default_prompt_path() -> Path:
    """
    Get path to default prompt file from package resources.

    Uses importlib.resources to access the packaged prompt file.
    Works with both regular installs and zip-based distributions.

    Returns:
        Path to sample_prompt_1.yml
    """
    prompt_resource = files("sec_nlp.core.config.prompts") / "sample_prompt_1.yml"

    with as_file(prompt_resource) as prompt_path:
        # For zip installations, as_file extracts to a temp location
        # We need to return a Path that exists beyond the context
        return Path(prompt_path)


def default_output_path() -> Path:
    """
    Get default output directory using platformdirs.

    Returns platform-specific user data directory:
    - Linux: ~/.local/share/sec_nlp/output
    - macOS: ~/Library/Application Support/sec_nlp/output
    - Windows: %LOCALAPPDATA%\\sec_nlp\\output

    Returns:
        Path to user data directory for output files
    """
    output_dir = Path(user_data_dir("sec_nlp", "sec_nlp")) / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def default_download_path() -> Path:
    """
    Get default download directory using platformdirs.

    Returns platform-specific user cache directory:
    - Linux: ~/.cache/sec_nlp/downloads
    - macOS: ~/Library/Caches/sec_nlp/downloads
    - Windows: %LOCALAPPDATA%\\sec_nlp\\Cache\\downloads

    Returns:
        Path to user cache directory for downloads
    """
    download_dir = Path(user_cache_dir("sec_nlp", "sec_nlp")) / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    return download_dir


class Pipeline(BaseModel):
    """
    End-to-end SEC filing processing pipeline.

    Features:
    - Downloads SEC filings (10-K, 10-Q)
    - Processes and chunks documents
    - Filters by keyword
    - Generates LLM summaries
    - Stores embeddings in Qdrant vector database

    All paths use platform-appropriate locations:
    - prompt_file: from package resources (importlib.resources)
    - out_path: user data directory (platformdirs)
    - dl_path: user cache directory (platformdirs)
    """

    mode: FilingMode
    start_date: date
    end_date: date
    keyword: str
    model_name: str = "google/flan-t5-base"

    prompt_file: Path = Field(default_factory=default_prompt_path)
    out_path: Path = Field(default_factory=default_output_path)
    dl_path: Path = Field(default_factory=default_download_path)

    limit: int | None = None
    max_new_tokens: int = 1024
    require_json: bool = True
    max_retries: int = 2
    batch_size: int = 16

    email: str | None = None
    collection_name: str | None = None

    dry_run: bool = False

    _prompt: BasePromptTemplate[Any]
    _llm: BaseLanguageModel[Any]
    _pre: Preprocessor | None = PrivateAttr(default=None)
    _qdrant: QdrantClient | None = PrivateAttr(default=None)
    _embedder: Any | None = PrivateAttr(default=None)
    _embedding_dim: int | None = PrivateAttr(default=None)
    _graph: Runnable[SummarizationInput, SummarizationOutput] | None = PrivateAttr(default=None)

    @field_validator("start_date")
    @classmethod
    def _check_start(cls, v: date) -> date:
        """Validate start_date is not in the future."""
        if v > date.today():
            raise ValueError("start_date cannot be in the future.")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def _not_too_old(cls, v: date) -> date:
        """Validate dates are not before SEC EDGAR system launch."""
        if v < date(1993, 1, 1):
            raise ValueError("Dates before 1993-01-01 are not supported.")
        return v

    @field_validator("keyword")
    @classmethod
    def _nonempty_keyword(cls, v: str) -> str:
        """Validate keyword is non-empty."""
        v = (v or "").strip()
        if not v:
            raise ValueError("keyword must be a non-empty string")
        return v

    @field_validator("prompt_file")
    @classmethod
    def _validate_prompt_file(cls, p: Path) -> Path:
        """
        Validate prompt file exists.

        For custom user-provided paths, checks filesystem.
        For default prompt, uses package resources via importlib.resources.
        """
        p = Path(p).resolve()

        if p.exists() and p.is_file():
            return p

        try:
            prompt_resource = files("sec_nlp.core.config.prompts") / "sample_prompt_1.yml"
            with as_file(prompt_resource) as default_path:
                default_path = Path(default_path)
                if default_path.exists():
                    logger.info("Using default prompt from package resources")
                    return default_path
        except Exception as e:
            logger.error("Failed to load default prompt: %s", e)

        raise FileNotFoundError("Prompt file not found: %s", p)

    @field_validator("out_path", "dl_path")
    @classmethod
    def _ensure_dirs(cls, v: Path) -> Path:
        """
        Ensure directory exists, creating if necessary.

        Resolves to absolute path and creates parent directories.
        """
        v = Path(v).resolve()
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("limit")
    @classmethod
    def _positive_limit(cls, v: int | None) -> int | None:
        """Validate limit is positive if provided."""
        if v is not None and v <= 0:
            raise ValueError("limit must be a positive integer when provided")
        return v

    @field_validator("max_new_tokens", "max_retries", "batch_size")
    @classmethod
    def _positive_ints(cls, v: int) -> int:
        """Validate integer fields are positive."""
        if v <= 0:
            raise ValueError("must be a positive integer")
        return v

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        """Validate date range is valid."""
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def keyword_lower(self) -> str:
        """Get lowercase version of keyword for case-insensitive matching."""
        return self.keyword.lower()

    def _collection_slug(self, symbol: str) -> str:
        """
        Generate Qdrant collection name for symbol and keyword.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Collection name string
        """
        base_name = _slugify(f"{symbol.upper()}-{self.keyword}")
        prefix = settings.qdrant_collection_prefix
        return f"{prefix}_{base_name}" if prefix else base_name

    def model_post_init(self, __ctx: Any) -> None:
        """Initialize pipeline after Pydantic validation."""
        if self.email is None:
            self.email = os.getenv("EMAIL", settings.email)

        try:
            self._prompt = load_prompt(str(self.prompt_file))
            logger.info("Loaded prompt: %s", self.prompt_file)
        except Exception as e:
            raise ValueError("Failed to load prompt from %s: %s", self.prompt_file, e) from e

        try:
            if self.model_name.startswith("ollama:"):
                from sec_nlp.core.llm import build_ollama_llm

                model_id = self.model_name.split(":", 1)[1]
                self._llm = build_ollama_llm(model_name=model_id)
            else:
                from sec_nlp.core.llm import FlanT5LocalLLM

                self._llm = FlanT5LocalLLM(
                    model_name=self.model_name,
                    device="cpu",
                    max_new_tokens=int(self.max_new_tokens),
                )
        except Exception as e:
            raise RuntimeError(
                "%s -- LLM failed to load %s", type(e).__name__, self.model_name
            ) from e

        pkg_version = _get_version()
        python_version = sys.version.split()[0]
        logger.info("Pipeline initialized: sec_nlp %s | Python %s", pkg_version, python_version)
        logger.info("Output directory: %s", self.out_path)
        logger.info("Download directory: %s", self.dl_path)

    def _get_preprocessor(self) -> Preprocessor:
        """Get or create preprocessor instance (lazy initialization)."""
        if self._pre is None:
            self._pre = Preprocessor(downloads_folder=self.dl_path)
        return self._pre

    def _ensure_qdrant(self) -> QdrantClient:
        """Initialize Qdrant client if not already initialized."""
        if self._qdrant is None:
            if self.dry_run:
                logger.info("Dry-run mode: skipping Qdrant client initialization")
                return None  # type: ignore[return-value]

            # Build connection parameters from settings
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

            logger.info(
                "Connected to Qdrant: %s",
                settings.qdrant_url or f"{settings.qdrant_host}:{settings.qdrant_port}",
            )

        return self._qdrant

    def _ensure_embedder(self) -> Any:
        """Initialize sentence transformer embedder."""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise ImportError(
                    "sentence-transformers not installed. Run: uv pip install sentence-transformers"
                ) from e

            self._embedder = SentenceTransformer(
                settings.embedding_model, device=settings.embedding_device
            )

            # Infer embedding dimension
            if self._embedding_dim is None:
                test_embedding = self._embedder.encode(["test"], show_progress_bar=False)
                self._embedding_dim = len(test_embedding[0])
                logger.info(
                    "Inferred embedding dimension: %d for model %s",
                    self._embedding_dim,
                    settings.embedding_model,
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

        logger.info(
            "Created Qdrant collection: %s (dimension=%d, distance=%s)",
            collection_name,
            vector_size,
            settings.qdrant_distance,
        )

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
        """Upsert texts with embeddings into Qdrant collection."""
        if not texts:
            return []

        if self.dry_run:
            logger.info(
                "Dry-run: would upsert %d texts to collection %s", len(texts), collection_name
            )
            return [str(uuid4()) for _ in texts]

        client = self._ensure_qdrant()
        vectors = self._embed_texts(texts)

        if ids is None:
            ids = [str(uuid4()) for _ in texts]
        if metadata is None:
            metadata = [{} for _ in texts]

        # Create points
        points = [
            PointStruct(
                id=point_id,
                vector=vector,
                payload={**meta, "text": text},
            )
            for point_id, vector, text, meta in zip(ids, vectors, texts, metadata, strict=True)
        ]

        # Upsert to Qdrant
        client.upsert(collection_name=collection_name, points=points)

        logger.info("Upserted %d vectors to collection %s", len(points), collection_name)
        return ids

    def _get_graph(self) -> Runnable[SummarizationInput, SummarizationOutput]:
        """Get or create LLM processing graph."""
        if self._graph is None:
            self._graph = build_summarization_runnable(
                prompt=self._prompt,
                llm=self._llm,
                require_json=bool(self.require_json),
            )
            logger.info("Built summarization runnable graph.")

        return self._graph

    def run_all(self, symbols: list[str]) -> dict[str, list[Path]]:
        """
        Run pipeline for multiple symbols.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            Dictionary mapping symbols to output file paths
        """
        return {sym: self.run(sym) for sym in symbols}

    def run(self, symbol: str) -> list[Path]:
        """
        Run pipeline for a single symbol.

        Process flow:
        1. Download SEC filings
        2. Parse and chunk documents
        3. Filter chunks by keyword
        4. Generate embeddings and store in Qdrant
        5. Generate LLM summaries
        6. Write results to JSON files

        Args:
            symbol: Stock ticker symbol

        Returns:
            List of output file paths
        """
        logger.info("Processing symbol: %s", symbol)
        symbol = symbol.strip().upper()

        logger.info(
            "Pipeline start: %s (%s → %s) mode=%s (form=%s) keyword=%r dry_run=%s",
            symbol,
            self.start_date,
            self.end_date,
            self.mode.value,
            self.mode.form,
            self.keyword,
            self.dry_run,
        )

        downloader = FilingManager(email=str(self.email), downloads_folder=self.dl_path)
        downloader.add_symbol(symbol)
        downloader.download_filings(
            start_date=self.start_date,
            end_date=self.end_date,
            mode=self.mode,
        )

        pre = self._get_preprocessor()
        html_paths = pre.html_paths_for_symbol(symbol, mode=self.mode, limit=self.limit)
        if not html_paths:
            logger.warning("No filings found for %s. Skipping...", symbol)
            return []

        graph = self._get_graph()

        collection_name = self.collection_name or self._collection_slug(symbol)

        if not self.dry_run:
            logger.info("Provisioning Qdrant collection: %s", collection_name)
            self._ensure_collection(collection_name)
        else:
            logger.info("Dry-run: skipping Qdrant collection provisioning and upserts.")

        output_files: list[Path] = []

        for html_path in html_paths:
            chunks = pre.transform_html(html_path)
            relevant = [c for c in chunks if self.keyword_lower in c.page_content.lower()]

            if not relevant:
                logger.warning("No chunks matched keyword %r in %s.", self.keyword, html_path.name)
                continue

            texts = [c.page_content for c in relevant]
            metas = [
                {"source": html_path.name, "symbol": symbol, "keyword": self.keyword}
                for _ in relevant
            ]

            self._upsert_texts(collection_name, texts, metadata=metas)

            logger.info(
                "%d relevant chunks found in %s. Summarizing...",
                len(relevant),
                html_path.name,
            )

            inputs: list[SummarizationInput] = [
                {"symbol": symbol, "chunk": t, "search_term": self.keyword} for t in texts
            ]
            summaries: list[SummarizationResult] = []

            for i in range(0, len(inputs), int(self.batch_size)):
                window = inputs[i : i + int(self.batch_size)]
                try:
                    results: list[SummarizationOutput] = graph.batch(window)
                    for r in results:
                        result_dict: SummarizationResult = r.get(
                            "summary",
                            SummarizationResult(
                                summary="(null)", error="No summary payload returned."
                            ),
                        )
                        summaries.append(result_dict)
                except Exception as e:
                    logger.error("Batch invocation failed: %s: %s", type(e).__name__, e)
                    traceback.print_exc()
                    summaries.extend(
                        [
                            SummarizationResult(
                                summary="(null)", error=f"Exception: {type(e).__name__}: {e}"
                            )
                            for _ in window
                        ]
                    )

            safe_kw = _slugify(self.keyword)
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

            logger.info("Summary written to %s", out_file.resolve())
            output_files.append(out_file)

        return output_files
