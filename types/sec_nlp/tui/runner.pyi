from asyncio.subprocess import Process
from collections.abc import Awaitable, Callable, Sequence

from sec_nlp.types import ConfigScalar

type LineHandler = Callable[[ConfigScalar], Awaitable[None] | None]
type ExitHandler = Callable[[int], Awaitable[None] | None]
type StartHandler = Callable[[Process], Awaitable[None] | None]

def strip_ansi(value: ConfigScalar) -> ConfigScalar: ...
async def run_cli(
    args: Sequence[ConfigScalar],
    *,
    on_line: LineHandler,
    on_exit: ExitHandler | None = None,
    on_start: StartHandler | None = None,
) -> int: ...
