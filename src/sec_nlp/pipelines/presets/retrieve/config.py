"""Config model for retrieve pipeline."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.vector.config import VectorConfig


class RetrieveSettings(BasePipelineSettings):
    """Configuration for EFTS-first retrieval pipeline."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_RETRIEVE_")

    pipeline_type: ClassVar[Literal["retrieve"]] = "retrieve"

    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Default filing mode when forms are not explicitly set.",
    )
    forms: list[str] | None = Field(
        default_factory=lambda: ["10-K", "10-Q"],
        description="SEC forms to include in retrieval candidate search.",
    )
    queries: list[str] = Field(
        default_factory=list,
        description="User retrieval queries to execute.",
        json_schema_extra={
            "cli_args": {
                "nargs": "+",
                "action": "extend",
                "aliases": ["--q", "--query", "--queries"],
            }
        },
    )
    sections: list[str] = Field(
        default_factory=list,
        description="Optional section IDs to target (stored for future chunk filtering).",
    )
    top_k: int = Field(
        default=20,
        ge=1,
        le=200,
        description="Maximum ranked hits to return per symbol.",
    )
    efts_candidates: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="Maximum EFTS candidates fetched per query.",
    )
    rerank_with_embeddings: bool = Field(
        default=False,
        description="Enable snippet embedding rerank after chunk hydration.",
    )
    embedding_weight: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Weight applied to embedding similarity when reranking.",
    )
    index_results: bool = Field(
        default=False,
        description="Upsert retrieved snippets into Qdrant for reuse.",
    )
    download_missing: bool = Field(
        default=True,
        description="Download missing accessions before chunk extraction.",
    )
    chunk_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Sentence chunks per section chunk during retrieve hydration.",
    )
    chunk_overlap: int = Field(
        default=2,
        ge=0,
        le=20,
        description="Sentence overlap used during retrieve chunk extraction.",
    )
    max_chunks_per_accession: int = Field(
        default=40,
        ge=1,
        le=500,
        description="Maximum chunks loaded per accession for query matching.",
    )
    snippet_chars: int = Field(
        default=500,
        ge=80,
        le=4000,
        description="Maximum characters stored in per-hit snippet output.",
    )
    vdb: VectorConfig = Field(
        default_factory=lambda: VectorConfig(
            collection_name="retrieve",
            search_type="similarity",
            vector_size=1024,
        ),
        description="Vector store configuration used for optional rerank/index.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="json",
        description="Output file format to emit.",
    )

    @field_validator("queries", mode="before")
    @classmethod
    def normalize_queries(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part.strip() for part in value.split("||") if part.strip()]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            cleaned = raw.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        return normalized

    @field_validator("sections", mode="before")
    @classmethod
    def normalize_sections(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            cleaned = raw.strip().upper()
            if not cleaned:
                continue
            if cleaned.startswith("ITEM"):
                cleaned = cleaned.removeprefix("ITEM").strip()
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(cleaned)
        return normalized

    @model_validator(mode="after")
    def validate_chunk_settings(self) -> RetrieveSettings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        return self

    def pipeline_label(self) -> str:
        return "Retrieve"
