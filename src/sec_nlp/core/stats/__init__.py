"""Statistical utilities backed by the Rust `corr` extension."""

from .correlation import (
    CorrExtensionError,
    average_true_range,
    beta,
    car,
    cumulative_return,
    event_study,
    garman_klass,
    pearson,
    rolling_returns,
    simple_returns,
    spearman,
    std_dev,
    volume_spike,
)
from .cross_filing import FilingTrend, cross_filing_trend
from .event_study import EventStudyResult, run_event_study
from .sector import SectorCorrelation, sector_correlation

__all__ = (
    "CorrExtensionError",
    "EventStudyResult",
    "FilingTrend",
    "SectorCorrelation",
    "average_true_range",
    "beta",
    "car",
    "cross_filing_trend",
    "cumulative_return",
    "event_study",
    "garman_klass",
    "pearson",
    "rolling_returns",
    "simple_returns",
    "spearman",
    "sector_correlation",
    "std_dev",
    "volume_spike",
    "run_event_study",
)
