import asyncio

from sec_nlp.tui.runner import run_cli, strip_ansi


class FakeStream:
    def __init__(self, lines) -> None:
        self._lines = list(lines)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._lines:
            raise StopAsyncIteration
        return self._lines.pop(0)


class FakeProcess:
    def __init__(self, lines, returncode) -> None:
        self.stdout = FakeStream(lines)
        self._returncode = returncode
        self.returncode = None

    async def wait(self):
        self.returncode = self._returncode
        return self._returncode


def test_strip_ansi_removes_codes() -> None:
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"


def test_run_cli_invokes_handlers(monkeypatch) -> None:
    process = FakeProcess(
        [b"first\n", b"\x1b[31mred\x1b[0m\n"],
        0,
    )

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(
        asyncio, "create_subprocess_exec", fake_create_subprocess_exec
    )

    seen = []
    exits = []
    starts = []

    async def on_line(line):
        seen.append(line)

    async def on_exit(code):
        exits.append(code)

    async def on_start(proc):
        starts.append(proc)

    result = asyncio.run(
        run_cli(
            ["analyze"],
            on_line=on_line,
            on_exit=on_exit,
            on_start=on_start,
        )
    )

    assert result == 0
    assert seen == ["first", "red"]
    assert exits == [0]
    assert starts == [process]
