# tests/core/edgar/test_relationships.py
"""Tests for filing relationship resolution."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.edgar.relationship_resolver import (
    RelationshipResolver,
    build_related_filings_map,
)
from sec_nlp.core.edgar.relationships import FilingRelationType
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.types import JsonDict


def _write_full_submission(
    path: Path,
    *,
    accession: str,
    form_type: str,
    filed_date: date,
    period_end: date | None,
    cik: str,
    extra_lines: list[str] | None = None,
) -> None:
    lines = [
        "<SEC-HEADER>",
        f"ACCESSION NUMBER: {accession}",
        f"CONFORMED SUBMISSION TYPE: {form_type}",
        f"FILED AS OF DATE: {filed_date.strftime('%Y%m%d')}",
        f"CENTRAL INDEX KEY: {cik}",
    ]
    if period_end:
        lines.append(
            f"CONFORMED PERIOD OF REPORT: {period_end.strftime('%Y%m%d')}"
        )
    if extra_lines:
        lines.extend(extra_lines)
    lines.append("</SEC-HEADER>")
    path.write_text("\n".join(lines))


def _create_filing(
    base: Path,
    *,
    symbol: str,
    form_dir: str,
    accession: str,
    form_type: str,
    filed_date: date,
    period_end: date | None,
    extra_lines: list[str] | None = None,
) -> None:
    filing_dir = base / "sec-edgar-filings" / symbol / form_dir / accession
    filing_dir.mkdir(parents=True, exist_ok=True)
    (filing_dir / "filing.html").write_text(
        "<html><body><p>Sample filing</p></body></html>"
    )
    _write_full_submission(
        filing_dir / "full-submission.txt",
        accession=accession,
        form_type=form_type,
        filed_date=filed_date,
        period_end=period_end,
        cik="0000123456",
        extra_lines=extra_lines,
    )


def _relations_index(
    resolver: RelationshipResolver, symbol: str
) -> set[tuple[str, str, FilingRelationType]]:
    graph = resolver.resolve_symbol(symbol)
    return {
        (
            relation.source.accession_number,
            relation.target.accession_number,
            relation.relation_type,
        )
        for relation in graph.relations
    }


def test_relationship_resolver_builds_links(tmp_path: Path) -> None:
    symbol = "ACME"
    tenk_acc = "0000000000-24-000001"
    tenk_a_acc = "0000000000-24-000002"
    eightk_acc = "0000000000-24-000003"
    proxy_acc = "0000000000-24-000004"

    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=tenk_acc,
        form_type="10-K",
        filed_date=date(2024, 2, 1),
        period_end=date(2023, 12, 31),
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=tenk_a_acc,
        form_type="10-K/A",
        filed_date=date(2024, 2, 20),
        period_end=date(2023, 12, 31),
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="8-K",
        accession=eightk_acc,
        form_type="8-K",
        filed_date=date(2024, 2, 15),
        period_end=None,
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="DEF 14A",
        accession=proxy_acc,
        form_type="DEF 14A",
        filed_date=date(2024, 3, 5),
        period_end=date(2023, 12, 31),
    )

    resolver = RelationshipResolver(downloads_folder=tmp_path)
    relations = _relations_index(resolver, symbol)

    assert (tenk_a_acc, tenk_acc, FilingRelationType.amendment) in relations
    assert (
        tenk_acc,
        tenk_a_acc,
        FilingRelationType.same_period,
    ) in relations or (
        tenk_a_acc,
        tenk_acc,
        FilingRelationType.same_period,
    ) in relations
    assert (tenk_acc, eightk_acc, FilingRelationType.related_8k) in relations
    assert (
        proxy_acc,
        tenk_acc,
        FilingRelationType.proxy_for_annual,
    ) in relations


def test_relationship_resolver_parses_header_references(
    tmp_path: Path,
) -> None:
    symbol = "ACME"
    tenk_acc = "0000000000-24-000010"
    eightk_acc = "0000000000-24-000011"

    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=tenk_acc,
        form_type="10-K",
        filed_date=date(2024, 1, 20),
        period_end=date(2023, 12, 31),
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="8-K",
        accession=eightk_acc,
        form_type="8-K",
        filed_date=date(2024, 2, 5),
        period_end=None,
        extra_lines=[f"INCORPORATED BY REFERENCE: {tenk_acc}"],
    )

    resolver = RelationshipResolver(downloads_folder=tmp_path)
    relations = _relations_index(resolver, symbol)

    assert (
        eightk_acc,
        tenk_acc,
        FilingRelationType.incorporation_by_reference,
    ) in relations


def test_relationship_resolver_links_6k_as_related_current_report(
    tmp_path: Path,
) -> None:
    symbol = "ACME"
    tenq_acc = "0000000000-24-000040"
    sixk_acc = "0000000000-24-000041"

    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-Q",
        accession=tenq_acc,
        form_type="10-Q",
        filed_date=date(2024, 5, 1),
        period_end=date(2024, 3, 31),
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="6-K",
        accession=sixk_acc,
        form_type="6-K",
        filed_date=date(2024, 5, 10),
        period_end=None,
    )

    resolver = RelationshipResolver(downloads_folder=tmp_path)
    relations = _relations_index(resolver, symbol)

    assert (tenq_acc, sixk_acc, FilingRelationType.related_8k) in relations


def test_loader_enriches_related_filings_metadata(
    tmp_path: Path,
) -> None:
    symbol = "ACME"
    tenk_acc = "0000000000-24-000021"
    eightk_acc = "0000000000-24-000022"

    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=tenk_acc,
        form_type="10-K",
        filed_date=date(2024, 2, 1),
        period_end=date(2023, 12, 31),
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="8-K",
        accession=eightk_acc,
        form_type="8-K",
        filed_date=date(2024, 2, 10),
        period_end=None,
    )

    loader = Loader(
        email="test@example.com",
        company_name="Test Company",
        downloads_folder=tmp_path,
    )
    loader.add_symbol(symbol)

    docs = loader.load_documents(
        mode=FilingMode.annual,
        perform_download=False,
    )

    related_items: list[JsonDict] = []
    for doc in docs:
        related = doc.metadata.get("related_filings") if doc.metadata else None
        if isinstance(related, list):
            for item in related:
                if isinstance(item, dict):
                    related_items.append(item)

    assert any(
        item.get("accession_number") == eightk_acc
        and item.get("relation_type") == "related_8k"
        for item in related_items
    )


def test_build_related_filings_map(tmp_path: Path) -> None:
    symbol = "ACME"
    tenk_acc = "0000000000-24-000031"
    tenk_a_acc = "0000000000-24-000032"

    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=tenk_acc,
        form_type="10-K",
        filed_date=date(2024, 2, 1),
        period_end=date(2023, 12, 31),
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=tenk_a_acc,
        form_type="10-K/A",
        filed_date=date(2024, 3, 1),
        period_end=date(2023, 12, 31),
    )

    resolver = RelationshipResolver(downloads_folder=tmp_path)
    graph = resolver.resolve_symbol(symbol)
    related_map = build_related_filings_map(graph)

    related_entries = related_map.get(tenk_a_acc) or []
    assert any(
        entry.get("relation_type") == "amendment"
        and entry.get("accession_number") == tenk_acc
        for entry in related_entries
    )


def test_get_amendments_returns_amending_filings(tmp_path: Path) -> None:
    symbol = "ACME"
    original_acc = "0000000000-24-000051"
    amendment_acc = "0000000000-24-000052"

    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=original_acc,
        form_type="10-K",
        filed_date=date(2024, 2, 1),
        period_end=date(2023, 12, 31),
    )
    _create_filing(
        tmp_path,
        symbol=symbol,
        form_dir="10-K",
        accession=amendment_acc,
        form_type="10-K/A",
        filed_date=date(2024, 2, 20),
        period_end=date(2023, 12, 31),
    )

    resolver = RelationshipResolver(downloads_folder=tmp_path)
    graph = resolver.resolve_symbol(symbol)

    amendments = graph.get_amendments(original_acc)

    assert [filing.accession_number for filing in amendments] == [amendment_acc]
