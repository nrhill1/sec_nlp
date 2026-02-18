# src/sec_nlp/core/edgar/relationship_resolver.py
"""Resolve relationships between SEC filings using on-disk metadata."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Final

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonDict

from .relationships import (
    FilingIdentifier,
    FilingRelation,
    FilingRelationshipGraph,
    FilingRelationType,
)

_ACCESSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"\d{10}-\d{2}-\d{6}")
_FORM_TYPE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"CONFORMED SUBMISSION TYPE:\s*(.+)"
)
_FILED_DATE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"FILED AS OF DATE:\s*(\d{8})"
)
_PERIOD_END_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"CONFORMED PERIOD OF REPORT:\s*(\d{8})"
)
_CIK_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"CENTRAL INDEX KEY:\s*(\d{10})"
)
_ACCEPTANCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"<ACCEPTANCE-DATETIME>(\d{14})"
)

_RELATED_CURRENT_REPORT_WINDOW_DAYS: Final[int] = 30


def _parse_yyyymmdd(value: str) -> date | None:
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    if "-" in value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return _parse_yyyymmdd(value)


def _normalize_accession(value: str) -> str:
    return value.replace("-", "").strip()


def _infer_fiscal_period(
    *,
    form_type: str | None,
    period_end: date | None,
    filed_date: date | None,
) -> tuple[int | None, str | None]:
    if period_end:
        fiscal_year = period_end.year
    elif filed_date:
        fiscal_year = filed_date.year
    else:
        fiscal_year = None

    if not form_type:
        return fiscal_year, None

    base_form = form_type[:-2] if form_type.endswith("/A") else form_type
    if base_form == "10-K":
        return fiscal_year, "FY"
    if base_form == "10-Q" and period_end:
        quarter = (period_end.month - 1) // 3 + 1
        return fiscal_year, f"Q{quarter}"

    return fiscal_year, None


def _is_proxy_form(form_type: str | None) -> bool:
    if not form_type:
        return False
    normalized = form_type.replace(" ", "").upper()
    return normalized in {"DEF14A", "DEFA14A"}


class RelationshipResolver:
    """Resolve filing relationships for a symbol based on on-disk headers."""

    def __init__(
        self,
        downloads_folder: Path,
        *,
        header_line_limit: int = 2000,
    ) -> None:
        self.downloads_folder = downloads_folder
        self.header_line_limit = header_line_limit

    def resolve_symbol(self, symbol: str) -> FilingRelationshipGraph:
        graph = FilingRelationshipGraph()
        symbol_dir = (
            self.downloads_folder / "sec-edgar-filings" / symbol.upper()
        )
        if not symbol_dir.exists():
            logger.debug("No filings directory for %s", symbol)
            return graph

        entries = self._collect_entries(symbol_dir, symbol.upper())
        for filing, _references in entries:
            graph.add_filing(filing)

        for filing, references in entries:
            for accession, relation_type, evidence in references:
                target = graph.filings.get(accession)
                if target is None:
                    target = FilingIdentifier(accession_number=accession)
                relation = FilingRelation(
                    source=filing,
                    target=target,
                    relation_type=relation_type,
                    confidence=0.7,
                    evidence=evidence,
                )
                graph.add_relation(relation)

        filings = [entry[0] for entry in entries]
        self._add_amendment_relations(graph, filings)
        self._add_same_period_relations(graph, filings)
        self._add_same_fiscal_year_relations(graph, filings)
        self._add_related_current_report_relations(graph, filings)
        self._add_proxy_relations(graph, filings)

        return graph

    def _collect_entries(
        self,
        symbol_dir: Path,
        symbol: str,
    ) -> list[
        tuple[FilingIdentifier, list[tuple[str, FilingRelationType, str]]]
    ]:
        entries: list[
            tuple[FilingIdentifier, list[tuple[str, FilingRelationType, str]]]
        ] = []
        for form_dir in symbol_dir.iterdir():
            if not form_dir.is_dir():
                continue
            for accession_dir in form_dir.iterdir():
                if not accession_dir.is_dir():
                    continue
                header_lines = self._read_header_lines(accession_dir)
                identifier = self._build_identifier(
                    accession_dir=accession_dir,
                    symbol=symbol,
                    form_fallback=form_dir.name,
                    header_lines=header_lines,
                )
                references = self._extract_references(
                    header_lines,
                    identifier.accession_number,
                )
                entries.append((identifier, references))
        return entries

    def _read_header_lines(self, filing_dir: Path) -> list[str]:
        submission_path = filing_dir / "full-submission.txt"
        if not submission_path.exists():
            return []
        lines: list[str] = []
        try:
            with open(
                submission_path, encoding="utf-8", errors="ignore"
            ) as handle:
                for line in handle:
                    cleaned = line.strip()
                    if cleaned:
                        lines.append(cleaned)
                    if cleaned.startswith(("</SEC-HEADER>", "<DOCUMENT>")):
                        break
                    if len(lines) >= self.header_line_limit:
                        break
        except OSError as exc:
            logger.debug(
                "Failed to read full-submission for %s: %s",
                filing_dir.name,
                exc,
            )
        return lines

    def _extract_references(
        self,
        header_lines: list[str],
        accession_number: str,
    ) -> list[tuple[str, FilingRelationType, str]]:
        references: list[tuple[str, FilingRelationType, str]] = []
        seen: set[tuple[str, FilingRelationType]] = set()
        own_normalized = _normalize_accession(accession_number)

        for line in header_lines:
            upper = line.upper()
            relation_type = self._classify_reference_line(upper)
            if relation_type is None:
                continue
            for match in _ACCESSION_PATTERN.findall(line):
                if _normalize_accession(match) == own_normalized:
                    continue
                key = (_normalize_accession(match), relation_type)
                if key in seen:
                    continue
                seen.add(key)
                references.append((match, relation_type, line.strip()))

        return references

    @staticmethod
    def _classify_reference_line(
        upper_line: str,
    ) -> FilingRelationType | None:
        if "INCORPORAT" in upper_line:
            return FilingRelationType.incorporation_by_reference
        if "EXHIBIT" in upper_line:
            return FilingRelationType.exhibit_reference
        return None

    def _build_identifier(
        self,
        *,
        accession_dir: Path,
        symbol: str,
        form_fallback: str,
        header_lines: list[str],
    ) -> FilingIdentifier:
        accession_number = accession_dir.name
        form_type = self._extract_header_value(header_lines, _FORM_TYPE_PATTERN)
        if not form_type:
            form_type = form_fallback

        filed_date = self._extract_header_value(
            header_lines, _FILED_DATE_PATTERN
        )
        acceptance = self._extract_header_value(
            header_lines, _ACCEPTANCE_PATTERN
        )
        period_end = self._extract_header_value(
            header_lines, _PERIOD_END_PATTERN
        )
        cik = self._extract_header_value(header_lines, _CIK_PATTERN)

        filed_date_obj = _parse_date(filed_date) if filed_date else None
        if filed_date_obj is None and acceptance:
            filed_date_obj = _parse_date(acceptance[:8])

        period_end_obj = _parse_date(period_end) if period_end else None
        fiscal_year, fiscal_period = _infer_fiscal_period(
            form_type=form_type,
            period_end=period_end_obj,
            filed_date=filed_date_obj,
        )

        return FilingIdentifier(
            accession_number=accession_number,
            cik=cik,
            form_type=form_type,
            filed_date=filed_date_obj,
            fiscal_year=fiscal_year,
            fiscal_period=fiscal_period,
            symbol=symbol,
        )

    @staticmethod
    def _extract_header_value(
        header_lines: list[str],
        pattern: re.Pattern[str],
    ) -> str | None:
        for line in header_lines:
            match = pattern.search(line)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _select_best_candidate(
        *,
        amendment: FilingIdentifier,
        candidates: list[FilingIdentifier],
    ) -> FilingIdentifier | None:
        if not candidates:
            return None
        if amendment.filed_date:
            dated = [
                filing
                for filing in candidates
                if filing.filed_date
                and filing.filed_date <= amendment.filed_date
            ]
            if dated:
                return max(dated, key=lambda filing: filing.filed_date)
        return max(
            candidates,
            key=lambda filing: filing.filed_date or date.min,
        )

    def _add_amendment_relations(
        self,
        graph: FilingRelationshipGraph,
        filings: list[FilingIdentifier],
    ) -> None:
        for filing in filings:
            if not filing.is_amendment:
                continue
            base_form = filing.base_form_type
            if not base_form:
                continue
            candidates = [
                other
                for other in filings
                if other.base_form_type == base_form and not other.is_amendment
            ]
            if filing.fiscal_year and filing.fiscal_period:
                candidates = [
                    other
                    for other in candidates
                    if other.fiscal_year == filing.fiscal_year
                    and other.fiscal_period == filing.fiscal_period
                ]
            elif filing.fiscal_year:
                candidates = [
                    other
                    for other in candidates
                    if other.fiscal_year == filing.fiscal_year
                ]
            target = self._select_best_candidate(
                amendment=filing, candidates=candidates
            )
            if target is None:
                continue
            relation = FilingRelation(
                source=filing,
                target=target,
                relation_type=FilingRelationType.amendment,
                confidence=1.0,
                evidence="Form type suffix indicates amendment",
            )
            graph.add_relation(relation)

    @staticmethod
    def _add_same_period_relations(
        graph: FilingRelationshipGraph,
        filings: list[FilingIdentifier],
    ) -> None:
        grouped: dict[tuple[int, str], list[FilingIdentifier]] = defaultdict(
            list
        )
        for filing in filings:
            if filing.fiscal_year is None or filing.fiscal_period is None:
                continue
            grouped[(filing.fiscal_year, filing.fiscal_period)].append(filing)

        for (year, period), group in grouped.items():
            if len(group) < 2:
                continue
            for i, source in enumerate(group):
                for target in group[i + 1 :]:
                    relation = FilingRelation(
                        source=source,
                        target=target,
                        relation_type=FilingRelationType.same_period,
                        confidence=0.8,
                        evidence=f"Shared fiscal period {period} {year}",
                    )
                    graph.add_relation(relation)

    @staticmethod
    def _add_same_fiscal_year_relations(
        graph: FilingRelationshipGraph,
        filings: list[FilingIdentifier],
    ) -> None:
        grouped: dict[int, list[FilingIdentifier]] = defaultdict(list)
        for filing in filings:
            if filing.fiscal_year is None:
                continue
            grouped[filing.fiscal_year].append(filing)

        for year, group in grouped.items():
            if len(group) < 2:
                continue
            for i, source in enumerate(group):
                for target in group[i + 1 :]:
                    relation = FilingRelation(
                        source=source,
                        target=target,
                        relation_type=FilingRelationType.same_fiscal_year,
                        confidence=0.6,
                        evidence=f"Shared fiscal year {year}",
                    )
                    graph.add_relation(relation)

    @staticmethod
    def _add_related_current_report_relations(
        graph: FilingRelationshipGraph,
        filings: list[FilingIdentifier],
    ) -> None:
        current_reports = [
            filing
            for filing in filings
            if (filing.base_form_type or "") in {"8-K", "6-K"}
            and filing.filed_date
        ]
        bases = [
            filing
            for filing in filings
            if (filing.base_form_type or "") in {"10-K", "10-Q"}
            and filing.filed_date
        ]

        for base in bases:
            for current_report in current_reports:
                if not base.filed_date or not current_report.filed_date:
                    continue
                delta = abs((current_report.filed_date - base.filed_date).days)
                if delta > _RELATED_CURRENT_REPORT_WINDOW_DAYS:
                    continue
                relation = FilingRelation(
                    source=base,
                    target=current_report,
                    relation_type=FilingRelationType.related_8k,
                    confidence=0.5,
                    evidence=(
                        f"{current_report.base_form_type or 'Current report'} "
                        f"filed within {_RELATED_CURRENT_REPORT_WINDOW_DAYS} "
                        f"days of {base.form_type or 'filing'}"
                    ),
                )
                graph.add_relation(relation)

    @staticmethod
    def _add_proxy_relations(
        graph: FilingRelationshipGraph,
        filings: list[FilingIdentifier],
    ) -> None:
        proxies = [
            filing for filing in filings if _is_proxy_form(filing.form_type)
        ]
        annuals = [
            filing
            for filing in filings
            if (filing.base_form_type or "") == "10-K"
            and not filing.is_amendment
        ]
        if not annuals:
            annuals = [
                filing
                for filing in filings
                if (filing.base_form_type or "") == "10-K"
            ]

        for proxy in proxies:
            if proxy.fiscal_year is None:
                continue
            candidates = [
                filing
                for filing in annuals
                if filing.fiscal_year == proxy.fiscal_year
            ]
            if not candidates:
                continue
            target = max(
                candidates,
                key=lambda filing: filing.filed_date or date.min,
            )
            relation = FilingRelation(
                source=proxy,
                target=target,
                relation_type=FilingRelationType.proxy_for_annual,
                confidence=0.7,
                evidence=f"Proxy and annual filing in {proxy.fiscal_year}",
            )
            graph.add_relation(relation)


def build_related_filings_map(
    graph: FilingRelationshipGraph,
) -> dict[str, list[JsonDict]]:
    related: dict[str, list[JsonDict]] = defaultdict(list)
    for relation in graph.relations:
        target = relation.target
        related[relation.source.accession_number].append(
            {
                "accession_number": target.accession_number,
                "form_type": target.form_type,
                "filed_date": (
                    target.filed_date.isoformat() if target.filed_date else None
                ),
                "fiscal_year": target.fiscal_year,
                "fiscal_period": target.fiscal_period,
                "relation_type": str(relation.relation_type),
                "confidence": relation.confidence,
                "evidence": relation.evidence,
            }
        )
    return dict(related)


def serialize_relationship_graph(
    graph: FilingRelationshipGraph,
) -> JsonDict:
    filings_payload: JsonDict = {}
    for accession, filing in graph.filings.items():
        filings_payload[accession] = {
            "accession_number": filing.accession_number,
            "cik": filing.cik,
            "form_type": filing.form_type,
            "filed_date": (
                filing.filed_date.isoformat() if filing.filed_date else None
            ),
            "fiscal_year": filing.fiscal_year,
            "fiscal_period": filing.fiscal_period,
            "symbol": filing.symbol,
        }

    relations_payload: list[JsonDict] = []
    for relation in graph.relations:
        relations_payload.append(
            {
                "source": relation.source.accession_number,
                "target": relation.target.accession_number,
                "relation_type": str(relation.relation_type),
                "confidence": relation.confidence,
                "evidence": relation.evidence,
            }
        )

    return {
        "filings": filings_payload,
        "relations": relations_payload,
    }
