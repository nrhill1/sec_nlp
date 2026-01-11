"""CLI helpers for the Yahoo-backed market extension."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from sec_nlp.core.infra.logger import (
    bullet_line,
    center_block,
    color_text,
    logger,
    styled_header,
    visible_length,
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
        logger.info(
            center_block(styled_header(f"Quotes: {self.ticker.upper()}"))
        )
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
            combined = "\n".join(csv_lines)
            if stats:
                width = max(visible_length(line) for line in csv_lines)
                combined = (
                    f"{combined}\n"
                    f"{color_text('─' * width, color='dim')}\n"
                    f"{stats}"
                )
            logger.info(color_text(center_block(combined), color="cyan"))
        else:
            table, width = self._render_table(records[: self.limit])
            combined = table
            if stats:
                combined = (
                    f"{combined}\n"
                    f"{color_text('─' * width, color='dim')}\n"
                    f"{stats}"
                )
            if len(quotes) > self.limit:
                combined += (
                    f"\n... {len(quotes) - self.limit} more rows not shown"
                )
            logger.info(color_text(center_block(combined), color="cyan"))

    def _render_table(
        self, records: Sequence[dict[str, Any]]
    ) -> tuple[str, int]:
        if not records:
            return "No quote data to display", 0

        columns = ["timestamp", "open", "high", "low", "close"]
        if self.include_adjclose:
            columns.append("adj_close")
        columns.append("volume")

        table_rows: list[dict[str, str]] = []
        widths = {col: len(col) for col in columns}

        for record in records:
            row: dict[str, str] = {}
            timestamp_value = record["timestamp"]
            timestamp_text = (
                timestamp_value.strftime("%Y-%m-%d %H:%M:%S")
                if hasattr(timestamp_value, "strftime")
                else str(timestamp_value)
            )
            row["timestamp"] = timestamp_text
            row["open"] = f"{record['open']:.2f}"
            row["high"] = f"{record['high']:.2f}"
            row["low"] = f"{record['low']:.2f}"
            row["close"] = f"{record['close']:.2f}"
            if self.include_adjclose:
                adj = record.get("adj_close")
                row["adj_close"] = f"{adj:.2f}" if adj is not None else "N/A"
            row["volume"] = f"{record['volume']:,}"

            for column, value in row.items():
                widths[column] = max(widths[column], len(value))
            table_rows.append(row)

        header = " | ".join(
            column.upper().ljust(widths[column]) for column in columns
        )
        divider = "-+-".join("-" * widths[column] for column in columns)

        lines = [header, divider]
        for row in table_rows:
            cells = []
            for column in columns:
                cell_value = row[column]
                if column == "timestamp":
                    padded = cell_value.ljust(widths[column])
                    cells.append(color_text(padded, color="blue"))
                elif column == "high":
                    padded = cell_value.rjust(widths[column])
                    cells.append(color_text(padded, color="red"))
                elif column == "low":
                    padded = cell_value.rjust(widths[column])
                    cells.append(color_text(padded, color="green"))
                else:
                    cells.append(cell_value.rjust(widths[column]))
            lines.append(" | ".join(cells))

        table_text = "\n".join(lines)
        width = max(visible_length(line) for line in lines)
        return table_text, width

    def _summarize_quotes(self, quotes: Sequence[MarketQuote]) -> str:
        open_price = quotes[0].open_price
        close_price = quotes[-1].close
        percent_change = ((close_price - open_price) / open_price) * 100
        high = max(quote.high for quote in quotes)
        low = min(quote.low for quote in quotes)
        avg_volume = sum(quote.volume for quote in quotes) / len(quotes)
        highest_close = max(quote.close for quote in quotes)
        high_text = color_text(f"high={high:.2f}", color="red")
        low_text = color_text(f"low={low:.2f}", color="green")
        change_amount = close_price - open_price
        change_color = (
            "green"
            if change_amount > 0
            else "red"
            if change_amount < 0
            else "dim"
        )
        change_text = color_text(
            f"change={change_amount:.2f} ({percent_change:.2f}%)",
            color=change_color,
        )
        return (
            f"\nopen={open_price:.2f} close={close_price:.2f} "
            f"{change_text} "
            f"{high_text} {low_text} highest_close={highest_close:.2f} avg_vol={avg_volume:,.0f}"
        )

    def cli_cmd(self) -> None:
        """Execute a market lookup."""
        logger.info(center_block(styled_header("Market lookup")))

        retriever = create_market_retriever()

        try:
            if self.latest:
                price = retriever.fetch_price(self.ticker)
                logger.info(
                    bullet_line(
                        "Latest close",
                        f"{self.ticker.upper()}: {price:.4f}",
                        color="green",
                    )
                )
                return

            date_range = self._determine_range()
            quotes = retriever.retrieve_range(self.ticker, date_range)
            self._print_range(quotes)
        except MarketExtensionError as error:
            logger.error(
                color_text(f"Failed to fetch market data: {error}", color="red")
            )

    def _determine_range(self) -> tuple[date, date]:
        if self._has_range():
            assert self.start_date is not None and self.end_date is not None
            return (self.start_date, self.end_date)
        today = date.today()
        return (today - timedelta(days=7), today)
