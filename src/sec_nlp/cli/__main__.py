# src/sec_nlp/cli/__main__.py
"""Dispatch one terminal research action without loading unused capabilities.

Help and version require neither application settings nor provider imports.
The full-screen workspace is loaded only for an interactive launch; scripts
use the same application actions through the selected command handler.
"""

import logging
import sys

from sec_nlp.cli.arguments import _normalize_cli_args as _normalize_cli_args
from sec_nlp.cli.catalog import COMMANDS, RETIRED_COMMANDS

logger = logging.getLogger(__name__)


def _show_help() -> None:
    """Render the lightweight command catalog with Rich."""
    from rich.console import Console
    from rich.table import Table

    console = Console()
    console.print("[bold]sec-nlp[/bold] · Terminal research workspace")
    console.print("Usage: sec-nlp [COMMAND] [OPTIONS]\n")
    catalog = Table(box=None, show_header=False, padding=(0, 2))
    for name, description in COMMANDS:
        catalog.add_row(name, description)
    console.print(catalog)
    console.print(
        "\nRun without a command to open the workspace in a terminal."
    )
    console.print("Use COMMAND --help for options; --version for the version.")


def main(argv: list[str] | None = None) -> int:
    """Run the selected command and return its process exit status.

    Args:
        argv: Explicit argument list, or process arguments when omitted.

    Returns:
        Zero on success, two for invalid input, or 130 after interruption.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if arguments and arguments[0] in {"--version", "-v", "version"}:
            from rich.console import Console

            from sec_nlp import __version__

            Console().print(f"sec-nlp {__version__}")
            return 0
        if arguments and arguments[0] in {"--help", "-h", "help"}:
            _show_help()
            return 0
        if not arguments:
            if not (sys.stdin.isatty() and sys.stdout.isatty()):
                _show_help()
                return 0
            from sec_nlp.tui.app import launch_workspace

            launch_workspace()
            return 0
        command, *remaining = arguments
        if command in RETIRED_COMMANDS:
            from rich.console import Console

            Console(stderr=True).print(
                f"Use sec-nlp {RETIRED_COMMANDS[command]}. "
                "See docs/MIGRATION.md for the command migration map.",
                markup=False,
            )
            return 2
        if command not in {name for name, _ in COMMANDS}:
            from rich.console import Console

            Console(stderr=True).print(
                f"Unknown command: {command}", markup=False
            )
            _show_help()
            return 2
        from sec_nlp.cli.workspace import run_command

        return run_command(command, remaining)
    except KeyboardInterrupt:
        from rich.console import Console

        Console(stderr=True).print(
            "Interrupted; saved evidence remains available."
        )
        return 130
    except (OSError, ValueError, RuntimeError) as exc:
        from rich.console import Console

        logger.debug("Command failed", exc_info=True)
        Console(stderr=True).print(str(exc), markup=False)
        return 1
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 1


if __name__ == "__main__":
    raise SystemExit(main())
