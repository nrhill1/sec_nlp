"""Textual widgets for the TUI."""

from __future__ import annotations

from pathlib import Path

from rich.syntax import Syntax
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Select,
    Static,
)

from sec_nlp.tui.interfaces import (
    FIELD_KIND_BOOL,
    FIELD_KIND_CHOICE,
    FIELD_KIND_LIST,
    FIELD_KIND_TEXT,
    FieldSpec,
    FormSpec,
    SectionSpec,
)
from sec_nlp.tui.market import (
    MARKET_METRIC_ADJCLOSE,
    MARKET_METRIC_CLOSE,
    MARKET_METRIC_RANGE,
    MARKET_METRIC_RETURNS,
    MARKET_METRIC_VOLUME,
    MARKET_STYLE_BARS,
    MARKET_STYLE_POINTS,
    MarketSnapshot,
    build_market_chart_lines,
    build_sparkline,
    compute_sma,
    format_stats_lines,
    select_market_series,
)
from sec_nlp.tui.specs import SegmentSpec
from sec_nlp.types import ConfigScalar

type _FieldWidget = Input | Checkbox | Select

_STATE_ICONS: dict[ConfigScalar, ConfigScalar] = {
    "pending": "[ ]",
    "running": "[~]",
    "done": "[x]",
    "error": "[!]",
}


class Spinner(Static):
    _frames = ("-", "\\", "|", "/")

    def __init__(self) -> None:
        super().__init__("")
        self._active = False
        self._frame_index = 0

    def on_mount(self) -> None:
        self.set_interval(0.15, self._tick)

    def start(self) -> None:
        self._active = True
        self._frame_index = 0

    def stop(self) -> None:
        self._active = False
        self.update("")

    def _tick(self) -> None:
        if not self._active:
            return
        frame = self._frames[self._frame_index % len(self._frames)]
        self._frame_index += 1
        self.update(frame)


class SegmentRow(Horizontal):
    def __init__(self, spec: SegmentSpec) -> None:
        super().__init__(classes="segment-row")
        self._spec = spec
        self._state: ConfigScalar = "pending"
        self._spinner = Spinner()
        self._status = Static(str(_STATE_ICONS[self._state]))
        self._label = Static(str(spec.label), classes="segment-label")
        self._detail = Static("", classes="segment-detail")

    def compose(self):
        yield self._spinner
        yield self._status
        yield self._label
        yield self._detail

    @property
    def state(self) -> ConfigScalar:
        return self._state

    def set_state(self, state: ConfigScalar) -> None:
        if state == self._state:
            return
        self.remove_class(f"state-{self._state}")
        self._state = state
        self.add_class(f"state-{self._state}")
        self._status.update(str(_STATE_ICONS.get(state, "[ ]")))
        if state == "running":
            self._spinner.start()
        else:
            self._spinner.stop()

    def set_detail(self, detail: ConfigScalar | None) -> None:
        if detail is None:
            self._detail.update("")
            return
        text = str(detail)
        if len(text) > 120:
            text = text[:117] + "..."
        self._detail.update(text)


class SegmentPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(classes="panel segment-panel")
        self._rows: list[SegmentRow] = []
        self._segment_keys: list[ConfigScalar] = []
        self._current_index = -1
        self._progress = ProgressBar(total=1, show_percentage=False)
        self._list_container = Vertical(classes="segment-list")

    def compose(self):
        yield Label("Segments", classes="panel-title")
        yield self._progress
        yield self._list_container

    def load_segments(self, segments: tuple[SegmentSpec, ...]) -> None:
        self._rows = [SegmentRow(spec) for spec in segments]
        self._segment_keys = [spec.key for spec in segments]
        self._current_index = -1
        self._list_container.remove_children()
        for row in self._rows:
            self._list_container.mount(row)
        total = max(len(self._rows), 1)
        self._progress.update(total=total, progress=0)

    def advance_to(
        self, index: int, detail: ConfigScalar | None = None
    ) -> None:
        if index < 0 or index >= len(self._rows):
            return
        if index > self._current_index:
            if self._current_index >= 0:
                self._rows[self._current_index].set_state("done")
            for idx in range(self._current_index + 1, index):
                self._rows[idx].set_state("done")
        self._rows[index].set_state("running")
        self._rows[index].set_detail(detail)
        self._current_index = index
        self._update_progress()

    def finish(self, success: bool) -> None:
        if success:
            for row in self._rows:
                row.set_state("done")
        elif 0 <= self._current_index < len(self._rows):
            self._rows[self._current_index].set_state("error")
        self._update_progress()

    def reset(self) -> None:
        for row in self._rows:
            row.set_state("pending")
            row.set_detail(None)
        self._current_index = -1
        self._update_progress()

    def _update_progress(self) -> None:
        done_count = sum(1 for row in self._rows if row.state == "done")
        total = max(len(self._rows), 1)
        self._progress.update(total=total, progress=done_count)


class FieldRow(Horizontal):
    def __init__(
        self,
        label: ConfigScalar,
        widget: _FieldWidget,
        help_text: ConfigScalar | None,
    ) -> None:
        super().__init__(classes="form-row")
        self._label = Label(str(label), classes="field-label")
        self._widget = widget
        if help_text:
            self.tooltip = str(help_text)

    def compose(self):
        yield self._label
        yield self._widget


class CollapsibleSection(Vertical):
    """A collapsible section with a toggle header."""

    def __init__(
        self,
        section_spec: SectionSpec,
        rows: list[FieldRow],
        classes: ConfigScalar = "collapsible-section",
    ) -> None:
        classes_text = None if classes is None else str(classes)
        super().__init__(classes=classes_text)
        self._spec = section_spec
        self._collapsed = section_spec.collapsed
        icon = "▶" if self._collapsed else "▼"
        self._header = Button(
            f"{icon} {section_spec.label}",
            classes="section-header",
            id=f"section-header-{section_spec.key}",
        )
        self._rows = rows
        self._content: Vertical | None = None

    def on_mount(self) -> None:
        self._apply_collapsed()

    def compose(self):
        yield self._header
        with Vertical(
            classes="section-content",
            id=f"section-content-{self._spec.key}",
        ) as content:
            self._content = content
            yield from self._rows

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button is self._header:
            self.toggle()

    def toggle(self) -> None:
        self._collapsed = not self._collapsed
        icon = "▶" if self._collapsed else "▼"
        self._header.label = f"{icon} {self._spec.label}"
        self._apply_collapsed()

    def _apply_collapsed(self) -> None:
        content = self._content
        if content is None:
            return
        if self._collapsed:
            content.set_styles("display: none;")
        else:
            content.set_styles("display: block;")

    @property
    def content(self) -> Vertical:
        if self._content is None:
            return self.query_one(
                f"#section-content-{self._spec.key}", Vertical
            )
        return self._content


class FormView(VerticalScroll):
    def __init__(self) -> None:
        super().__init__(classes="panel")
        self._form_spec: FormSpec | None = None
        self._fields: dict[ConfigScalar, _FieldWidget] = {}
        self._extra_args: Input | None = None
        self._sections: dict[ConfigScalar, CollapsibleSection] = {}
        self._pending_form_spec: FormSpec | None = None

    def set_form(self, form_spec: FormSpec) -> None:
        self._form_spec = form_spec
        self._fields = {}
        self._sections = {}
        self.remove_children()
        self.mount(Label("Configuration", classes="panel-title"))

        # Group fields by section
        section_fields: dict[ConfigScalar, list[FieldSpec]] = {}
        root_fields: list[FieldSpec] = []
        for field in form_spec.fields:
            if field.section is not None:
                if field.section not in section_fields:
                    section_fields[field.section] = []
                section_fields[field.section].append(field)
            else:
                root_fields.append(field)

        # Build sections with their fields inline
        if form_spec.sections:
            for section_spec in form_spec.sections:
                section_widget = self._build_section(
                    section_spec, section_fields.get(section_spec.key, [])
                )
                self.mount(section_widget)
                self._sections[section_spec.key] = section_widget

        # Add root fields (not in any section)
        for field in root_fields:
            row = self._build_field_row(field)
            self.mount(row)

        extra_input = Input(
            placeholder=str(form_spec.extra_args_placeholder),
            id="extra-args",
        )
        extra_row = FieldRow(
            form_spec.extra_args_label,
            extra_input,
            "Additional CLI arguments",
        )
        self.mount(extra_row)
        self._extra_args = extra_input

    def _build_section(
        self, section_spec: SectionSpec, fields: list[FieldSpec]
    ) -> CollapsibleSection:
        """Build a collapsible section with fields pre-populated."""
        rows: list[FieldRow] = [
            self._build_field_row(field) for field in fields
        ]
        return CollapsibleSection(section_spec, rows)

    def _build_field_row(self, field: FieldSpec) -> FieldRow:
        """Build a row containing a label and widget for a field."""
        widget = self._build_widget(field)
        self._fields[field.key] = widget
        return FieldRow(field.label, widget, field.help)

    def focus_first(self) -> None:
        for widget in self._fields.values():
            widget.focus()
            return
        if self._extra_args is not None:
            self._extra_args.focus()

    def focus_field(self, key: ConfigScalar) -> None:
        widget = self._fields.get(key)
        if widget is None:
            return
        widget.focus()

    def get_values(self) -> dict[ConfigScalar, ConfigScalar]:
        values: dict[ConfigScalar, ConfigScalar] = {}
        for key, widget in self._fields.items():
            if isinstance(widget, Input):
                values[key] = widget.value
            elif isinstance(widget, Checkbox):
                values[key] = widget.value
            elif isinstance(widget, Select):
                value = widget.value
                if value is None:
                    values[key] = ""
                elif isinstance(value, (str, int, float, bool, Path)):
                    values[key] = value
                else:
                    values[key] = ""
            else:
                values[key] = ""
        return values

    def get_extra_args(self) -> ConfigScalar | None:
        if self._extra_args is None:
            return None
        return self._extra_args.value

    def _build_widget(self, field: FieldSpec) -> _FieldWidget:
        if field.kind == FIELD_KIND_BOOL:
            widget = Checkbox()
            if field.default is not None:
                widget.value = bool(field.default)
            return widget

        if field.kind == FIELD_KIND_CHOICE:
            options = [(str(choice), str(choice)) for choice in field.choices]
            widget = Select(options, allow_blank=True)
            if field.default is not None:
                widget.value = str(field.default)
            return widget

        if field.kind in (FIELD_KIND_TEXT, FIELD_KIND_LIST):
            value = ""
            if field.default is not None:
                value = str(field.default)
            return Input(
                value=value,
                placeholder=(
                    str(field.placeholder)
                    if field.placeholder is not None
                    else ""
                ),
            )

        return Input(
            placeholder=(
                str(field.placeholder) if field.placeholder is not None else ""
            )
        )


_MARKET_METRIC_LABELS: dict[ConfigScalar, ConfigScalar] = {
    MARKET_METRIC_CLOSE: "Close",
    MARKET_METRIC_VOLUME: "Volume",
    MARKET_METRIC_RANGE: "Range",
    MARKET_METRIC_ADJCLOSE: "Adj Close",
    MARKET_METRIC_RETURNS: "Returns",
}

_MARKET_STYLE_LABELS: dict[ConfigScalar, ConfigScalar] = {
    MARKET_STYLE_BARS: "Bars",
    MARKET_STYLE_POINTS: "Points",
}

MARKET_DISPLAY_FULL = "full"
MARKET_DISPLAY_CHART = "chart"
MARKET_DISPLAY_STATS = "stats"

_MARKET_DISPLAY_LABELS: dict[ConfigScalar, ConfigScalar] = {
    MARKET_DISPLAY_FULL: "Full",
    MARKET_DISPLAY_CHART: "Chart",
    MARKET_DISPLAY_STATS: "Stats",
}


class MarketPanel(Vertical):
    def __init__(self, classes: ConfigScalar = "panel market-panel") -> None:
        classes_text = None if classes is None else str(classes)
        super().__init__(classes=classes_text)
        metric_options = [
            (str(label), str(key))
            for key, label in _MARKET_METRIC_LABELS.items()
        ]
        style_options = [
            (str(label), str(key))
            for key, label in _MARKET_STYLE_LABELS.items()
        ]
        display_options = [
            (str(label), str(key))
            for key, label in _MARKET_DISPLAY_LABELS.items()
        ]
        self._metric_select = Select(
            metric_options,
            value=str(MARKET_METRIC_CLOSE),
            allow_blank=False,
            id="market-metric",
        )
        self._style_select = Select(
            style_options,
            value=str(MARKET_STYLE_BARS),
            allow_blank=False,
            id="market-style",
        )
        self._display_select = Select(
            display_options,
            value=str(MARKET_DISPLAY_FULL),
            allow_blank=False,
            id="market-display",
        )
        self._normalize_toggle = Checkbox(
            label="Normalize",
            value=True,
            id="market-normalize",
        )
        self._sma_toggle = Checkbox(
            label="SMA",
            value=False,
            id="market-sma",
        )
        self._summary = Static("", id="market-summary")
        self._chart = Static("", id="market-chart")
        self._detail = Static("", id="market-detail")
        self._stats = Static("", id="market-stats")
        self._context_label = Static("", id="market-context")
        self._snapshot: MarketSnapshot | None = None
        self._message: ConfigScalar | None = (
            "Run analyze with market enabled to populate this view."
        )

    def compose(self):
        yield Label("Market", classes="panel-title")
        with Horizontal(classes="market-controls"):
            yield Label("Metric", classes="market-label")
            yield self._metric_select
            yield Label("View", classes="market-label")
            yield self._style_select
            yield Label("Display", classes="market-label")
            yield self._display_select
            yield self._normalize_toggle
            yield self._sma_toggle
        yield self._summary
        yield self._chart
        yield self._detail
        yield self._stats
        yield self._context_label

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select in (
            self._metric_select,
            self._style_select,
            self._display_select,
        ):
            self._render_snapshot()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox in (self._normalize_toggle, self._sma_toggle):
            self._render_snapshot()

    def on_resize(self) -> None:
        self._render_snapshot()

    def set_snapshot(self, snapshot: MarketSnapshot | None) -> None:
        self._snapshot = snapshot
        self._render_snapshot()

    def set_message(self, message: ConfigScalar | None) -> None:
        self._message = message
        if self._snapshot is None:
            self._render_snapshot()

    def reset(self) -> None:
        self._snapshot = None
        self._render_snapshot()

    def _render_snapshot(self) -> None:
        display_key = self._select_value(
            self._display_select, MARKET_DISPLAY_FULL
        )
        self._apply_display(display_key)
        if self._snapshot is None:
            message = self._message or "No market data yet."
            self._summary.update(str(message))
            self._chart.update("(no market data)")
            self._detail.update("")
            self._context_label.update("")
            return

        metric_key = self._select_value(
            self._metric_select, MARKET_METRIC_CLOSE
        )
        style_key = self._select_value(self._style_select, MARKET_STYLE_BARS)
        normalize = bool(self._normalize_toggle.value)
        show_sma = bool(self._sma_toggle.value)

        series = select_market_series(self._snapshot, metric_key)
        label = _MARKET_METRIC_LABELS.get(metric_key, "Metric")
        summary = self._build_summary(self._snapshot)
        # append sparkline to summary for quick glance
        spark = build_sparkline(series, max(10, self._chart_width() - 8))
        summary_text = f"{summary}  {spark}" if spark else str(summary)
        self._summary.update(str(summary_text))

        # Optionally overlay SMA
        sma_series = compute_sma(series, window=5) if show_sma else None
        chart_lines = build_market_chart_lines(
            series,
            width=self._chart_width(),
            height=6,
            style=style_key,
            normalize=normalize,
            overlay=sma_series,
        )
        self._chart.update(
            "\n".join(str(line) for line in chart_lines)
            if chart_lines
            else "(no chart data)"
        )
        detail = self._build_detail(label, series)
        self._detail.update(str(detail))
        # stats
        stats_lines = format_stats_lines(series)
        self._stats.update("\n".join(str(line) for line in stats_lines))
        context = self._snapshot.correlation
        self._context_label.update(str(context) if context else "")

    def _apply_display(self, display: ConfigScalar) -> None:
        show_chart = display in (MARKET_DISPLAY_FULL, MARKET_DISPLAY_CHART)
        show_stats = display in (MARKET_DISPLAY_FULL, MARKET_DISPLAY_STATS)
        show_context = display in (MARKET_DISPLAY_FULL, MARKET_DISPLAY_STATS)
        show_detail = show_chart
        self._set_visible(self._chart, show_chart)
        self._set_visible(self._detail, show_detail)
        self._set_visible(self._stats, show_stats)
        self._set_visible(self._context_label, show_context)

    def _set_visible(self, widget: Static, visible: bool) -> None:
        if visible:
            widget.set_styles("display: block;")
        else:
            widget.set_styles("display: none;")

    def _build_summary(self, snapshot: MarketSnapshot) -> ConfigScalar:
        window = f"{snapshot.window_start}..{snapshot.window_end}"
        parts = [
            f"{snapshot.ticker} {snapshot.granularity}",
            f"window {window}",
        ]
        if snapshot.filing_date:
            parts.append(f"filing {snapshot.filing_date}")
        return " | ".join(parts)

    def _build_detail(
        self, label: ConfigScalar, series: list[float]
    ) -> ConfigScalar:
        if not series:
            return ""
        min_value = min(series)
        max_value = max(series)
        last_value = series[-1]
        delta = last_value - series[0]
        return (
            f"{label}: last {self._format_number(last_value)} "
            f"range {self._format_number(min_value)}..{self._format_number(max_value)} "
            f"delta {self._format_number(delta)}"
        )

    def _format_number(self, value: float) -> ConfigScalar:
        abs_value = abs(value)
        if abs_value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if abs_value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if abs_value >= 1_000:
            return f"{value / 1_000:.2f}K"
        return f"{value:.2f}"

    def _select_value(
        self, select: Select, default: ConfigScalar
    ) -> ConfigScalar:
        value = select.value
        if isinstance(value, str) and value:
            return value
        return default

    def _chart_width(self) -> int:
        width = self.size.width - 4
        if width < 10:
            return 10
        return width


class ResultsPanel(Vertical):
    def __init__(self, classes: ConfigScalar = "panel results-panel") -> None:
        classes_text = None if classes is None else str(classes)
        super().__init__(classes=classes_text)
        self._filter_input = Input(
            placeholder="Filter files...", id="results-filter"
        )
        self._list = ListView(id="results-list")
        self._viewer = Static("", id="results-view")
        self._all_paths: list[Path] = []
        self._filtered_paths: list[Path] = []
        self._filter_generation = 0

    def compose(self):
        yield Label("Results", classes="panel-title")
        yield self._filter_input
        with Horizontal(classes="results-row"):
            yield self._list
            yield self._viewer

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is self._filter_input:
            self._apply_filter()

    def set_paths(self, paths: list[Path]) -> None:
        # de-duplicate and keep newest first
        unique: list[Path] = []
        seen: set[str] = set()
        for p in sorted(
            paths,
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        ):
            key = str(p)
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)
        self._all_paths = unique
        self._filter_input.value = ""
        self._apply_filter()

    def _apply_filter(self) -> None:
        query = self._filter_input.value.strip().lower()
        if query:
            self._filtered_paths = [
                p for p in self._all_paths if query in p.name.lower()
            ]
        else:
            self._filtered_paths = list(self._all_paths)
        # Increment generation to ensure unique IDs across filter operations
        self._filter_generation += 1
        gen = self._filter_generation
        # Remove existing children before adding new ones
        self._list.remove_children()
        if self._filtered_paths:
            items = [
                ListItem(Label(p.name), id=f"result-{gen}-{idx}")
                for idx, p in enumerate(self._filtered_paths)
            ]
            for item in items:
                self._list.mount(item)
            self._list.index = 0
            self._load_index(0)
        else:
            self._viewer.update("(no YAML results)")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None or event.item.id is None:
            return
        item_id = str(event.item.id)
        if not item_id.startswith("result-"):
            return
        # ID format: result-{generation}-{index}
        parts = item_id.removeprefix("result-").split("-", 1)
        if len(parts) != 2:
            return
        try:
            idx = int(parts[1])
        except ValueError:
            return
        self._load_index(idx)

    def _load_index(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._filtered_paths):
            return
        path = self._filtered_paths[idx]
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            self._viewer.update("(failed to read file)")
            return
        # Try syntax highlight; fall back to plain text
        try:
            syntax = Syntax(text, "yaml", theme="ansi_light", word_wrap=True)
            self._viewer.update(syntax)
        except Exception:
            self._viewer.update(text)
