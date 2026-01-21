import asyncio

from textual.app import App, ComposeResult
from textual.widgets import Checkbox, Input

from sec_nlp.tui.interfaces import get_form_spec
from sec_nlp.tui.specs import ANALYZE_SEGMENTS
from sec_nlp.tui.widgets import FormView, SegmentPanel


class PanelApp(App):
    def compose(self) -> ComposeResult:
        yield SegmentPanel()


class FormApp(App):
    def compose(self) -> ComposeResult:
        yield FormView()


def test_segment_panel_progression() -> None:
    app = PanelApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(SegmentPanel)
            panel.load_segments(ANALYZE_SEGMENTS)
            panel.advance_to(0, "line one")
            assert panel._rows[0].state == "running"
            panel.advance_to(1, "line two")
            assert panel._rows[0].state == "done"
            assert panel._rows[1].state == "running"
            panel.finish(True)
            assert all(row.state == "done" for row in panel._rows)

    asyncio.run(run_test())


def test_form_view_collects_values() -> None:
    app = FormApp()
    form_spec = get_form_spec("analyze")
    assert form_spec is not None

    async def run_test() -> None:
        async with app.run_test():
            view = app.query_one(FormView)
            view.set_form(form_spec)
            symbols = view._fields["symbols"]
            assert isinstance(symbols, Input)
            symbols.value = "AAPL MSFT"
            market_enabled = view._fields["market_enabled"]
            assert isinstance(market_enabled, Checkbox)
            market_enabled.value = False
            extra_args = view._extra_args
            assert extra_args is not None
            extra_args.value = "--market-limit 10"
            values = view.get_values()
            assert values["symbols"] == "AAPL MSFT"
            assert values["market_enabled"] is False
            assert view.get_extra_args() == "--market-limit 10"

    asyncio.run(run_test())
