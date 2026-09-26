# tests/core/test_documents.py
"""Test dependency-free document records and optional adapter boundaries.

These checks protect source metadata when deterministic services enrich records
and ensure specialist imports work before optional AI packages are installed.
"""

import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from sec_nlp.core.documents import DocumentRecord


def test_document_owns_metadata_and_freezes_identity() -> None:
    """Keep caller metadata independent while forbidding source replacement."""
    metadata = {"source": "filing.html"}
    record = DocumentRecord(
        page_content="Quoted filing evidence.", metadata=metadata, id="filing:1"
    )
    record.metadata.update({"symbol": "AAPL"})
    assert metadata == {"source": "filing.html"}
    with pytest.raises(ValidationError, match="frozen"):
        record.page_content = "Changed evidence."


def test_vector_document_round_trip_preserves_provenance() -> None:
    """Keep text and source identifiers intact across the optional adapter."""
    from sec_nlp.adapters.documents import from_langchain, to_langchain

    record = DocumentRecord(
        page_content="Evidence.",
        metadata={"source": "filing.html", "symbol": "AAPL"},
        id="filing:1",
    )
    external = to_langchain(record)
    external.metadata["score"] = 0.8
    restored = from_langchain(external)
    assert restored.page_content == record.page_content
    assert restored.id == record.id
    assert restored.metadata["source"] == "filing.html"
    assert restored.metadata["score"] == 0.8
    assert "score" not in record.metadata


def test_deterministic_specialist_imports_without_optional_packages(
    tmp_path: Path,
) -> None:
    """Import deterministic services with AI and model packages unavailable."""
    script = """
import sys
for package in ('langchain', 'langchain_core', 'langchain_community', 'langchain_ollama', 'langchain_qdrant', 'langchain_experimental', 'qdrant_client', 'numpy', 'pandas', 'nltk', 'unstructured'):
    sys.modules[package] = None
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.pipelines.presets.exb.pipeline import ExhibitPipeline
from sec_nlp.pipelines.presets.warranty.pipeline import WarrantyPipeline
from sec_nlp.pipelines.presets.financials.pipeline import FinancialsPipeline
from sec_nlp.pipelines.presets.holdings.pipeline import HoldingsPipeline
from sec_nlp.pipelines.presets.insider.pipeline import InsiderPipeline
from sec_nlp.pipelines.presets.retrieve.pipeline import RetrievePipeline
from sec_nlp.core.text.semantic_settings import SemanticChunkingSettings
assert not SemanticChunkingSettings().enabled
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
