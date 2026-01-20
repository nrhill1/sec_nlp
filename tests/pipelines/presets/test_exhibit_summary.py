# tests/pipelines/presets/test_exhibit_summary.py
"""Tests for expanded exhibit summaries in the exhibit pipeline."""

from pathlib import Path

from langchain_core.documents import Document

from sec_nlp.core.types import as_json_dict
from sec_nlp.pipelines.presets.exb.config import ExhibitConfig
from sec_nlp.pipelines.presets.exb.io.exhibit_summary import (
    build_exhibit_summary,
)


def _make_config(tmp_path: Path, exhibit_numbers):
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    dl_path.mkdir(parents=True, exist_ok=True)
    out_path.mkdir(parents=True, exist_ok=True)
    return ExhibitConfig(
        email="test@example.com",
        dl_path=dl_path,
        out_path=out_path,
        exhibit_numbers=exhibit_numbers,
    )


def test_build_exhibit_summary_extracts_core_details(tmp_path: Path) -> None:
    config = _make_config(tmp_path, exhibit_numbers=["10", "21", "23"])
    docs = [
        Document(
            page_content=(
                "Subsidiary Name  Jurisdiction\n"
                "Acme LLC  Delaware\n"
                "Beta Ltd  Canada"
            ),
            metadata={
                "accession_number": "0001",
                "filing_date": "2023-03-01",
                "form_type": "10-K",
                "exhibit_number": "21",
            },
        ),
        Document(
            page_content=(
                "We consent to the incorporation by reference.\n"
                "Deloitte & Touche LLP\n"
                "March 1, 2023"
            ),
            metadata={
                "accession_number": "0001",
                "filing_date": "2023-03-01",
                "form_type": "10-K",
                "exhibit_number": "23",
            },
        ),
        Document(
            page_content=(
                "This Supply Agreement is between Acme Corp. and Beta LLC. "
                "Supplier shall deliver components on time."
            ),
            metadata={
                "accession_number": "0001",
                "filing_date": "2023-03-01",
                "form_type": "10-K",
                "exhibit_number": "10",
            },
        ),
    ]

    summary = build_exhibit_summary(
        symbol="ACME",
        docs=docs,
        config=config,
    )

    accessions = summary.get("accessions")
    assert isinstance(accessions, list)
    assert len(accessions) == 1
    details = as_json_dict(accessions[0].get("exhibit_details"))
    assert details is not None

    exhibit_21 = as_json_dict(details.get("21"))
    assert exhibit_21 is not None
    assert exhibit_21.get("subsidiary_count") == 2
    subsidiaries = exhibit_21.get("subsidiaries")
    assert isinstance(subsidiaries, list)
    found_acme = False
    for item in subsidiaries:
        item_dict = as_json_dict(item)
        if item_dict is None:
            continue
        if item_dict.get("name") == "Acme LLC":
            found_acme = True
            break
    assert found_acme

    exhibit_23 = as_json_dict(details.get("23"))
    assert exhibit_23 is not None
    auditor_name = exhibit_23.get("auditor_name")
    auditor_text = auditor_name if isinstance(auditor_name, str) else ""
    assert "Deloitte" in auditor_text
    consent_date = exhibit_23.get("consent_date")
    consent_text = consent_date if isinstance(consent_date, str) else ""
    assert "March 1, 2023" in consent_text

    exhibit_10 = as_json_dict(details.get("10"))
    assert exhibit_10 is not None
    counterparties = exhibit_10.get("counterparties")
    assert isinstance(counterparties, list)
    assert any(
        isinstance(item, str) and "Acme" in item for item in counterparties
    )
    obligations = exhibit_10.get("key_obligations")
    assert isinstance(obligations, list)
    assert any(
        isinstance(item, str) and "shall deliver" in item
        for item in obligations
    )


def test_build_exhibit_summary_tracks_changes(tmp_path: Path) -> None:
    config = _make_config(tmp_path, exhibit_numbers=["21", "23"])
    docs = [
        Document(
            page_content="Alpha LLC  Delaware",
            metadata={
                "accession_number": "0001",
                "filing_date": "2023-03-01",
                "form_type": "10-K",
                "exhibit_number": "21",
            },
        ),
        Document(
            page_content="We consent. Firm One LLP. March 1, 2023.",
            metadata={
                "accession_number": "0001",
                "filing_date": "2023-03-01",
                "form_type": "10-K",
                "exhibit_number": "23",
            },
        ),
        Document(
            page_content="Alpha LLC  Delaware\nGamma Inc  Nevada",
            metadata={
                "accession_number": "0002",
                "filing_date": "2024-03-01",
                "form_type": "10-K",
                "exhibit_number": "21",
            },
        ),
        Document(
            page_content="We consent. Firm Two LLP. March 1, 2024.",
            metadata={
                "accession_number": "0002",
                "filing_date": "2024-03-01",
                "form_type": "10-K",
                "exhibit_number": "23",
            },
        ),
    ]

    summary = build_exhibit_summary(
        symbol="ACME",
        docs=docs,
        config=config,
    )

    changes = as_json_dict(summary.get("changes"))
    assert changes is not None
    subsidiaries = as_json_dict(changes.get("subsidiaries"))
    assert subsidiaries is not None
    added = subsidiaries.get("added")
    assert isinstance(added, list)
    assert "Gamma Inc" in added

    auditor_change = as_json_dict(changes.get("auditor"))
    assert auditor_change is not None
    assert auditor_change.get("from_auditor") == "Firm One LLP"
    assert auditor_change.get("to_auditor") == "Firm Two LLP"
