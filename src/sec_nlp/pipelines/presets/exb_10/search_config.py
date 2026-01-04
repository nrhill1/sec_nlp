# src/sec_nlp/pipelines/presets/exb_10/search_config.py
"""Configuration for semantic search on Exhibit 10 contracts."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from sec_nlp.types import JsonValue


class SearchConfig(BaseSettings):
    """Configuration for semantic search after vector upsert."""

    model_config = SettingsConfigDict(
        env_prefix="SEARCH_",
        frozen=True,
        defer_build=True,
        validate_assignment=False,
    )

    enabled: bool = Field(
        default=True,
        description="Enable semantic search after vector upsert",
        json_schema_extra={
            # Allow bare flag usage: --search.enabled sets True
            "cli_args": {"nargs": "?", "const": True},
        },
    )

    queries: list[str] = Field(
        default_factory=lambda: [
            "Supply agreements with exclusivity for diesel engine components",
            "Contracts providing parts at cost or cost-plus pricing to OEMs",
            "Aftermarket repair, replacement, or maintenance obligations for parts",
            "Exclusive supplier agreements covering diesel engine parts and services",
            "Aftermarket service and parts pricing provisions",
        ],
        description="List of search queries to run against the vector database",
    )

    search_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Additional keyword arguments for the search method",
    )

    limit: int = Field(
        default=30,
        ge=1,
        le=100,
        description="Maximum number of results per query",
    )

    score_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold",
    )

    export_results: bool = Field(
        default=True,
        description="Export search results to JSON files",
        json_schema_extra={
            "cli_args": {"nargs": "?", "const": True},
        },
    )

    mmr_fetch_k: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Number of candidates to retrieve before MMR reranking",
    )
    mmr_lambda: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Diversity/exploitation balance for MMR (higher favors top scores)",
    )

    @field_validator("queries", mode="before")
    @classmethod
    def normalize_queries(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            v = [part for part in v.replace(",", " ").split() if part]
        return [q.strip() for q in v]
