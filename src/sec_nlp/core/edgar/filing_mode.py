# src/sec_nlp/core/filing_mode.py
from __future__ import annotations

from enum import StrEnum


class FilingMode(StrEnum):
    """
    Enum values are CLI/user-facing tokens.
    Use .form to get the primary SEC form code (e.g., "10-K", "S-1").
    Use .forms to get all SEC form codes for the mode.
    """

    annual = "annual"  # 10-K
    quarterly = "quarterly"  # 10-Q
    current = "current"  # 8-K / 6-K
    proxy = "proxy"  # DEF 14A
    holdings = "holdings"  # 13F-HR
    insider = "insider"  # Forms 3/4
    registration = "registration"  # S-1
    shelf_registration = "shelf"  # S-3

    def __str__(self) -> str:
        return self.value

    @property
    def form(self) -> str:
        """Return the SEC form type for this filing mode."""
        form_map: dict[FilingMode, str] = {
            FilingMode.annual: "10-K",
            FilingMode.quarterly: "10-Q",
            FilingMode.current: "8-K",
            FilingMode.proxy: "DEF 14A",
            FilingMode.holdings: "13F-HR",
            FilingMode.insider: "4",
            FilingMode.registration: "S-1",
            FilingMode.shelf_registration: "S-3",
        }
        form_type = form_map.get(self)
        if form_type is None:
            raise ValueError(f"Unknown filing mode: {self}")
        return form_type

    @property
    def description(self) -> str:
        """Return a human-readable description of the filing type."""
        descriptions: dict[FilingMode, str] = {
            FilingMode.annual: "Annual Report",
            FilingMode.quarterly: "Quarterly Report",
            FilingMode.current: "Current Report (Material Events; 8-K/6-K)",
            FilingMode.proxy: "Proxy Statement (Shareholder Meeting)",
            FilingMode.holdings: "Institutional Holdings Report",
            FilingMode.insider: "Insider Ownership Reports (Forms 3/4)",
            FilingMode.registration: "Registration Statement (IPO)",
            FilingMode.shelf_registration: "Shelf Registration Statement",
        }
        return descriptions.get(self, "Unknown")

    @property
    def forms(self):
        """Return all SEC form types associated with this mode."""
        if self == FilingMode.current:
            return ("8-K", "6-K")
        if self == FilingMode.insider:
            return ("3", "4")
        return (self.form,)

    @property
    def is_periodic(self) -> bool:
        """Check if this is a periodic filing (10-K, 10-Q)."""
        return self in (FilingMode.annual, FilingMode.quarterly)

    @property
    def is_registration(self) -> bool:
        """Check if this is a registration filing (S-1, S-3)."""
        return self in (FilingMode.registration, FilingMode.shelf_registration)
