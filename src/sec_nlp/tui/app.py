"""Textual TUI application for SEC NLP pipelines."""

from __future__ import annotations

import asyncio
import re
from asyncio.subprocess import Process
from pathlib import Path

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
        background: #0a0f14;
        color: #e8e3d9;
    }

    Header, Footer {
        background: #101725;
        color: #e8e3d9;
    }

    #layout {
        height: 1fr;
    }

    #sidebar {
        width: 30;
        background: #0f1724;
        border: round #334155;
        padding: 1 1;
    }

    #main {
        padding: 1 2;
        height: 1fr;
    }

    .panel {
        background: #141c28;
        border: round #2f3c50;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    .panel-title {
        color: #f3c57b;
        text-style: bold;
        margin-bottom: 1;
    }

    #pipeline-list {
        height: 1fr;
        margin-top: 1;
        background: #0f1522;
        border: round #2f3c50;
    }

    ListView > ListItem {
        padding: 0 1;
    }

    ListView > ListItem.--highlight,
    ListView > ListItem.-highlight,
    ListView > ListItem:focus {
        background: #1f2a3a;
        color: #f3c57b;
    }

    #pipeline-desc {
        color: #9aa6b2;
        margin-top: 1;
    }

    #actions {
        height: auto;
        margin-top: 1;
        margin-bottom: 1;
    }

    #status-row {
        height: auto;
        margin-bottom: 1;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .field-label {
        width: 18;
        color: #9aa6b2;
    }

    Input, Select, Checkbox {
        background: #0c131f;
        border: round #334155;
        color: #e8e3d9;
    }

    Input:focus, Select:focus, Checkbox:focus {
        border: round #f3c57b;
        color: #f8eed1;
    }

    Checkbox {
        padding: 0 1;
    }

    .collapsible-section {
        margin-bottom: 1;
    }

    .section-header {
        background: #162133;
        color: #f3c57b;
        padding: 0 1;
        text-style: bold;
    }

    .section-header:hover {
        background: #1f2a3a;
    }

    Button.section-header {
        border: none;
        content-align: left middle;
        width: 1fr;
    }

    Button.section-header:focus {
        border: round #f3c57b;
    }

    .section-content {
        padding-left: 1;
        margin-top: 0;
    }

    .section-active {
        height: 1fr;
    }

    .section-active .section-content {
        height: 1fr;
    }

    .section-hidden {
        display: none;
    }

    Button {
        border: round #3a4a63;
        background: #1c2533;
        color: #e8e3d9;
        text-style: bold;
        margin-right: 1;
    }

    Button:focus {
        border: round #f3c57b;
    }

    Button#run {
        background: #1f5b43;
        border: round #2e7d58;
        color: #dff5ea;
    }

    Button#stop {
        background: #6a2a2a;
        border: round #8c3a3a;
        color: #f6d6d6;
    }

    #status {
        margin-left: 1;
        color: #9aa6b2;
        background: #0f1623;
        padding: 0 1;
        border: round #2e3a4f;
    }

    ProgressBar {
        background: #0f1522;
        color: #f3c57b;
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
        color: #8f9aaa;
        width: 1fr;
    }

    .segment-row.state-running {
        background: #1b2534;
        color: #f3c57b;
    }

    .segment-row.state-done {
        color: #8ad9b8;
    }

    .segment-row.state-error {
        color: #f0a0a0;
        background: #331b1b;
    }

    .segment-panel {
        width: 1fr;
    }

    .market-panel {
        width: 46;
        min-width: 34;
        background: #131d2a;
        border: round #344965;
    }

    .market-controls {
        height: auto;
        margin-bottom: 1;
    }

    .market-label {
        width: 7;
        color: #9aa6b2;
    }

    #market-summary {
        color: #d6deea;
        margin-bottom: 1;
    }

    #market-chart {
        background: #0c131f;
        border: round #2f3c50;
        color: #7dd3fc;
        padding: 1 1;
        height: 7;
    }

    #market-detail {
        color: #9aa6b2;
        margin-top: 1;
    }

    #market-context {
        color: #8b93a1;
        margin-top: 1;
    }

    #market-stats {
        color: #cbd5e1;
        background: #0f1623;
        border: round #2f3c50;
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
        background: #0f1522;
        border: round #2f3c50;
        height: 12;
        margin-right: 1;
    }

    #results-view {
        height: 12;
        background: #0c131f;
        border: round #2f3c50;
        color: #e8e3d9;
        padding: 1;
    }

    #log-panel {
        background: #0b111b;
        border: round #2f3c50;
        padding: 1;
        height: 1fr;
        min-height: 8;
    }

    #results-filter {
        margin-bottom: 1;
    }

    TabbedContent {
        background: #0a0f14;
        height: 1fr;
    }

    TabPane {
        padding: 1 2;
        height: 1fr;
    }

    TabBar {
        background: #0f1623;
        border: round #2f3c50;
    }

    Tab {
        background: #111c2b;
        color: #9aa6b2;
        text-style: bold;
    }

    Tab.-active,
    Tab.--active {
        background: #1f2a3a;
        color: #f3c57b;
    }

    .market-full {
        height: 1fr;
    }

    .results-full {
        height: 1fr;
    }

    #results-view-full {
        height: 1fr;
        background: #0c131f;
        border: round #2f3c50;
        color: #e8e3d9;
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
        height: 1fr;
        min-height: 14;
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
            self._capture_output_path(line)
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
            self._refresh_market_panel()
            self._refresh_results_panel()
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
        run_button = self.query_one("#run-btn", Button)
        stop_button = self.query_one("#stop-btn", Button)
        run_button.disabled = running
        stop_button.disabled = not running

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


def main() -> None:
    app = SecNlpTuiApp()
    app.run()
