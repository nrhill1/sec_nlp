# src/sec_nlp/cli/commands/market.py
"""CLI helpers for the Yahoo-backed market extension."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.formatting import (
    ColumnSpec,
    center_text,
    format_divider,
    format_key_value,
    format_section_header,
    format_status,
    format_table,
)
from sec_nlp.core.infra.logger import (
    color_text,
    logger,
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

    symbol: CliPositionalArg[str] = Field(
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
    include_adjclose: bool = Field(
        default=True,
        description="Include adjusted close in the range output.",
        json_schema_extra={"cli_args": {"aliases": ["--adjclose"]}},
    )
    format: Literal["table", "json", "csv"] = Field(
        default="table",
        description="Output format for range data.",
        json_schema_extra={"cli_args": {"choices": ["table", "json", "csv"]}},
    )
    show_stats: bool = Field(
        default=True,
        description="Show summary statistics (change, percent change, volume).",
        json_schema_extra={"cli_args": {"aliases": ["--stats"]}},
    )

    def _has_range(self) -> bool:
        return self.start_date is not None and self.end_date is not None

    def _print_range(self, quotes: Sequence[MarketQuote]) -> None:
        header = format_section_header(
            f"Quotes: {self.symbol.upper()}",
            style="box",
        )
        logger.info(header)

        if not quotes:
            logger.info(
                format_status(
                    "No quotes found for the requested range", status="warning"
                )
            )
            return

        records: list[dict[str, str | int | float]] = [
            {
                "timestamp": pd.to_datetime(quote.timestamp, unit="s").strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "open": quote.open_price,
                "high": quote.high,
                "low": quote.low,
                "close": quote.close,
                "volume": quote.volume,
                **(
                    {"adj_close": quote.adjclose}
                    if self.include_adjclose
                    else {}
                ),
            }
            for quote in quotes
        ]

        stats = self._summarize_quotes(quotes) if self.show_stats else ""
        if self.format == "json":
            preview = records[: self.limit]
            logger.info(
                color_text(
                    json.dumps(preview, default=str, indent=2), color="cyan"
                )
            )
        elif self.format == "csv":
            csv_text = (
                pd.DataFrame(records).head(self.limit).to_csv(index=False)
            )
            csv_lines = csv_text.strip().splitlines()
            combined = "\n".join(center_text(line) for line in csv_lines)
            if stats:
                combined = (
                    f"{combined}\n{format_divider()}\n{center_text(stats)}"
                )
            logger.info(color_text(combined, color="cyan"))
        else:
            table_str = self._render_table(records[: self.limit])
            # Print table directly to avoid logger prefix breaking alignment
            print(table_str)
            if stats:
                print(format_divider())
                # Center each line of the stats separately
                for stat_line in stats.split("\n"):
                    print(center_text(stat_line))
            if len(quotes) > self.limit:
                more_msg = f"... {len(quotes) - self.limit} more rows not shown"
                print(center_text(color_text(more_msg, color="dim")))

    def _render_table(
        self, records: Sequence[dict[str, str | float | int]]
    ) -> str:
        if not records:
            return "No quote data to display"

        headers = ["TIMESTAMP", "OPEN", "HIGH", "LOW", "CLOSE"]
        if self.include_adjclose:
            headers.append("ADJ_CLOSE")
        headers.append("VOLUME")

        column_specs = [
            ColumnSpec(header="TIMESTAMP", align="left", color="blue"),
            ColumnSpec(header="OPEN", align="right"),
            ColumnSpec(header="HIGH", align="right", color="green"),
            ColumnSpec(header="LOW", align="right", color="red"),
            ColumnSpec(header="CLOSE", align="right"),
        ]
        if self.include_adjclose:
            column_specs.append(ColumnSpec(header="ADJ_CLOSE", align="right"))
        column_specs.append(ColumnSpec(header="VOLUME", align="right"))

        rows: list[list[str]] = []
        for record in records:
            row = [
                str(record["timestamp"]),
                f"{record['open']:.2f}",
                f"{record['high']:.2f}",
                f"{record['low']:.2f}",
                f"{record['close']:.2f}",
            ]
            if self.include_adjclose:
                adj = record.get("adj_close")
                row.append(f"{adj:.2f}" if adj is not None else "N/A")
            row.append(f"{record['volume']:,}")
            rows.append(row)

        return format_table(
            rows,
            headers=headers,
            column_specs=column_specs,
            border=True,
            centered=True,
        )

    def _summarize_quotes(self, quotes: Sequence[MarketQuote]) -> str:
        """Build a formatted summary of quote statistics."""
        open_price = quotes[0].open_price
        close_price = quotes[-1].close
        percent_change = ((close_price - open_price) / open_price) * 100
        high = max(quote.high for quote in quotes)
        low = min(quote.low for quote in quotes)
        avg_volume = sum(quote.volume for quote in quotes) / len(quotes)
        highest_close = max(quote.close for quote in quotes)
        change_amount = close_price - open_price
        change_color = (
            "green"
            if change_amount > 0
            else "red"
            if change_amount < 0
            else "dim"
        )

        # Build summary as two-column key-value pairs
        open_str = color_text(f"{open_price:.2f}", color="cyan")
        close_str = color_text(f"{close_price:.2f}", color="cyan")
        change_str = color_text(
            f"{change_amount:+.2f} ({percent_change:+.2f}%)", color=change_color
        )
        high_str = color_text(f"{high:.2f}", color="green")
        low_str = color_text(f"{low:.2f}", color="red")
        best_close_str = color_text(f"{highest_close:.2f}", color="yellow")
        volume_str = color_text(f"{avg_volume:,.0f}", color="blue")

        # Format as aligned key-value lines
        lines = [
            f"{'Open:':>12}  {open_str:<14}  {'High:':>12}  {high_str}",
            f"{'Close:':>12}  {close_str:<14}  {'Low:':>12}  {low_str}",
            f"{'Change:':>12}  {change_str:<14}  {'Best Close:':>12}  {best_close_str}",
            f"{'Avg Volume:':>12}  {volume_str}",
        ]

        return "\n".join(lines)

    def cli_cmd(self) -> None:
        """Execute a market lookup."""
        header = format_section_header("Market Lookup", style="box")
        logger.info(header)

        retriever = create_market_retriever()

        try:
            if self.latest:
                price = retriever.fetch_price(self.symbol)
                result = format_key_value(
                    "Latest close",
                    f"{self.symbol.upper()}: {price:.4f}",
                    label_color="green",
                )
                logger.info(center_text(result))
                return

            date_range = self._determine_range()
            quotes = retriever.retrieve_range(self.symbol, date_range)
            self._print_range(quotes)
        except MarketExtensionError as error:
            logger.error(
                format_status(
                    f"Failed to fetch market data: {error}", status="error"
                )
            )

    def _determine_range(self) -> tuple[date, date]:
        if self._has_range():
            assert self.start_date is not None and self.end_date is not None
            return (self.start_date, self.end_date)
        today = date.today()
        return (today - timedelta(days=7), today)
