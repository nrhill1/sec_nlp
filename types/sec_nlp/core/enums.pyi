from enum import Enum

class FilingMode(str, Enum):
    annual = "annual"
    quarterly = "quarterly"
    def __str__(self) -> str: ...
    @property
    def form(self) -> str: ...
