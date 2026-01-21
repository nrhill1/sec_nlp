from asyncio.subprocess import Process
from collections.abc import Awaitable, Callable, Sequence

from sec_nlp.types import ConfigScalar

type Handler[T] = Callable[[T], Awaitable[None] | None]
type LineHandler = Handler[ConfigScalar]
type ExitHandler = Handler[int]
type StartHandler = Handler[Process]

def strip_ansi(value: ConfigScalar) -> ConfigScalar: ...
async def run_cli(
    args: Sequence[ConfigScalar],
    *,
    on_line: LineHandler,
    on_exit: ExitHandler | None = None,
    on_start: StartHandler | None = None,
) -> int: ...
