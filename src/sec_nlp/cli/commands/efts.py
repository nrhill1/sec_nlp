# src/sec_nlp/cli/commands/efts.py
"""CLI command for SEC EDGAR Full-Text Search (EFTS) queries."""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from typing import Literal

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
from sec_nlp.core.edgar.efts import EFTSAPIError, create_efts_client
from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.infra.logger import color_text, logger


class EFTS(BaseModel):
    """Search SEC EDGAR filings using the Full-Text Search API."""

    model_config = ConfigDict(
        defer_build=True,
        frozen=True,
        extra="forbid",
    )

    query: CliPositionalArg[str] = Field(
        description="Search query string (e.g., 'warranty accrual').",
    )
    forms: list[str] = Field(
        default_factory=list,
        description="Form types to filter (e.g., 10-K, 8-K). Empty = all forms.",
        json_schema_extra={"cli_args": {"nargs": "+", "action": "extend"}},
    )
    tickers: list[str] = Field(
        default_factory=list,
        description="Ticker symbols to filter. Empty = all companies.",
        json_schema_extra={
            "cli_args": {"nargs": "+", "action": "extend", "aliases": ["-t"]}
        },
    )
    start_date: date | None = Field(
        default=None,
        description="Start date for filing date range (inclusive).",
        json_schema_extra={"cli_args": {"aliases": ["--start"]}},
    )
    end_date: date | None = Field(
        default=None,
        description="End date for filing date range (inclusive).",
        json_schema_extra={"cli_args": {"aliases": ["--end"]}},
    )
    years: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Years of filings to search (used when dates not specified).",
        json_schema_extra={"cli_args": {"aliases": ["-y"]}},
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum results to return.",
        json_schema_extra={"cli_args": {"aliases": ["-n"]}},
    )
    email: str = Field(
        default="user@example.com",
        description="Contact email for SEC API (required by SEC).",
        json_schema_extra={"cli_args": {"aliases": ["-e"]}},
    )
    format: Literal["table", "json", "simple"] = Field(
        default="table",
        description="Output format.",
        json_schema_extra={
            "cli_args": {"choices": ["table", "json", "simple"]}
        },
    )
    show_snippets: bool = Field(
        default=True,
        description="Show text snippets from matched filings.",
        json_schema_extra={"cli_args": {"aliases": ["--snippets"]}},
    )

    def _get_date_range(self) -> tuple[date | None, date | None]:
        """Calculate date range for search."""
        if self.start_date and self.end_date:
            return self.start_date, self.end_date

        # Default to last N years
        end = date.today()
        start = end - timedelta(days=365 * self.years)
        return start, end

    def _render_table(self, hits: list[EFTSHit]) -> str:
        """Render hits as a formatted table."""
        if not hits:
            return "No results found"

        headers = ["FILED", "FORM", "COMPANY", "SCORE"]
        column_specs = [
            ColumnSpec(header="FILED", align="left", color="blue"),
            ColumnSpec(header="FORM", align="center"),
            ColumnSpec(header="COMPANY", align="left"),
            ColumnSpec(header="SCORE", align="right", color="green"),
        ]

        rows: list[list[str]] = []
        for hit in hits:
            company = (
                hit.company_name[:40] + "..."
                if len(hit.company_name) > 40
                else hit.company_name
            )
            rows.append(
                [
                    hit.filed_date.isoformat(),
                    hit.form_type,
                    company,
                    f"{hit.score:.2f}",
                ]
            )

        return format_table(
            rows,
            headers=headers,
            column_specs=column_specs,
            border=True,
            centered=True,
        )

    def _print_simple(self, hits: list[EFTSHit]) -> None:
        """Print results in simple text format."""
        for i, hit in enumerate(hits, 1):
            logger.info(
                color_text(f"\n[{i}] ", color="yellow")
                + color_text(hit.company_name, color="cyan")
            )
            logger.info(
                f"    Form: {hit.form_type}  |  Filed: {hit.filed_date}  |  Score: {hit.score:.2f}"
            )
            logger.info(f"    Accession: {hit.accession_number}")
            if self.show_snippets and hit.snippet:
                snippet = (
                    hit.snippet[:200] + "..."
                    if len(hit.snippet) > 200
                    else hit.snippet
                )
                logger.info(f"    {color_text(snippet, color='dim')}")

    def _print_json(self, hits: list[EFTSHit]) -> None:
        """Print results as JSON."""
        data = [
            {
                "company_name": hit.company_name,
                "form_type": hit.form_type,
                "filed_date": hit.filed_date.isoformat(),
                "accession_number": hit.accession_number,
                "cik": hit.cik,
                "score": hit.score,
                "edgar_url": hit.edgar_url,
                "snippet": hit.snippet if self.show_snippets else None,
            }
            for hit in hits
        ]
        logger.info(color_text(json.dumps(data, indent=2), color="cyan"))

    async def _run_search(self) -> list[EFTSHit]:
        """Execute the EFTS search."""
        client = create_efts_client(
            email=self.email,
            company_name="SEC NLP Tool",
        )

        start_date, end_date = self._get_date_range()

        response = await client.search(
            self.query,
            forms=self.forms if self.forms else None,
            tickers=self.tickers if self.tickers else None,
            start_date=start_date,
            end_date=end_date,
            limit=self.limit,
        )

        return response.hits

    def cli_cmd(self) -> None:
        """Execute an EFTS search."""
        header = format_section_header(
            "SEC EDGAR Full-Text Search", style="box"
        )
        logger.info(header)

        # Show search parameters
        start_date, end_date = self._get_date_range()
        params_info = [
            format_key_value("Query", self.query, label_color="green"),
        ]
        if self.forms:
            params_info.append(
                format_key_value(
                    "Forms", ", ".join(self.forms), label_color="blue"
                )
            )
        if self.tickers:
            params_info.append(
                format_key_value(
                    "Tickers", ", ".join(self.tickers), label_color="blue"
                )
            )
        params_info.append(
            format_key_value(
                "Date Range",
                f"{start_date} to {end_date}",
                label_color="blue",
            )
        )

        for info in params_info:
            logger.info(center_text(info))

        logger.info(format_divider())

        # Run the async search
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            hits = loop.run_until_complete(self._run_search())
        except EFTSAPIError as e:
            logger.error(
                format_status(
                    f"EFTS search failed: {e.message}", status="error"
                )
            )
            return
        except Exception as e:
            logger.error(format_status(f"Search failed: {e}", status="error"))
            return
        finally:
            asyncio.set_event_loop(None)
            if not loop.is_closed():
                loop.close()

        if not hits:
            logger.info(
                format_status(
                    "No filings matched your search", status="warning"
                )
            )
            return

        # Show results count
        logger.info(
            center_text(
                format_key_value(
                    "Results", f"{len(hits)} filings found", label_color="green"
                )
            )
        )
        logger.info("")

        # Render output based on format
        if self.format == "json":
            self._print_json(hits)
        elif self.format == "simple":
            self._print_simple(hits)
        else:
            table_str = self._render_table(hits)
            print(table_str)
            if self.show_snippets:
                logger.info("")
                logger.info(
                    center_text(
                        color_text(
                            "Use --format simple to see text snippets",
                            color="dim",
                        )
                    )
                )
