# src/sec_nlp/core/edgar/relationships.py
"""Models for filing relationships and cross-referencing."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FilingRelationType(StrEnum):
    """Types of relationships between SEC filings."""

    # Direct relationships
    amendment = "amendment"  # 10-K/A amends 10-K
    supersedes = "supersedes"  # Later filing supersedes earlier one
    restates = "restates"  # Filing restates prior period

    # Reference relationships
    exhibit_reference = (
        "exhibit_reference"  # References exhibit from another filing
    )
    incorporation_by_reference = (
        "incorporation_by_reference"  # IBR from prior filing
    )

    # Temporal relationships
    same_period = "same_period"  # Filings covering same fiscal period
    same_fiscal_year = "same_fiscal_year"  # Filings in same fiscal year
    prior_period = "prior_period"  # Previous period filing
    subsequent_period = "subsequent_period"  # Next period filing

    # Event relationships
    related_8k = "related_8k"  # 8-K related to the filing
    proxy_for_annual = "proxy_for_annual"  # DEF 14A associated with 10-K

    def __str__(self) -> str:
        return self.value

    @property
    def is_direct(self) -> bool:
        """Check if this is a direct/explicit relationship."""
        return self in (
            FilingRelationType.amendment,
            FilingRelationType.supersedes,
            FilingRelationType.restates,
        )

    @property
    def is_temporal(self) -> bool:
        """Check if this is a temporal relationship."""
        return self in (
            FilingRelationType.same_period,
            FilingRelationType.same_fiscal_year,
            FilingRelationType.prior_period,
            FilingRelationType.subsequent_period,
        )


class FilingIdentifier(BaseModel):
    """Identifier for an SEC filing."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    accession_number: str = Field(
        description="SEC accession number (format: XXXXXXXXXX-XX-XXXXXX)",
    )
    cik: str | None = Field(
        default=None,
        description="Central Index Key (10-digit padded)",
    )
    form_type: str | None = Field(
        default=None,
        description="SEC form type (e.g., 10-K, 8-K)",
    )
    filed_date: date | None = Field(
        default=None,
        description="Date the filing was submitted",
    )
    fiscal_year: int | None = Field(
        default=None,
        description="Fiscal year covered by the filing",
    )
    fiscal_period: str | None = Field(
        default=None,
        description="Fiscal period (e.g., 'FY', 'Q1', 'Q2', 'Q3', 'Q4')",
    )
    symbol: str | None = Field(
        default=None,
        description="Ticker symbol if known",
    )

    @property
    def is_amendment(self) -> bool:
        """Check if this is an amended filing based on form type."""
        if not self.form_type:
            return False
        return self.form_type.endswith("/A")

    @property
    def base_form_type(self) -> str | None:
        """Get the base form type without amendment suffix."""
        if not self.form_type:
            return None
        if self.form_type.endswith("/A"):
            return self.form_type[:-2]
        return self.form_type


class FilingRelation(BaseModel):
    """A relationship between two SEC filings."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    source: FilingIdentifier = Field(
        description="The source filing (from which the relationship originates)",
    )
    target: FilingIdentifier = Field(
        description="The target filing (to which the relationship points)",
    )
    relation_type: FilingRelationType = Field(
        description="Type of relationship between the filings",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for the relationship (1.0 = certain)",
    )
    evidence: str | None = Field(
        default=None,
        description="Evidence or reason for the relationship",
    )

    @property
    def is_bidirectional(self) -> bool:
        """Check if this relationship type implies a reverse relationship."""
        return self.relation_type in (
            FilingRelationType.same_period,
            FilingRelationType.same_fiscal_year,
        )

    def reverse(self) -> FilingRelation | None:
        """Create the reverse relationship if applicable."""
        reverse_map: dict[FilingRelationType, FilingRelationType] = {
            FilingRelationType.prior_period: FilingRelationType.subsequent_period,
            FilingRelationType.subsequent_period: FilingRelationType.prior_period,
            FilingRelationType.same_period: FilingRelationType.same_period,
            FilingRelationType.same_fiscal_year: FilingRelationType.same_fiscal_year,
        }

        if self.relation_type not in reverse_map:
            return None

        return FilingRelation(
            source=self.target,
            target=self.source,
            relation_type=reverse_map[self.relation_type],
            confidence=self.confidence,
            evidence=self.evidence,
        )


class FilingRelationshipGraph(BaseModel):
    """A graph of relationships between SEC filings."""

    model_config = ConfigDict(
        extra="forbid",
    )

    filings: dict[str, FilingIdentifier] = Field(
        default_factory=dict,
        description="Map of accession numbers to filing identifiers",
    )
    relations: list[FilingRelation] = Field(
        default_factory=list,
        description="List of relationships between filings",
    )

    def add_filing(self, filing: FilingIdentifier) -> None:
        """Add a filing to the graph."""
        self.filings[filing.accession_number] = filing

    def add_relation(self, relation: FilingRelation) -> None:
        """Add a relationship to the graph."""
        # Ensure both filings are in the graph
        if relation.source.accession_number not in self.filings:
            self.filings[relation.source.accession_number] = relation.source
        if relation.target.accession_number not in self.filings:
            self.filings[relation.target.accession_number] = relation.target

        self.relations.append(relation)

        # Add reverse relationship if applicable
        reverse = relation.reverse()
        if reverse and not self._has_relation(reverse):
            self.relations.append(reverse)

    def _has_relation(self, relation: FilingRelation) -> bool:
        """Check if a relationship already exists."""
        for existing in self.relations:
            if (
                existing.source.accession_number
                == relation.source.accession_number
                and existing.target.accession_number
                == relation.target.accession_number
                and existing.relation_type == relation.relation_type
            ):
                return True
        return False

    def get_related(
        self,
        accession: str,
        relation_types: list[FilingRelationType] | None = None,
    ) -> list[tuple[FilingIdentifier, FilingRelation]]:
        """Get all filings related to a given accession number.

        Args:
            accession: The accession number to find relations for
            relation_types: Optional filter for specific relation types

        Returns:
            List of (related filing, relationship) tuples
        """
        results: list[tuple[FilingIdentifier, FilingRelation]] = []

        for relation in self.relations:
            if relation.source.accession_number != accession:
                continue
            if relation_types and relation.relation_type not in relation_types:
                continue

            target = self.filings.get(relation.target.accession_number)
            if target:
                results.append((target, relation))

        return results

    def get_amendments(self, accession: str) -> list[FilingIdentifier]:
        """Get all amendments to a given filing."""
        related = self.get_related(
            accession,
            relation_types=[FilingRelationType.amendment],
        )
        return [filing for filing, _ in related]

    def get_same_period_filings(self, accession: str) -> list[FilingIdentifier]:
        """Get all filings from the same period."""
        related = self.get_related(
            accession,
            relation_types=[FilingRelationType.same_period],
        )
        return [filing for filing, _ in related]

    def get_related_8ks(self, accession: str) -> list[FilingIdentifier]:
        """Get related 8-K filings."""
        related = self.get_related(
            accession,
            relation_types=[FilingRelationType.related_8k],
        )
        return [filing for filing, _ in related]
