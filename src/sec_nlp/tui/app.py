"""Textual TUI application for SEC NLP pipelines."""

from __future__ import annotations

import asyncio
import re
from asyncio.subprocess import Process

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
)

from sec_nlp.tui.interfaces import FormSpec, build_cli_args, get_form_spec
from sec_nlp.tui.runner import run_cli
from sec_nlp.tui.specs import find_pipeline_spec, get_pipeline_specs
from sec_nlp.tui.widgets import FormView, SegmentPanel
from sec_nlp.types import ConfigScalar


class SegmentMatcher:
    def __init__(self, patterns: tuple[tuple[ConfigScalar, ...], ...]) -> None:
        compiled: list[list[re.Pattern]] = []
        for segment_patterns in patterns:
            segment_regexes: list[re.Pattern] = []
            for raw in segment_patterns:
                if isinstance(raw, str) and raw:
                    segment_regexes.append(re.compile(raw))
            compiled.append(segment_regexes)
        self._patterns = compiled
        self._current_index = -1

    def match(self, line: ConfigScalar) -> int | None:
        if not isinstance(line, str):
            return None
        match_index = self._match_forward(line)
        if match_index is None:
            return None
        if match_index > self._current_index:
            self._current_index = match_index
        return match_index

    def _match_forward(self, line: ConfigScalar) -> int | None:
        if not isinstance(line, str):
            return None
        start_index = self._current_index + 1
        if start_index < 0:
            start_index = 0
        for idx in range(start_index, len(self._patterns)):
            patterns = self._patterns[idx]
            for pattern in patterns:
                if pattern.search(line):
                    return idx
        if 0 <= self._current_index < len(self._patterns):
            for pattern in self._patterns[self._current_index]:
                if pattern.search(line):
                    return self._current_index
        return None
        for pattern in patterns:
            if pattern.search(line):
                return idx
        return None


class SecNlpTuiApp(App):
    CSS = """
    Screen {
        background: #0b0f16;
        color: #e6e2d7;
    }

    Header, Footer {
        background: #0f1624;
        color: #e6e2d7;
    }

    #layout {
        height: 1fr;
    }

    #sidebar {
        width: 30;
        background: #111827;
        border: round #2f3948;
        padding: 1 1;
    }

    #main {
        padding: 1 2;
    }

    .panel {
        background: #151d2a;
        border: round #2b3442;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    .panel-title {
        color: #f3d8a2;
        text-style: bold;
        margin-bottom: 1;
    }

    #pipeline-list {
        height: 1fr;
        margin-top: 1;
        background: #0f1520;
        border: round #2b3442;
    }

    ListView > ListItem {
        padding: 0 1;
    }

    ListView > ListItem.--highlight,
    ListView > ListItem.-highlight,
    ListView > ListItem:focus {
        background: #243044;
        color: #f3d8a2;
    }

    #pipeline-desc {
        color: #aab2c2;
        margin-top: 1;
    }

    #actions {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .field-label {
        width: 22;
        color: #aab2c2;
    }

    Input, Select, Checkbox {
        background: #0c121c;
        border: round #2c3442;
        color: #e6e2d7;
    }

    Checkbox {
        padding: 0 1;
    }

    Button {
        border: round #3a4557;
        background: #1a2230;
        color: #e6e2d7;
        text-style: bold;
        margin-right: 1;
    }

    Button#run {
        background: #1f4b3a;
        border: round #2a5c47;
    }

    Button#stop {
        background: #4a2323;
        border: round #6b2a2a;
    }

    #status {
        margin-left: 1;
        color: #aab2c2;
    }

    ProgressBar {
        background: #0f1520;
        color: #f3d8a2;
    }

    .segment-row {
        height: auto;
        padding: 0 1;
    }

    .segment-label {
        width: 18;
        text-style: bold;
    }

    .segment-detail {
        color: #8b93a1;
        width: 1fr;
    }

    .segment-row.state-running {
        background: #1b2332;
        color: #f3d8a2;
    }

    .segment-row.state-done {
        color: #9fe2c6;
    }

    .segment-row.state-error {
        color: #f4a4a4;
        background: #2b1717;
    }

    #log-panel {
        background: #0b111b;
        border: round #2c3442;
        padding: 1;
        height: 1fr;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "run_pipeline", "Run"),
        ("s", "stop_pipeline", "Stop"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._pipeline_key: ConfigScalar | None = None
        self._segment_matcher: SegmentMatcher | None = None
        self._run_task: asyncio.Task | None = None
        self._active_process: Process | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="layout"):
            with Vertical(id="sidebar"):
                yield Label("Pipelines", classes="panel-title")
                items = [
                    ListItem(Label(str(spec.label)), id=str(spec.key))
                    for spec in get_pipeline_specs()
                ]
                yield ListView(*items, id="pipeline-list")
                yield Static(id="pipeline-desc")
            with Vertical(id="main"):
                yield FormView()
                with Horizontal(id="actions"):
                    yield Button("Run", id="run")
                    yield Button("Stop", id="stop", disabled=True)
                    yield Static("Idle", id="status")
                yield SegmentPanel()
                yield RichLog(id="log-panel", wrap=True, highlight=False)
        yield Footer()

    def on_mount(self) -> None:
        pipeline_list = self.query_one("#pipeline-list", ListView)
        pipeline_list.index = 0
        specs = get_pipeline_specs()
        if specs:
            self._select_pipeline(specs[0].key)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None:
            return
        item_id = event.item.id
        if item_id is None:
            return
        self._select_pipeline(str(item_id))

    def action_run_pipeline(self) -> None:
        self._start_run()

    def action_stop_pipeline(self) -> None:
        self._stop_run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self._start_run()
        elif event.button.id == "stop":
            self._stop_run()

    def _select_pipeline(self, key: ConfigScalar) -> None:
        spec = find_pipeline_spec(str(key))
        if spec is None:
            return
        form_spec = get_form_spec(spec.key)
        if form_spec is None:
            return
        self._pipeline_key = spec.key
        form_view = self.query_one(FormView)
        form_view.set_form(form_spec)
        form_view.call_after_refresh(form_view.focus_first)
        segment_panel = self.query_one(SegmentPanel)
        segment_panel.load_segments(spec.segments)
        desc = self.query_one("#pipeline-desc", Static)
        desc.update(str(spec.description))

    def _start_run(self) -> None:
        if self._run_task is not None and not self._run_task.done():
            return
        if self._pipeline_key is None:
            return
        spec = find_pipeline_spec(str(self._pipeline_key))
        if spec is None:
            return
        form_spec = get_form_spec(spec.key)
        if form_spec is None:
            return

        form_view = self.query_one(FormView)
        values = form_view.get_values()
        if self._requires_symbols(form_spec):
            symbols = self._split_symbols(values.get("symbols"))
            if not symbols:
                log_panel = self.query_one("#log-panel", RichLog)
                log_panel.clear()
                log_panel.write(
                    "Add at least one symbol to run. Interactive setup is not available in the TUI."
                )
                self._set_status("Symbols required")
                form_view.focus_field("symbols")
                return
        extra_args = form_view.get_extra_args()
        extra = extra_args if extra_args is not None else ""
        args = build_cli_args(form_spec, values, extra)
        command_args = [spec.command, *args]

        log_panel = self.query_one("#log-panel", RichLog)
        log_panel.clear()

        segment_panel = self.query_one(SegmentPanel)
        segment_panel.reset()
        if spec.segments:
            segment_panel.advance_to(0)

        pattern_groups = tuple(segment.patterns for segment in spec.segments)
        self._segment_matcher = SegmentMatcher(pattern_groups)

        self._set_status("Running")
        self._set_running(True)

        self._run_task = asyncio.create_task(self._run_cli(command_args))

    def _stop_run(self) -> None:
        if (
            self._active_process is not None
            and self._active_process.returncode is None
        ):
            self._active_process.terminate()
        if self._run_task is not None and not self._run_task.done():
            self._run_task.cancel()
        self._set_status("Stopping")

    async def _run_cli(self, args: list[ConfigScalar]) -> None:
        async def on_start(process: Process) -> None:
            self._active_process = process

        async def on_line(line: ConfigScalar) -> None:
            log_panel = self.query_one("#log-panel", RichLog)
            log_panel.write(str(line))
            matcher = self._segment_matcher
            if matcher is None:
                return
            match_index = matcher.match(line)
            if match_index is None:
                return
            segment_panel = self.query_one(SegmentPanel)
            segment_panel.advance_to(match_index, line)

        async def on_exit(returncode: int) -> None:
            self._active_process = None
            segment_panel = self.query_one(SegmentPanel)
            segment_panel.finish(returncode == 0)
            status = (
                "Completed" if returncode == 0 else f"Failed ({returncode})"
            )
            self._set_status(status)
            self._set_running(False)

        try:
            await run_cli(
                args,
                on_line=on_line,
                on_exit=on_exit,
                on_start=on_start,
            )
        except asyncio.CancelledError:
            self._set_status("Cancelled")
            segment_panel = self.query_one(SegmentPanel)
            segment_panel.finish(False)
            self._set_running(False)
            raise
        except Exception as exc:
            log_panel = self.query_one("#log-panel", RichLog)
            log_panel.write(f"Runner error: {exc}")
            segment_panel = self.query_one(SegmentPanel)
            segment_panel.finish(False)
            self._set_status("Failed")
            self._set_running(False)

    def _set_status(self, message: ConfigScalar) -> None:
        status = self.query_one("#status", Static)
        status.update(str(message))

    def _set_running(self, running: bool) -> None:
        run_button = self.query_one("#run", Button)
        stop_button = self.query_one("#stop", Button)
        run_button.disabled = running
        stop_button.disabled = not running

    def _requires_symbols(self, form_spec: FormSpec) -> bool:
        return any(field.key == "symbols" for field in form_spec.fields)

    def _split_symbols(self, value: ConfigScalar | None) -> list[ConfigScalar]:
        if not isinstance(value, str):
            return []
        cleaned = value.replace(",", " ")
        return [part for part in cleaned.split() if part]


def main() -> None:
    app = SecNlpTuiApp()
    app.run()
