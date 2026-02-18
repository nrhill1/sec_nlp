"""Tests for RAG chat pipeline."""

from __future__ import annotations

import json
from pathlib import Path

from sec_nlp.pipelines.presets.chat import ChatPipeline, ChatSettings
from sec_nlp.pipelines.presets.chat.pipeline import _RetrievedChunk


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

    csv_path = next(path for path in result.outputs if path.suffix == ".csv")
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
    assert lines[4] == "turn_index,role,message,citations"


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
