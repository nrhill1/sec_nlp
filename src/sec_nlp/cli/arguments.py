# src/sec_nlp/cli/arguments.py
"""Normalize legacy specialist option values before selected-command parsing.

This module contains no command imports, so argument normalization does not
load research dependencies or initialize runtime services.
"""

# Common field suggestions for typo correction
FIELD_SUGGESTIONS: list[tuple[str, list[str]]] = [
    ("symbol", ["symbols"]),
    ("topic", ["topics"]),
    ("keyword", ["keywords"]),
    ("model", ["llm.model-name"]),
    ("temperature", ["llm.temperature"]),
    ("format", ["export-format"]),
    ("output", ["out-path", "export-format"]),
    ("input", ["dl-path"]),
    ("section", ["section-numbers", "section-type"]),
    ("batch", ["batch-size"]),
    ("chunk", ["top-k-chunks", "max-chunk-length", "min-chunk-length"]),
]

# Flags that routinely accept multiple values but the underlying parser only
# consumes one per occurrence. We normalize argv so users can pass multiple
# values after a single flag (e.g., --periods 2023 2024) without hitting
# argparse "unrecognized arguments" errors.
_MULTI_VALUE_FLAGS: set[str] = {
    "--periods",
    "--collections",
    "--sections",
    "--section-numbers",
    "--topics",
    "--keywords",
    "--skip-categories",
    "--analysis-fields",
    "--search-terms",
    "--search.queries",
    "--queries",
    "--material-keywords",
    "--exhibit-numbers",
    "--forms",
    "--feeds",
    "--filer-ciks",
}

# Commands whose leading positional args are symbol-like identifiers.
# Numeric CIK inputs must stay string-typed, but pydantic-settings may try
# to JSON-decode unquoted numbers for list fields. We wrap numeric tokens
# before handing argv to CliApp so they remain strings (e.g. "0000102909").
_SYMBOL_POSITIONAL_COMMANDS: set[str] = {
    "analyze",
    "chat",
    "warranty",
    "exb",
    "financials",
    "holdings",
    "insider",
    "news",
    "events",
    "retrieve",
}

_FALSEY: set[str] = {"false", "0", "no", "off", "n"}
_BOOLEAN_FLAGS: set[str] = {
    "--aggregate-by-filing",
    "--cleanup",
    "--collect-metrics",
    "--deduplicate-chunks",
    "--detect-material-changes",
    "--dry-run",
    "--enable-tracing",
    "--filter-indices",
    "--fresh",
    "--include-history",
    "--include-market-context",
    "--include-news-context",
    "--include-raw-chunks",
    "--include-full-diff",
    "--include-unchanged",
    "--incremental",
    "--interactive",
    "--loader-use-async",
    "--llm.require-json",
    "--prefetch-retrieve",
    "--prioritize-topics",
    "--vdb.qdrant-on-disk-payload",
    "--vdb.qdrant-prefer-grpc",
    "--vdb.qdrant-https",
    "--search.export-results",
    "--search.analyze",
    "--skip-empty-sections",
    "--trace-log-prompts",
    "--use-llm-summary",
    "--use-section-filter",
    "--vector-store-relevant",
    "--verbose",
    "--force",
    "--strict-citations",
    "--transcript-autosave",
}


def _normalize_cli_args(argv: list[str]) -> list[str]:
    """Expand space-separated list args and coerce bool false values."""
    if argv and argv[0] in _SYMBOL_POSITIONAL_COMMANDS:
        rewritten_symbols: list[str] = [argv[0]]
        i = 1
        while i < len(argv) and not argv[i].startswith("-"):
            token = argv[i]
            if token.isdigit():
                rewritten_symbols.append(f'"{token}"')
            else:
                rewritten_symbols.append(token)
            i += 1
        rewritten_symbols.extend(argv[i:])
        argv = rewritten_symbols

    normalized: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]

        # Treat string booleans as optional flags (e.g., --verbose false)
        if arg in _BOOLEAN_FLAGS:
            if i + 1 < len(argv) and argv[i + 1].lower() in _FALSEY:
                normalized.append(f"--no-{arg.lstrip('-')}")
                i += 2
                continue
            if "=" in arg:
                flag, value = arg.split("=", 1)
                if flag in _BOOLEAN_FLAGS and value.lower() in _FALSEY:
                    normalized.append(f"--no-{flag.lstrip('-')}")
                    i += 1
                    continue

        # Expand list-like flags into repeated flags
        if arg in _MULTI_VALUE_FLAGS:
            values: list[str] = []
            i += 1
            while i < len(argv) and not argv[i].startswith("-"):
                values.append(argv[i])
                i += 1
            if not values:
                normalized.append(arg)
            else:
                for v in values:
                    normalized.extend([arg, v])
            continue

        normalized.append(arg)
        i += 1

    command_name = normalized[0] if normalized else ""
    rewrite_queries = command_name in {"analyze", "exb"}

    rewritten: list[str] = []
    for token in normalized:
        if rewrite_queries and token == "--queries":
            rewritten.append("--search.queries")
        else:
            rewritten.append(token)
    return rewritten
