# src/sec_nlp/pipelines/presets/insider/steps/correlate.py
"""Correlation and alert heuristics for insider transaction data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.ingest.filings import get_filing_date_from_dir
from sec_nlp.core.market import MarketExtensionError, create_market_retriever
from sec_nlp.core.stats.correlation import (
    CorrExtensionError,
    car as corr_car,
    volume_spike as corr_volume_spike,
)

from ..config import InsiderSettings
from ..models import InsiderAlert, InsiderTransaction
from .aggregate import TradeCluster, transaction_direction

MATERIAL_FORMS: tuple[str, ...] = ("8-K", "10-K", "10-Q")


@dataclass(frozen=True)
class MaterialFilingEvent:
    """Material filing date used for pre-filing insider checks."""

    form_type: str
    filing_date: date
    accession_number: str


def _parse_iso_date(value: str | None) -> date | None:
    """Parse iso date."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _owner_name(transaction: InsiderTransaction) -> str:
    """Normalize owner names for grouping and alerting."""
    if transaction.owner_name:
        return transaction.owner_name
    if transaction.owner_cik is not None:
        return str(transaction.owner_cik)
    return "unknown"


def _owner_key(transaction: InsiderTransaction) -> str:
    """Build a stable owner key for clustering activity."""
    if transaction.owner_cik is not None:
        return str(transaction.owner_cik)
    if transaction.owner_name:
        return transaction.owner_name.strip().lower()
    return "unknown"


def _effective_date_range(settings: InsiderSettings) -> tuple[date, date]:
    """Resolve effective date bounds for market-correlation windows."""
    end_date = settings.end_date or date.today()
    start_date = settings.start_date or (
        end_date - timedelta(days=30 * settings.lookback_months)
    )
    return start_date, end_date


def _collect_material_filing_events(
    *, symbol: str, settings: InsiderSettings
) -> list[MaterialFilingEvent]:
    """Collect material filing events."""
    from sec_edgar_downloader import Downloader

    normalized_symbol = symbol.strip().upper()
    start_date, end_date = _effective_date_range(settings)

    downloader = Downloader(
        "SEC NLP Tool", settings.email, str(settings.dl_path)
    )
    for form_type in MATERIAL_FORMS:
        try:
            downloader.get(
                form_type,
                normalized_symbol,
                after=start_date,
                before=end_date,
                limit=24,
                download_details=True,
            )
        except Exception as exc:
            logger.debug(
                "Material filing download failed for %s (%s): %s",
                normalized_symbol,
                form_type,
                exc,
            )

    events: list[MaterialFilingEvent] = []
    for form_type in MATERIAL_FORMS:
        form_dir = (
            settings.dl_path
            / "sec-edgar-filings"
            / normalized_symbol
            / form_type
        )
        if not form_dir.exists():
            continue
        for accession_dir in form_dir.iterdir():
            if not accession_dir.is_dir():
                continue
            filing_date = get_filing_date_from_dir(accession_dir)
            if filing_date is None:
                continue
            if filing_date < start_date or filing_date > end_date:
                continue
            events.append(
                MaterialFilingEvent(
                    form_type=form_type,
                    filing_date=filing_date,
                    accession_number=accession_dir.name,
                )
            )

    unique_by_accession: dict[str, MaterialFilingEvent] = {}
    for event in sorted(
        events, key=lambda item: item.filing_date, reverse=True
    ):
        unique_by_accession[event.accession_number] = event
    return list(unique_by_accession.values())


def _fallback_car(
    symbol_closes: list[float], benchmark_closes: list[float]
) -> float | None:
    """Compute fallback cumulative abnormal return when event study is unavailable."""
    if len(symbol_closes) < 2 or len(benchmark_closes) < 2:
        return None
    first_symbol = symbol_closes[0]
    first_benchmark = benchmark_closes[0]
    if first_symbol == 0 or first_benchmark == 0:
        return None
    symbol_return = (symbol_closes[-1] / first_symbol) - 1.0
    benchmark_return = (benchmark_closes[-1] / first_benchmark) - 1.0
    return symbol_return - benchmark_return


def _fallback_volume_spike(volumes: list[float]) -> float | None:
    """Compute fallback volume spike metrics from quote windows."""
    if not volumes:
        return None
    avg_volume = sum(volumes) / len(volumes)
    if avg_volume == 0:
        return None
    return max(volumes) / avg_volume


def _market_window_metrics(
    *,
    symbol: str,
    event_date: date,
    window_days: int,
) -> tuple[float | None, float | None]:
    """Compute market-window metrics for insider filing events."""
    retriever = create_market_retriever()
    start_date = event_date - timedelta(days=window_days)
    end_date = event_date + timedelta(days=window_days)

    symbol_quotes = retriever.retrieve_range(symbol, (start_date, end_date))
    benchmark_quotes = retriever.retrieve_range("SPY", (start_date, end_date))

    by_ts_symbol = {quote.timestamp: quote for quote in symbol_quotes}
    by_ts_benchmark = {quote.timestamp: quote for quote in benchmark_quotes}
    common_timestamps = sorted(set(by_ts_symbol) & set(by_ts_benchmark))

    aligned_symbol: list[float] = []
    aligned_benchmark: list[float] = []
    aligned_volumes: list[float] = []

    for timestamp in common_timestamps:
        symbol_quote = by_ts_symbol[timestamp]
        benchmark_quote = by_ts_benchmark[timestamp]
        aligned_symbol.append(symbol_quote.close)
        aligned_benchmark.append(benchmark_quote.close)
        aligned_volumes.append(float(symbol_quote.volume))

    abnormal_car: float | None
    try:
        abnormal_car = corr_car(aligned_symbol, aligned_benchmark)
    except CorrExtensionError:
        abnormal_car = _fallback_car(aligned_symbol, aligned_benchmark)

    try:
        volume_spike = corr_volume_spike(aligned_volumes)
    except CorrExtensionError:
        volume_spike = _fallback_volume_spike(aligned_volumes)

    return abnormal_car, volume_spike


def _large_trade_alerts(
    *,
    symbol: str,
    transactions: list[InsiderTransaction],
    threshold_shares: float,
) -> list[InsiderAlert]:
    """Generate alerts for unusually large insider trades."""
    alerts: list[InsiderAlert] = []
    for transaction in transactions:
        shares = transaction.transaction_shares
        if shares is None or abs(shares) < threshold_shares:
            continue

        severity = "high" if abs(shares) >= threshold_shares * 2 else "medium"
        tx_id = transaction.transaction_id
        alert_ids = [tx_id] if tx_id else []
        alerts.append(
            InsiderAlert(
                symbol=symbol,
                alert_type="large_trade",
                severity=severity,
                message=(
                    "Large insider transaction "
                    f"({shares:,.0f} shares) by {_owner_name(transaction)}"
                ),
                transaction_date=transaction.transaction_date,
                accession_number=transaction.accession_number,
                owner_names=[_owner_name(transaction)],
                related_transaction_ids=alert_ids,
            )
        )
    return alerts


def _cluster_alerts(
    *,
    symbol: str,
    clusters: list[TradeCluster],
    threshold: int,
) -> list[InsiderAlert]:
    """Generate alerts for clustered insider activity."""
    alerts: list[InsiderAlert] = []
    for cluster in clusters:
        severity = (
            "high"
            if cluster.unique_owners >= max(threshold + 1, 4)
            else "medium"
        )
        alerts.append(
            InsiderAlert(
                symbol=symbol,
                alert_type="cluster_activity",
                severity=severity,
                message=(
                    f"{cluster.unique_owners} insiders traded between "
                    f"{cluster.start_date} and {cluster.end_date}"
                ),
                transaction_date=cluster.start_date,
                owner_names=cluster.owner_names,
                related_transaction_ids=cluster.transaction_ids,
            )
        )
    return alerts


def _pre_filing_sell_alerts(
    *,
    symbol: str,
    transactions: list[InsiderTransaction],
    material_filings: list[MaterialFilingEvent],
    alert_window_days: int,
) -> list[InsiderAlert]:
    """Generate alerts for sell activity before filing dates."""
    dated_transactions: list[tuple[date, InsiderTransaction]] = []
    for transaction in transactions:
        tx_date = _parse_iso_date(transaction.transaction_date)
        if tx_date is None:
            continue
        dated_transactions.append((tx_date, transaction))

    alerts: list[InsiderAlert] = []
    for filing in material_filings:
        sell_window: list[InsiderTransaction] = []
        for tx_date, transaction in dated_transactions:
            delta_days = (filing.filing_date - tx_date).days
            if delta_days < 0 or delta_days > alert_window_days:
                continue
            if transaction_direction(transaction) < 0:
                sell_window.append(transaction)

        if not sell_window:
            continue

        owners = sorted({_owner_name(tx) for tx in sell_window})
        if len(owners) < 2:
            continue

        tx_ids = sorted(
            {
                tx.transaction_id
                for tx in sell_window
                if tx.transaction_id is not None
            }
        )
        severity = "high" if filing.form_type == "8-K" else "medium"
        alerts.append(
            InsiderAlert(
                symbol=symbol,
                alert_type="pre_filing_sell_cluster",
                severity=severity,
                message=(
                    f"{len(owners)} insiders sold within {alert_window_days}d "
                    f"before {filing.form_type} filed on "
                    f"{filing.filing_date.isoformat()}"
                ),
                transaction_date=filing.filing_date.isoformat(),
                accession_number=filing.accession_number,
                owner_names=owners,
                related_transaction_ids=tx_ids,
            )
        )

    return alerts


def _market_move_alerts(
    *,
    symbol: str,
    transactions: list[InsiderTransaction],
    alert_window_days: int,
) -> tuple[list[InsiderAlert], int]:
    """Generate alerts for significant post-filing market moves."""
    by_date: dict[date, list[InsiderTransaction]] = {}
    for transaction in transactions:
        tx_date = _parse_iso_date(transaction.transaction_date)
        if tx_date is None:
            continue
        by_date.setdefault(tx_date, []).append(transaction)

    alerts: list[InsiderAlert] = []
    evaluated_windows = 0

    for tx_date, txs in sorted(by_date.items()):
        try:
            abnormal_car, volume_spike = _market_window_metrics(
                symbol=symbol,
                event_date=tx_date,
                window_days=alert_window_days,
            )
        except MarketExtensionError:
            logger.debug("Market extension unavailable; skipping market alerts")
            break
        except Exception as exc:
            logger.debug("Market correlation failed for %s %s", tx_date, exc)
            continue

        evaluated_windows += 1

        sell_owners = sorted(
            {_owner_name(tx) for tx in txs if transaction_direction(tx) < 0}
        )
        if abnormal_car is None:
            continue
        if abnormal_car > -0.08:
            continue

        severity = "high" if abnormal_car <= -0.15 else "medium"
        tx_ids = sorted(
            {tx.transaction_id for tx in txs if tx.transaction_id is not None}
        )
        direction_label = "sales" if sell_owners else "trades"
        owner_names = (
            sell_owners
            if sell_owners
            else sorted({_owner_name(tx) for tx in txs})
        )

        market_note = ""
        if volume_spike is not None:
            market_note = f"; volume spike {volume_spike:.2f}x"

        alerts.append(
            InsiderAlert(
                symbol=symbol,
                alert_type="post_trade_market_drop",
                severity=severity,
                message=(
                    f"Market drop after insider {direction_label} on "
                    f"{tx_date.isoformat()} (abnormal CAR {abnormal_car:.3f}"
                    f"{market_note})"
                ),
                transaction_date=tx_date.isoformat(),
                owner_names=owner_names,
                related_transaction_ids=tx_ids,
            )
        )

    return alerts, evaluated_windows


def _dedupe_alerts(alerts: list[InsiderAlert]) -> list[InsiderAlert]:
    """Deduplicate alerts while preserving highest-severity entries."""
    deduped: list[InsiderAlert] = []
    seen: set[tuple[str, str, str | None, tuple[str, ...]]] = set()

    for alert in alerts:
        key = (
            alert.alert_type,
            alert.message,
            alert.transaction_date,
            tuple(sorted(alert.related_transaction_ids)),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(alert)

    return deduped


def correlate_insider_activity(
    *,
    symbol: str,
    transactions: list[InsiderTransaction],
    clusters: list[TradeCluster],
    settings: InsiderSettings,
) -> tuple[list[InsiderAlert], dict[str, int]]:
    """Generate insider alerts by combining trade, filing, and market signals."""
    alerts: list[InsiderAlert] = []

    alerts.extend(
        _large_trade_alerts(
            symbol=symbol,
            transactions=transactions,
            threshold_shares=settings.large_trade_threshold_shares,
        )
    )
    alerts.extend(
        _cluster_alerts(
            symbol=symbol,
            clusters=clusters,
            threshold=settings.alert_cluster_threshold,
        )
    )

    material_filings = _collect_material_filing_events(
        symbol=symbol, settings=settings
    )
    alerts.extend(
        _pre_filing_sell_alerts(
            symbol=symbol,
            transactions=transactions,
            material_filings=material_filings,
            alert_window_days=settings.alert_window_days,
        )
    )

    market_alerts, evaluated_windows = _market_move_alerts(
        symbol=symbol,
        transactions=transactions,
        alert_window_days=settings.alert_window_days,
    )
    alerts.extend(market_alerts)

    deduped = _dedupe_alerts(alerts)
    metadata = {
        "material_filings_considered": len(material_filings),
        "market_windows_evaluated": evaluated_windows,
        "alerts_generated": len(deduped),
    }
    return deduped, metadata
