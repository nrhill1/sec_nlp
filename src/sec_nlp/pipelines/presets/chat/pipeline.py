"""Pipeline for RAG chat over indexed filing chunks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import ClassVar, Literal, cast

from qdrant_client.http.models import (
    Condition,
    FieldCondition,
    Filter,
    MatchValue,
)

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import (
    build_run_file_stem,
    build_run_header_fields,
)
from sec_nlp.types import JsonDict, JsonValue, ResultDict

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


@dataclass(frozen=True)
class _RetrievedChunk:
    collection: str
    score: float
    symbol: str | None
    accession_number: str | None
    form_type: str | None
    filed_date: str | None
    source: str | None
    snippet: str


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
            answer, used_citation_ids = self._build_answer(
                question=question,
                citations=citations,
            )

            turns = self._build_turns(
                question=question,
                answer=answer,
                citation_ids=used_citation_ids,
            )

            outputs: list[Path] = []
            metadata: ResultDict = {
                "collections": list(self.config.collections),
                "hits_retrieved": len(citations),
                "citations_returned": len(used_citation_ids),
                "strict_citations": self.config.strict_citations,
                "symbol_scope": self.config.symbols,
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
            }

            if self.config.transcript_autosave:
                outputs = self._write_outputs(
                    question=question,
                    answer=answer,
                    citations=citations,
                    citation_ids=used_citation_ids,
                    turns=turns,
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
        apply_post_filters = bool(allowed_forms or filed_after or filed_before)
        query_limit = self.config.top_k
        if apply_post_filters:
            query_limit = min(
                _FILTER_FETCH_MAX_POINTS,
                max(
                    self.config.top_k,
                    self.config.top_k * _FILTER_FETCH_MULTIPLIER,
                ),
            )

        combined: list[_RetrievedChunk] = []

        for collection in self.config.collections:
            name = collection.strip()
            if not name:
                continue
            if not qdrant.collection_exists(name):
                logger.debug("Skipping missing collection '%s'", name)
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

        for chunk in combined:
            key = (
                chunk.collection.casefold(),
                (chunk.accession_number or "").casefold(),
                chunk.snippet.casefold(),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(chunk)
            if len(deduped) >= self.config.top_k:
                break

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
    ) -> tuple[str, list[str]]:
        if not citations:
            return (
                "I could not find indexed evidence for this question in the selected collections.",
                [],
            )

        prompt = self._build_prompt(question=question, citations=citations)
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

        return (
            "You are a financial filings assistant.\n"
            "Use only the provided context.\n"
            "If context is insufficient, say so directly.\n"
            "Every factual claim must include citation IDs in [C#] form.\n\n"
            f"Conversation history:\n{history_block}\n\n"
            f"Question:\n{question}\n\n"
            f"Context chunks:\n{context_block}\n\n"
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
    ) -> list[Path]:
        symbol = (
            self.config.symbols[0].upper()
            if self.config.symbols
            else (citations[0].symbol or "ALL")
            if citations
            else "ALL"
        )

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
            metadata={
                "collections": list(self.config.collections),
                "top_k": self.config.top_k,
                "max_context_chunks": self.config.max_context_chunks,
                "strict_citations": self.config.strict_citations,
                "include_history": self.config.include_history,
                "history_turns": self.config.history_turns,
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
            },
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
