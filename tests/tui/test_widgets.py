import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory

from textual.app import App, ComposeResult
from textual.widgets import Checkbox, Input, Select

from sec_nlp.tui.interfaces import get_form_spec
from sec_nlp.tui.market import MarketQuotePoint, MarketSnapshot
from sec_nlp.tui.specs import ANALYZE_SEGMENTS
from sec_nlp.tui.widgets import (
    FormView,
    MarketPanel,
    ResultsPanel,
    SegmentPanel,
)


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


class MarketApp(App):
    def compose(self) -> ComposeResult:
        yield MarketPanel()


class MarketAppWithClasses(App):
    def compose(self) -> ComposeResult:
        yield MarketPanel(classes="custom-class")


class ResultsApp(App):
    def compose(self) -> ComposeResult:
        yield ResultsPanel()


class ResultsAppWithClasses(App):
    def compose(self) -> ComposeResult:
        yield ResultsPanel(classes="custom-results")


def _make_test_snapshot() -> MarketSnapshot:
    quotes = [
        MarketQuotePoint(
            start="2024-01-01",
            end="2024-01-02",
            open_value=100.0,
            high_value=110.0,
            low_value=95.0,
            close_value=105.0,
            adjclose_value=105.0,
            volume_value=1000000.0,
        ),
        MarketQuotePoint(
            start="2024-01-03",
            end="2024-01-04",
            open_value=106.0,
            high_value=115.0,
            low_value=100.0,
            close_value=112.0,
            adjclose_value=112.0,
            volume_value=1200000.0,
        ),
    ]
    return MarketSnapshot(
        symbol="AAPL",
        ticker="SPY",
        filing_date="2024-01-15",
        window_start="2024-01-01",
        window_end="2024-01-31",
        granularity="daily",
        quotes=tuple(quotes),
        correlation="test correlation",
    )


def test_market_panel_accepts_classes_kwarg() -> None:
    """MarketPanel should accept classes kwarg without error."""
    app = MarketAppWithClasses()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(MarketPanel)
            assert "custom-class" in panel.classes

    asyncio.run(run_test())


def test_market_panel_set_snapshot() -> None:
    """MarketPanel should display snapshot data."""
    app = MarketApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(MarketPanel)
            snapshot = _make_test_snapshot()
            panel.set_snapshot(snapshot)
            assert panel._snapshot is snapshot

    asyncio.run(run_test())


def test_market_panel_reset() -> None:
    """MarketPanel.reset() should clear the snapshot."""
    app = MarketApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(MarketPanel)
            panel.set_snapshot(_make_test_snapshot())
            panel.reset()
            assert panel._snapshot is None

    asyncio.run(run_test())


def test_market_panel_set_message() -> None:
    """MarketPanel.set_message() should update the message when no snapshot."""
    app = MarketApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(MarketPanel)
            panel.set_message("Custom message")
            assert panel._message == "Custom message"

    asyncio.run(run_test())


def test_results_panel_accepts_classes_kwarg() -> None:
    """ResultsPanel should accept classes kwarg without error."""
    app = ResultsAppWithClasses()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(ResultsPanel)
            assert "custom-results" in panel.classes

    asyncio.run(run_test())


def test_results_panel_set_paths() -> None:
    """ResultsPanel.set_paths() should populate the list."""
    app = ResultsApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(ResultsPanel)
            with TemporaryDirectory() as tmpdir:
                path1 = Path(tmpdir) / "test1.yaml"
                path2 = Path(tmpdir) / "test2.yaml"
                path1.write_text("key: value1\n")
                path2.write_text("key: value2\n")
                panel.set_paths([path1, path2])
                assert len(panel._all_paths) == 2
                assert len(panel._filtered_paths) == 2

    asyncio.run(run_test())


def test_results_panel_filter() -> None:
    """ResultsPanel filter should narrow the list."""
    app = ResultsApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(ResultsPanel)
            with TemporaryDirectory() as tmpdir:
                path1 = Path(tmpdir) / "alpha.yaml"
                path2 = Path(tmpdir) / "beta.yaml"
                path3 = Path(tmpdir) / "gamma.yaml"
                path1.write_text("a: 1\n")
                path2.write_text("b: 2\n")
                path3.write_text("c: 3\n")
                panel.set_paths([path1, path2, path3])
                assert len(panel._filtered_paths) == 3
                panel._filter_input.value = "alpha"
                panel._apply_filter()
                assert len(panel._filtered_paths) == 1
                assert panel._filtered_paths[0].name == "alpha.yaml"

    asyncio.run(run_test())


def test_results_panel_empty_paths() -> None:
    """ResultsPanel should handle empty paths list."""
    app = ResultsApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(ResultsPanel)
            panel.set_paths([])
            assert panel._all_paths == []
            assert panel._filtered_paths == []

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


def test_form_view_sections_toggle() -> None:
    app = FormApp()
    form_spec = get_form_spec("analyze")
    assert form_spec is not None

    async def run_test() -> None:
        async with app.run_test() as pilot:
            view = app.query_one(FormView)
            view.set_form(form_spec)
            await pilot.pause()
            sections = view._sections
            assert sections
            core_section = sections.get("core")
            assert core_section is not None
            initial = core_section._collapsed
            core_section.toggle()
            assert core_section._collapsed is not initial

    asyncio.run(run_test())


def test_market_panel_display_select() -> None:
    app = MarketApp()

    async def run_test() -> None:
        async with app.run_test():
            panel = app.query_one(MarketPanel)
            display_select = panel.query_one("#market-display", Select)
            assert display_select.value == "full"

    asyncio.run(run_test())
