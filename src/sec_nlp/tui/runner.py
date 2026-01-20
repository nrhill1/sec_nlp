"""CLI runner utilities for the TUI."""

from __future__ import annotations

import asyncio
import re
import sys
from asyncio.subprocess import Process
from collections.abc import Awaitable, Callable, Sequence

from sec_nlp.types import ConfigScalar

type LineHandler = Callable[[ConfigScalar], Awaitable[None] | None]
type ExitHandler = Callable[[int], Awaitable[None] | None]
type StartHandler = Callable[[Process], Awaitable[None] | None]

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(value: ConfigScalar) -> ConfigScalar:
    if not isinstance(value, str):
        return value
    return _ANSI_RE.sub("", value)


async def _maybe_await(
    handler: LineHandler | ExitHandler, value: ConfigScalar
) -> None:
    result = handler(value)
    if asyncio.iscoroutine(result):
        await result


async def _maybe_await_start(handler: StartHandler, process: Process) -> None:
    result = handler(process)
    if asyncio.iscoroutine(result):
        await result


async def run_cli(
    args: Sequence[ConfigScalar],
    *,
    on_line: LineHandler,
    on_exit: ExitHandler | None = None,
    on_start: StartHandler | None = None,
) -> int:
    command = [sys.executable, "-m", "sec_nlp.cli.__main__"]
    command.extend(str(item) for item in args)

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )

    if on_start is not None:
        await _maybe_await_start(on_start, process)

    if process.stdout is None:
        returncode = await process.wait()
        if on_exit is not None:
            await _maybe_await(on_exit, returncode)
        return returncode

    async for raw in process.stdout:
        line = raw.decode(errors="replace").rstrip()
        cleaned = strip_ansi(line)
        await _maybe_await(on_line, cleaned)

    returncode = await process.wait()
    if on_exit is not None:
        await _maybe_await(on_exit, returncode)
    return returncode
