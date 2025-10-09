from enum import Enum


class FilingMode(str, Enum):
    """
    Enum values are CLI/user-facing tokens ("annual"/"quarterly").
    Use .form to get the SEC form code ("10-K"/"10-Q").
    """

    annual = "annual"
    quarterly = "quarterly"

    @property
    def form(self) -> str:
        return "10-K" if self is FilingMode.annual else "10-Q"
