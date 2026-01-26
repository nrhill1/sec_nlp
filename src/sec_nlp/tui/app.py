"""Textual TUI application for SEC NLP pipelines."""

from __future__ import annotations

import asyncio
import re
import time
from asyncio.subprocess import Process
from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.timer import Timer
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from sec_nlp.tui.interfaces import FormSpec, build_cli_args, get_form_spec
from sec_nlp.tui.market import load_market_snapshot
from sec_nlp.tui.runner import run_cli
from sec_nlp.tui.specs import find_pipeline_spec, get_pipeline_specs
from sec_nlp.tui.widgets import (
    FormView,
    MarketPanel,
    ResultsPanel,
    SectionModeChanged,
    SegmentPanel,
)
from sec_nlp.types import ConfigScalar

_OUTPUT_PATH_RE = re.compile(r"(?P<path>[^\s]+\.(?:json|ya?ml))")
_PROGRESS_RE = re.compile(r"\[[^]]*<[^]]*\]")


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


class SecNlpTuiApp(App):
    CSS = """
    Screen {
        background: #000000;
        color: #f5f5f5;
    }

    Header, Footer {
        background: #000000;
        color: #f5f5f5;
    }

    #layout {
        height: 1fr;
    }

    #sidebar {
        width: 30;
        background: #0b0b0b;
        border: round #2b2b2b;
        padding: 1 1;
    }

    #main {
        padding: 1 2;
        height: 1fr;
        background: #000000;
        color: #f5f5f5;
    }

    .panel {
        background: #141414;
        border: round #2b2b2b;
        padding: 1 2;
        margin: 0 0 1 0;
        color: #f5f5f5;
    }

    .panel-title {
        color: #f5f5f5;
        text-style: bold;
        margin-bottom: 1;
    }

    #pipeline-list {
        height: 1fr;
        margin-top: 1;
        background: #111111;
        border: round #2b2b2b;
    }

    ListView > ListItem {
        padding: 0 1;
    }

    ListView > ListItem.--highlight,
    ListView > ListItem.-highlight,
    ListView > ListItem:focus {
        background: #1a1a1a;
        color: #5eead4;
    }

    #pipeline-desc {
        color: #c7c7c7;
        margin-top: 1;
    }

    #actions {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }

    #status-row {
        height: 1fr;
        margin-bottom: 1;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .section-switcher {
        margin-bottom: 1;
    }

    .field-label {
        width: 18;
        color: #c7c7c7;
    }

    Input, Select, Checkbox {
        background: #0f0f0f;
        border: round #2b2b2b;
        color: #f5f5f5;
    }

    Button, Input, Select, Checkbox, Tab, .section-header, ListView > ListItem {
        transition: background 0.2 linear 0, color 0.2 linear 0, border 0.2 linear 0;
    }

    .segment-row, #status, .segment-status {
        transition: background 0.2 linear 0, color 0.2 linear 0, border 0.2 linear 0;
    }

    Input:focus, Select:focus, Checkbox:focus {
        border: round #5eead4;
        color: #f5f5f5;
    }

    Checkbox {
        padding: 0 1;
    }

    .collapsible-section {
        margin-bottom: 1;
    }

    .section-header {
        background: #1a1a1a;
        color: #f5f5f5;
        padding: 0 1;
        text-style: bold;
    }

    .section-header:hover {
        background: #1a1a1a;
    }

    Button.section-header {
        border: round #2b2b2b;
        content-align: left middle;
        width: 1fr;
    }

    Button.section-header:focus {
        border: round #5eead4;
    }

    .section-content {
        padding-left: 1;
        margin-top: 0;
    }

    .section-hidden {
        display: none;
    }

    .section-active .section-header {
        background: #0f3d3a;
        border: round #1f6f69;
        color: #d8f4f1;
    }

    Button {
        border: round #2b2b2b;
        background: #1a1a1a;
        color: #f5f5f5;
        text-style: bold;
        margin-right: 1;
    }

    Button:focus {
        border: round #5eead4;
    }

    Button#run {
        background: #0f3d3a;
        border: round #1f6f69;
        color: #d8f4f1;
    }

    Button#stop {
        background: #3a1212;
        border: round #6b2b2b;
        color: #f2d7d7;
    }

    #status {
        margin-left: 1;
        color: #c7c7c7;
        background: #0f0f0f;
        padding: 0 1;
        border: round #2b2b2b;
    }

    #elapsed {
        margin-left: 1;
        color: #c7c7c7;
        background: #0f0f0f;
        padding: 0 1;
        border: round #2b2b2b;
    }

    ProgressBar {
        background: #0f0f0f;
        color: #5eead4;
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
        color: #b0b0b0;
        width: 1fr;
    }

    .segment-row.state-running {
        background: #1a1a1a;
        color: #5eead4;
    }

    .segment-row.state-done {
        color: #86efac;
    }

    .segment-row.state-error {
        color: #fca5a5;
        background: #2a0f0f;
    }

    .segment-panel {
        width: 1fr;
        height: 1fr;
    }

    .segment-list {
        height: 1fr;
    }

    .segment-status {
        margin-top: 1;
        padding: 0 1;
        color: #f5f5f5;
        background: #141414;
        border: round #2b2b2b;
    }

    .market-panel {
        width: 46;
        min-width: 34;
        background: #141414;
        border: round #2b2b2b;
    }

    .market-controls {
        height: auto;
        margin-bottom: 1;
    }

    .market-label {
        width: 7;
        color: #c7c7c7;
    }

    #market-summary {
        color: #f5f5f5;
        margin-bottom: 1;
    }

    #market-chart {
        background: #0b0b0b;
        border: round #2b2b2b;
        color: #5eead4;
        padding: 1 1;
        height: 7;
    }

    #market-detail {
        color: #c7c7c7;
        margin-top: 1;
    }

    #market-context {
        color: #b0b0b0;
        margin-top: 1;
    }

    #market-stats {
        color: #f5f5f5;
        background: #0f0f0f;
        border: round #2b2b2b;
        padding: 0 1;
        margin-top: 1;
    }

    .results-panel {
        width: 1fr;
    }

    .results-row {
        height: auto;
        margin-top: 1;
    }

    #results-list {
        width: 36;
        background: #0f0f0f;
        border: round #2b2b2b;
        height: 12;
        margin-right: 1;
    }

    #results-view {
        height: 12;
        background: #0b0b0b;
        border: round #2b2b2b;
        color: #f5f5f5;
        padding: 1;
    }

    #log-panel {
        background: #0b0b0b;
        border: round #2b2b2b;
        padding: 1;
        height: 1fr;
        min-height: 8;
    }

    #results-filter {
        margin-bottom: 1;
    }

    TabbedContent {
        background: #000000;
        height: 1fr;
    }

    TabPane {
        padding: 1 2;
        height: 1fr;
    }

    TabBar {
        background: #0b0b0b;
        border: round #2b2b2b;
    }

    Tab {
        background: #121212;
        color: #c7c7c7;
        text-style: bold;
    }

    Tab.-active,
    Tab.--active {
        background: #1a1a1a;
        color: #5eead4;
    }

    .market-full {
        height: 1fr;
    }

    .results-full {
        height: 1fr;
    }

    #results-view-full {
        height: 1fr;
        background: #0b0b0b;
        border: round #2b2b2b;
        color: #f5f5f5;
        padding: 1;
    }

    #run {
        height: 1fr;
        layout: vertical;
        overflow: hidden;
    }

    #run-bottom {
        height: 1fr;
    }

    #run.section-mode #run-bottom {
        display: none;
    }

    #market {
        height: 1fr;
    }

    #results {
        height: 1fr;
    }

    #config-panel {
        height: 2fr;
        min-height: 18;
    }

    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "run_pipeline", "Run"),
        ("s", "stop_pipeline", "Stop"),
        ("1", "switch_tab('run')", "Run tab"),
        ("2", "switch_tab('market')", "Market tab"),
        ("3", "switch_tab('results')", "Results tab"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._pipeline_key: ConfigScalar | None = None
        self._segment_matcher: SegmentMatcher | None = None
        self._run_task: asyncio.Task | None = None
        self._active_process: Process | None = None
        self._output_paths: list[Path] = []
        self._run_start: float | None = None
        self._elapsed_timer: Timer | None = None

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
                with TabbedContent(initial="run"):
                    with TabPane("Run", id="run"):
                        form_view = FormView()
                        form_view.id = "config-panel"
                        yield form_view
                        with Vertical(id="run-bottom"):
                            with Horizontal(id="actions"):
                                yield Button("Run", id="run-btn")
                                yield Button(
                                    "Stop", id="stop-btn", disabled=True
                                )
                                yield Static("Idle", id="status")
                                yield Static("Elapsed 00:00", id="elapsed")
                            with Horizontal(id="status-row"):
                                yield SegmentPanel()
                            yield RichLog(
                                id="log-panel", wrap=True, highlight=False
                            )
                    with TabPane("Market", id="market"):
                        yield MarketPanel(classes="market-full")
                    with TabPane("Results", id="results"):
                        yield ResultsPanel(classes="results-full")
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
        # Only handle selections that correspond to pipeline keys
        valid_keys = {str(spec.key) for spec in get_pipeline_specs()}
        if str(item_id) not in valid_keys:
            return
        self._select_pipeline(str(item_id))

    def action_run_pipeline(self) -> None:
        self._start_run()

    def action_stop_pipeline(self) -> None:
        self._stop_run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self._start_run()
        elif event.button.id == "stop-btn":
            self._stop_run()

    def on_section_mode_changed(self, event: SectionModeChanged) -> None:
        run_pane = self.query_one("#run", TabPane)
        if event.active:
            run_pane.add_class("section-mode")
        else:
            run_pane.remove_class("section-mode")

    def action_switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one(TabbedContent)
        tabs.active = tab_id

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
        market_panel = self.query_one(MarketPanel)
        if spec.key == "analyze":
            market_panel.set_message(
                "Run analyze with market enabled to populate this view."
            )
        else:
            market_panel.set_message(
                "Market data is available in the analyze pipeline."
            )
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
        self._output_paths = []

        segment_panel = self.query_one(SegmentPanel)
        segment_panel.reset()
        if spec.segments:
            segment_panel.advance_to(0)
        market_panel = self.query_one(MarketPanel)
        market_panel.reset()

        pattern_groups = tuple(segment.patterns for segment in spec.segments)
        self._segment_matcher = SegmentMatcher(pattern_groups)

        self._set_status("Running")
        self._set_running(True)
        self._start_elapsed()

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
        self._stop_elapsed(final=True)

    async def _run_cli(self, args: list[ConfigScalar]) -> None:
        async def on_start(process: Process) -> None:
            self._active_process = process

        async def on_line(line: ConfigScalar) -> None:
            log_panel = self.query_one("#log-panel", RichLog)
            display_line = self._sanitize_log_line(
                self._sanitize_progress_line(line)
            )
            log_panel.write(str(display_line))
            self._capture_output_path(line)
            matcher = self._segment_matcher
            if matcher is None:
                return
            match_index = matcher.match(line)
            if match_index is None:
                return
            segment_panel = self.query_one(SegmentPanel)
            detail = self._sanitize_log_line(
                self._sanitize_segment_detail(line)
            )
            segment_panel.advance_to(match_index, detail)

        async def on_exit(returncode: int) -> None:
            self._active_process = None
            segment_panel = self.query_one(SegmentPanel)
            segment_panel.finish(returncode == 0)
            self._refresh_market_panel()
            self._refresh_results_panel()
            status = (
                "Completed" if returncode == 0 else f"Failed ({returncode})"
            )
            self._set_status(status)
            self._set_running(False)
            self._stop_elapsed(final=True)

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
            self._stop_elapsed(final=True)
            raise
        except Exception as exc:
            log_panel = self.query_one("#log-panel", RichLog)
            log_panel.write(f"Runner error: {exc}")
            segment_panel = self.query_one(SegmentPanel)
            segment_panel.finish(False)
            self._set_status("Failed")
            self._set_running(False)
            self._stop_elapsed(final=True)

    def _set_status(self, message: ConfigScalar) -> None:
        status = self.query_one("#status", Static)
        status.update(str(message))

    def _set_running(self, running: bool) -> None:
        run_button = self.query_one("#run-btn", Button)
        stop_button = self.query_one("#stop-btn", Button)
        run_button.disabled = running
        stop_button.disabled = not running

    def _start_elapsed(self) -> None:
        self._run_start = time.monotonic()
        self._set_elapsed(0.0)
        if self._elapsed_timer is None:
            self._elapsed_timer = self.set_interval(1.0, self._tick_elapsed)

    def _stop_elapsed(self, *, final: bool) -> None:
        if final and self._run_start is not None:
            elapsed = time.monotonic() - self._run_start
            self._set_elapsed(elapsed)
        self._run_start = None
        if self._elapsed_timer is not None:
            self._elapsed_timer.stop()
            self._elapsed_timer = None

    def _tick_elapsed(self) -> None:
        if self._run_start is None:
            return
        elapsed = time.monotonic() - self._run_start
        self._set_elapsed(elapsed)

    def _set_elapsed(self, seconds: float) -> None:
        elapsed = self._format_elapsed(seconds)
        label = self.query_one("#elapsed", Static)
        label.update(f"Elapsed {elapsed}")

    def _format_elapsed(self, seconds: float) -> str:
        total = int(seconds)
        mins, secs = divmod(total, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours:d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    def _requires_symbols(self, form_spec: FormSpec) -> bool:
        return any(field.key == "symbols" for field in form_spec.fields)

    def _split_symbols(self, value: ConfigScalar | None) -> list[ConfigScalar]:
        if not isinstance(value, str):
            return []
        cleaned = value.replace(",", " ")
        return [part for part in cleaned.split() if part]

    def _capture_output_path(self, line: ConfigScalar) -> None:
        if not isinstance(line, str):
            return
        for match in _OUTPUT_PATH_RE.finditer(line):
            path_text = match.group("path").rstrip(".,)")
            if not path_text:
                continue
            path = Path(path_text)
            if not path.is_absolute():
                path = Path.cwd() / path
            if path not in self._output_paths:
                self._output_paths.append(path)

    def _refresh_market_panel(self) -> None:
        market_panel = self.query_one(MarketPanel)
        snapshot = load_market_snapshot(self._output_paths)
        market_panel.set_snapshot(snapshot)

    def _refresh_results_panel(self) -> None:
        results_panel = self.query_one(ResultsPanel)
        yaml_paths = [
            path
            for path in self._output_paths
            if path.suffix.lower() in (".yaml", ".yml")
        ]
        results_panel.set_paths(yaml_paths)

    def _sanitize_segment_detail(
        self, detail: ConfigScalar
    ) -> ConfigScalar | None:
        if not isinstance(detail, str):
            return detail
        elapsed = self._elapsed_since_start()
        if elapsed is None:
            return detail
        return _PROGRESS_RE.sub(f"[elapsed {elapsed}]", detail)

    def _sanitize_progress_line(
        self, detail: ConfigScalar
    ) -> ConfigScalar | None:
        if not isinstance(detail, str):
            return detail
        elapsed = self._elapsed_since_start()
        if elapsed is None:
            return detail
        return _PROGRESS_RE.sub(f"[elapsed {elapsed}]", detail)

    def _sanitize_log_line(
        self, detail: ConfigScalar | None
    ) -> ConfigScalar | None:
        if not isinstance(detail, str):
            return detail
        return detail.encode("ascii", "ignore").decode()

    def _elapsed_since_start(self) -> ConfigScalar | None:
        if self._run_start is None:
            return None
        return self._format_elapsed(time.monotonic() - self._run_start)


def main() -> None:
    app = SecNlpTuiApp()
    app.run()
