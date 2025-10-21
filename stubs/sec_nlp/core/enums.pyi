from enum import Enum

class FilingMode(str, Enum):
    annual = "annual"
    quarterly = "quarterly"
    @property
    def form(self) -> str: ...
