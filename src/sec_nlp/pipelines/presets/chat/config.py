# src/sec_nlp/pipelines/presets/chat/config.py
"""Config model for RAG chat pipeline."""

from __future__ import annotations

from datetime import date
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import SettingsConfigDict

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.llm.config import LLMConfig
from sec_nlp.pipelines.vector.config import VectorConfig

from .bridge import ChatRetrievedChunk, ChatSeedBundle


class ChatHistoryTurn(BaseModel):
    """Single turn used as conversation history input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["user", "assistant"]
    message: str


class ChatSettings(BasePipelineSettings):
    """Configuration for retrieval-augmented chat over indexed filings."""

    model_config = SettingsConfigDict(env_prefix="SEC_NLP_CHAT_")

    pipeline_type: ClassVar[Literal["chat"]] = "chat"
    symbols_optional: ClassVar[bool] = True

    symbols: list[str] = Field(
        default_factory=list,
        description="Optional ticker symbols to scope retrieval.",
    )
    mode: FilingMode = Field(
        default=FilingMode.annual,
        description="Default filing mode when forms are not explicitly set.",
    )
    forms: list[str] | None = Field(
        default=None,
        description="Optional form filters applied to retrieved chunks (e.g., 10-K, 10-Q, 8-K, 6-K).",
    )
    start_date: date | None = Field(
        default=None,
        description="Optional lower bound for filing date filter (inclusive).",
    )
    end_date: date | None = Field(
        default=None,
        description="Optional upper bound for filing date filter (inclusive).",
    )
    question: str | None = Field(
        default=None,
        description="Single question to answer. Omit to use interactive mode.",
        json_schema_extra={
            "cli_args": {
                "aliases": ["--q", "--query", "--question"],
            }
        },
    )
    chat_history: list[ChatHistoryTurn] = Field(
        default_factory=list,
        description="Prior turns included for context and transcript generation.",
    )
    interactive: bool = Field(
        default=True,
        description="Enable interactive terminal chat when --question is omitted.",
    )
    collections: list[str] = Field(
        default_factory=lambda: ["retrieve", "analyze"],
        description="Qdrant collections searched for context chunks.",
        json_schema_extra={
            "cli_args": {
                "nargs": "+",
                "action": "extend",
            }
        },
    )
    seed_context: ChatSeedBundle | None = Field(
        default=None,
        description=(
            "Optional in-memory seeded context bundle from an upstream flow stage. "
            "When provided, chat can bypass vector collection search."
        ),
        exclude=True,
    )
    seed_chunks: tuple[ChatRetrievedChunk, ...] = Field(
        default_factory=tuple,
        description=(
            "Optional prebuilt retrieval chunks injected by flow runtime to "
            "bypass seed model conversion."
        ),
        exclude=True,
    )
    top_k: int = Field(
        default=8,
        ge=1,
        le=100,
        description="Maximum total retrieved chunks per question.",
    )
    max_context_chunks: int = Field(
        default=8,
        ge=1,
        le=40,
        description="Maximum chunks passed into the answer prompt.",
    )
    context_token_budget: int = Field(
        default=6000,
        ge=500,
        le=40000,
        description="Approximate token budget for packed filing context in the prompt.",
    )
    per_symbol_min_chunks: int = Field(
        default=1,
        ge=0,
        le=20,
        description=(
            "Minimum number of chunks to reserve per requested symbol when selecting context."
        ),
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum vector score required to keep a hit.",
    )
    rerank_mode: Literal["score", "mmr"] = Field(
        default="score",
        description="Chunk reranking mode after retrieval (raw score or MMR diversity rerank).",
    )
    rerank_lambda: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="MMR relevance weight (higher = more relevance, lower = more diversity).",
    )
    rerank_candidates: int = Field(
        default=32,
        ge=1,
        le=200,
        description="Maximum candidate chunks considered by reranker.",
    )
    prefetch_retrieve: bool = Field(
        default=False,
        description="Preemptively run retrieve indexing when target collection is missing or sparse.",
    )
    prefetch_min_points: int = Field(
        default=1,
        ge=0,
        le=10000,
        description="Minimum points required in a collection before skipping prefetch.",
    )
    prefetch_queries: list[str] = Field(
        default_factory=list,
        description="Optional retrieve queries used during prefetch (defaults to the chat question).",
        json_schema_extra={
            "cli_args": {
                "nargs": "+",
                "action": "extend",
            }
        },
    )
    prefetch_efts_candidates: int = Field(
        default=200,
        ge=1,
        le=1000,
        description="EFTS candidate cap used by prefetch retrieve runs.",
    )
    prefetch_top_k: int = Field(
        default=40,
        ge=1,
        le=200,
        description="Top-K retrieve hits persisted during prefetch runs.",
    )
    include_market_context: bool = Field(
        default=False,
        description="Attach recent market context (price/volatility) to prompt.",
    )
    market_context_profile: Literal["compact", "standard"] = Field(
        default="standard",
        description="Market context verbosity profile (compact=1 line/symbol, standard=2-3 lines/symbol).",
    )
    market_context_scope: Literal["auto", "single", "multi"] = Field(
        default="auto",
        description="How market context symbols are selected: single symbol, multi-symbol, or auto mode.",
    )
    market_context_max_symbols: int = Field(
        default=8,
        ge=1,
        le=50,
        description="Maximum symbols included when market context scope resolves to multi-symbol mode.",
    )
    include_news_context: bool = Field(
        default=False,
        description="Attach recent news/geopolitical headlines to prompt.",
    )
    market_lookback_days: int = Field(
        default=30,
        ge=5,
        le=365,
        description="Lookback window for market context calculations.",
    )
    news_lookback_days: int = Field(
        default=14,
        ge=1,
        le=90,
        description="Lookback window for supplemental news context.",
    )
    max_news_items: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum supplemental headlines included in prompt context.",
    )
    market_benchmark_symbol: str = Field(
        default="SPY",
        description="Benchmark symbol used for relative market context.",
    )
    strict_citations: bool = Field(
        default=True,
        description="Require citation IDs in every assistant answer.",
    )
    llm_timeout_seconds: int = Field(
        default=180,
        ge=1,
        le=3600,
        description="Timeout for LLM answer generation in seconds.",
    )
    generation_token_cap: int = Field(
        default=512,
        ge=0,
        le=8192,
        description=(
            "Optional hard cap for generated tokens per answer "
            "(0 disables cap)."
        ),
    )
    include_history: bool = Field(
        default=True,
        description="Include prior turns in LLM prompt context.",
    )
    history_turns: int = Field(
        default=6,
        ge=0,
        le=50,
        description="Maximum prior turns injected into prompt context.",
    )
    transcript_autosave: bool = Field(
        default=True,
        description="Persist transcript output after each answered question.",
    )
    output_format: Literal["csv", "json", "yaml", "all"] = Field(
        default="all",
        description="Transcript output format to emit.",
    )
    llm: LLMConfig = Field(
        default_factory=lambda: LLMConfig(
            model_name="llama3.2:1b",
            require_json=False,
            temperature=0.1,
            max_new_tokens=384,
        ),
        description="LLM settings for response generation.",
    )
    vdb: VectorConfig = Field(
        default_factory=lambda: VectorConfig(
            collection_name="retrieve",
            search_type="similarity",
            vector_size=1024,
        ),
        description="Vector store settings used for retrieval.",
    )

    @field_validator("question", mode="before")
    @classmethod
    def _normalize_question(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("prefetch_queries", mode="before")
    @classmethod
    def _normalize_prefetch_queries(
        cls, value: list[str] | str | None
    ) -> list[str]:
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

    @field_validator("market_benchmark_symbol", mode="before")
    @classmethod
    def _normalize_benchmark_symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("market_benchmark_symbol cannot be empty")
        return cleaned

    @field_validator("collections", mode="before")
    @classmethod
    def _normalize_collections(cls, value: list[str] | str | None) -> list[str]:
        if value is None:
            return ["retrieve", "analyze"]
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]

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
        return normalized or ["retrieve", "analyze"]

    @field_validator("chat_history", mode="before")
    @classmethod
    def _normalize_history(
        cls,
        value: list[ChatHistoryTurn | dict[str, str]] | None,
    ) -> list[ChatHistoryTurn]:
        if value is None:
            return []

        normalized: list[ChatHistoryTurn] = []
        for raw in value:
            if isinstance(raw, ChatHistoryTurn):
                normalized.append(raw)
                continue
            if isinstance(raw, dict):
                normalized.append(ChatHistoryTurn.model_validate(raw))
        return normalized

    def pipeline_label(self) -> str:
        return "Chat"
