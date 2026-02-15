# src/sec_nlp/cli/__main__.py
"""Main CLI application."""

import os
import signal
import sys
import traceback
from types import FrameType

from pydantic import ValidationError
from pydantic_settings import CliApp


# Install a fast SIGINT handler before importing the rest of the app to avoid noisy tracebacks
def _graceful_sigint(signum: int, frame: FrameType | None) -> None:
    print("\nInterrupted by user (Ctrl+C)")
    sys.exit(130)


signal.signal(signal.SIGINT, _graceful_sigint)

# Import after SIGINT is set so early interrupts are clean
from sec_nlp.cli.commands import Root  # noqa: E402
from sec_nlp.cli.validation import (  # noqa: E402
    format_validation_error,
)
from sec_nlp.core.infra.logger import (  # noqa: E402
    color_text,
    get_timestamped_log_path,
    logger,
    setup_logging,
)

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
    "--filer-ciks",
}

# Commands whose leading positional args are symbol-like identifiers.
# Numeric CIK inputs must stay string-typed, but pydantic-settings may try
# to JSON-decode unquoted numbers for list fields. We wrap numeric tokens
# before handing argv to CliApp so they remain strings (e.g. "0000102909").
_SYMBOL_POSITIONAL_COMMANDS: set[str] = {
    "analyze",
    "warranty",
    "exb",
    "financials",
    "holdings",
    "insider",
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
    "--include-raw-chunks",
    "--include-full-diff",
    "--include-unchanged",
    "--loader-use-async",
    "--llm.require-json",
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

    rewritten: list[str] = []
    for token in normalized:
        if token == "--queries":
            rewritten.append("--search.queries")
        else:
            rewritten.append(token)
    return rewritten


def main() -> int:
    """
    Run the CLI application.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """

    # Install a fast SIGINT handler to exit cleanly without long tracebacks
    def _graceful_sigint(signum: int, frame: FrameType | None) -> None:
        # Use stdout for immediate feedback; logger may not be initialized yet
        print("\nInterrupted by user (Ctrl+C)")
        sys.exit(130)

    signal.signal(signal.SIGINT, _graceful_sigint)

    # Skip logging setup for version command (fast path)
    is_version_cmd = len(sys.argv) > 1 and sys.argv[1] in (
        "version",
        "--version",
        "-v",
    )

    if not is_version_cmd:
        # Configure logging with a timestamped file by default
        log_level = os.getenv("LOG_LEVEL", "INFO")
        log_path = get_timestamped_log_path(prefix="cli")
        setup_logging(level=log_level, log_file=log_path)

    # Normalize argv for friendlier multi-value and bool parsing before handing
    # off to pydantic-settings (helps with --periods 2023 2024, etc.).
    try:
        sys.argv[1:] = _normalize_cli_args(list(sys.argv[1:]))
    except Exception:  # pragma: no cover - normalization is best-effort
        pass

    try:
        CliApp.run(Root)
        return 0

    except KeyboardInterrupt:
        logger.warning("\nInterrupted by user (Ctrl+C)")
        return 130  # SIGINT Code

    except SystemExit as e:
        # Check if it's an argparse error (unrecognized arguments)
        if e.code == 2 and len(sys.argv) > 1:
            # Try to find the problematic argument
            for arg in sys.argv[1:]:
                if (
                    arg.startswith("-")
                    and "=" not in arg
                    and arg not in ("-h", "--help")
                ):
                    # Check if this might be an unknown arg
                    pass  # argparse already printed the error
        if e.code == 0:
            logger.debug("CLI exited normally")
        return e.code if isinstance(e.code, int) else 1

    except ValidationError as e:
        logger.debug("Validation traceback:\n%s", traceback.format_exc())
        print(format_validation_error(e))
        return 2

    except ValueError as e:
        error_msg = str(e)
        logger.error(
            color_text("Configuration Error: ", color="red") + error_msg
        )

        # Provide helpful suggestions for common errors
        if "email" in error_msg.lower():
            logger.info(
                color_text("Tip: ", color="cyan")
                + "Set a valid email with --email your@email.com or in .env file"
            )
        elif "date" in error_msg.lower():
            logger.info(
                color_text("Tip: ", color="cyan")
                + "Use YYYY-MM-DD format for dates (e.g., 2024-01-01)"
            )
        elif "symbol" in error_msg.lower():
            logger.info(
                color_text("Tip: ", color="cyan")
                + "Provide ticker symbols as positional args (e.g., AAPL MSFT)"
            )

        return 2

    except FileNotFoundError as e:
        logger.debug("FileNotFoundError traceback:\n%s", traceback.format_exc())
        logger.error(color_text("File not found: ", color="red") + str(e))
        logger.info(
            color_text("Tip: ", color="cyan")
            + "Check that the path exists and is accessible."
        )
        return 3

    except PermissionError as e:
        logger.debug("PermissionError traceback:\n%s", traceback.format_exc())
        logger.error(color_text("Permission denied: ", color="red") + str(e))
        logger.info(
            color_text("Tip: ", color="cyan")
            + "Check file permissions or try a different output directory."
        )
        return 4

    except ConnectionError as e:
        logger.debug("ConnectionError traceback:\n%s", traceback.format_exc())
        logger.error(color_text("Connection error: ", color="red") + str(e))
        logger.info(
            color_text("Tip: ", color="cyan")
            + "Check your network connection and try again."
        )
        return 5

    except Exception as e:
        logger.error(
            color_text("Unexpected error occurred: ", color="red")
            + f"{type(e).__name__} -- {e}"
        )
        logger.debug("Unexpected traceback:\n%s", traceback.format_exc())
        logger.info(
            color_text("Tip: ", color="cyan")
            + "Check the log file for details or report this issue."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
