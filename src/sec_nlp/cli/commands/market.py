"""CLI helpers for the Yahoo-backed market extension."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import (
    bullet_line,
    color_text,
    logger,
    styled_header,
)
from sec_nlp.core.market import (
    MarketExtensionError,
    MarketQuote,
    create_market_retriever,
)


def _format_quote(quote: MarketQuote) -> str:
    return (
        f"{quote.timestamp}: "
        f"open={quote.open_price:.2f} "
        f"high={quote.high:.2f} "
        f"low={quote.low:.2f} "
        f"close={quote.close:.2f} "
        f"vol={quote.volume:,}"
    )


class Market(BaseModel):
    """Fetch Yahoo quotes from the compiled market extension."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
        extra="forbid",
    )

    ticker: str = Field(
        description="Ticker symbol (e.g., AAPL).",
    )
    start_date: date | None = Field(
        default=None,
        description="Inclusive start date for range queries (requires end-date).",
    )
    end_date: date | None = Field(
        default=None,
        description="Inclusive end date for range queries (requires start-date).",
    )
    latest: bool = Field(
        default=False,
        description="Show just the latest close price instead of a full range.",
        json_schema_extra={"cli_args": {"aliases": ["-l", "--last"]}},
    )
    limit: int = Field(
        default=5,
        ge=1,
        description="Maximum number of range rows to display.",
    )

    def _has_range(self) -> bool:
        return self.start_date is not None and self.end_date is not None

    def _print_range(self, quotes: Sequence[MarketQuote]) -> None:
        logger.info(styled_header(f"Quotes: {self.ticker.upper()}"))
        if not quotes:
            logger.info(
                color_text(
                    "No quotes found for the requested range", color="yellow"
                )
            )
            return

        records = [
            {
                "timestamp": pd.to_datetime(quote.timestamp, unit="s"),
                "open": quote.open_price,
                "high": quote.high,
                "low": quote.low,
                "close": quote.close,
                "volume": quote.volume,
                "adj_close": quote.adjclose,
            }
            for quote in quotes
        ]
        df = pd.DataFrame(records).head(self.limit)
        logger.info(color_text(df.to_markdown(index=False), color="cyan"))

        if len(quotes) > self.limit:
            logger.info(
                color_text(
                    f"... {len(quotes) - self.limit} more rows not shown",
                    color="dim",
                )
            )

    def cli_cmd(self) -> None:
        """Execute a market lookup."""
        logger.info(styled_header("Market lookup"))

        retriever = create_market_retriever()

        try:
            if self.latest or not self._has_range():
                price = retriever.fetch_price(self.ticker)
                logger.info(
                    bullet_line(
                        "Latest close",
                        f"{self.ticker.upper()}: {price:.4f}",
                        color="green",
                    )
                )
                return

            assert self.start_date is not None and self.end_date is not None
            date_range: tuple[date, date] = (self.start_date, self.end_date)
            quotes = retriever.retrieve_range(self.ticker, date_range)
            self._print_range(quotes)
        except MarketExtensionError as error:
            logger.error(
                color_text(f"Failed to fetch market data: {error}", color="red")
            )
