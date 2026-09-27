# tests/core/test_parser_model_preflight.py
"""Verify HTML parsing never downloads or installs a missing NLP model.

The pinned Unstructured version automatically installs its spaCy model unless
we validate an existing local model before calling its partitioner. Missing or
broken models must use the established logged text fallback with provenance.
"""

from collections.abc import Iterator
from importlib.machinery import ModuleSpec
from pathlib import Path
from unittest.mock import patch

import pytest
from unstructured.documents.elements import ElementMetadata, NarrativeText

from sec_nlp.core.ingest.parser import HtmlProcessor, _require_local_html_model
from sec_nlp.core.text.semantic_settings import SemanticChunkingSettings


def _processor() -> HtmlProcessor:
    """Build the deterministic parser with short source-preserving chunks."""
    return HtmlProcessor(
        section_chunking=False,
        chunk_size=10,
        chunk_overlap=2,
        section_chunk_max_length=500000,
        keyword_mode="any",
        semantic_chunking=SemanticChunkingSettings(enabled=False),
    )


@pytest.fixture(autouse=True)
def clear_local_model_preflight() -> Iterator[None]:
    """Keep local-model verification state independent between test cases."""
    _require_local_html_model.cache_clear()
    yield
    _require_local_html_model.cache_clear()


@pytest.mark.parametrize("from_file", [False, True])
def test_missing_model_falls_back_without_partitioning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, from_file: bool
) -> None:
    """Preserve visible text and source metadata without calling the model loader."""
    html_path = tmp_path / "filing.html"
    html = "<p>Warranty reserves increased during this fiscal year.</p>"
    html_path.write_text(html)
    processor = _processor()
    with (
        patch("sec_nlp.core.ingest.parser.find_spec", return_value=None),
        patch("unstructured.partition.html.partition_html") as partition,
        patch("spacy.load") as load_model,
    ):
        records = (
            processor.transform_html(html_path)
            if from_file
            else processor.transform_html_string(
                html, metadata={"source": "filing.html"}
            )
        )
    partition.assert_not_called()
    load_model.assert_not_called()
    assert records and "Warranty reserves" in records[0].page_content
    assert records[0].metadata["source"] == (
        str(html_path) if from_file else "filing.html"
    )
    assert "automatic model downloads are disabled" in caplog.text


def test_broken_local_model_cannot_trigger_unstructured_install(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fall back before partitioning when an installed model cannot be loaded."""
    with (
        patch(
            "sec_nlp.core.ingest.parser.find_spec",
            return_value=ModuleSpec("en_core_web_sm", loader=None),
        ),
        patch("spacy.load", side_effect=OSError("incomplete model files")),
        patch("unstructured.partition.html.partition_html") as partition,
    ):
        records = _processor().transform_html_string(
            "<p>Warranty disclosure.</p>"
        )
    partition.assert_not_called()
    assert records[0].page_content == "Warranty disclosure."
    assert "could not be loaded locally" in caplog.text


def test_available_model_retains_structured_parser_and_caches_preflight(
    tmp_path: Path,
) -> None:
    """Use structured elements when a model is already usable on this machine."""
    html_path = tmp_path / "filing.html"
    html_path.write_text("<p>Warranty evidence.</p>")
    element = NarrativeText(
        "Warranty evidence.", metadata=ElementMetadata(filename="filing.html")
    )
    processor = _processor()
    with (
        patch(
            "sec_nlp.core.ingest.parser.find_spec",
            return_value=ModuleSpec("en_core_web_sm", loader=None),
        ),
        patch("spacy.load") as load_model,
        patch(
            "unstructured.partition.html.partition_html", return_value=[element]
        ) as partition,
    ):
        file_records = processor.transform_html(html_path)
        text_records = processor.transform_html_string(
            "<p>Warranty evidence.</p>"
        )
    load_model.assert_called_once_with("en_core_web_sm")
    assert partition.call_count == 2
    assert file_records[0].page_content == text_records[0].page_content
    assert file_records[0].metadata["source"] == str(html_path)
    assert file_records[0].metadata["category"] == "NarrativeText"
