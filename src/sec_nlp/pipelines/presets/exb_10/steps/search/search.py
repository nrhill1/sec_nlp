# src/sec_nlp/pipelines/presets/exb_10/steps/search/search.py
"""Semantic search for Exhibit 10 supplier contracts."""

from __future__ import annotations

from pathlib import Path

import yaml
from langchain_qdrant import QdrantVectorStore
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.utils import slugify
from sec_nlp.types import JsonObject, JsonValue


class SearchResult(BaseModel):
    """Result from a semantic search query."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        defer_build=True,
    )

    text: str = Field(description="Contract text chunk")
    score: float = Field(description="Similarity score", ge=0.0, le=1.0)
    metadata: dict[str, JsonValue] = Field(
        default_factory=dict, description="Associated metadata"
    )


class Exhibit10Search(BaseModel):
    """Semantic search tool for Exhibit 10 contracts."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
        extra="forbid",
        defer_build=True,
    )

    vector_store: QdrantVectorStore = Field(
        description="Vector store backend",
    )

    # Configuration fields
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
    search_kwargs: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="Additional kwargs forwarded to vector search",
    )

    search_type: str = Field(
        default="similarity",
        description="Search type used by the vector store (e.g., similarity, mmr)",
    )

    def search(
        self,
        query: str,
        symbols: list[str] | None = None,
        limit: int | None = None,
        score_threshold: float | None = 0.9,
        search_kwargs: dict[str, JsonValue] | None = None,
    ) -> list[SearchResult]:
        """Search for contracts matching the query.

        Args:
            query: Natural language search query
            symbols: Optional list of symbols to filter by
            limit: Maximum number of results (defaults to config limit)
            score_threshold: Minimum similarity score (defaults to config threshold)

        Returns:
            List of search results with text, score, and metadata
        """
        limit = self.limit if limit is None else limit
        score_threshold = (
            self.score_threshold if score_threshold is None else score_threshold
        )
        merged_kwargs = dict(self.search_kwargs or {})
        if search_kwargs:
            merged_kwargs.update(search_kwargs)

        results: list[SearchResult] = []

        collection_name = "exhibit_10"

        if not self._collection_exists(collection_name):
            logger.debug("Collection %s does not exist", collection_name)
            return results

        try:
            if self.search_type == "mmr":
                # MMR search: extract MMR-specific params, use max_marginal_relevance_search
                fetch_k = merged_kwargs.pop("fetch_k", limit * 2)
                lambda_mult = merged_kwargs.pop("lambda_mult", 0.5)
                docs = self.vector_store.max_marginal_relevance_search(
                    query=query,
                    k=limit,
                    fetch_k=fetch_k,
                    lambda_mult=lambda_mult,
                    **merged_kwargs,
                )
                # MMR doesn't return scores, so we assign a decreasing score based on rank
                for i, doc in enumerate(docs):
                    if (
                        not doc.page_content
                        or not str(doc.page_content).strip()
                    ):
                        continue
                    # Assign score based on rank (1.0 for first, decreasing)
                    rank_score = 1.0 - (i / max(len(docs), 1))
                    if rank_score < score_threshold:
                        continue
                    results.append(
                        SearchResult(
                            text=doc.page_content,
                            score=rank_score,
                            metadata=doc.metadata or {},
                        )
                    )
            else:
                # Standard similarity search with scores
                # Remove any MMR-specific kwargs that might have been passed
                merged_kwargs.pop("fetch_k", None)
                merged_kwargs.pop("lambda_mult", None)
                for (
                    doc,
                    score,
                ) in self.vector_store.similarity_search_with_score(
                    query=query,
                    k=limit,
                    score_threshold=score_threshold,
                    **merged_kwargs,
                ):
                    if (
                        not doc.page_content
                        or not str(doc.page_content).strip()
                    ):
                        continue
                    if score is None or score < score_threshold:
                        continue
                    results.append(
                        SearchResult(
                            text=doc.page_content,
                            score=score,
                            metadata=doc.metadata or {},
                        )
                    )

        except Exception as e:
            logger.error(
                "Error searching collection %s: %s", collection_name, e
            )

        # Sort by score descending
        results.sort(key=lambda r: r.score, reverse=True)

        # Collapse to best hit per accession_number to avoid duplicates
        results = self._dedupe_by_accession(results)

        # Limit total results
        results = results[:limit]

        logger.info("Found %d results for query: %s", len(results), query)
        return results

    def export_results(
        self,
        query: str,
        results: list[SearchResult],
        output_path: Path,
        search_type: str = "similarity",
        run_id: str | None = None,
    ) -> None:
        """Export search results to YAML file.

        Args:
            query: Original search query
            results: Search results
            output_path: Output file path
            search_type: Type of search performed (similarity, mmr)
            run_id: Pipeline run identifier
        """

        # Ensure .yaml extension
        if output_path.suffix == ".json":
            output_path = output_path.with_suffix(".yaml")

        # Build clean, readable output structure
        output_data: JsonObject = {
            "query": query,
            "count": len(results),
            "hits": [
                {
                    "accession": r.metadata.get("accession_number", "unknown"),
                    "symbol": r.metadata.get("symbol", "unknown"),
                    "doc_type": r.metadata.get("doc_type", "EX-10"),
                    "filed": r.metadata.get("filing_date", ""),
                    "score": round(r.score, 3),
                }
                for r in results
            ],
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(
                output_data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

        logger.info("Exported %d results to %s", len(results), output_path)

    def _get_collection_name(self, symbol: str) -> str:
        """Generate collection name for a symbol."""
        return slugify(f"exhibit10_{symbol.lower()}")

    def _collection_exists(self, collection_name: str) -> bool:
        """Check if a collection exists in the vector store.

        Args:
            collection_name: Name of the collection to check

        Returns:
            True if the collection exists, False otherwise
        """
        try:
            client = self.vector_store.client
            client.get_collection(collection_name)
            return True
        except Exception:
            return False

    @staticmethod
    def _dedupe_by_accession(results: list[SearchResult]) -> list[SearchResult]:
        """Keep the best-scoring hit per accession_number."""
        best: dict[str, SearchResult] = {}
        for res in results:
            accession = str(res.metadata.get("accession_number", "") or "")
            if accession == "":
                accession = f"unknown-{id(res)}"
            if accession not in best or res.score > best[accession].score:
                best[accession] = res
        return sorted(best.values(), key=lambda r: r.score, reverse=True)
