from enum import StrEnum

class FilingMode(StrEnum):
    annual = "annual"
    quarterly = "quarterly"
    current = "current"
    proxy = "proxy"
    holdings = "holdings"
    @property
    def form(self) -> str: ...
    @property
    def description(self) -> str: ...
