"""Tests for insider pipeline and step helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from sec_nlp.pipelines.presets.insider.config import InsiderSettings
from sec_nlp.pipelines.presets.insider.models import (
    InsiderAlert,
    InsiderTransaction,
)
from sec_nlp.pipelines.presets.insider.pipeline import InsiderPipeline
from sec_nlp.pipelines.presets.insider.steps.aggregate import (
    build_insider_ledgers,
    compute_net_buy_ratio,
    find_trade_clusters,
)
from sec_nlp.pipelines.presets.insider.steps.correlate import (
    MaterialFilingEvent,
    correlate_insider_activity,
)
from sec_nlp.pipelines.presets.insider.steps.download import (
    DownloadedInsiderFiling,
)


def _transaction(
    *,
    owner_name: str,
    owner_cik: str,
    tx_id: str,
    tx_date: str,
    ownership_type: str,
    shares: float,
    price: float,
) -> InsiderTransaction:
    return InsiderTransaction(
        symbol="ABC",
        accession_number="0000000000-24-000001",
        form_type="4",
        filed_date="2024-01-31",
        transaction_id=tx_id,
        transaction_date=tx_date,
        owner_name=owner_name,
        owner_cik=owner_cik,
        relationship_roles=["officer"],
        transaction_code="P" if ownership_type == "A" else "S",
        ownership_type=ownership_type,
        transaction_shares=shares,
        transaction_price=price,
    )


def test_build_insider_ledgers_and_net_buy_ratio() -> None:
    transactions = [
        _transaction(
            owner_name="Jane Doe",
            owner_cik="0001111111",
            tx_id="t1",
            tx_date="2024-01-10",
            ownership_type="A",
            shares=100.0,
            price=10.0,
        ),
        _transaction(
            owner_name="Jane Doe",
            owner_cik="0001111111",
            tx_id="t2",
            tx_date="2024-01-15",
            ownership_type="D",
            shares=40.0,
            price=12.0,
        ),
        _transaction(
            owner_name="John Roe",
            owner_cik="0002222222",
            tx_id="t3",
            tx_date="2024-01-16",
            ownership_type="A",
            shares=60.0,
            price=8.0,
        ),
    ]

    ledgers = build_insider_ledgers(transactions)
    assert len(ledgers) == 2

    jane = next(
        ledger for ledger in ledgers if ledger.owner_cik == "0001111111"
    )
    assert jane.total_transactions == 2
    assert jane.buy_transactions == 1
    assert jane.sell_transactions == 1
    assert jane.net_shares == 60.0
    assert jane.net_value == 520.0

    net_buy_ratio = compute_net_buy_ratio(transactions)
    assert net_buy_ratio == (2 - 1) / 3


def test_find_trade_clusters_detects_short_window_activity() -> None:
    transactions = [
        _transaction(
            owner_name="Jane Doe",
            owner_cik="0001111111",
            tx_id="t1",
            tx_date="2024-01-10",
            ownership_type="A",
            shares=100.0,
            price=10.0,
        ),
        _transaction(
            owner_name="John Roe",
            owner_cik="0002222222",
            tx_id="t2",
            tx_date="2024-01-12",
            ownership_type="D",
            shares=40.0,
            price=12.0,
        ),
        _transaction(
            owner_name="Ava Poe",
            owner_cik="0003333333",
            tx_id="t3",
            tx_date="2024-01-13",
            ownership_type="A",
            shares=60.0,
            price=8.0,
        ),
    ]

    clusters = find_trade_clusters(
        transactions,
        window_days=5,
        cluster_threshold=3,
    )

    assert len(clusters) == 1
    assert clusters[0].unique_owners == 3
    assert clusters[0].transaction_count == 3


def test_correlate_insider_activity_generates_large_and_prefiling_alerts(
    monkeypatch,
) -> None:
    transactions = [
        _transaction(
            owner_name="Jane Doe",
            owner_cik="0001111111",
            tx_id="t1",
            tx_date="2024-01-10",
            ownership_type="D",
            shares=200_000.0,
            price=10.0,
        ),
        _transaction(
            owner_name="John Roe",
            owner_cik="0002222222",
            tx_id="t2",
            tx_date="2024-01-11",
            ownership_type="D",
            shares=50_000.0,
            price=12.0,
        ),
    ]

    clusters = find_trade_clusters(
        transactions,
        window_days=5,
        cluster_threshold=2,
    )

    filing_event = MaterialFilingEvent(
        form_type="8-K",
        filing_date=date(2024, 1, 13),
        accession_number="0000000000-24-000111",
    )

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.insider.steps.correlate._collect_material_filing_events",
        lambda symbol, settings: [filing_event],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.insider.steps.correlate._market_move_alerts",
        lambda symbol, transactions, alert_window_days: ([], 0),
    )

    settings = InsiderSettings(
        email="test@example.com",
        symbols=["ABC"],
        lookback_months=12,
        alert_window_days=5,
        alert_cluster_threshold=2,
        large_trade_threshold_shares=100_000.0,
    )

    alerts, metadata = correlate_insider_activity(
        symbol="ABC",
        transactions=transactions,
        clusters=clusters,
        settings=settings,
    )

    alert_types = {alert.alert_type for alert in alerts}
    assert "large_trade" in alert_types
    assert "pre_filing_sell_cluster" in alert_types
    assert metadata["material_filings_considered"] == 1


def test_pipeline_run_writes_outputs_with_mocked_steps(
    tmp_path: Path, monkeypatch
) -> None:
    dl_path = tmp_path / "downloads"
    out_path = tmp_path / "outputs"
    config = InsiderSettings(
        email="test@example.com",
        symbols=["ABC"],
        dl_path=dl_path,
        out_path=out_path,
        output_format="all",
        lookback_months=6,
        alert_cluster_threshold=2,
        alert_window_days=5,
        large_trade_threshold_shares=100_000.0,
    )

    filing = DownloadedInsiderFiling(
        symbol="ABC",
        form_type="4",
        accession_number="0000000000-24-000001",
        filing_dir=tmp_path,
        filed_date=date(2024, 1, 31),
    )

    transaction = _transaction(
        owner_name="Jane Doe",
        owner_cik="0001111111",
        tx_id="t1",
        tx_date="2024-01-10",
        ownership_type="A",
        shares=100.0,
        price=10.0,
    )

    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.insider.pipeline.download_insider_filings",
        lambda symbol, settings: [filing],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.insider.pipeline.parse_insider_transactions",
        lambda symbol, filing, parser: [transaction],
    )
    monkeypatch.setattr(
        "sec_nlp.pipelines.presets.insider.pipeline.correlate_insider_activity",
        lambda symbol, transactions, clusters, settings: (
            [
                InsiderAlert(
                    symbol=symbol,
                    alert_type="cluster_activity",
                    severity="medium",
                    message="test alert",
                    owner_names=["Jane Doe"],
                    related_transaction_ids=["t1"],
                )
            ],
            {
                "material_filings_considered": 0,
                "market_windows_evaluated": 0,
                "alerts_generated": 1,
            },
        ),
    )

    pipeline = InsiderPipeline(config=config)
    result = pipeline.run()

    assert result.success is True
    assert result.symbols_processed == 1
    assert result.transactions_processed == 1
    assert result.alerts_generated == 1
    assert len(result.outputs) == 5
    for output_path in result.outputs:
        assert output_path.exists()
