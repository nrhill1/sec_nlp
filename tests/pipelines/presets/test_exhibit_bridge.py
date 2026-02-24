# tests/pipelines/presets/test_exhibit_bridge.py
"""Tests for EXB-to-flow bridge evidence conversion."""

from langchain_core.documents import Document

from sec_nlp.pipelines.presets.exb.bridge import build_contract_evidence_bundle


def test_build_contract_evidence_bundle_maps_metadata() -> None:
    docs = [
        Document(
            page_content="  Exclusive supply agreement for NdPr components.  ",
            metadata={
                "ticker": "AEM",
                "accession_number": "0001234567-26-000001",
                "form_type": "10-K",
                "filing_date": "2026-01-10",
                "exhibit_number": "10.1",
                "exhibit_category": "contracts",
                "section_number": "10.1",
                "source_file": "/tmp/aem/10.1.html",
                "keyword_score": "0.91",
            },
        )
    ]

    bundle = build_contract_evidence_bundle(
        symbol="AEM",
        docs=docs,
        run_id="11111111-1111-1111-1111-111111111111",
        run_short_id=42,
        queries=["exclusive supply agreement"],
    )

    assert bundle.upstream_pipeline == "exhibit"
    assert bundle.upstream_run_id == "11111111-1111-1111-1111-111111111111"
    assert bundle.upstream_short_id == 42
    assert bundle.symbols == ["AEM"]
    assert bundle.queries == ["exclusive supply agreement"]
    assert len(bundle.chunks) == 1
    assert bundle.chunks[0].accession_number == "0001234567-26-000001"
    assert bundle.chunks[0].score == 0.91
    assert bundle.chunks[0].source == "/tmp/aem/10.1.html"


def test_build_contract_evidence_bundle_truncates_snippet() -> None:
    docs = [
        Document(
            page_content="x" * 32,
            metadata={},
        )
    ]

    bundle = build_contract_evidence_bundle(
        symbol="MP",
        docs=docs,
        run_id="11111111-1111-1111-1111-111111111111",
        run_short_id=None,
        snippet_chars=12,
    )

    assert bundle.chunks[0].snippet == "xxxxxxxxx..."
