"""Tests for events pipeline and step helpers."""

from __future__ import annotations

import json
from pathlib import Path

from sec_nlp.core.stats.event_study import EventStudyResult
from sec_nlp.pipelines.presets.events import EventsPipeline, EventsSettings
from sec_nlp.pipelines.presets.events.models import DetectedEvent
from sec_nlp.pipelines.presets.events.steps.scan import scan_events_for_symbol
from sec_nlp.pipelines.presets.events.steps.score import score_event_impacts


def _write_filing_fixture(
    *,
    base: Path,
    symbol: str,
    accession: str,
    filed_as_of: str,
    html_name: str,
    html_body: str,
) -> Path:
    accession_dir = base / "sec-edgar-filings" / symbol / "8-K" / accession
    accession_dir.mkdir(parents=True, exist_ok=True)
    submission = accession_dir / "full-submission.txt"
    submission.write_text(
        f"FILED AS OF DATE:\t\t{filed_as_of}\n",
        encoding="utf-8",
    )
    html_path = accession_dir / html_name
    html_path.write_text(html_body, encoding="utf-8")
    return html_path


def test_scan_events_for_symbol_extracts_item_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    symbol = "ABC"
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    _write_filing_fixture(
        base=dl_path,
        symbol=symbol,
        accession="0000000000-26-000001",
        filed_as_of="20260201",
        html_name="abc_8k.html",
        html_body="Item 5.02 Departure of Director or Certain Officers",
    )

    settings = EventsSettings(
        email="test@example.com",
        symbols=[symbol],
        dl_path=dl_path,
        out_path=out_path,
        include_news_context=False,
        include_market_context=False,
        limit=10,
    )

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.events.steps.scan.download_filings",
        lambda **_: {symbol: {"downloaded": 0}},
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.events.steps.scan.detect_events",
        lambda text: [],
    )

    events, downloaded, scanned = scan_events_for_symbol(
        symbol=symbol,
        settings=settings,
    )

    assert downloaded == 0
    assert scanned == 1
    assert len(events) == 1
    assert events[0].event_type == "executive_change"
    assert events[0].filing_items == ["5.02"]


def test_score_event_impacts_attaches_metrics(monkeypatch) -> None:
    settings = EventsSettings(
        email="test@example.com",
        symbols=["ABC"],
        include_news_context=False,
        include_market_context=True,
        significance_threshold=0.05,
    )
    events = [
        DetectedEvent(
            symbol="ABC",
            event_type="executive_change",
            event_date="2026-01-15",
            filing_accession="0000000000-26-000001",
            filing_items=["5.02"],
        )
    ]

    def _fake_run_event_study(**kwargs):
        post_window = int(kwargs["post_window"])
        if post_window <= 5:
            return EventStudyResult(
                symbol="ABC",
                event_date="2026-01-15",
                car_pre=0.0,
                car_post=0.01,
                t_stat=1.2,
                p_value=0.08,
                volume_spike=1.1,
            )
        return EventStudyResult(
            symbol="ABC",
            event_date="2026-01-15",
            car_pre=0.0,
            car_post=0.03,
            t_stat=2.4,
            p_value=0.02,
            volume_spike=1.8,
        )

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.events.steps.score.run_event_study",
        _fake_run_event_study,
    )

    scored, scored_count = score_event_impacts(
        symbol="ABC",
        events=events,
        settings=settings,
    )

    assert scored_count == 1
    assert scored[0].impact is not None
    assert scored[0].impact.car_5d == 0.01
    assert scored[0].impact.car_30d == 0.03
    assert scored[0].impact.significant is True


def test_events_pipeline_run_writes_outputs_with_mocked_steps(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config = EventsSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=tmp_path / "downloads",
        out_path=tmp_path / "outputs",
        output_format="all",
    )

    scanned_events = [
        DetectedEvent(
            symbol="ABC",
            event_type="executive_change",
            event_date="2026-01-15",
            filing_accession="0000000000-26-000001",
            filing_items=["5.02"],
            text_snippet="Officer departure",
        )
    ]

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.events.pipeline.scan_events_for_symbol",
        lambda symbol, settings: (scanned_events, 1, 1),
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.events.pipeline.enrich_events_with_news",
        lambda symbol, events, settings: (events, 0),
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.events.pipeline.score_event_impacts",
        lambda symbol, events, settings: (events, 0),
    )

    pipeline = EventsPipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert result.symbols_processed == 1
    assert result.events_detected == 1
    assert len(result.outputs) == 3

    json_path = next(path for path in result.outputs if path.suffix == ".json")
    payload = json.loads(json_path.read_text())
    expected_short_id = config.short_id if config.short_id > 0 else None
    assert payload["run_id"] == str(config.run_id)
    assert payload["run_short_id"] == expected_short_id
    assert isinstance(payload["run_timestamp"], str)

    csv_path = next(path for path in result.outputs if path.suffix == ".csv")
    lines = csv_path.read_text().splitlines()
    assert lines[0].startswith("# run_timestamp:")
    assert lines[1].startswith("# run_short_id:")
    assert lines[2].startswith("# run_id:")
    assert lines[3].startswith("# run_short_id_display:")
    assert lines[4].startswith("symbol,event_date")
