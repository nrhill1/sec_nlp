# src/sec_nlp/pipelines/presets/exb/steps/extract/contract_types.py
"""Contract type categorization for contract exhibits."""

from __future__ import annotations

from enum import StrEnum


class ContractCategory(StrEnum):
    """Categories of contracts found in contract exhibits."""

    SUPPLY = "supply"
    CREDIT = "credit"
    EMPLOYMENT = "employment"
    LEASE = "lease"
    LICENSE = "license"
    SERVICE = "service"
    OTHER = "other"

    @classmethod
    def material_categories(cls) -> list[ContractCategory]:
        """Return categories typically considered 'material contracts'."""
        return [cls.SUPPLY, cls.LICENSE, cls.SERVICE, cls.LEASE]

    @classmethod
    def non_material_categories(cls) -> list[ContractCategory]:
        """Return categories typically considered non-material (credit, employment)."""
        return [cls.CREDIT, cls.EMPLOYMENT]


# Keyword mappings for each contract category
# Used for pre-filtering and scoring chunks
CONTRACT_KEYWORDS: dict[ContractCategory, list[str]] = {
    ContractCategory.SUPPLY: [
        "supply agreement",
        "supply contract",
        "purchase agreement",
        "procurement",
        "supplier",
        "vendor",
        "component",
        "parts",
        "materials",
        "goods",
        "delivery",
        "shipment",
        "inventory",
        "manufacturing",
        "oem",
        "distributor",
        "distribution agreement",
        "exclusive",
        "exclusivity",
        "aftermarket",
        "repair",
        "replacement",
        "maintenance",
        "service parts",
        "spare parts",
        "at cost",
        "cost plus",
    ],
    ContractCategory.CREDIT: [
        "credit agreement",
        "credit facility",
        "loan agreement",
        "revolving credit",
        "term loan",
        "borrower",
        "lender",
        "interest rate",
        "libor",
        "sofr",
        "principal",
        "maturity",
        "covenant",
        "collateral",
        "security interest",
        "guarantor",
        "indebtedness",
        "promissory note",
    ],
    ContractCategory.EMPLOYMENT: [
        "employment agreement",
        "employment contract",
        "executive compensation",
        "severance",
        "termination",
        "base salary",
        "bonus",
        "equity award",
        "stock option",
        "restricted stock",
        "change of control",
        "non-compete",
        "non-solicitation",
        "confidentiality",
    ],
    ContractCategory.LEASE: [
        "lease agreement",
        "lease contract",
        "landlord",
        "tenant",
        "premises",
        "rent",
        "lease term",
        "renewal option",
        "square feet",
        "real property",
        "sublease",
        "operating lease",
        "finance lease",
    ],
    ContractCategory.LICENSE: [
        "license agreement",
        "licensing",
        "intellectual property",
        "patent",
        "trademark",
        "copyright",
        "royalty",
        "royalties",
        "sublicense",
        "technology transfer",
        "know-how",
        "trade secret",
        "software license",
    ],
    ContractCategory.SERVICE: [
        "service agreement",
        "services contract",
        "consulting agreement",
        "professional services",
        "managed services",
        "outsourcing",
        "statement of work",
        "service level",
        "sla",
        "maintenance agreement",
        "support services",
    ],
    ContractCategory.OTHER: [],
}


def get_keywords_for_categories(
    categories: list[ContractCategory],
) -> list[str]:
    """Get combined keyword list for specified categories."""
    keywords: set[str] = set()
    for cat in categories:
        keywords.update(CONTRACT_KEYWORDS.get(cat, []))
    return sorted(keywords)


def detect_contract_category(text: str) -> ContractCategory:
    """Detect the most likely contract category from text content.

    Uses keyword density to determine category. Returns OTHER if no
    clear match.
    """
    text_lower = text.lower()
    scores: dict[ContractCategory, int] = {}

    for category, keywords in CONTRACT_KEYWORDS.items():
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[category] = score

    if not scores:
        return ContractCategory.OTHER

    return max(scores, key=lambda k: scores[k])


def is_category_match(
    text: str,
    categories: list[ContractCategory],
    min_keywords: int = 2,
) -> bool:
    """Check if text matches any of the specified categories.

    Args:
        text: Content to check
        categories: Categories to match against
        min_keywords: Minimum keyword hits required

    Returns:
        True if text matches at least one category with sufficient keywords
    """
    text_lower = text.lower()

    for category in categories:
        keywords = CONTRACT_KEYWORDS.get(category, [])
        hits = sum(1 for kw in keywords if kw in text_lower)
        if hits >= min_keywords:
            return True

    return False
