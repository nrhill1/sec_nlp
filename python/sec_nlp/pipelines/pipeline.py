# sec_nlp/pipelines/pipeline.py
import importlib.resources as resources
import json
import logging
import os
import re
import traceback
from collections.abc import Mapping, Sequence
from datetime import date
from importlib.resources import files
from os import fspath
from pathlib import Path
from typing import Any, Self
from uuid import uuid4

from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.loading import load_prompt
from langchain_core.runnables import Runnable
from pinecone import Pinecone, ServerlessSpec
from pydantic import (
    BaseModel,
    Field,
    PrivateAttr,
    computed_field,
    field_validator,
    model_validator,
)

from sec_nlp import __version__
from sec_nlp.chains import (
    SummarizationInput,
    SummarizationOutput,
    build_sec_runnable,
)
from sec_nlp.llms import FlanT5LocalLLM
from sec_nlp.types import FilingMode
from sec_nlp.utils import Preprocessor, SECFilingDownloader

logger = logging.getLogger(__name__)


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", s.lower()).strip("-")


def _safe_name(s: str, allow: str = r"a-zA-Z0-9._-") -> str:
    return re.sub(rf"[^{allow}]+", "_", s)[:120]


def _default_prompt_path() -> Path:
    return Path(fspath(files("sec_nlp.prompts").joinpath("sample_prompt_1.yml")))


class Pipeline(BaseModel):
    """
    End-to-end SEC filing processing pipeline.
    Loads the prompt and builds the runnable graph once; reuses across symbols.
    """

    mode: FilingMode
    start_date: date
    end_date: date
    keyword: str
    model_name: str = "google/flan-t5-base"

    prompt_file: Path = Field(default_factory=_default_prompt_path)
    out_path: Path = Field(default_factory=lambda: Path("./data/output"))
    dl_path: Path = Field(default_factory=lambda: Path("./data/downloads"))

    limit: int | None = None
    max_new_tokens: int = 1024
    require_json: bool = True
    max_retries: int = 2
    batch_size: int = 16

    email: str | None = None
    pinecone_api_key: str | None = None

    pinecone_model: str | None = None
    pinecone_metric: str | None = None
    pinecone_cloud: str | None = None
    pinecone_region: str | None = None
    pinecone_dimension: int | None = None
    pinecone_namespace: str | None = None

    dry_run: bool = False

    _pre: Preprocessor | None = PrivateAttr(default=None)
    _pc: Pinecone | None = PrivateAttr(default=None)
    _index: Any | None = PrivateAttr(default=None)

    _prompt: BasePromptTemplate | None = PrivateAttr(default=None)
    _graph: Runnable[SummarizationInput, SummarizationOutput] | None = PrivateAttr(default=None)

    @field_validator("start_date")
    @classmethod
    def _check_start(cls, v: date) -> date:
        if v > date.today():
            raise ValueError("start_date cannot be in the future.")
        return v

    @field_validator("start_date", "end_date")
    @classmethod
    def _not_too_old(cls, v: date) -> date:
        if v < date(1993, 1, 1):
            raise ValueError("Dates before 1993-01-01 are not supported.")
        return v

    @field_validator("keyword")
    @classmethod
    def _nonempty_keyword(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("keyword must be a non-empty string")
        return v

    @field_validator("prompt_file")
    @classmethod
    def _prompt_valid(cls, p: Path) -> Path:
        if p.exists():
            return p
        try:
            prompt_path = resources.files("sec_nlp.prompts") / "sample_prompt_1.yml"
            if prompt_path.exists():
                logger.warning("Using built-in prompt file: %s", fspath(prompt_path))
                return Path(fspath(prompt_path))
            raise ValueError(f"Prompt file does not exist: {p}")
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Prompt file not found: {p}") from e

    @field_validator("out_path", "dl_path")
    @classmethod
    def _ensure_dirs(cls, v: Path) -> Path:
        v = Path(v)
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("limit")
    @classmethod
    def _positive_limit(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            raise ValueError("limit must be a positive integer when provided")
        return v

    @field_validator("max_new_tokens", "max_retries", "batch_size")
    @classmethod
    def _positive_ints(cls, v: int) -> int:
        if int(v) <= 0:
            raise ValueError("must be a positive integer")
        return int(v)

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.start_date > self.end_date:
            raise ValueError("start_date cannot be after end_date.")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def keyword_lower(self) -> str:
        return self.keyword.lower()

    def _index_slug(self, symbol: str) -> str:
        return _slugify(f"{symbol.upper()}-{self.keyword}-docs")

    def model_post_init(self, __ctx: Any) -> None:
        if self.email is None:
            self.email = os.getenv("EMAIL", "xxxxxx_xxxx@gmail.com")

        if self.pinecone_api_key is None:
            self.pinecone_api_key = os.getenv("PINECONE_API_KEY")

        self.pinecone_model = self.pinecone_model or os.getenv(
            "PINECONE_MODEL", "multilingual-e5-large"
        )
        self.pinecone_metric = self.pinecone_metric or os.getenv("PINECONE_METRIC", "cosine")
        self.pinecone_cloud = self.pinecone_cloud or os.getenv("PINECONE_CLOUD", "aws")
        self.pinecone_region = self.pinecone_region or os.getenv("PINECONE_REGION", "us-east-1")

        dim_env = os.getenv("PINECONE_DIMENSION")
        if self.pinecone_dimension is None and dim_env:
            try:
                self.pinecone_dimension = int(dim_env)
            except ValueError:
                logger.warning("Invalid PINECONE_DIMENSION=%r; will infer at runtime.", dim_env)

        ns_env = os.getenv("PINECONE_NAMESPACE")
        if self.pinecone_namespace is None and ns_env:
            self.pinecone_namespace = ns_env

        if not self.dry_run and not self.pinecone_api_key:
            raise ValueError("PINECONE_API_KEY not set and dry_run is False.")

        try:
            self._prompt = load_prompt(self.prompt_file)
            logger.info("Loaded prompt: %s", self.prompt_file)
        except Exception as e:
            raise ValueError(f"Failed to load prompt from {self.prompt_file}: {e}") from e

        logger.info(
            "Pipeline initialized: sec_nlp %s \n Python %s",
            __version__,
            os.sys.version.split()[0],
        )

    def reload_prompt(self, path: Path | None = None) -> None:
        if path is not None:
            self.prompt_file = path
        self._prompt = load_prompt(self.prompt_file)
        self._graph = None
        logger.info("Reloaded prompt: %s", self.prompt_file)

    def _get_preprocessor(self) -> Preprocessor:
        if self._pre is None:
            self._pre = Preprocessor(downloads_folder=self.dl_path)
        return self._pre

    def _ensure_pinecone(self) -> Pinecone:
        if self._pc is None:
            self._pc = Pinecone(api_key=str(self.pinecone_api_key))
        return self._pc

    def _ensure_index(self, index_name: str) -> None:
        pc = self._ensure_pinecone()
        if self.pinecone_dimension is None:
            dim = self._infer_dimension(str(self.pinecone_model))
            self.pinecone_dimension = int(dim)
            logger.info(
                "Inferred embedding dimension for %s = %d",
                self.pinecone_model,
                self.pinecone_dimension,
            )
        if not pc.has_index(index_name):
            logger.info("Creating Pinecone index: %s", index_name)
            pc.create_index(
                name=index_name,
                dimension=int(self.pinecone_dimension),
                metric=str(self.pinecone_metric),
                spec=ServerlessSpec(
                    cloud=str(self.pinecone_cloud), region=str(self.pinecone_region)
                ),
            )
        self._index = pc.Index(index_name)
        logger.info("Using Pinecone index: %s", index_name)

    def _infer_dimension(self, model: str) -> int:
        pc = self._ensure_pinecone()
        vecs: Any = pc.inference.embed(model=model, inputs=["ok"])
        data = getattr(vecs, "data", None) or (
            vecs.get("data", []) if isinstance(vecs, Mapping) else []
        )
        if not data or not (data[0].get("values") or data[0].get("embedding")):
            raise RuntimeError(f"Could not infer embedding dimension for model: {model}")
        values: Sequence[float] = data[0].get("values") or data[0].get("embedding")
        return len(values)

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        pc = self._ensure_pinecone()
        res: Any = pc.inference.embed(model=str(self.pinecone_model), inputs=texts)
        rows = getattr(res, "data", []) or (res.get("data", []) if isinstance(res, Mapping) else [])
        return [list(row.get("values") or row.get("embedding") or []) for row in rows]

    def _upsert_texts(
        self,
        texts: list[str],
        metadata: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
        namespace: str | None = None,
    ) -> list[str]:
        if not texts:
            return []
        vectors = self._embed_texts(texts)
        if ids is None:
            ids = [str(uuid4()) for _ in texts]
        if metadata is None:
            metadata = [{} for _ in texts]

        payload: list[dict[str, Any]] = []
        for _id, vec, meta in zip(ids, vectors, metadata, strict=True):
            payload.append({"id": _id, "values": vec, "metadata": meta or {}})

        assert self._index is not None, "Pinecone index not initialized"
        self._index.upsert(vectors=payload, namespace=namespace)

        logger.info(
            "Upserted %d vectors into index %s",
            len(payload),
            getattr(self._index, "name", "<index>"),
        )
        return ids

    def _get_graph(self) -> Runnable[SummarizationInput, SummarizationOutput]:
        """
        Build once, reuse across symbols. Rebuilt only if reload_prompt() is called.
        """
        if self._graph is None:
            if self._prompt is None:
                # Defensive: should be set in model_post_init
                self._prompt = load_prompt(self.prompt_file)

            llm = FlanT5LocalLLM(
                model_name=self.model_name,
                device="cpu",
                max_new_tokens=int(self.max_new_tokens),
            )

            self._graph = build_sec_runnable(
                prompt=self._prompt,
                llm=llm,
                require_json=bool(self.require_json),
            )
            logger.info("Built summarization runnable graph.")
        return self._graph

    def run_all(self, symbols: list[str]) -> dict[str, list[Path]]:
        out: dict[str, list[Path]] = {}
        for sym in symbols:
            out[sym] = self.run(sym)
        return out

    def run(self, symbol: str) -> list[Path]:
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

        downloader = SECFilingDownloader(email=str(self.email), downloads_folder=self.dl_path)
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

        if not self.dry_run:
            logger.info("Provisioning Pinecone index for %s...", symbol)
            index_name = self._index_slug(symbol)
            self._ensure_index(index_name)
        else:
            logger.info("Dry-run set: skipping Pinecone index provisioning and upserts.")

        output_files: list[Path] = []

        for html_path in html_paths:
            chunks = pre.transform_html(html_path)
            relevant = [c for c in chunks if self.keyword_lower in c.page_content.lower()]
            if not relevant:
                logger.warning("No chunks matched keyword %r in %s.", self.keyword, html_path.name)
                continue

            texts = [c.page_content for c in relevant]
            metas = [{"source": html_path.name} for _ in relevant]

            if not self.dry_run:
                self._upsert_texts(texts, metadata=metas, namespace=self.pinecone_namespace)

            logger.info(
                "%d relevant chunks found in %s. Summarizing...",
                len(relevant),
                html_path.name,
            )

            inputs: list[SummarizationInput] = [
                {"symbol": symbol, "chunk": t, "search_term": self.keyword} for t in texts
            ]
            summaries: list[dict[str, Any]] = []

            for i in range(0, len(inputs), int(self.batch_size)):
                window = inputs[i : i + int(self.batch_size)]
                try:
                    results: list[SummarizationOutput] = graph.batch(window)
                    for r in results:
                        payload_dict = r.get(
                            "summary",
                            {
                                "summary": "(null)",
                                "error": "No summary payload returned.",
                            },
                        )
                        summaries.append(payload_dict)
                except Exception as e:
                    logger.error("Batch invocation failed: %s: %s", type(e).__name__, e)
                    traceback.print_exc()
                    summaries.extend(
                        [
                            {
                                "summary": None,
                                "error": f"Exception: {type(e).__name__}: {e}",
                            }
                            for _ in window
                        ]
                    )

            safe_kw = re.sub(r"[^a-z0-9_-]+", "_", self.keyword_lower)
            safe_doc = _safe_name(html_path.stem)
            out_file = self.out_path / f"{symbol.lower()}_{safe_kw}_{safe_doc}.summary.json"

            with open(out_file, "w") as f:
                json.dump(
                    {
                        "symbol": symbol,
                        "document": html_path.name,
                        "summaries": summaries,
                    },
                    f,
                    indent=2,
                )

            logger.info("Summary written to %s", out_file.resolve())
            output_files.append(out_file)

        return output_files
