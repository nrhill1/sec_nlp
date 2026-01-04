# src/scripts/format_ty_output.py
"""Format ty diagnostics from GitHub annotation output."""

from __future__ import annotations

import os
import re
import sys

from pydantic.dataclasses import dataclass

HEADER_RE = re.compile(r"file=([^,]+),line=(\d+)")


def should_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM") == "dumb":
        return False
    return sys.stdout.isatty()


def colorize(text: str, code: str, use_color: bool) -> str:
    if not use_color:
        return text
    return f"\033[{code}m{text}\033[0m"


@dataclass(frozen=True)
class Diagnostic:
    level: str
    path: str
    line: str
    message: str


def parse_diagnostics(
    lines: list[str],
) -> tuple[list[Diagnostic], list[Diagnostic], list[Diagnostic]]:
    errors: list[Diagnostic] = []
    warnings: list[Diagnostic] = []
    others: list[Diagnostic] = []

    for raw in lines:
        line = raw.rstrip("\n")
        if not line.startswith("::"):
            continue
        parts = line.split("::", 2)
        if len(parts) < 3:
            continue
        header = parts[1].strip()
        message = parts[2].strip()
        if not header:
            continue
        level, _, meta = header.partition(" ")
        match = HEADER_RE.search(meta)
        if not match:
            continue

        path, line_no = match.group(1), match.group(2)
        level_lower = level.lower()
        diag = Diagnostic(
            level=level.upper(), path=path, line=line_no, message=message
        )
        if level_lower == "error":
            errors.append(diag)
        elif level_lower == "warning":
            warnings.append(diag)
        else:
            others.append(diag)

    return errors, warnings, others


def main() -> int:
    use_color = should_color()
    errors, warnings, others = parse_diagnostics(list(sys.stdin))

    def print_group(items: list[Diagnostic], color_code: str) -> None:
        for idx, item in enumerate(items):
            if idx:
                print("")
            print(
                colorize(
                    f"  {item.level} {item.path}:{item.line}",
                    color_code,
                    use_color,
                )
            )
            if item.message:
                print(colorize(f"    {item.message}", color_code, use_color))

    printed_group = False
    if errors:
        printed_group = True
        print(colorize(f"Errors ({len(errors)}):", "31", use_color))
        print_group(errors, "31")

    if warnings or others:
        if printed_group:
            print("")
        if warnings:
            printed_group = True
            print(colorize(f"Warnings ({len(warnings)}):", "33", use_color))
            print_group(warnings, "33")
        if others:
            if warnings:
                print("")
            printed_group = True
            print(colorize(f"Other ({len(others)}):", "36", use_color))
            print_group(others, "36")

    total = len(errors) + len(warnings) + len(others)
    if printed_group:
        print("")
    print("Diagnostics Summary:")
    print(colorize(f"  Errors   : {len(errors)}", "31", use_color))
    print(colorize(f"  Warnings : {len(warnings)}", "33", use_color))
    print(colorize(f"  Other    : {len(others)}", "36", use_color))
    print(f"  Total    : {total}")
    print(
        f"  Status   : {colorize('PASS', '32', use_color) if not total else 'FAIL'}"
    )
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
