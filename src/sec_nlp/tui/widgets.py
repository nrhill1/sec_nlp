"""Textual widgets for the TUI."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
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
from sec_nlp.tui.specs import SegmentSpec
from sec_nlp.types import ConfigScalar

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
        self._label = Static(str(spec.label))

    def compose(self):
        yield self._spinner
        yield self._status
        yield self._label

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


class SegmentPanel(Vertical):
    def __init__(self) -> None:
        super().__init__(classes="panel")
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

    def advance_to(self, index: int) -> None:
        if index < 0 or index >= len(self._rows):
            return
        if index > self._current_index:
            if self._current_index >= 0:
                self._rows[self._current_index].set_state("done")
            for idx in range(self._current_index + 1, index):
                self._rows[idx].set_state("done")
        self._rows[index].set_state("running")
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
        self._fields: dict[ConfigScalar, Widget] = {}
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
            row.mount(label)
            row.mount(widget)
            self.mount(row)
            self._fields[field.key] = widget

        extra_row = Horizontal(classes="form-row")
        extra_label = Label(
            str(form_spec.extra_args_label), classes="field-label"
        )
        extra_input = Input(
            placeholder=str(form_spec.extra_args_placeholder),
            id="extra-args",
        )
        extra_row.mount(extra_label)
        extra_row.mount(extra_input)
        self.mount(extra_row)
        self._extra_args = extra_input

    def get_values(self) -> dict[ConfigScalar, ConfigScalar]:
        values: dict[ConfigScalar, ConfigScalar] = {}
        for key, widget in self._fields.items():
            if isinstance(widget, Input):
                values[key] = widget.value
            elif isinstance(widget, Checkbox):
                values[key] = widget.value
            elif isinstance(widget, Select):
                values[key] = widget.value or ""
            else:
                values[key] = ""
        return values

    def get_extra_args(self) -> ConfigScalar | None:
        if self._extra_args is None:
            return None
        return self._extra_args.value

    def _build_widget(self, field: FieldSpec) -> Widget:
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
