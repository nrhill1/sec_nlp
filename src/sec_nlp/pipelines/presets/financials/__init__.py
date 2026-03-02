# src/sec_nlp/pipelines/presets/financials/__init__.py
"""Financial statement extraction pipeline."""

from .config import FinancialsSettings
from .models import FinancialFact, FinancialsResult, FinancialStatement
from .pipeline import FinancialsPipeline

__all__: tuple[str, ...] = (
    "FinancialFact",
    "FinancialStatement",
    "FinancialsPipeline",
    "FinancialsResult",
    "FinancialsSettings",
)
