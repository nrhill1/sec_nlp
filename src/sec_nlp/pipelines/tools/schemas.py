# src/sec_nlp/pipelines/tools/schemas.py
"""Input/output schemas for reusable LangChain tools."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sec_nlp.types import JsonDict

type ToolJsonRecord = JsonDict


def _normalize_symbol_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in values:
        symbol = raw.strip().upper()
        if not symbol:
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


class MarketContextToolInput(BaseModel):
    """Arguments for the market context tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbols: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    benchmark: str = Field(default="SPY")
    profile: Literal["compact", "standard"] = Field(default="standard")
    timeout_seconds: float | None = Field(default=30.0, ge=0.1)

    @field_validator("symbols", mode="before")
    @classmethod
    def _normalize_symbols(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]
        return _normalize_symbol_list(value)

    @field_validator("benchmark", mode="before")
    @classmethod
    def _normalize_benchmark(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("benchmark cannot be empty")
        return cleaned


class MarketContextToolOutput(BaseModel):
    """Return payload for the market context tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    window: str
    benchmark: str
    symbols: list[str]
    metrics: list[ToolJsonRecord]
    lines: list[str] = Field(default_factory=list)


class RetrieveHitsToolInput(BaseModel):
    """Arguments for retrieve-hits tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbols: list[str] = Field(default_factory=list)
    queries: list[str]
    forms: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None
    top_k: int = Field(default=20, ge=1, le=200)
    collection: str = Field(default="retrieve")
    timeout_seconds: float | None = Field(default=30.0, ge=0.1)

    @field_validator("symbols", mode="before")
    @classmethod
    def _normalize_symbols(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]
        return _normalize_symbol_list(value)

    @field_validator("queries", mode="before")
    @classmethod
    def _normalize_queries(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            value = [part.strip() for part in value.split("||") if part.strip()]
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            query = raw.strip()
            if not query:
                continue
            key = query.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(query)
        if not normalized:
            raise ValueError("queries cannot be empty")
        return normalized


class RetrieveHitsToolOutput(BaseModel):
    """Return payload for retrieve-hits tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str
    run_metadata: ToolJsonRecord
    hits: list[ToolJsonRecord]


class QdrantSearchToolInput(BaseModel):
    """Arguments for Qdrant semantic-search tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str
    query: str
    top_k: int = Field(default=20, ge=1, le=200)
    symbols: list[str] = Field(default_factory=list)
    forms: list[str] = Field(default_factory=list)
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    timeout_seconds: float | None = Field(default=30.0, ge=0.1)

    @field_validator("symbols", mode="before")
    @classmethod
    def _normalize_symbols(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]
        return _normalize_symbol_list(value)

    @field_validator("forms", mode="before")
    @classmethod
    def _normalize_forms(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            value = [part for part in value.replace(",", " ").split() if part]
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            form = raw.strip().upper()
            if not form:
                continue
            if form in {"10K", "10Q", "8K", "6K"}:
                form = form[:-1] + "-" + form[-1]
            if form in seen:
                continue
            seen.add(form)
            normalized.append(form)
        return normalized


class QdrantSearchToolOutput(BaseModel):
    """Return payload for Qdrant semantic-search tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    collection: str
    query: str
    hit_count: int
    hits: list[ToolJsonRecord]


class NewsContextToolInput(BaseModel):
    """Arguments for news-context tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    keywords: list[str]
    max_results: int = Field(default=50, ge=1, le=200)
    lookback_days: int = Field(default=14, ge=1, le=365)
    timeout_seconds: float | None = Field(default=30.0, ge=0.1)

    @field_validator("keywords", mode="before")
    @classmethod
    def _normalize_keywords(cls, value: list[str] | str) -> list[str]:
        if isinstance(value, str):
            value = [part.strip() for part in value.split("||") if part.strip()]
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in value:
            keyword = raw.strip()
            if not keyword:
                continue
            key = keyword.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(keyword)
        if not normalized:
            raise ValueError("keywords cannot be empty")
        return normalized


class NewsContextToolOutput(BaseModel):
    """Return payload for news-context tool."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lookback_days: int
    items: list[ToolJsonRecord]
