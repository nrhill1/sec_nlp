# src/sec_nlp/cli/__main__.py
"""Main CLI application."""

import os
import re
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
    "--material-keywords",
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
    "--search.enabled",
    "--skip-empty-sections",
    "--trace-log-prompts",
    "--use-llm-summary",
    "--use-section-filter",
    "--validate-config",
    "--vector-store-relevant",
    "--verbose",
    "--force",
}


def _normalize_cli_args(argv: list[str]) -> list[str]:
    """Expand space-separated list args and coerce bool false values."""
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

    return normalized


def format_validation_error(error: ValidationError) -> str:
    """Format a pydantic validation error with helpful suggestions.

    Args:
        error: The validation error

    Returns:
        Formatted error message with suggestions
    """
    lines = ["\n" + color_text("Configuration Error", color="red")]
    lines.append(color_text("=" * 50, color="red"))

    for err in error.errors():
        loc = ".".join(str(x) for x in err["loc"])
        msg = err["msg"]
        err_type = err["type"]

        lines.append(f"\n  {color_text('Field:', color='yellow')} {loc}")
        lines.append(f"  {color_text('Error:', color='red')} {msg}")

        # Add type-specific suggestions
        if err_type == "missing":
            lines.append(
                f"  {color_text('Fix:', color='green')} This field is required. Add --{loc.replace('.', '-')} <value>"
            )
        elif err_type == "string_type":
            lines.append(
                f"  {color_text('Fix:', color='green')} Expected a string value. Try quoting the value."
            )
        elif err_type == "int_parsing":
            lines.append(
                f"  {color_text('Fix:', color='green')} Expected an integer (e.g., 5, 10, 100)"
            )
        elif err_type == "float_parsing":
            lines.append(
                f"  {color_text('Fix:', color='green')} Expected a number (e.g., 0.5, 1.0)"
            )
        elif "enum" in err_type or "literal" in err_type:
            # Extract allowed values from message
            match = re.search(r"'([^']+)'(?:,\s*'([^']+)')*", msg)
            if match:
                lines.append(
                    f"  {color_text('Fix:', color='green')} Use one of the allowed values shown above."
                )

    lines.append("\n" + color_text("=" * 50, color="red"))
    lines.append(
        color_text("Tip:", color="cyan")
        + " Run 'sec-nlp <command> --help' for available options."
    )

    return "\n".join(lines)


def format_unknown_arg_error(arg: str) -> str:
    """Format an unknown argument error with suggestions.

    Args:
        arg: The unknown argument

    Returns:
        Formatted error message with suggestions
    """
    lines = ["\n" + color_text(f"Unknown argument: {arg}", color="red")]

    # Look for similar field names
    arg_lower = arg.lower().lstrip("-")
    suggestions = []

    for key, values in FIELD_SUGGESTIONS:
        if key in arg_lower or arg_lower in key:
            suggestions.extend(values)

    if suggestions:
        lines.append(f"\n{color_text('Did you mean:', color='yellow')}")
        for suggestion in suggestions[:3]:
            lines.append(f"  --{suggestion}")

    lines.append(
        f"\n{color_text('Tip:', color='cyan')} Run 'sec-nlp <command> --help' for available options."
    )

    return "\n".join(lines)


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
