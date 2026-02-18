"""Tests for RAG chat pipeline."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from sec_nlp.pipelines.presets.chat import ChatPipeline, ChatSettings
from sec_nlp.pipelines.presets.chat.pipeline import _RetrievedChunk
from sec_nlp.pipelines.vector.config import VectorConfig


def test_chat_pipeline_run_writes_outputs_with_mocked_retrieval(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question="What changed in liquidity risk?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="all",
        collections=["retrieve", "analyze"],
        forms=["10-K"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        top_k=5,
    )

    monkeypatch.setattr(
        ChatPipeline,
        "_search_collections",
        lambda self, question: [
            _RetrievedChunk(
                collection="retrieve",
                score=0.91,
                symbol="CDE",
                accession_number="0000215466-24-000003",
                form_type="10-K",
                filed_date="2024-02-21",
                source="https://www.sec.gov/ixviewer/ix.html",
                snippet="Liquidity risk increased due to higher debt servicing costs.",
            )
        ],
    )
    monkeypatch.setattr(
        ChatPipeline,
        "_build_answer",
        lambda self, question, citations: (
            "Liquidity risk increased, primarily from debt costs. [C1]",
            ["C1"],
        ),
    )

    result = ChatPipeline(config=config).run()

    assert result.success is True
    assert result.hits_retrieved == 1
    assert result.citations_returned == 1
    assert result.citation_ids == ["C1"]
    assert len(result.outputs) == 3

    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    expected_short_id = config.short_id if config.short_id > 0 else None
    assert payload["run_id"] == str(config.run_id)
    assert payload["run_short_id"] == expected_short_id
    assert payload["question"] == "What changed in liquidity risk?"
    assert payload["citation_ids"] == ["C1"]
    assert payload["metadata"]["forms_filter"] == ["10-K"]
    assert payload["metadata"]["filed_after"] == "2024-01-01"
    assert payload["metadata"]["filed_before"] == "2024-12-31"

    csv_path = next(path for path in result.outputs if path.suffix == ".csv")
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
    assert lines[4] == "turn_index,role,message,citations"


def test_chunk_matches_filters_by_form_and_date() -> None:
    chunk = _RetrievedChunk(
        collection="retrieve",
        score=0.9,
        symbol="NAMM",
        accession_number="0000000000-24-000001",
        form_type="6-K/A",
        filed_date="2024-05-10",
        source="https://example.com",
        snippet="sample",
    )

    assert ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"6-K"},
        filed_after=None,
        filed_before=None,
    )
    assert not ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"8-K"},
        filed_after=None,
        filed_before=None,
    )
    assert ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"6-K"},
        filed_after=date(2024, 1, 1),
        filed_before=date(2024, 12, 31),
    )
    assert not ChatPipeline._chunk_matches_filters(
        chunk,
        forms={"6-K"},
        filed_after=date(2024, 6, 1),
        filed_before=None,
    )


def test_search_collections_applies_form_and_date_filters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["NAMM"],
        question="What changed?",
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        collections=["retrieve"],
        forms=["6-K"],
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31),
        top_k=3,
    )

    class _FakeEmbedder:
        def embed_query(self, query: str) -> list[float]:
            return [0.1, 0.2]

    class _FakePoint:
        def __init__(self, payload: dict[str, object], score: float) -> None:
            self.payload = payload
            self.score = score

    class _FakeResponse:
        def __init__(self, points: list[_FakePoint]) -> None:
            self.points = points

    class _FakeQdrant:
        def __init__(self) -> None:
            self.last_limit: int | None = None

        def collection_exists(self, name: str) -> bool:
            return True

        def query_points(self, **kwargs):
            self.last_limit = int(kwargs["limit"])
            return _FakeResponse(
                [
                    _FakePoint(
                        payload={
                            "symbol": "NAMM",
                            "form_type": "6-K",
                            "filed_date": "2024-06-01",
                            "snippet": "kept chunk",
                        },
                        score=0.95,
                    ),
                    _FakePoint(
                        payload={
                            "symbol": "NAMM",
                            "form_type": "8-K",
                            "filed_date": "2024-06-01",
                            "snippet": "wrong form",
                        },
                        score=0.94,
                    ),
                    _FakePoint(
                        payload={
                            "symbol": "NAMM",
                            "form_type": "6-K",
                            "filed_date": "2023-12-31",
                            "snippet": "too old",
                        },
                        score=0.93,
                    ),
                ]
            )

    fake_qdrant = _FakeQdrant()

    monkeypatch.setattr(
        VectorConfig,
        "setup_embedding_model",
        lambda self: (_FakeEmbedder(), 2),
    )
    monkeypatch.setattr(
        VectorConfig,
        "setup_qdrant_client",
        lambda self: fake_qdrant,
    )

    chunks = ChatPipeline(config=config)._search_collections("neodymium")

    assert len(chunks) == 1
    assert chunks[0].form_type == "6-K"
    assert chunks[0].snippet == "kept chunk"
    assert fake_qdrant.last_limit == 12


def test_chat_pipeline_run_requires_question(tmp_path: Path) -> None:
    config = ChatSettings(
        email="test@example.com",
        symbols=["CDE"],
        question=None,
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
    )

    result = ChatPipeline(config=config).run()

    assert result.success is False
    assert result.error is not None
    assert "requires a question" in result.error
