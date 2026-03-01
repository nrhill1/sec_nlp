# src/scripts/build/check_imports.py
"""Check core Python and optional Rust extension imports."""

import argparse
import importlib
import sys
from collections.abc import Sequence

from rich.console import Console

PYTHON_MODULES: tuple[str, ...] = (
    "sec_nlp",
    "sec_nlp.core",
    "sec_nlp.pipelines",
    "sec_nlp.cli",
)
RUST_MODULES: tuple[str, ...] = (
    "market",
    "efts",
    "corr",
    "xbrl",
    "entity",
    "newswatch",
)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    """Parse script command-line arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verbose", action="store_true", help="Show every successful import"
    )
    parser.add_argument(
        "--no-check-rust",
        action="store_true",
        help="Skip import checks for Rust extension modules",
    )
    return parser.parse_args(argv)


def _check_modules(
    modules: Sequence[str],
    *,
    console: Console,
    verbose: bool,
    failures: list[str],
) -> None:
    """Try importing each module and record failures."""
    for module_name in modules:
        try:
            importlib.import_module(module_name)
        except Exception as error:
            failures.append(module_name)
            console.print(f"[red]✗[/red] {module_name}: {error}")
        else:
            if verbose:
                console.print(f"[green]✓[/green] {module_name}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run import checks and return a shell-compatible exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    console = Console()
    failures: list[str] = []

    _check_modules(
        PYTHON_MODULES,
        console=console,
        verbose=args.verbose,
        failures=failures,
    )

    if not args.no_check_rust:
        _check_modules(
            RUST_MODULES,
            console=console,
            verbose=args.verbose,
            failures=failures,
        )

    if failures:
        console.print(f"[red]Import checks failed:[/red] {', '.join(failures)}")
        return 1
    console.print("[green]All import checks passed[/green]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
