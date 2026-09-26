# src/sec_nlp/cli/catalog.py
"""Describe terminal research commands without importing their implementations."""

COMMANDS: tuple[tuple[str, str], ...] = (
    (
        "refresh",
        "Refresh SEC filings, headlines, or market context explicitly.",
    ),
    ("search", "Search SEC filings by keywords, forms, and dates."),
    ("scan", "Save and run repeatable topic scans."),
    ("read", "Read a filing and its documents, including cached evidence."),
    ("research", "Run specialist extraction or optional AI research."),
    ("journal", "Record and review observations and investment theses."),
    ("export", "Export saved evidence as Markdown or JSON."),
    ("workspace", "Initialize, configure, or migrate a research workspace."),
)

RETIRED_COMMANDS: dict[str, str] = {
    "analyze": "research analyze",
    "chat": "research ask",
    "warranty": "research warranty",
    "exb": "research exb",
    "financials": "research financials",
    "holdings": "research holdings",
    "insider": "research insider",
    "events": "research events",
    "retrieve": "research retrieve (or search for metadata discovery)",
    "efts": "search",
    "news": "refresh --source news",
    "market": "refresh --source market",
    "invest": "workspace, journal, refresh, or export",
    "flow": "research recipe",
    "runs": "workspace jobs",
    "qdrant": "research index",
    "clean": "workspace status",
}
