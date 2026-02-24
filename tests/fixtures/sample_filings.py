# tests/fixtures/sample_filings.py
"""Reusable sample filings and helpers for tests."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

# Small HTML snippets reused across tests
SAMPLE_EXHIBIT_HTML = """
<html>
  <body>
    <h1>Exhibit 10 - Material Contract</h1>
    <p>This agreement is between the company and the supplier.</p>
  </body>
</html>
"""

SAMPLE_ITEM_HTML = """
<html>
  <body>
    <h1>Item 1A. Risk Factors</h1>
    <p>We face intense competition and rapidly changing technology.</p>
  </body>
</html>
"""

SAMPLE_ERROR_HTML = """
<html>
  <head><title>Error</title></head>
  <body><h1>404 Not Found</h1></body>
</html>
"""


def write_sample_filing(
    base: Path,
    ticker: str,
    form: str,
    accession: str,
    content: str,
    filename: str = "primary-document.html",
) -> Path:
    """Write a single filing HTML file to the expected directory layout."""
    filing_dir = base / "sec-edgar-filings" / ticker / form / accession
    filing_dir.mkdir(parents=True, exist_ok=True)
    html_path = filing_dir / filename
    html_path.write_text(content.strip())
    return html_path


def create_sample_filings(
    base: Path,
    ticker: str = "AAPL",
    form: str = "10-K",
    count: int = 3,
    template: str | None = None,
    start_index: int = 0,
) -> list[Path]:
    """Create a sequence of simple filings for a ticker."""
    html_template = template or SAMPLE_ITEM_HTML
    paths: list[Path] = []

    for i in range(start_index, start_index + count):
        accession = f"000000000{i}"
        html_content = html_template.replace("Report", f"Report {i}")
        paths.append(
            write_sample_filing(
                base=base,
                ticker=ticker,
                form=form,
                accession=accession,
                content=html_content,
            )
        )

    return paths


def create_mixed_filings(
    base: Path,
    specs: Iterable[tuple[str, str, str]],
    template: str | None = None,
) -> list[Path]:
    """Create filings for multiple tickers/forms based on (ticker, form, accession)."""
    html_template = template or SAMPLE_EXHIBIT_HTML
    paths: list[Path] = []

    for ticker, form, accession in specs:
        paths.append(
            write_sample_filing(
                base=base,
                ticker=ticker,
                form=form,
                accession=accession,
                content=html_template,
            )
        )

    return paths
