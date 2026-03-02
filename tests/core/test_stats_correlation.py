# tests/core/test_stats_correlation.py
"""Tests for the core stats correlation wrapper module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sec_nlp.core.stats import correlation


def test_wrapper_forwards_inputs_to_extension(monkeypatch) -> None:
    calls: dict[str, tuple] = {}

    def _record(name: str, *args) -> None:
        calls[name] = args

    fake_module = SimpleNamespace(
        pearson=lambda x, y: (_record("pearson", x, y), 0.11)[1],
        spearman=lambda x, y: (_record("spearman", x, y), 0.22)[1],
        simple_returns=lambda prices: (
            _record("simple_returns", prices),
            [0.1],
        )[1],
        cumulative_return=lambda prices: (
            _record("cumulative_return", prices),
            0.33,
        )[1],
        car=lambda x, y: (_record("car", x, y), 0.44)[1],
        rolling_returns=lambda prices, window: (
            _record("rolling_returns", prices, window),
            [0.55],
        )[1],
        std_dev=lambda values: (_record("std_dev", values), 0.66)[1],
        volume_spike=lambda values: (_record("volume_spike", values), 1.77)[1],
        average_true_range=lambda high, low, close: (
            _record("average_true_range", high, low, close),
            0.88,
        )[1],
        garman_klass=lambda high, low, open_, close: (
            _record("garman_klass", high, low, open_, close),
            0.99,
        )[1],
        beta=lambda asset, bench: (_record("beta", asset, bench), 1.11)[1],
        event_study=lambda prices, ts, event_ts, pre, post: (
            _record("event_study", prices, ts, event_ts, pre, post),
            {"p_value": 0.05},
        )[1],
    )

    monkeypatch.setattr(correlation, "_load_corr_module", lambda: fake_module)

    assert correlation.pearson((1.0, 2.0), (3.0, 4.0)) == 0.11
    assert correlation.spearman((1.0, 2.0), (3.0, 4.0)) == 0.22
    assert correlation.simple_returns((10.0, 11.0)) == [0.1]
    assert correlation.cumulative_return((10.0, 11.0)) == 0.33
    assert correlation.car((10.0, 11.0), (20.0, 22.0)) == 0.44
    assert correlation.rolling_returns((10.0, 11.0, 12.0), 2) == [0.55]
    assert correlation.std_dev((0.1, 0.2)) == 0.66
    assert correlation.volume_spike((100.0, 120.0)) == 1.77
    assert correlation.average_true_range((3.0,), (1.0,), (2.0,)) == 0.88
    assert correlation.garman_klass((3.0,), (1.0,), (2.0,), (2.5,)) == 0.99
    assert correlation.beta((0.1, 0.2), (0.05, 0.1)) == 1.11
    assert correlation.event_study(
        (10.0, 11.0), (1700000000, 1700086400), 1700000000, 5, 30
    ) == {"p_value": 0.05}

    assert calls["pearson"] == ([1.0, 2.0], [3.0, 4.0])
    assert calls["spearman"] == ([1.0, 2.0], [3.0, 4.0])
    assert calls["simple_returns"] == ([10.0, 11.0],)
    assert calls["cumulative_return"] == ([10.0, 11.0],)
    assert calls["car"] == ([10.0, 11.0], [20.0, 22.0])
    assert calls["rolling_returns"] == ([10.0, 11.0, 12.0], 2)
    assert calls["std_dev"] == ([0.1, 0.2],)
    assert calls["volume_spike"] == ([100.0, 120.0],)
    assert calls["average_true_range"] == ([3.0], [1.0], [2.0])
    assert calls["garman_klass"] == ([3.0], [1.0], [2.0], [2.5])
    assert calls["beta"] == ([0.1, 0.2], [0.05, 0.1])
    assert calls["event_study"] == (
        [10.0, 11.0],
        [1700000000, 1700086400],
        1700000000,
        5,
        30,
    )


def test_load_corr_module_raises_clear_error(monkeypatch) -> None:
    correlation._load_corr_module.cache_clear()

    def fail_import(_name: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(correlation, "import_module", fail_import)

    with pytest.raises(
        correlation.CorrExtensionError, match="corr extension is not available"
    ):
        correlation._load_corr_module()

    correlation._load_corr_module.cache_clear()
