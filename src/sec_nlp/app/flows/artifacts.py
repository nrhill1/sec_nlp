"""Typed in-memory artifact storage for flow stage handoff."""

from __future__ import annotations

from sec_nlp.pipelines.presets.chat.bridge import ChatSeedBundle, ChatSeedChunk
from sec_nlp.pipelines.presets.retrieve.bridge import (
    RetrieveChatSeedBundle,
    RetrieveChatSeedChunk,
)


class FlowArtifactStore:
    """Stage-scoped in-memory artifact store for local flow runs."""

    def __init__(self) -> None:
        self._retrieve_seed_by_stage: dict[str, RetrieveChatSeedBundle] = {}
        self._chat_seed_cache: dict[str, ChatSeedBundle] = {}

    def put_retrieve_seed(
        self, stage_id: str, bundle: RetrieveChatSeedBundle
    ) -> None:
        """Store retrieve handoff bundle keyed by stage ID."""
        self._retrieve_seed_by_stage[stage_id] = bundle
        self._chat_seed_cache.pop(stage_id, None)

    def get_retrieve_seed(self, stage_id: str) -> RetrieveChatSeedBundle | None:
        """Load retrieve seed bundle for a stage ID."""
        return self._retrieve_seed_by_stage.get(stage_id)

    def get_chat_seed(self, stage_id: str) -> ChatSeedBundle | None:
        """Get chat seed bundle converted from retrieve artifact once."""
        cached = self._chat_seed_cache.get(stage_id)
        if cached is not None:
            return cached

        retrieve_bundle = self.get_retrieve_seed(stage_id)
        if retrieve_bundle is None:
            return None

        chat_bundle = ChatSeedBundle(
            upstream_pipeline="retrieve",
            upstream_run_id=retrieve_bundle.run_id,
            upstream_short_id=retrieve_bundle.run_short_id,
            symbols=list(retrieve_bundle.symbols),
            queries=list(retrieve_bundle.queries),
            chunks=[
                self._to_chat_chunk(chunk) for chunk in retrieve_bundle.chunks
            ],
        )
        self._chat_seed_cache[stage_id] = chat_bundle
        return chat_bundle

    @staticmethod
    def _to_chat_chunk(chunk: RetrieveChatSeedChunk) -> ChatSeedChunk:
        return ChatSeedChunk(
            collection=chunk.collection,
            score=chunk.score,
            symbol=chunk.symbol,
            accession_number=chunk.accession_number,
            form_type=chunk.form_type,
            filed_date=chunk.filed_date,
            source=chunk.source,
            snippet=chunk.snippet,
        )
