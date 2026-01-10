"""Manual stub for the CLI market command."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel, ConfigDict

from sec_nlp.core.market import MarketQuote

def _format_quote(quote: MarketQuote) -> str: ...

class Market(BaseModel):
    model_config: ConfigDict
    ticker: str
    start_date: date | None
    end_date: date | None
    latest: bool
    limit: int

    def _has_range(self) -> bool: ...
    def _print_range(self, quotes: Sequence[MarketQuote]) -> None: ...
    def cli_cmd(self) -> None: ...
