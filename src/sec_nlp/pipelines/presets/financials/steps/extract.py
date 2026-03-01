# src/sec_nlp/pipelines/presets/financials/steps/extract.py
"""XBRL extraction + concept normalization for the financials pipeline."""

from __future__ import annotations

import math
import re
from pathlib import Path

from sec_nlp.core.edgar.xbrl_facts import XbrlFact, XbrlParser
from sec_nlp.core.infra.logger import logger

from ..models import FinancialFact
from .download import DownloadedFiling

CANONICAL_CONCEPT_ALIASES: dict[str, str] = {
    # Revenue
    "revenuefromcontractwithcustomerexcludingassessedtax": "revenue",
    "revenues": "revenue",
    "salesrevenuenet": "revenue",
    "revenue": "revenue",
    "ifrs-full:revenue": "revenue",
    # Net income
    "netincomeloss": "net_income",
    "profitloss": "net_income",
    "ifrs-full:profitloss": "net_income",
    # EPS
    "earningspersharebasic": "eps_basic",
    "earningspersharediluted": "eps_diluted",
    "basicearningslosspershare": "eps_basic",
    "dilutedearningslosspershare": "eps_diluted",
    # Balance sheet
    "assets": "total_assets",
    "liabilities": "total_liabilities",
    "liabilitiesandstockholdersequity": "total_liabilities",
    "stockholdersequity": "stockholders_equity",
    "equityattributabletoownersofparent": "stockholders_equity",
    "cashandcashequivalentsatcarryingvalue": "cash_and_cash_equivalents",
    "cashandcashequivalents": "cash_and_cash_equivalents",
    "longtermdebt": "long_term_debt",
    "longtermdebtnoncurrent": "long_term_debt",
    "noncurrentborrowings": "long_term_debt",
    "currentassets": "current_assets",
    "currentliabilities": "current_liabilities",
    # Income statement line items
    "operatingincomeloss": "operating_income",
    "profitlossfromoperatingactivities": "operating_income",
    "grossprofit": "gross_profit",
}


def _normalize_token(value: str) -> str:
    """Normalize text token for XBRL tag matching."""
    return re.sub(r"[^a-z0-9:]", "", value.lower())


def normalize_concept(tag: str, local_name: str) -> str | None:
    """Map raw tag/local-name values to canonical concept identifiers."""
    candidates = (
        tag,
        local_name,
        tag.split(":", 1)[-1] if ":" in tag else tag,
    )
    for candidate in candidates:
        key = _normalize_token(candidate)
        if key in CANONICAL_CONCEPT_ALIASES:
            return CANONICAL_CONCEPT_ALIASES[key]
    return None


def _period_for_fact(
    fact: XbrlFact,
) -> tuple[str | None, str | None, str | None]:
    """Resolve reporting period label for an extracted XBRL fact."""
    return fact.period_start, fact.period_end, fact.period_instant


def _discover_xbrl_files(filing_dir: Path) -> list[Path]:
    """Discover candidate XBRL files under an accession directory."""
    files: list[Path] = []
    for pattern in ("*.xml", "*.htm", "*.html"):
        files.extend(sorted(filing_dir.glob(pattern)))
    if not files:
        fallback = filing_dir / "full-submission.txt"
        if fallback.exists():
            files.append(fallback)
    return files


def extract_financial_facts(
    *, symbol: str, filing: DownloadedFiling, parser: XbrlParser
) -> list[FinancialFact]:
    """Extract normalized financial facts from filing files."""
    normalized_symbol = symbol.upper()
    output: list[FinancialFact] = []
    seen: set[tuple[str, str | None, float, str | None]] = set()

    for source_path in _discover_xbrl_files(filing.filing_dir):
        try:
            parsed_facts = parser.parse_file(source_path)
        except Exception as exc:
            logger.debug(
                "XBRL parse failed for %s (%s): %s",
                source_path,
                filing.accession_number,
                exc,
            )
            continue

        for raw_fact in parsed_facts:
            concept = normalize_concept(raw_fact.tag, raw_fact.local_name)
            if concept is None:
                continue
            if not math.isfinite(raw_fact.value):
                continue

            period_start, period_end, period_instant = _period_for_fact(
                raw_fact
            )
            period_key = period_end or period_instant or period_start
            dedupe_key = (concept, period_key, raw_fact.value, raw_fact.segment)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            output.append(
                FinancialFact(
                    symbol=normalized_symbol,
                    accession_number=filing.accession_number,
                    form_type=filing.form_type,
                    concept=concept,
                    raw_tag=raw_fact.tag,
                    value=raw_fact.value,
                    unit=raw_fact.unit,
                    decimals=raw_fact.decimals,
                    period_start=period_start,
                    period_end=period_end,
                    period_instant=period_instant,
                    segment=raw_fact.segment,
                    source_file=source_path.name,
                )
            )

    return output
