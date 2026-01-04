# src/sec_nlp/core/filing_mode.py
from __future__ import annotations

from enum import StrEnum


class FilingMode(StrEnum):
    """
    Enum values are CLI/user-facing tokens ("annual"/"quarterly"/"current"/"proxy"/"holdings").
    Use .form to get the SEC form code ("10-K"/"10-Q"/"8-K"/"DEF 14A"/"13F-HR").
    """

    annual = "annual"
    quarterly = "quarterly"
    current = "current"
    proxy = "proxy"
    holdings = "holdings"

    def __str__(self) -> str:
        return self.value

    @property
    def form(self) -> str:
        """Return the SEC form type for this filing mode."""
        if self is FilingMode.annual:
            return "10-K"
        elif self is FilingMode.quarterly:
            return "10-Q"
        elif self is FilingMode.current:
            return "8-K"
        elif self is FilingMode.proxy:
            return "DEF 14A"
        elif self is FilingMode.holdings:
            return "13F-HR"
        else:
            raise ValueError(f"Unknown filing mode: {self}")

    @property
    def description(self) -> str:
        """Return a human-readable description of the filing type."""
        descriptions = {
            FilingMode.annual: "Annual Report",
            FilingMode.quarterly: "Quarterly Report",
            FilingMode.current: "Current Report (Material Events)",
            FilingMode.proxy: "Proxy Statement (Shareholder Meeting)",
            FilingMode.holdings: "Institutional Holdings Report",
        }
        return descriptions.get(self, "Unknown")
