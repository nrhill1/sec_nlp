"""Textual widgets for the TUI."""

from __future__ import annotations

from pathlib import Path

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Checkbox,
    Input,
    Label,
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
)
from sec_nlp.tui.market import (
    MARKET_METRIC_ADJCLOSE,
    MARKET_METRIC_CLOSE,
    MARKET_METRIC_RANGE,
    MARKET_METRIC_VOLUME,
    MARKET_STYLE_BARS,
    MARKET_STYLE_POINTS,
    MarketSnapshot,
    build_market_chart_lines,
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


class FormView(VerticalScroll):
    def __init__(self) -> None:
        super().__init__(classes="panel")
        self._form_spec: FormSpec | None = None
        self._fields: dict[ConfigScalar, _FieldWidget] = {}
        self._extra_args: Input | None = None

    def set_form(self, form_spec: FormSpec) -> None:
        self._form_spec = form_spec
        self._fields = {}
        self.remove_children()
        self.mount(Label("Configuration", classes="panel-title"))

        for field in form_spec.fields:
            row = Horizontal(classes="form-row")
            label = Label(str(field.label), classes="field-label")
            widget = self._build_widget(field)
            self.mount(row)
            row.mount(label)
            row.mount(widget)
            self._fields[field.key] = widget

        extra_row = Horizontal(classes="form-row")
        extra_label = Label(
            str(form_spec.extra_args_label), classes="field-label"
        )
        extra_input = Input(
            placeholder=str(form_spec.extra_args_placeholder),
            id="extra-args",
        )
        self.mount(extra_row)
        extra_row.mount(extra_label)
        extra_row.mount(extra_input)
        self._extra_args = extra_input

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
}

_MARKET_STYLE_LABELS: dict[ConfigScalar, ConfigScalar] = {
    MARKET_STYLE_BARS: "Bars",
    MARKET_STYLE_POINTS: "Points",
}


class MarketPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(classes="panel market-panel")
        metric_options = [
            (str(label), str(key))
            for key, label in _MARKET_METRIC_LABELS.items()
        ]
        style_options = [
            (str(label), str(key))
            for key, label in _MARKET_STYLE_LABELS.items()
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
        self._normalize_toggle = Checkbox(
            label="Normalize",
            value=True,
            id="market-normalize",
        )
        self._summary = Static("", id="market-summary")
        self._chart = Static("", id="market-chart")
        self._detail = Static("", id="market-detail")
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
            yield self._normalize_toggle
        yield self._summary
        yield self._chart
        yield self._detail
        yield self._context_label

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select in (self._metric_select, self._style_select):
            self._render_snapshot()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox is self._normalize_toggle:
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

        series = select_market_series(self._snapshot, metric_key)
        label = _MARKET_METRIC_LABELS.get(metric_key, "Metric")
        summary = self._build_summary(self._snapshot)
        self._summary.update(str(summary))
        chart_lines = build_market_chart_lines(
            series,
            width=self._chart_width(),
            height=6,
            style=style_key,
            normalize=normalize,
        )
        self._chart.update(
            "\n".join(str(line) for line in chart_lines)
            if chart_lines
            else "(no chart data)"
        )
        detail = self._build_detail(label, series)
        self._detail.update(str(detail))
        context = self._snapshot.correlation
        self._context_label.update(str(context) if context else "")

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
