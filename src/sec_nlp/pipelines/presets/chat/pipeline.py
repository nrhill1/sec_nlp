"""Pipeline for RAG chat over indexed filing chunks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import ClassVar, Literal, Protocol, cast

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Condition,
    FieldCondition,
    Filter,
    MatchValue,
)

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.market import MarketExtensionError, create_market_retriever
from sec_nlp.core.news.client import (
    NewswatchExtensionError,
    create_news_retriever,
)
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import (
    build_run_file_stem,
    build_run_header_fields,
)
from sec_nlp.types import JsonDict, JsonValue, ResultDict

from ..retrieve import RetrievePipeline, RetrieveSettings
from .config import ChatSettings
from .io import (
    write_chat_transcript_csv,
    write_chat_transcript_json,
    write_chat_transcript_yaml,
)
from .models import ChatCitation, ChatResult, ChatTranscriptPayload, ChatTurn

_CITATION_RE = re.compile(r"\[(C\d+)\]")
_WHITESPACE_RE = re.compile(r"\s+")
_FILTER_FETCH_MULTIPLIER = 4
_FILTER_FETCH_MAX_POINTS = 200
_QUESTION_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9/-]{2,}")
_STOPWORDS = {
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "how",
    "from",
    "into",
    "that",
    "this",
    "with",
    "without",
    "about",
    "across",
    "between",
    "recent",
    "changes",
    "change",
    "risk",
    "risks",
    "opportunity",
    "opportunities",
    "material",
    "company",
    "filing",
    "filings",
}


@dataclass(slots=True, frozen=True)
class _RetrievedChunk:
    collection: str
    score: float
    symbol: str | None
    accession_number: str | None
    form_type: str | None
    filed_date: str | None
    source: str | None
    snippet: str


class _SnippetEmbedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...


class ChatPipeline(BasePipeline):
    """Answer questions against indexed SEC filing chunks."""

    pipeline_type: ClassVar[Literal["chat"]] = "chat"
    description: ClassVar[str] = (
        "Interactive retrieval-augmented Q&A over indexed filings"
    )
    requires_llm: ClassVar[bool] = True

    config: ChatSettings

    @classmethod
    def config_model(cls) -> type[ChatSettings]:
        return ChatSettings

    @classmethod
    def result_model(cls) -> type[ChatResult]:
        return ChatResult

    def _build_components(self) -> None:
        return

    def _effective_end_date(self) -> date:
        return self.config.end_date or date.today()

    def _chunk_identity(self, chunk: _RetrievedChunk) -> tuple[str, str, str]:
        return (
            chunk.collection.casefold(),
            (chunk.accession_number or "").casefold(),
            self._snippet_fingerprint(chunk.snippet),
        )

    def _base_metadata(
        self,
        *,
        external_context: str,
        external_metadata: dict[str, JsonValue],
    ) -> ResultDict:
        metadata: ResultDict = {
            "collections": list(self.config.collections),
            "forms_filter": self.config.forms or [],
            "filed_after": (
                self.config.start_date.isoformat()
                if self.config.start_date
                else None
            ),
            "filed_before": (
                self.config.end_date.isoformat()
                if self.config.end_date
                else None
            ),
            "rerank_mode": self.config.rerank_mode,
            "prefetch_retrieve": self.config.prefetch_retrieve,
            "include_market_context": self.config.include_market_context,
            "include_news_context": self.config.include_news_context,
            "external_context": external_context,
            **external_metadata,
        }
        return metadata

    def run(self) -> ChatResult:
        try:
            self.config.setup_paths()
            question = (self.config.question or "").strip()
            if not question:
                raise ValueError(
                    "Chat pipeline requires a question (--question or --query)."
                )

            chunks = self._search_collections(question)
            citations = self._to_citations(chunks)
            external_context, external_metadata = self._build_external_context(
                question=question,
                citations=citations,
            )
            answer, used_citation_ids = self._build_answer(
                question=question,
                citations=citations,
                external_context=external_context,
            )

            turns = self._build_turns(
                question=question,
                answer=answer,
                citation_ids=used_citation_ids,
            )

            outputs: list[Path] = []
            metadata = self._base_metadata(
                external_context=external_context,
                external_metadata=external_metadata,
            )
            metadata.update(
                {
                    "hits_retrieved": len(citations),
                    "citations_returned": len(used_citation_ids),
                    "strict_citations": self.config.strict_citations,
                    "symbol_scope": self.config.symbols,
                }
            )

            if self.config.transcript_autosave:
                outputs = self._write_outputs(
                    question=question,
                    answer=answer,
                    citations=citations,
                    citation_ids=used_citation_ids,
                    turns=turns,
                    external_context=external_context,
                    external_metadata=external_metadata,
                )

            self.config.complete_run(
                success=True,
                metadata=cast(JsonDict, metadata),
            )
            return ChatResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                turns_processed=len(turns),
                hits_retrieved=len(citations),
                citations_returned=len(used_citation_ids),
                answer=answer,
                citation_ids=used_citation_ids,
            )
        except Exception as exc:
            logger.exception("Chat pipeline failed")
            self.config.complete_run(success=False)
            return ChatResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _search_collections(self, question: str) -> list[_RetrievedChunk]:
        embedder, _ = self.config.vdb.setup_embedding_model()
        query_vector = list(embedder.embed_query(question))
        qdrant = self.config.vdb.setup_qdrant_client()

        symbols = [
            symbol.upper() for symbol in self.config.symbols if symbol.strip()
        ]
        allowed_forms = self._normalized_form_filters(self.config.forms)
        filed_after = self.config.start_date
        filed_before = self.config.end_date
        apply_post_filters = bool(
            allowed_forms
            or filed_after
            or filed_before
            or self.config.rerank_mode == "mmr"
        )
        query_limit = max(self.config.top_k, self.config.rerank_candidates)
        if apply_post_filters:
            query_limit = min(
                _FILTER_FETCH_MAX_POINTS,
                max(
                    query_limit,
                    self.config.top_k * _FILTER_FETCH_MULTIPLIER,
                ),
            )

        combined: list[_RetrievedChunk] = []

        for collection in self.config.collections:
            name = collection.strip()
            if not name:
                continue
            if not qdrant.collection_exists(name):
                self._maybe_prefetch_collection(
                    qdrant=qdrant,
                    collection=name,
                    symbols=symbols,
                    question=question,
                )
            if not qdrant.collection_exists(name):
                logger.debug("Skipping unavailable collection '%s'", name)
                continue

            if (
                self.config.prefetch_retrieve
                and self.config.prefetch_min_points > 0
            ):
                point_count = self._collection_points(
                    qdrant=qdrant,
                    collection=name,
                )
                if (
                    point_count is not None
                    and point_count < self.config.prefetch_min_points
                ):
                    self._maybe_prefetch_collection(
                        qdrant=qdrant,
                        collection=name,
                        symbols=symbols,
                        question=question,
                    )
                point_count = self._collection_points(
                    qdrant=qdrant,
                    collection=name,
                )
                if (
                    point_count is not None
                    and point_count < self.config.prefetch_min_points
                ):
                    logger.debug(
                        "Collection '%s' remains sparse (%d points < %d)",
                        name,
                        point_count,
                        self.config.prefetch_min_points,
                    )
            if not qdrant.collection_exists(name):
                continue

            query_filter = self._build_symbol_filter(symbols)
            response = qdrant.query_points(
                collection_name=name,
                query=query_vector,
                query_filter=query_filter,
                limit=query_limit,
                with_payload=True,
                with_vectors=False,
                score_threshold=self.config.min_score,
            )
            points = getattr(response, "points", [])
            for point in points:
                chunk = self._point_to_chunk(collection=name, point=point)
                if chunk is None:
                    continue
                if not self._chunk_matches_filters(
                    chunk,
                    forms=allowed_forms,
                    filed_after=filed_after,
                    filed_before=filed_before,
                ):
                    continue
                combined.append(chunk)

        combined.sort(key=lambda chunk: chunk.score, reverse=True)
        deduped: list[_RetrievedChunk] = []
        seen: set[tuple[str, str, str]] = set()
        dedupe_limit = max(self.config.top_k, self.config.rerank_candidates)

        for chunk in combined:
            key = self._chunk_identity(chunk)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(chunk)
            if len(deduped) >= dedupe_limit:
                break

        if self.config.rerank_mode == "mmr":
            reranked = self._rerank_chunks_mmr(
                chunks=deduped,
                query_vector=query_vector,
                embedder=embedder,
            )
            return reranked[: self.config.top_k]

        return deduped

    def _build_symbol_filter(self, symbols: list[str]) -> Filter | None:
        if not symbols:
            return None

        symbol_conditions: list[Condition] = []
        for symbol in symbols:
            symbol_conditions.extend(
                [
                    FieldCondition(
                        key="symbol", match=MatchValue(value=symbol)
                    ),
                    FieldCondition(
                        key="ticker", match=MatchValue(value=symbol)
                    ),
                    FieldCondition(
                        key="metadata.symbol",
                        match=MatchValue(value=symbol),
                    ),
                    FieldCondition(
                        key="metadata.ticker",
                        match=MatchValue(value=symbol),
                    ),
                ]
            )
        return Filter(should=symbol_conditions)

    @staticmethod
    def _snippet_fingerprint(text: str) -> str:
        return hashlib.blake2b(
            text.casefold().encode("utf-8"),
            digest_size=8,
        ).hexdigest()

    def _collection_points(
        self,
        *,
        qdrant: QdrantClient,
        collection: str,
    ) -> int | None:
        try:
            info = qdrant.get_collection(collection)
            points_count = getattr(info, "points_count", None)
            if isinstance(points_count, int):
                return points_count
        except Exception as exc:
            logger.debug(
                "Failed to inspect collection '%s': %s", collection, exc
            )
        return None

    def _maybe_prefetch_collection(
        self,
        *,
        qdrant: QdrantClient,
        collection: str,
        symbols: list[str],
        question: str,
    ) -> None:
        if not self.config.prefetch_retrieve:
            return
        if "retrieve" not in collection.casefold():
            return
        if not symbols:
            logger.debug(
                "Prefetch skipped for '%s': symbol scope required",
                collection,
            )
            return

        hydrated = self._hydrate_retrieve_collection(
            collection=collection,
            symbols=symbols,
            question=question,
        )
        if hydrated and qdrant.collection_exists(collection):
            logger.info(
                "Prefetch populated collection '%s' for symbols=%s",
                collection,
                ",".join(symbols),
            )

    def _hydrate_retrieve_collection(
        self,
        *,
        collection: str,
        symbols: list[str],
        question: str,
    ) -> bool:
        queries = (
            self.config.prefetch_queries
            if self.config.prefetch_queries
            else [question.strip()]
        )
        queries = [query for query in queries if query]
        if not queries:
            return False

        try:
            vdb_config = self.config.vdb.model_dump(mode="python")
            vdb_config["collection_name"] = collection
            retrieve_config = RetrieveSettings(
                email=self.config.email,
                symbols=symbols,
                forms=self.config.forms,
                start_date=self.config.start_date,
                end_date=self.config.end_date,
                queries=queries,
                efts_candidates=self.config.prefetch_efts_candidates,
                top_k=self.config.prefetch_top_k,
                index_results=True,
                dry_run=False,
                output_format="json",
                dl_path=self.config.dl_path,
                out_path=self.config.out_path,
                vdb=vdb_config,
            )
            retrieve_result = RetrievePipeline(config=retrieve_config).run()
            return retrieve_result.success
        except Exception as exc:
            logger.warning(
                "Prefetch retrieve failed for collection '%s': %s",
                collection,
                exc,
            )
            logger.debug(
                "Prefetch retrieve traceback for collection '%s'",
                collection,
                exc_info=True,
            )
            return False

    @staticmethod
    def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot = 0.0
        norm_a = 0.0
        norm_b = 0.0
        for a, b in zip(vec_a, vec_b, strict=False):
            dot += a * b
            norm_a += a * a
            norm_b += b * b
        if norm_a <= 0.0 or norm_b <= 0.0:
            return 0.0
        return dot / ((norm_a**0.5) * (norm_b**0.5))

    def _rerank_chunks_mmr(
        self,
        *,
        chunks: list[_RetrievedChunk],
        query_vector: list[float],
        embedder: _SnippetEmbedder,
    ) -> list[_RetrievedChunk]:
        if len(chunks) <= 1:
            return chunks

        candidates = chunks[: self.config.rerank_candidates]
        snippets = [chunk.snippet for chunk in candidates]
        try:
            raw_vectors = embedder.embed_documents(snippets)
        except Exception as exc:
            logger.debug("MMR rerank skipped (embedding failure): %s", exc)
            return chunks

        vectors: list[list[float]] = []
        for raw in raw_vectors:
            if isinstance(raw, list):
                vectors.append(
                    [
                        float(value)
                        for value in raw
                        if isinstance(value, (int, float))
                    ]
                )
            else:
                vectors.append([])
        if len(vectors) != len(candidates):
            return chunks

        selected_indices: list[int] = []
        remaining = list(range(len(candidates)))

        while remaining and len(selected_indices) < self.config.top_k:
            best_idx = remaining[0]
            best_score = float("-inf")
            for idx in remaining:
                relevance = self._cosine_similarity(query_vector, vectors[idx])
                diversity = 0.0
                if selected_indices:
                    diversity = max(
                        self._cosine_similarity(vectors[idx], vectors[chosen])
                        for chosen in selected_indices
                    )
                mmr_score = (
                    self.config.rerank_lambda * relevance
                    - (1.0 - self.config.rerank_lambda) * diversity
                )
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx

            selected_indices.append(best_idx)
            remaining.remove(best_idx)

        selected = [candidates[idx] for idx in selected_indices]
        selected_keys = {self._chunk_identity(chunk) for chunk in selected}
        for chunk in chunks:
            key = self._chunk_identity(chunk)
            if key in selected_keys:
                continue
            selected.append(chunk)
        return selected

    @staticmethod
    def _normalized_form_filters(forms: list[str] | None) -> set[str]:
        if not forms:
            return set()

        normalized: set[str] = set()
        for raw in forms:
            cleaned = raw.strip().upper()
            if cleaned in {"10K", "10Q", "8K", "6K"}:
                cleaned = cleaned[:-1] + "-" + cleaned[-1]
            base = cleaned[:-2] if cleaned.endswith("/A") else cleaned
            if base:
                normalized.add(base)
        return normalized

    @staticmethod
    def _parse_filed_date(value: str | None) -> date | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if "T" in cleaned:
            cleaned = cleaned.split("T", 1)[0]
        if len(cleaned) == 8 and cleaned.isdigit():
            try:
                return date(
                    int(cleaned[:4]),
                    int(cleaned[4:6]),
                    int(cleaned[6:8]),
                )
            except ValueError:
                return None
        try:
            return date.fromisoformat(cleaned)
        except ValueError:
            return None

    @classmethod
    def _chunk_matches_filters(
        cls,
        chunk: _RetrievedChunk,
        *,
        forms: set[str],
        filed_after: date | None,
        filed_before: date | None,
    ) -> bool:
        if forms:
            chunk_form = cls._normalized_form_filters([chunk.form_type or ""])
            if not chunk_form.intersection(forms):
                return False

        if filed_after is None and filed_before is None:
            return True

        filing_date = cls._parse_filed_date(chunk.filed_date)
        if filing_date is None:
            return False
        if filed_after is not None and filing_date < filed_after:
            return False
        return filed_before is None or filing_date <= filed_before

    @staticmethod
    def _parse_news_timestamp(value: str | None) -> datetime | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            pass
        try:
            return parsedate_to_datetime(cleaned)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _question_keywords(question: str, max_keywords: int = 8) -> list[str]:
        keywords: list[str] = []
        seen: set[str] = set()
        for match in _QUESTION_TOKEN_RE.finditer(question):
            token = match.group(0).lower()
            if token in _STOPWORDS:
                continue
            if token in seen:
                continue
            seen.add(token)
            keywords.append(token)
            if len(keywords) >= max_keywords:
                break
        return keywords

    def _context_symbol(self, citations: list[ChatCitation]) -> str | None:
        if self.config.symbols:
            return self.config.symbols[0].upper()
        if citations and citations[0].symbol:
            return citations[0].symbol.upper()
        return None

    def _build_external_context(
        self,
        *,
        question: str,
        citations: list[ChatCitation],
    ) -> tuple[str, dict[str, JsonValue]]:
        symbol = self._context_symbol(citations)
        if not symbol:
            return "", {"market_context_items": 0, "news_context_items": 0}

        sections: list[str] = []
        metadata: dict[str, JsonValue] = {
            "market_context_items": 0,
            "news_context_items": 0,
            "external_context_symbol": symbol,
        }

        if self.config.include_market_context:
            lines = self._market_context_lines(symbol=symbol)
            if lines:
                sections.append("Market context:\n" + "\n".join(lines))
                metadata["market_context_items"] = len(lines)

        if self.config.include_news_context:
            lines = self._news_context_lines(symbol=symbol, question=question)
            if lines:
                sections.append(
                    "News/geopolitics context:\n" + "\n".join(lines)
                )
                metadata["news_context_items"] = len(lines)

        if not sections:
            return "", metadata
        return "\n\n".join(sections), metadata

    def _market_context_lines(self, *, symbol: str) -> list[str]:
        end = self._effective_end_date()
        start = max(
            self.config.start_date
            or (end - timedelta(days=self.config.market_lookback_days)),
            end - timedelta(days=self.config.market_lookback_days),
        )
        try:
            retriever = create_market_retriever()
            symbol_quotes = retriever.retrieve_range(symbol, (start, end))
            benchmark_quotes = retriever.retrieve_range(
                self.config.market_benchmark_symbol,
                (start, end),
            )
        except MarketExtensionError as exc:
            logger.debug("Market context unavailable: %s", exc)
            return []
        except Exception as exc:
            logger.debug("Market context fetch failed: %s", exc)
            return []

        if len(symbol_quotes) < 2 or len(benchmark_quotes) < 2:
            return []

        start_price = symbol_quotes[0].adjclose
        end_price = symbol_quotes[-1].adjclose
        benchmark_start = benchmark_quotes[0].adjclose
        benchmark_end = benchmark_quotes[-1].adjclose
        if start_price <= 0.0 or benchmark_start <= 0.0:
            return []

        symbol_return_pct = ((end_price / start_price) - 1.0) * 100.0
        benchmark_return_pct = ((benchmark_end / benchmark_start) - 1.0) * 100.0
        spread_pct = symbol_return_pct - benchmark_return_pct
        highs = [quote.high for quote in symbol_quotes]
        lows = [quote.low for quote in symbol_quotes]
        high_price = max(highs)
        low_price = min(lows)
        range_pct = (
            ((high_price - low_price) / low_price * 100.0)
            if low_price > 0
            else 0.0
        )

        return [
            (
                f"- {symbol}: {start.isoformat()} to {end.isoformat()} "
                f"return {symbol_return_pct:+.2f}% (benchmark {self.config.market_benchmark_symbol}: {benchmark_return_pct:+.2f}%, spread {spread_pct:+.2f}%)."
            ),
            f"- {symbol}: high/low range {range_pct:.2f}% in lookback window.",
        ]

    def _news_context_lines(self, *, symbol: str, question: str) -> list[str]:
        lookback_start = self._effective_end_date() - timedelta(
            days=self.config.news_lookback_days
        )
        keywords = [symbol]
        keywords.extend(self._question_keywords(question))
        keywords = list(dict.fromkeys(keywords))

        try:
            retriever = create_news_retriever(
                user_agent=f"SEC NLP Tool ({self.config.email})",
                rate_limit_secs=0.15,
            )
            raw_items = retriever.fetch(
                keywords=keywords,
                max_results=max(self.config.max_news_items * 4, 20),
            )
        except NewswatchExtensionError as exc:
            logger.debug("News context unavailable: %s", exc)
            return []
        except Exception as exc:
            logger.debug("News context fetch failed: %s", exc)
            return []

        deduped: list[tuple[datetime, str, str]] = []
        seen: set[str] = set()
        for item in raw_items:
            timestamp = self._parse_news_timestamp(item.published_at)
            if timestamp is None:
                continue
            published = timestamp.astimezone(UTC)
            published_date = published.date()
            if published_date < lookback_start:
                continue
            title = item.title.strip()
            url = item.url.strip()
            dedupe_key = f"{title.casefold()}::{url.casefold()}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            source = item.source.strip() or "unknown"
            deduped.append((published, source, title))

        deduped.sort(key=lambda current: current[0], reverse=True)
        deduped = deduped[: self.config.max_news_items]
        lines = [
            f"- {published.date().isoformat()} | {source} | {title}"
            for published, source, title in deduped
        ]
        return lines

    def _point_to_chunk(
        self,
        *,
        collection: str,
        point: object,
    ) -> _RetrievedChunk | None:
        payload = getattr(point, "payload", None)
        if not isinstance(payload, dict):
            return None

        snippet = self._extract_snippet(payload)
        if snippet is None:
            return None

        metadata = payload.get("metadata")
        metadata_dict: dict[str, JsonValue]
        if isinstance(metadata, dict):
            metadata_dict = cast(dict[str, JsonValue], metadata)
        else:
            metadata_dict = {}

        score_raw = getattr(point, "score", None)
        score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0

        symbol = self._first_text(
            payload,
            metadata_dict,
            keys=("symbol", "ticker"),
        )
        accession = self._first_text(
            payload,
            metadata_dict,
            keys=("accession_number", "accession"),
        )
        form_type = self._first_text(
            payload,
            metadata_dict,
            keys=("form_type",),
        )
        filed_date = self._first_text(
            payload,
            metadata_dict,
            keys=("filed_date",),
        )
        source = self._first_text(
            payload,
            metadata_dict,
            keys=("source", "edgar_url"),
        )

        return _RetrievedChunk(
            collection=collection,
            score=score,
            symbol=symbol,
            accession_number=accession,
            form_type=form_type,
            filed_date=filed_date,
            source=source,
            snippet=snippet,
        )

    @staticmethod
    def _first_text(
        payload: dict[str, JsonValue],
        metadata: dict[str, JsonValue],
        *,
        keys: tuple[str, ...],
    ) -> str | None:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            meta_value = metadata.get(key)
            if isinstance(meta_value, str) and meta_value.strip():
                return meta_value.strip()
        return None

    @staticmethod
    def _extract_snippet(payload: dict[str, JsonValue]) -> str | None:
        candidates: list[str] = []

        direct_keys = ("snippet", "page_content", "content", "text")
        for key in direct_keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value)

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata_dict = cast(dict[str, JsonValue], metadata)
            for key in ("raw_chunk", "page_content", "snippet", "content"):
                value = metadata_dict.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value)

        if not candidates:
            return None

        snippet = _WHITESPACE_RE.sub(" ", candidates[0]).strip()
        if len(snippet) > 700:
            snippet = snippet[:697].rstrip() + "..."
        return snippet

    def _to_citations(
        self, chunks: list[_RetrievedChunk]
    ) -> list[ChatCitation]:
        citations: list[ChatCitation] = []
        for idx, chunk in enumerate(chunks, start=1):
            citations.append(
                ChatCitation(
                    citation_id=f"C{idx}",
                    collection=chunk.collection,
                    score=float(chunk.score),
                    symbol=chunk.symbol,
                    accession_number=chunk.accession_number,
                    form_type=chunk.form_type,
                    filed_date=chunk.filed_date,
                    source=chunk.source,
                    snippet=chunk.snippet,
                )
            )
        return citations

    def _build_answer(
        self,
        *,
        question: str,
        citations: list[ChatCitation],
        external_context: str = "",
    ) -> tuple[str, list[str]]:
        if not citations:
            return (
                "I could not find indexed evidence for this question in the selected collections.",
                [],
            )

        prompt = self._build_prompt(
            question=question,
            citations=citations,
            external_context=external_context,
        )
        llm = self.config.llm.setup_ollama_model()
        raw_answer = llm.invoke(prompt)
        answer = raw_answer if isinstance(raw_answer, str) else str(raw_answer)
        answer = answer.strip()
        if not answer:
            answer = "I could not generate a grounded answer from the retrieved evidence."

        available = {citation.citation_id for citation in citations}
        used_ids = [
            cid for cid in _CITATION_RE.findall(answer) if cid in available
        ]
        used_ids = list(dict.fromkeys(used_ids))

        if self.config.strict_citations and not used_ids:
            fallback_ids = [
                citation.citation_id
                for citation in citations[: min(3, len(citations))]
            ]
            if fallback_ids:
                suffix = " ".join(f"[{cid}]" for cid in fallback_ids)
                answer = f"{answer}\n\nSources: {suffix}"
                used_ids = fallback_ids

        return answer, used_ids

    def _build_prompt(
        self,
        *,
        question: str,
        citations: list[ChatCitation],
        external_context: str = "",
    ) -> str:
        history_lines: list[str] = []
        if self.config.include_history and self.config.chat_history:
            keep = self.config.history_turns
            turns = self.config.chat_history[-keep:] if keep > 0 else []
            for turn in turns:
                role = "User" if turn.role == "user" else "Assistant"
                history_lines.append(f"{role}: {turn.message}")

        context_sections: list[str] = []
        for citation in citations[: self.config.max_context_chunks]:
            summary_parts = [f"Collection={citation.collection}"]
            if citation.symbol:
                summary_parts.append(f"Symbol={citation.symbol}")
            if citation.form_type:
                summary_parts.append(f"Form={citation.form_type}")
            if citation.filed_date:
                summary_parts.append(f"Filed={citation.filed_date}")
            if citation.accession_number:
                summary_parts.append(f"Accession={citation.accession_number}")
            summary = "; ".join(summary_parts)
            context_sections.append(
                f"[{citation.citation_id}] {summary}\n{citation.snippet}"
            )

        history_block = (
            "\n".join(history_lines)
            if history_lines
            else "(no prior conversation)"
        )
        context_block = "\n\n".join(context_sections)
        external_block = (
            external_context if external_context.strip() else "(none)"
        )

        return (
            "You are a financial filings assistant.\n"
            "Use only the provided context.\n"
            "If context is insufficient, say so directly.\n"
            "Every factual claim must include citation IDs in [C#] form.\n\n"
            f"Conversation history:\n{history_block}\n\n"
            f"Question:\n{question}\n\n"
            f"Context chunks:\n{context_block}\n\n"
            "Supplemental context (market/news; non-filing evidence):\n"
            f"{external_block}\n\n"
            "Use supplemental context only for macro framing. "
            "Company-specific factual claims must still cite filing chunks.\n\n"
            "Answer succinctly with grounded evidence and citations."
        )

    def _build_turns(
        self,
        *,
        question: str,
        answer: str,
        citation_ids: list[str],
    ) -> list[ChatTurn]:
        turns: list[ChatTurn] = [
            ChatTurn(role=turn.role, message=turn.message)
            for turn in self.config.chat_history
        ]
        turns.append(ChatTurn(role="user", message=question))
        turns.append(
            ChatTurn(
                role="assistant",
                message=answer,
                citations=citation_ids,
            )
        )
        return turns

    def _write_outputs(
        self,
        *,
        question: str,
        answer: str,
        citations: list[ChatCitation],
        citation_ids: list[str],
        turns: list[ChatTurn],
        external_context: str,
        external_metadata: dict[str, JsonValue],
    ) -> list[Path]:
        symbol = self._context_symbol(citations) or "ALL"

        symbol_out = self.config.get_symbol_output_dir(symbol)
        base_stem = build_run_file_stem(symbol, "chat", self.config.run_id)
        run_header = build_run_header_fields(
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )

        run_short_id_raw = run_header.get("run_short_id")
        run_short_id = (
            run_short_id_raw if isinstance(run_short_id_raw, int) else None
        )

        payload_metadata = self._base_metadata(
            external_context=external_context,
            external_metadata=external_metadata,
        )
        payload_metadata.update(
            {
                "top_k": self.config.top_k,
                "max_context_chunks": self.config.max_context_chunks,
                "strict_citations": self.config.strict_citations,
                "include_history": self.config.include_history,
                "history_turns": self.config.history_turns,
            }
        )

        payload = ChatTranscriptPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            question=question,
            answer=answer,
            citations=citations,
            citation_ids=citation_ids,
            turns=turns,
            metadata=cast(dict[str, JsonValue], payload_metadata),
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            csv_path = symbol_out / f"{base_stem}_transcript.csv"
            write_chat_transcript_csv(
                csv_path,
                payload,
                header_fields=run_header,
            )
            outputs.append(csv_path)

        if self.config.output_format in ("json", "all"):
            json_path = symbol_out / f"{base_stem}_summary.json"
            write_chat_transcript_json(json_path, payload)
            outputs.append(json_path)

        if self.config.output_format in ("yaml", "all"):
            yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            write_chat_transcript_yaml(yaml_path, payload)
            outputs.append(yaml_path)

        return outputs
