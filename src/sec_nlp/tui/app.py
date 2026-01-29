"""Textual TUI application for SEC NLP pipelines."""

from __future__ import annotations

import asyncio
import re
import time
from asyncio.subprocess import Process
from pathlib import Path
from typing import TYPE_CHECKING

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

from sec_nlp.types import ConfigScalar

if TYPE_CHECKING:
    from sec_nlp.tui.interfaces import FormSpec
    from sec_nlp.tui.widgets import (
        SectionModeChanged,
    )

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
    /* ═══════════════════════════════════════════════════════════════════════
       SEC NLP TUI - Glass Morphism Dark Theme
       A stunning, modern interface inspired by contemporary UI design
       ═══════════════════════════════════════════════════════════════════════ */

    /* ─── Color System ────────────────────────────────────────────────────── */
    /* Deep, rich backgrounds with subtle purple undertones */
    $bg-base: #08080c;
    $bg-surface: #0c0c12;
    $bg-elevated: #12121a;
    $bg-card: #16161f;
    $bg-hover: #1a1a26;
    $bg-active: #1e1e2e;

    /* Refined border palette */
    $border-faint: #1a1a24;
    $border-subtle: #242432;
    $border-medium: #2e2e40;
    $border-strong: #3a3a50;

    /* Typography colors with warm undertones */
    $text-bright: #f0f0f5;
    $text-primary: #d4d4dc;
    $text-secondary: #9898a8;
    $text-muted: #686878;
    $text-faint: #484858;

    /* Vibrant accent spectrum */
    $accent-cyan: #22d3ee;
    $accent-blue: #3b82f6;
    $accent-indigo: #6366f1;
    $accent-violet: #8b5cf6;
    $accent-purple: #a855f7;

    /* Semantic colors */
    $success-bright: #34d399;
    $success-base: #10b981;
    $success-dim: #064e3b;
    $warning-bright: #fbbf24;
    $warning-base: #f59e0b;
    $error-bright: #fb7185;
    $error-base: #ef4444;
    $error-dim: #450a0a;

    /* ─── Global Foundation ───────────────────────────────────────────────── */
    Screen {
        background: $bg-base;
        color: $text-primary;
    }

    /* ─── Header - Floating Glass Bar ─────────────────────────────────────── */
    Header {
        background: $bg-surface;
        color: $accent-cyan;
        text-style: bold;
        height: 1;
        border-bottom: solid $border-faint;
    }

    /* ─── Footer - Subtle Command Palette ─────────────────────────────────── */
    Footer {
        background: $bg-surface;
        color: $text-muted;
        height: 1;
        border-top: solid $border-faint;
    }

    FooterKey > .footer-key--key {
        background: $bg-elevated;
        color: $accent-cyan;
    }

    FooterKey > .footer-key--description {
        color: $text-secondary;
    }

    /* ─── Layout Structure ────────────────────────────────────────────────── */
    #layout {
        height: 1fr;
    }

    #sidebar {
        width: 26;
        background: $bg-surface;
        padding: 1 0;
        border-right: solid $border-faint;
    }

    #main {
        padding: 0;
        height: 1fr;
        background: $bg-base;
    }

    /* ─── Glass Panels ────────────────────────────────────────────────────── */
    .panel {
        background: $bg-surface;
        border: solid $border-faint;
        padding: 1 1;
        margin: 0;
        color: $text-primary;
    }

    .panel-title {
        color: $accent-cyan;
        text-style: bold;
        margin-bottom: 1;
        padding: 0 1;
    }

    /* ─── Pipeline Navigation ─────────────────────────────────────────────── */
    #pipeline-list {
        height: 1fr;
        margin: 0;
        background: transparent;
        border: none;
        scrollbar-size: 1 1;
    }

    #pipeline-list > ListItem {
        padding: 0 2;
        color: $text-muted;
        height: 3;
        background: transparent;
    }

    #pipeline-list > ListItem:hover {
        background: $bg-elevated;
        color: $text-secondary;
    }

    #pipeline-list > ListItem.--highlight,
    #pipeline-list > ListItem.-highlight,
    #pipeline-list > ListItem:focus {
        background: $bg-hover;
        color: $accent-cyan;
        text-style: none;
    }

    #pipeline-desc {
        color: $text-faint;
        margin-top: 1;
        padding: 0 2;
    }

    /* ─── Action Buttons Bar ──────────────────────────────────────────────── */
    #actions {
        height: auto;
        margin: 0;
        padding: 0 1;
        background: $bg-surface;
        border-bottom: solid $border-faint;
    }

    #status-row {
        height: 1fr;
        margin: 0;
    }

    /* ─── Form Layout ─────────────────────────────────────────────────────── */
    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .field-label {
        width: 14;
        color: $text-muted;
        padding: 1 0;
    }

    .section-pane {
        padding: 1 1;
        background: transparent;
    }

    .section-title {
        color: $accent-violet;
        text-style: bold;
        margin-bottom: 1;
        padding-bottom: 1;
        border-bottom: solid $border-faint;
    }

    /* ─── Input Fields - Glass Style ──────────────────────────────────────── */
    Input {
        background: $bg-elevated;
        border: solid $border-subtle;
        color: $text-primary;
        height: 3;
        padding: 0 1;
    }

    Input:hover {
        border: solid $border-medium;
        background: $bg-card;
    }

    Input:focus {
        border: solid $accent-blue;
        background: $bg-card;
        color: $text-bright;
    }

    Input.-valid {
        border: solid $success-base;
    }

    /* ─── Select Dropdowns ────────────────────────────────────────────────── */
    Select {
        background: $bg-elevated;
        border: solid $border-subtle;
        color: $text-primary;
        height: 3;
    }

    Select:hover {
        border: solid $border-medium;
        background: $bg-card;
    }

    Select:focus {
        border: solid $accent-blue;
        background: $bg-card;
    }

    SelectOverlay {
        background: $bg-card;
        border: solid $border-medium;
    }

    SelectCurrent {
        background: $bg-hover;
        color: $accent-cyan;
    }

    OptionList {
        background: $bg-card;
        border: none;
        scrollbar-size: 1 1;
        padding: 0;
    }

    OptionList > .option-list--option {
        padding: 0 2;
        color: $text-secondary;
        background: transparent;
    }

    OptionList > .option-list--option-hover {
        background: $bg-hover;
        color: $text-bright;
    }

    OptionList > .option-list--option-highlighted {
        background: $accent-indigo;
        color: $text-bright;
    }

    /* ─── Checkboxes - Modern Toggle Style ────────────────────────────────── */
    Checkbox {
        background: transparent;
        color: $text-muted;
        padding: 0 1;
    }

    Checkbox:hover {
        color: $text-secondary;
    }

    Checkbox:focus {
        color: $accent-cyan;
    }

    Checkbox.-on {
        color: $success-bright;
    }

    /* ─── Smooth Transitions ──────────────────────────────────────────────── */
    Button, Input, Select, Checkbox, Tab, ListView > ListItem {
        transition: background 80ms linear, color 80ms linear, border 80ms linear;
    }

    .segment-row, Static {
        transition: background 80ms linear, color 80ms linear;
    }


    /* ─── Buttons - Pill Style ────────────────────────────────────────────── */
    Button {
        border: solid $border-subtle;
        background: $bg-elevated;
        color: $text-muted;
        text-style: none;
        margin-right: 1;
        min-width: 10;
        height: 3;
    }

    Button:hover {
        background: $bg-card;
        color: $text-secondary;
        border: solid $border-medium;
    }

    Button:focus {
        border: solid $accent-blue;
        color: $accent-cyan;
    }

    /* Primary action - vibrant gradient effect */
    Button#run-btn {
        background: $success-dim;
        border: solid $success-base;
        color: $success-bright;
    }

    Button#run-btn:hover {
        background: $success-base;
        color: $text-bright;
        border: solid $success-bright;
    }

    Button#run-btn:focus {
        border: solid $success-bright;
    }

    /* Destructive action */
    Button#stop-btn {
        background: $error-dim;
        border: solid $error-base;
        color: $error-bright;
    }

    Button#stop-btn:hover {
        background: $error-base;
        color: $text-bright;
        border: solid $error-bright;
    }

    Button#stop-btn:focus {
        border: solid $error-bright;
    }

    Button:disabled {
        background: $bg-base;
        border: solid $border-faint;
        color: $text-faint;
        text-style: none;
    }

    /* ─── Status Badges ──────────────────────────────────────────────────── */
    #status {
        margin-left: 1;
        color: $text-muted;
        background: $bg-elevated;
        padding: 0 2;
        border: solid $border-faint;
        min-width: 14;
    }

    #elapsed {
        margin-left: 1;
        color: $accent-cyan;
        background: transparent;
        padding: 0 2;
        border: none;
        text-style: none;
    }

    /* ─── Progress Bar - Modern Track ────────────────────────────────────── */
    ProgressBar {
        background: $bg-elevated;
        color: $accent-indigo;
        padding: 0;
        height: 1;
    }

    ProgressBar > .bar--bar {
        color: $accent-indigo;
    }

    ProgressBar > .bar--complete {
        color: $success-bright;
    }

    /* ─── Segment Panel - Card Layout ────────────────────────────────────── */
    .segment-row {
        height: auto;
        padding: 0 2;
        margin: 0;
    }

    .segment-label {
        width: 22;
        text-style: none;
        color: $text-muted;
    }

    .segment-detail {
        color: $text-faint;
        width: 1fr;
    }

    .segment-row.state-pending {
        color: $text-muted;
    }

    .segment-row.state-running {
        background: $bg-hover;
        color: $accent-cyan;
    }

    .segment-row.state-running .segment-label {
        color: $accent-cyan;
        text-style: bold;
    }

    .segment-row.state-done {
        color: $success-bright;
    }

    .segment-row.state-done .segment-label {
        color: $success-bright;
    }

    .segment-row.state-error {
        color: $error-bright;
        background: $error-dim;
    }

    .segment-row.state-error .segment-label {
        color: $error-bright;
    }

    .segment-panel {
        width: 1fr;
        height: 1fr;
        border: solid $border-faint;
        background: $bg-surface;
    }

    .segment-list {
        height: 1fr;
        background: transparent;
        border: none;
        scrollbar-size: 1 1;
    }

    .segment-status {
        margin-top: 1;
        padding: 0 2;
        color: $text-muted;
        background: transparent;
        border: none;
    }

    /* ─── Market Panel - Glass Card ──────────────────────────────────────── */
    .market-panel {
        width: 1fr;
        min-width: 40;
        background: $bg-surface;
        border: solid $border-faint;
        padding: 1 2;
    }

    .market-fetch-row {
        height: auto;
        margin-bottom: 1;
    }

    .market-controls {
        height: auto;
        margin-bottom: 1;
    }

    .market-label {
        width: 8;
        color: $text-muted;
        padding: 1 0;
    }

    #market-ticker {
        width: 14;
        margin-right: 1;
    }

    #market-days {
        width: 10;
        margin-right: 1;
    }

    #market-fetch-btn {
        min-width: 8;
        background: $accent-indigo;
        border: solid $accent-blue;
        color: $text-bright;
    }

    #market-fetch-btn:hover {
        background: $accent-blue;
        border: solid $accent-cyan;
    }

    #market-fetch-status {
        margin-left: 1;
        color: $text-muted;
        padding: 1 0;
    }

    #market-summary {
        color: $accent-cyan;
        margin-bottom: 1;
        text-style: bold;
    }

    #market-chart {
        background: $bg-elevated;
        border: solid $border-faint;
        color: $accent-cyan;
        padding: 0 1;
        height: 12;
        min-height: 10;
    }

    #market-detail {
        color: $text-secondary;
        margin-top: 1;
    }

    #market-context {
        color: $text-muted;
        margin-top: 1;
    }

    #market-stats {
        color: $text-secondary;
        background: $bg-elevated;
        border: solid $border-faint;
        padding: 1 2;
        margin-top: 1;
    }

    /* ─── Results Panel - Glass Card ─────────────────────────────────────── */
    .results-panel {
        width: 1fr;
        border: solid $border-faint;
        background: $bg-surface;
    }

    .results-row {
        height: auto;
        margin-top: 1;
    }

    #results-list {
        width: 38;
        background: $bg-elevated;
        border: solid $border-faint;
        height: 14;
        margin-right: 1;
    }

    #results-view {
        height: 14;
        background: $bg-elevated;
        border: solid $border-faint;
        color: $text-primary;
        padding: 1;
    }

    #log-panel {
        background: $bg-surface;
        border: solid $border-faint;
        padding: 1;
        height: 1fr;
        min-height: 8;
        color: $text-muted;
        scrollbar-size: 1 1;
    }

    #results-filter {
        margin-bottom: 1;
    }

    /* ─── Tabs - Floating Style ─────────────────────────────────────────── */
    TabbedContent {
        background: $bg-base;
        height: 1fr;
    }

    TabPane {
        padding: 1 1;
        height: 1fr;
        background: $bg-base;
    }

    ContentSwitcher {
        background: $bg-base;
    }

    Tabs {
        background: $bg-surface;
        border-bottom: solid $border-faint;
        height: 3;
        width: auto;
    }

    Tab {
        background: transparent;
        color: $text-muted;
        text-style: none;
        padding: 0 3;
        height: 3;
        content-align: center middle;
        margin: 0;
    }

    Tab > Label {
        color: $text-muted;
    }

    Tab:hover {
        color: $text-secondary;
        background: $bg-elevated;
    }

    Tab:hover > Label {
        color: $text-secondary;
    }

    Tab.-active,
    Tab.--active {
        background: $bg-base;
        color: $accent-cyan;
        border-bottom: solid $accent-cyan;
        text-style: none;
    }

    Tab.-active > Label,
    Tab.--active > Label {
        color: $accent-cyan;
    }

    Tab:focus {
        text-style: none;
        color: $accent-cyan;
    }

    Tab:focus > Label {
        color: $accent-cyan;
    }

    Underline {
        background: $border-subtle;
    }

    Underline > .underline--bar {
        background: $accent-cyan;
        color: $accent-cyan;
    }

    /* ─── Full-size Variants ──────────────────────────────────────────────── */
    .market-full {
        height: 1fr;
    }

    .results-full {
        height: 1fr;
    }

    #results-view-full {
        height: 1fr;
        background: $bg-elevated;
        border: solid $border-faint;
        color: $text-primary;
        padding: 1;
    }

    #results-view-scroll {
        height: 1fr;
        border: none;
        scrollbar-size: 1 1;
    }

    /* ─── Run Tab Layout ──────────────────────────────────────────────────── */
    #run {
        height: 1fr;
        layout: vertical;
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
        min-height: 16;
        border: solid $border-faint;
        background: $bg-surface;
    }

    /* ─── Scrollbars - Minimal ───────────────────────────────────────────── */
    Scrollbar {
        background: transparent;
        width: 1;
    }

    ScrollbarGripper {
        background: $border-subtle;
    }

    ScrollbarGripper:hover {
        background: $border-medium;
    }

    /* ─── Tree - File Browser Style ──────────────────────────────────────── */
    Tree {
        scrollbar-size: 1 1;
        background: $bg-elevated;
    }

    Tree > .tree--guides {
        color: $border-subtle;
    }

    Tree > .tree--cursor {
        background: $bg-hover;
        color: $accent-cyan;
    }

    /* ─── Tooltip - Floating Card ────────────────────────────────────────── */
    Tooltip {
        background: $bg-card;
        color: $text-bright;
        border: solid $border-medium;
        padding: 0 2;
    }

    /* ─── Section Navigation (FormView sidebar) ──────────────────────────── */
    #section-nav {
        width: 20;
        background: $bg-surface;
        border-right: solid $border-faint;
        padding: 0;
    }

    #section-nav > ListItem {
        padding: 0 2;
        color: $text-muted;
        height: 2;
        background: transparent;
    }

    #section-nav > ListItem:hover {
        background: $bg-elevated;
        color: $text-secondary;
    }

    #section-nav > ListItem.--highlight,
    #section-nav > ListItem.-highlight,
    #section-nav > ListItem:focus {
        background: $bg-hover;
        color: $accent-violet;
        text-style: none;
    }

    #section-content {
        padding: 0 1;
        background: transparent;
    }

    /* ─── EFTS Panel ──────────────────────────────────────────────────────── */
    .efts-panel {
        background: $bg-surface;
        border: solid $border-faint;
        padding: 1 2;
    }

    .efts-panel Input {
        background: $bg-elevated;
    }

    .efts-panel Button {
        background: $accent-indigo;
        border: solid $accent-blue;
        color: $text-bright;
    }

    .efts-panel Button:hover {
        background: $accent-blue;
    }

    /* ─── DataTable - Modern Grid ────────────────────────────────────────── */
    DataTable {
        background: $bg-elevated;
        scrollbar-size: 1 1;
    }

    DataTable > .datatable--header {
        background: $bg-card;
        color: $accent-cyan;
        text-style: bold;
    }

    DataTable > .datatable--cursor {
        background: $bg-hover;
        color: $text-bright;
    }

    DataTable > .datatable--hover {
        background: $bg-hover;
    }

    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "run_pipeline", "Run"),
        ("s", "stop_pipeline", "Stop"),
        ("1", "switch_tab('run')", "Run tab"),
        ("2", "switch_tab('market')", "Market tab"),
        ("3", "switch_tab('results')", "Results tab"),
        ("4", "switch_tab('efts')", "EFTS tab"),
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
        # Lazy imports for faster initial load
        from sec_nlp.tui.specs import get_pipeline_specs
        from sec_nlp.tui.widgets import (
            EFTSPanel,
            FormView,
            MarketPanel,
            ResultsPanel,
            SegmentPanel,
        )

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
                    with TabPane("EFTS", id="efts"):
                        yield EFTSPanel()
        yield Footer()

    def on_mount(self) -> None:
        from sec_nlp.tui.specs import get_pipeline_specs

        pipeline_list = self.query_one("#pipeline-list", ListView)
        pipeline_list.index = 0
        specs = get_pipeline_specs()
        if specs:
            self._select_pipeline(specs[0].key)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        from sec_nlp.tui.specs import get_pipeline_specs

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
        from sec_nlp.tui.interfaces import get_form_spec
        from sec_nlp.tui.specs import find_pipeline_spec
        from sec_nlp.tui.widgets import (
            FormView,
            MarketPanel,
            SegmentPanel,
        )

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
        from sec_nlp.tui.interfaces import build_cli_args, get_form_spec
        from sec_nlp.tui.specs import find_pipeline_spec
        from sec_nlp.tui.widgets import FormView, MarketPanel, SegmentPanel

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
        from sec_nlp.tui.runner import run_cli
        from sec_nlp.tui.widgets import SegmentPanel

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
        from sec_nlp.tui.market import load_market_snapshot
        from sec_nlp.tui.widgets import MarketPanel

        market_panel = self.query_one(MarketPanel)
        snapshot = load_market_snapshot(self._output_paths)
        market_panel.set_snapshot(snapshot)

    def _refresh_results_panel(self) -> None:
        from sec_nlp.tui.widgets import ResultsPanel

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
