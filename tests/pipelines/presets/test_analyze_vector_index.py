# tests/pipelines/presets/test_analyze_vector_index.py
"""Tests for batched analyze vector indexing behavior."""

from collections.abc import Sequence
from pathlib import Path

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.conversions import common_types as qdrant_types
from qdrant_client.http.models import Record
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

from sec_nlp.core.text.deduplication import SimHashConfig, SimHashDeduplicator
from sec_nlp.pipelines.presets.analyze import AnalyzeConfig
from sec_nlp.pipelines.presets.analyze.steps.indexing.vector_index import (
    VectorIndexer,
)


class _FakeClient(QdrantClient):
    def __init__(self, *, existing_simhashes: set[int]) -> None:
        self.existing_simhashes = existing_simhashes
        self.scroll_calls = 0

    def scroll(
        self,
        collection_name: str,
        scroll_filter: qdrant_types.Filter | None = None,
        limit: int = 10,
        order_by: qdrant_types.OrderBy | None = None,
        offset: qdrant_types.PointId | None = None,
        with_payload: bool
        | Sequence[str]
        | qdrant_types.PayloadSelector = True,
        with_vectors: bool | Sequence[str] = False,
        consistency: qdrant_types.ReadConsistency | None = None,
        shard_key_selector: qdrant_types.ShardKeySelector | None = None,
        timeout: int | None = None,
        **kwargs,
    ) -> tuple[list[qdrant_types.Record], qdrant_types.PointId | None]:
        _ = collection_name
        _ = limit
        _ = order_by
        _ = offset
        _ = with_payload
        _ = with_vectors
        _ = consistency
        _ = shard_key_selector
        _ = timeout
        _ = kwargs
        self.scroll_calls += 1
        assert isinstance(scroll_filter, Filter)

        simhashes: set[int] = set()
        symbol = ""
        must_conditions = scroll_filter.must
        assert isinstance(must_conditions, list)
        for condition in must_conditions:
            if not isinstance(condition, FieldCondition):
                continue
            if condition.key == "metadata.simhash":
                match = condition.match
                if isinstance(match, MatchAny):
                    simhashes.update(
                        value for value in match.any if isinstance(value, int)
                    )
                elif isinstance(match, MatchValue) and isinstance(
                    match.value, int
                ):
                    simhashes.add(match.value)
            elif condition.key == "metadata.symbol":
                match = condition.match
                if isinstance(match, MatchValue) and isinstance(
                    match.value, str
                ):
                    symbol = match.value

        assert symbol == "AAPL"
        matches = sorted(self.existing_simhashes.intersection(simhashes))
        records = [
            Record(
                id=simhash,
                payload={"metadata": {"simhash": simhash}},
                vector=None,
                shard_key=None,
                order_value=None,
            )
            for simhash in matches
        ]
        return records, None


class _FakeVectorStore(QdrantVectorStore):
    def __init__(self, *, client: _FakeClient) -> None:
        self._fake_client = client
        self._collection_name = "analyze-test"
        self.added_documents: list[Document] = []

    @property
    def client(self) -> QdrantClient:
        return self._fake_client

    @property
    def collection_name(self) -> str:
        return self._collection_name

    def add_documents(self, documents: list[Document], **kwargs) -> list[str]:
        _ = kwargs
        self.added_documents.extend(documents)
        return [str(idx) for idx, _doc in enumerate(documents)]


def _simhash_for(content: str) -> int:
    deduper = SimHashDeduplicator(
        config=SimHashConfig(num_bits=64, max_distance=6)
    )
    is_unique, simhash = deduper.add_if_unique(content)
    assert is_unique
    assert isinstance(simhash, int)
    return simhash


def test_vector_indexer_batches_remote_simhash_checks(tmp_path: Path) -> None:
    existing_hash = _simhash_for("existing supplier concentration risk")
    fake_client = _FakeClient(existing_simhashes={existing_hash})
    vector_store = _FakeVectorStore(client=fake_client)
    config = AnalyzeConfig(
        symbols=["AAPL"],
        out_path=tmp_path,
        dl_path=tmp_path,
        collect_metrics=False,
    )
    deduper = SimHashDeduplicator(
        config=SimHashConfig(
            num_bits=config.simhash_bits,
            max_distance=config.simhash_max_distance,
        )
    )
    indexer = VectorIndexer(
        config=config,
        vector_store=vector_store,
        deduplicator=deduper,
    )
    docs = [
        Document(
            page_content="existing supplier concentration risk",
            metadata={"section_number": "1A"},
        ),
        Document(
            page_content="new margin expansion disclosure",
            metadata={"section_number": "7"},
        ),
        Document(
            page_content="new margin expansion disclosure",
            metadata={"section_number": "7"},
        ),
    ]

    timings: dict[str, float] = {}
    added = indexer.index("AAPL", docs, timings)

    assert added == 1
    assert fake_client.scroll_calls == 1
    assert len(vector_store.added_documents) == 1
    stored_doc = vector_store.added_documents[0]
    assert stored_doc.page_content == "new margin expansion disclosure"
    assert stored_doc.metadata["symbol"] == "AAPL"
    assert isinstance(stored_doc.metadata["simhash"], int)
    assert "store" in timings
