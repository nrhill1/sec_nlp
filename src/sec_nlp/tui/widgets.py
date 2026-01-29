"""Textual widgets for the TUI."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date
from pathlib import Path

from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
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
    Tree,
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
    MARKET_STYLE_CANDLE,
    MARKET_STYLE_LINE,
    MARKET_STYLE_POINTS,
    MarketQuotePoint,
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
type SectionToggleHandler = Callable[[ConfigScalar, bool], None]


class SectionModeChanged(Message):
    def __init__(self, active: bool) -> None:
        super().__init__()
        self.active = active


_STATE_ICONS: dict[ConfigScalar, ConfigScalar] = {
    "pending": "○",
    "running": "◉",
    "done": "✓",
    "error": "⚠",
}


class Spinner(Static):
    _frames = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")

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

    @property
    def label(self) -> ConfigScalar:
        return self._spec.label

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
        self._list_container = VerticalScroll(classes="segment-list")
        self._list_container.show_vertical_scrollbar = True
        self._status = Static("", classes="segment-status")

    def compose(self):
        yield Label("Segments", classes="panel-title")
        yield self._progress
        yield self._list_container
        yield self._status

    def load_segments(self, segments: tuple[SegmentSpec, ...]) -> None:
        self._rows = [SegmentRow(spec) for spec in segments]
        self._segment_keys = [spec.key for spec in segments]
        self._current_index = -1
        self._list_container.remove_children()
        for row in self._rows:
            self._list_container.mount(row)
        total = max(len(self._rows), 1)
        self._progress.update(total=total, progress=0)
        self._set_status("Ready to run.", None)

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
        label = self._rows[index].label
        step = f"Step {index + 1}/{len(self._rows)}: {label}"
        self._set_status(step, detail)

    def finish(self, success: bool) -> None:
        if success:
            for row in self._rows:
                row.set_state("done")
            self._set_status("Pipeline completed.", None)
        elif 0 <= self._current_index < len(self._rows):
            self._rows[self._current_index].set_state("error")
            label = self._rows[self._current_index].label
            self._set_status(f"Failed at: {label}", None)
        self._update_progress()

    def reset(self) -> None:
        for row in self._rows:
            row.set_state("pending")
            row.set_detail(None)
        self._current_index = -1
        self._update_progress()
        self._set_status("Ready to run.", None)

    def _update_progress(self) -> None:
        done_count = sum(1 for row in self._rows if row.state == "done")
        total = max(len(self._rows), 1)
        self._progress.update(total=total, progress=done_count)

    def _set_status(
        self, message: ConfigScalar, detail: ConfigScalar | None
    ) -> None:
        if detail is None:
            self._status.update(str(message))
            return
        detail_text = str(detail)
        if len(detail_text) > 140:
            detail_text = detail_text[:137] + "..."
        self._status.update(f"{message}\n{detail_text}")


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
        on_toggle: SectionToggleHandler | None = None,
        classes: ConfigScalar = "collapsible-section",
    ) -> None:
        classes_text = None if classes is None else str(classes)
        super().__init__(classes=classes_text)
        self._spec = section_spec
        self._collapsed = section_spec.collapsed
        self._on_toggle = on_toggle
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
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool, *, notify: bool = True) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        icon = "▶" if self._collapsed else "▼"
        self._header.label = f"{icon} {self._spec.label}"
        self._apply_collapsed()
        if self._on_toggle is not None and notify:
            self._on_toggle(self._spec.key, self._collapsed)

    def _apply_collapsed(self) -> None:
        content = self._content
        if content is None:
            return
        if self._collapsed:
            content.set_styles("display: none;")
        else:
            content.set_styles("display: block;")
        self.refresh(layout=True)

    @property
    def content(self) -> Vertical:
        if self._content is None:
            return self.query_one(
                f"#section-content-{self._spec.key}", Vertical
            )
        return self._content


class FormView(Horizontal):
    """Form view with sidebar section navigation.

    Uses a ListView on the left for section selection, and shows
    the selected section's fields on the right.
    """

    can_focus = True
    can_focus_children = True

    DEFAULT_CSS = """
    FormView {
        height: 1fr;
    }

    FormView > .section-nav {
        width: 22;
        height: 1fr;
        background: #09090b;
        border: none;
        margin-right: 1;
    }

    FormView > .section-nav > ListItem {
        padding: 0 1;
        height: 2;
        color: #6b7280;
    }

    FormView > .section-nav > ListItem:hover {
        background: #161619;
        color: #9ca3af;
    }

    FormView > .section-nav > ListItem.-active {
        background: #1c1c20;
        color: #60a5fa;
    }

    FormView > .section-nav > ListItem.--highlight,
    FormView > .section-nav > ListItem:focus {
        background: #1c1c20;
        color: #60a5fa;
    }

    FormView > .section-content {
        width: 1fr;
        height: 1fr;
    }
    """

    # Class-level counter for unique widget IDs across form switches
    _form_counter: int = 0

    def __init__(self) -> None:
        super().__init__(classes="panel")
        self._form_spec: FormSpec | None = None
        self._fields: dict[ConfigScalar, _FieldWidget] = {}
        self._extra_args: Input | None = None
        self._section_containers: dict[ConfigScalar, Vertical] = {}
        self._pending_form_spec: FormSpec | None = None
        self._root_container: Vertical | None = None
        self._extra_row: FieldRow | None = None
        self._active_section_key: ConfigScalar | None = None
        self._section_mode_active = False
        self._section_field_keys: dict[ConfigScalar, list[ConfigScalar]] = {}
        self._section_nav: ListView | None = None
        self._section_keys: list[ConfigScalar] = []
        self._content_area: VerticalScroll | None = None
        self._id_suffix: int = 0

    def compose(self) -> ComposeResult:
        # Will be populated by set_form
        self._section_nav = ListView(id="section-nav-0", classes="section-nav")
        self._content_area = VerticalScroll(
            id="section-content-0", classes="section-content"
        )
        yield self._section_nav
        yield self._content_area

    def set_form(self, form_spec: FormSpec) -> None:
        self._form_spec = form_spec
        self._fields = {}
        self._section_containers = {}
        self._root_container = None
        self._extra_row = None
        self._active_section_key = None
        self._section_field_keys = {}
        self._section_keys = []

        # Replace the entire ListView and VerticalScroll containers to avoid
        # duplicate ID issues. Widget.remove() is async, so we can't reliably
        # clear and re-populate. Instead, we remove the old containers entirely
        # and mount fresh ones with unique IDs using an incrementing suffix.
        if self._section_nav is not None:
            self._section_nav.remove()
        if self._content_area is not None:
            self._content_area.remove()

        # Increment suffix to ensure unique IDs
        self._id_suffix += 1
        suffix = self._id_suffix

        # Create fresh containers with unique IDs and mount them to self
        self._section_nav = ListView(
            id=f"section-nav-{suffix}", classes="section-nav"
        )
        self._content_area = VerticalScroll(
            id=f"section-content-{suffix}", classes="section-content"
        )
        self.mount(self._section_nav)
        self.mount(self._content_area)

        # Group fields by section
        section_fields: dict[ConfigScalar, list[FieldSpec]] = {}
        root_fields: list[FieldSpec] = []
        for field in form_spec.fields:
            if field.section is not None:
                if field.section not in section_fields:
                    section_fields[field.section] = []
                section_fields[field.section].append(field)
                if field.section not in self._section_field_keys:
                    self._section_field_keys[field.section] = []
                self._section_field_keys[field.section].append(field.key)
            else:
                root_fields.append(field)

        # Build navigation items
        nav_items: list[ListItem] = []
        # Add "Overview" for root fields
        nav_items.append(ListItem(Label("Overview"), id="nav-__overview__"))
        self._section_keys.append("__overview__")

        # Add section items
        if form_spec.sections:
            for section_spec in form_spec.sections:
                nav_items.append(
                    ListItem(
                        Label(str(section_spec.label)),
                        id=f"nav-{section_spec.key}",
                    )
                )
                self._section_keys.append(section_spec.key)

        # Mount nav items
        if self._section_nav is not None:
            for item in nav_items:
                self._section_nav.mount(item)

        # Build content containers - collect children first, then mount
        if self._content_area is not None:
            # Overview container (root fields + extra args)
            overview_children: list[FieldRow] = []
            for field in root_fields:
                row = self._build_field_row(field)
                overview_children.append(row)
            # Extra args at end of overview
            extra_input = Input(
                placeholder=str(form_spec.extra_args_placeholder),
                id="extra-args",
            )
            extra_row = FieldRow(
                form_spec.extra_args_label,
                extra_input,
                "Additional CLI arguments",
            )
            overview_children.append(extra_row)
            self._extra_args = extra_input
            self._extra_row = extra_row

            overview = Vertical(
                *overview_children,
                id="content-__overview__",
                classes="section-pane",
            )
            self._content_area.mount(overview)
            self._root_container = overview
            self._section_containers["__overview__"] = overview

            # Section containers
            if form_spec.sections:
                for section_spec in form_spec.sections:
                    section_children: list[Label | FieldRow] = [
                        Label(str(section_spec.label), classes="section-title")
                    ]
                    for field in section_fields.get(section_spec.key, []):
                        row = self._build_field_row(field)
                        section_children.append(row)
                    container = Vertical(
                        *section_children,
                        id=f"content-{section_spec.key}",
                        classes="section-pane",
                    )
                    self._content_area.mount(container)
                    self._section_containers[section_spec.key] = container

        # Show overview by default
        self._set_active_section("__overview__")
        if self._section_nav is not None:
            self._section_nav.index = 0

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view is not self._section_nav:
            return
        if event.item is None or event.item.id is None:
            return
        # Extract section key from item id (nav-{key})
        item_id = str(event.item.id)
        if item_id.startswith("nav-"):
            key = item_id[4:]  # Remove "nav-" prefix
            self._set_active_section(key)

    def _build_field_row(self, field: FieldSpec) -> FieldRow:
        """Build a row containing a label and widget for a field."""
        widget = self._build_widget(field)
        self._fields[field.key] = widget
        return FieldRow(field.label, widget, field.help)

    def focus_first(self) -> None:
        active = self._active_section_key
        if active is not None and active != "__overview__":
            self._focus_section_first(active)
            return
        for widget in self._fields.values():
            widget.focus()
            return
        if self._extra_args is not None:
            self._extra_args.focus()

    def _focus_section_first(self, key: ConfigScalar) -> None:
        field_keys = self._section_field_keys.get(key)
        if field_keys is None:
            return
        for field_key in field_keys:
            widget = self._fields.get(field_key)
            if widget is not None:
                widget.focus()
                return

    def _set_active_section(self, key: ConfigScalar | None) -> None:
        if key is None:
            key = "__overview__"
        was_active = self._section_mode_active
        self._active_section_key = key
        self._apply_section_visibility()
        self._section_mode_active = key != "__overview__"
        if was_active != self._section_mode_active:
            self.post_message(SectionModeChanged(self._section_mode_active))

    def _apply_section_visibility(self) -> None:
        active = self._active_section_key
        if active is None:
            active = "__overview__"

        for key, container in self._section_containers.items():
            if key == active:
                container.set_styles("display: block;")
            else:
                container.set_styles("display: none;")
        self.refresh(layout=True)

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
    MARKET_STYLE_CANDLE: "Candle",
    MARKET_STYLE_LINE: "Line",
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
        # Direct fetch controls
        self._ticker_input = Input(
            placeholder="AAPL",
            id="market-ticker",
        )
        self._days_input = Input(
            placeholder="30",
            value="30",
            id="market-days",
        )
        self._fetch_button = Button("Fetch", id="market-fetch-btn")
        self._fetch_status = Static("", id="market-fetch-status")
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
            "Enter a ticker and click Fetch, or run analyze with market enabled."
        )
        self._fetching = False

    def compose(self):
        yield Label("Market Data", classes="panel-title")
        with Horizontal(classes="market-fetch-row"):
            yield Label("Ticker", classes="market-label")
            yield self._ticker_input
            yield Label("Days", classes="market-label")
            yield self._days_input
            yield self._fetch_button
            yield self._fetch_status
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

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button is self._fetch_button:
            self._start_fetch()

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

    def _start_fetch(self) -> None:
        if self._fetching:
            return
        ticker = self._ticker_input.value.strip().upper()
        if not ticker:
            self._fetch_status.update("Enter a ticker")
            return
        days_text = self._days_input.value.strip()
        try:
            days = int(days_text) if days_text else 30
        except ValueError:
            days = 30
        if days < 1:
            days = 1
        if days > 365:
            days = 365
        self._fetching = True
        self._fetch_button.disabled = True
        self._fetch_status.update("Fetching...")
        asyncio.create_task(self._do_fetch(ticker, days))

    async def _do_fetch(self, ticker: str, days: int) -> None:
        from datetime import (
            datetime as dt,
            timedelta,
        )

        from sec_nlp.core.market import (
            MarketExtensionError,
            create_market_retriever,
        )

        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        retriever = create_market_retriever()
        try:
            raw_quotes = await asyncio.to_thread(
                retriever.retrieve_range, ticker, (start_date, end_date)
            )
        except MarketExtensionError as exc:
            self._fetch_status.update(f"Error: {exc}")
            self._fetching = False
            self._fetch_button.disabled = False
            return
        except Exception as exc:
            self._fetch_status.update(f"Error: {exc}")
            self._fetching = False
            self._fetch_button.disabled = False
            return

        if not raw_quotes:
            self._fetch_status.update("No data found")
            self._fetching = False
            self._fetch_button.disabled = False
            return

        # Convert to MarketQuotePoint
        quotes: list[MarketQuotePoint] = []
        for q in raw_quotes:
            quotes.append(
                MarketQuotePoint(
                    start=dt.fromtimestamp(q.timestamp).date().isoformat(),
                    end=dt.fromtimestamp(q.timestamp).date().isoformat(),
                    open_value=q.open_price,
                    high_value=q.high,
                    low_value=q.low,
                    close_value=q.close,
                    adjclose_value=q.adjclose,
                    volume_value=float(q.volume),
                )
            )

        snapshot = MarketSnapshot(
            symbol=ticker,
            ticker=ticker,
            filing_date=None,
            window_start=start_date.isoformat(),
            window_end=end_date.isoformat(),
            granularity="daily",
            quotes=tuple(quotes),
            correlation=None,
        )
        self._snapshot = snapshot
        self._fetch_status.update(f"Loaded {len(quotes)} quotes")
        self._fetching = False
        self._fetch_button.disabled = False
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
        # Pass quotes for candlestick rendering
        quotes = list(self._snapshot.quotes) if self._snapshot else None
        chart_width = self._chart_width()
        chart_height = 8  # Rows for the chart
        chart_lines = build_market_chart_lines(
            series,
            width=chart_width,
            height=chart_height,
            style=style_key,
            normalize=normalize,
            overlay=sma_series,
            quotes=quotes,
        )

        # Build chart display with axis labels
        if chart_lines and series:
            min_val = min(series)
            max_val = max(series)
            # Add price axis labels on the left
            labeled_lines: list[str] = []
            for i, line in enumerate(chart_lines):
                if i == 0:
                    price_label = f"{self._format_number(max_val):>8} │"
                elif i == len(chart_lines) - 1:
                    price_label = f"{self._format_number(min_val):>8} │"
                elif i == len(chart_lines) // 2:
                    mid_val = (max_val + min_val) / 2
                    price_label = f"{self._format_number(mid_val):>8} │"
                else:
                    price_label = "         │"
                labeled_lines.append(f"{price_label}{line}")
            # Add bottom axis line
            labeled_lines.append("         └" + "─" * min(chart_width, 60))
            chart_text = "\n".join(labeled_lines)
        else:
            chart_text = "(no chart data)"

        self._chart.update(chart_text)
        detail = self._build_detail(label, series)
        self._detail.update(str(detail))

        # Stats display
        stats_lines = format_stats_lines(series)
        if stats_lines:
            self._stats.update("\n".join(str(line) for line in stats_lines))
        else:
            self._stats.update("(no stats)")

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
        """Calculate available width for chart rendering."""
        # Account for padding (2 chars each side) and border (1 char each side)
        width = self.size.width - 6
        # Ensure minimum width for readable charts
        if width < 20:
            return 20
        # Cap at reasonable max to prevent overly wide charts
        if width > 120:
            return 120
        return width


class ResultsPanel(Vertical):
    """Results panel with tree view for hierarchical file browsing."""

    DEFAULT_CSS = """
    ResultsPanel {
        height: 1fr;
    }

    #results-tree {
        width: 42;
        height: 1fr;
        background: #09090b;
        border: none;
        margin-right: 1;
        scrollbar-size: 1 1;
    }

    #results-tree > .tree--guides {
        color: #1e1e22;
    }

    #results-tree > .tree--cursor {
        background: #161619;
        color: #60a5fa;
    }

    #results-view-full {
        height: 1fr;
        background: #09090b;
        border: none;
        padding: 1;
        overflow-y: auto;
    }
    """

    def __init__(self, classes: ConfigScalar = "panel results-panel") -> None:
        classes_text = None if classes is None else str(classes)
        super().__init__(classes=classes_text)
        self._filter_input = Input(
            placeholder="Filter files...", id="results-filter"
        )
        self._tree: Tree[Path] = Tree("Results", id="results-tree")
        self._tree.show_root = True
        self._tree.guide_depth = 2
        self._viewer = Static("", id="results-view-full")
        self._all_paths: list[Path] = []
        self._path_to_node: dict[str, Path] = {}

    def compose(self):
        yield Label("Results", classes="panel-title")
        yield self._filter_input
        with Horizontal(classes="results-row"):
            yield self._tree
            yield VerticalScroll(self._viewer, id="results-view-scroll")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input is self._filter_input:
            self._rebuild_tree()

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
        self._rebuild_tree()

    def _rebuild_tree(self) -> None:
        """Build tree structure from paths, grouped by symbol/pipeline/run."""
        query = self._filter_input.value.strip().lower()
        if query:
            filtered = [p for p in self._all_paths if query in str(p).lower()]
        else:
            filtered = list(self._all_paths)

        self._tree.clear()
        self._path_to_node = {}

        if not filtered:
            self._viewer.update("(no results)")
            return

        # Group paths into hierarchy: symbol -> pipeline -> run_id -> files
        # Expected structure: outputs/<SYMBOL>/<pipeline>/<run_id>/<accession>/file.yaml
        hierarchy: dict[
            str, dict[str, dict[str, list[Path]]]
        ] = {}  # symbol -> pipeline -> run -> files

        for path in filtered:
            parts = path.parts
            # Try to find 'outputs' in path and extract hierarchy
            symbol, pipeline, run_id = self._extract_hierarchy(parts)
            if symbol not in hierarchy:
                hierarchy[symbol] = {}
            if pipeline not in hierarchy[symbol]:
                hierarchy[symbol][pipeline] = {}
            if run_id not in hierarchy[symbol][pipeline]:
                hierarchy[symbol][pipeline][run_id] = []
            hierarchy[symbol][pipeline][run_id].append(path)

        # Build tree nodes
        root = self._tree.root
        root.expand()

        for symbol in sorted(hierarchy.keys()):
            symbol_node = root.add(f"📁 {symbol}", expand=True)
            for pipeline in sorted(hierarchy[symbol].keys()):
                pipeline_label = self._pipeline_icon(pipeline) + f" {pipeline}"
                pipeline_node = symbol_node.add(pipeline_label, expand=True)
                for run_id in sorted(
                    hierarchy[symbol][pipeline].keys(), reverse=True
                ):
                    run_files = hierarchy[symbol][pipeline][run_id]
                    if len(run_files) == 1:
                        # Single file - add as leaf directly
                        path = run_files[0]
                        file_label = f"📄 {run_id}/{path.name}"
                        pipeline_node.add_leaf(file_label, data=path)
                        self._path_to_node[str(path)] = path
                    else:
                        # Multiple files - add run as folder
                        run_node = pipeline_node.add(
                            f"📂 {run_id}", expand=False
                        )
                        for path in run_files:
                            run_node.add_leaf(f"📄 {path.name}", data=path)
                            self._path_to_node[str(path)] = path

        # Select first file if available
        if filtered:
            self._load_path(filtered[0])

    def _extract_hierarchy(
        self, parts: tuple[str, ...]
    ) -> tuple[str, str, str]:
        """Extract symbol, pipeline, run_id from path parts."""
        # Look for 'outputs' directory and extract structure after it
        try:
            outputs_idx = list(parts).index("outputs")
            if len(parts) > outputs_idx + 3:
                symbol = parts[outputs_idx + 1]
                pipeline = parts[outputs_idx + 2]
                run_id = parts[outputs_idx + 3]
                return symbol, pipeline, run_id
        except ValueError:
            pass
        # Fallback: use parent directories
        if len(parts) >= 4:
            return parts[-4], parts[-3], parts[-2]
        if len(parts) >= 3:
            return "unknown", parts[-3], parts[-2]
        if len(parts) >= 2:
            return "unknown", "unknown", parts[-2]
        return "unknown", "unknown", "unknown"

    def _pipeline_icon(self, pipeline: str) -> str:
        icons = {
            "analyze": "🔍",
            "exhibit": "📋",
            "warranty": "⚙️",
            "search": "🔎",
        }
        return icons.get(pipeline.lower(), "📁")

    def on_tree_node_selected(self, event: Tree.NodeSelected[Path]) -> None:
        node = event.node
        if node.data is not None:
            self._load_path(node.data)

    def _load_path(self, path: Path) -> None:
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


class EFTSPanel(Vertical):
    """Interactive EDGAR Full-Text Search panel."""

    DEFAULT_CSS = """
    EFTSPanel {
        height: 1fr;
        padding: 1 2;
    }

    #efts-search-row {
        height: auto;
        margin-bottom: 1;
    }

    #efts-query {
        width: 1fr;
    }

    #efts-form-types {
        width: 24;
        margin-left: 1;
    }

    #efts-search-btn {
        margin-left: 1;
    }

    #efts-options-row {
        height: auto;
        margin-bottom: 1;
    }

    #efts-progress-row {
        height: auto;
        margin-bottom: 1;
    }

    #efts-progress {
        width: 1fr;
    }

    #efts-max-results {
        width: 12;
        margin-left: 1;
    }

    #efts-status {
        height: auto;
        margin-bottom: 1;
        color: #a1a1aa;
    }

    #efts-results-container {
        height: 1fr;
    }

    #efts-results-list {
        width: 50;
        height: 1fr;
        background: #0a0a0b;
        border: solid #27272a;
    }

    #efts-detail {
        height: 1fr;
        background: #0a0a0b;
        border: solid #27272a;
        padding: 1;
        margin-left: 1;
        overflow-y: auto;
    }

    .efts-result-item {
        padding: 0 1;
    }

    .efts-result-item:hover {
        background: #18181b;
    }

    .efts-result-item:focus {
        background: #1f1f23;
        color: #22d3ee;
    }
    """

    def __init__(self, classes: ConfigScalar = "panel") -> None:
        classes_text = None if classes is None else str(classes)
        super().__init__(classes=classes_text)
        self._query_input = Input(
            placeholder="Search query (e.g., cybersecurity, breach, risk factor)",
            id="efts-query",
        )
        self._form_types_input = Input(
            placeholder="10-K,10-Q,8-K",
            value="10-K,10-Q",
            id="efts-form-types",
        )
        self._search_btn = Button(
            "Search", id="efts-search-btn", variant="primary"
        )
        self._exact_match = Checkbox(
            label="Exact", value=False, id="efts-exact"
        )
        self._max_results_input = Input(
            placeholder="100",
            value="100",
            id="efts-max-results",
        )
        self._progress = ProgressBar(
            total=100, show_percentage=True, id="efts-progress"
        )
        self._status = Static(
            "Enter a search query and press Search or Enter", id="efts-status"
        )
        self._results_list = ListView(id="efts-results-list")
        self._detail_view = Static("", id="efts-detail")
        self._results: list[dict[str, str | int | float | date | None]] = []
        self._search_task: asyncio.Task[None] | None = None
        self._spinner = Spinner()

    def compose(self):
        yield Label("EFTS — EDGAR Full-Text Search", classes="panel-title")
        with Horizontal(id="efts-search-row"):
            yield self._query_input
            yield self._form_types_input
            yield self._search_btn
            yield self._spinner
        with Horizontal(id="efts-options-row"):
            yield self._exact_match
            yield Label("Max results:", classes="market-label")
            yield self._max_results_input
        with Horizontal(id="efts-progress-row"):
            yield self._progress
        yield self._status
        with Horizontal(id="efts-results-container"):
            yield self._results_list
            yield VerticalScroll(self._detail_view, id="efts-detail-scroll")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "efts-search-btn":
            self._run_search()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "efts-query":
            self._run_search()

    def _run_search(self) -> None:
        query = self._query_input.value.strip()
        if not query:
            self._status.update("Please enter a search query")
            return

        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()

        self._search_task = asyncio.create_task(self._execute_search(query))

    async def _execute_search(self, query: str) -> None:
        from sec_nlp.core.edgar.efts import EFTSClient

        self._spinner.start()
        self._status.update(f"Searching for '{query}'...")
        self._results_list.remove_children()
        self._detail_view.update("")
        self._results = []
        self._progress.update(total=100, progress=0)

        form_types_raw = self._form_types_input.value.strip()
        form_types: list[str] | None = None
        if form_types_raw:
            form_types = [
                ft.strip() for ft in form_types_raw.split(",") if ft.strip()
            ]

        # Parse max results
        try:
            max_results = int(self._max_results_input.value.strip())
            max_results = max(1, min(max_results, 1000))
        except ValueError:
            max_results = 100

        try:
            client = EFTSClient()

            # Use search_all for pagination with larger result sets
            if max_results > 100:
                self._status.update(
                    f"Fetching up to {max_results} results for '{query}'..."
                )
                hits = await client.search_all(
                    query,
                    forms=form_types,
                    max_results=max_results,
                )
                total = len(hits)
                # Update progress to complete
                self._progress.update(total=100, progress=100)
            else:
                response = await client.search(
                    query,
                    forms=form_types,
                    limit=max_results,
                )
                hits = response.hits
                total = response.total
                self._progress.update(total=100, progress=100)

            self._results = [
                {
                    "cik": hit.cik,
                    "company": hit.company_name,
                    "form": hit.form_type,
                    "filed": hit.filed_date,
                    "accession": hit.accession_number,
                    "url": hit.filing_url,
                    "snippet": hit.snippet,
                    "score": hit.score,
                }
                for hit in hits
            ]

            self._spinner.stop()
            self._status.update(
                f"Found {total:,} results (showing {len(hits)})"
            )

            if self._results:
                for idx, result in enumerate(self._results):
                    company = str(result.get("company", "Unknown"))[:40]
                    form = result.get("form", "")
                    filed = result.get("filed", "")
                    label_text = f"{company} | {form} | {filed}"
                    item = ListItem(
                        Label(label_text),
                        id=f"efts-hit-{idx}",
                        classes="efts-result-item",
                    )
                    self._results_list.mount(item)
                self._results_list.index = 0
                self._show_result(0)
            else:
                self._detail_view.update("No results found.")

        except Exception as exc:
            self._spinner.stop()
            self._status.update(f"Search failed: {exc}")
            self._detail_view.update(f"Error: {exc}")

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None or event.item.id is None:
            return
        item_id = str(event.item.id)
        if not item_id.startswith("efts-hit-"):
            return
        try:
            idx = int(item_id.removeprefix("efts-hit-"))
        except ValueError:
            return
        self._show_result(idx)

    def _show_result(self, idx: int) -> None:
        if idx < 0 or idx >= len(self._results):
            return
        result = self._results[idx]
        score = result.get("score", 0)
        score_display = (
            f"{score:.2f}" if isinstance(score, float) else str(score)
        )
        lines = [
            f"Company:   {result.get('company', 'N/A')}",
            f"CIK:       {result.get('cik', 'N/A')}",
            f"Form:      {result.get('form', 'N/A')}",
            f"Filed:     {result.get('filed', 'N/A')}",
            f"Accession: {result.get('accession', 'N/A')}",
            f"Score:     {score_display}",
            "",
            f"URL: {result.get('url', 'N/A')}",
        ]
        snippet = result.get("snippet", "")
        if snippet:
            lines.append("")
            lines.append("─" * 40)
            lines.append("Snippet:")
            lines.append(str(snippet))
        self._detail_view.update("\n".join(lines))
