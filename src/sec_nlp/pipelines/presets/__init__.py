# src/sec_nlp/pipelines/presets/__init__.py
"""Out of the box pipelines."""

from .analyze import AnalyzeConfig, AnalyzePipeline
from .exb import ExhibitConfig, ExhibitPipeline
from .financials import FinancialsPipeline, FinancialsSettings
from .insider import InsiderPipeline, InsiderSettings
from .warranty import WarrantyConfig, WarrantyPipeline

__all__: tuple[str, ...] = (
    "AnalyzeConfig",
    "AnalyzePipeline",
    "ExhibitConfig",
    "ExhibitPipeline",
    "FinancialsPipeline",
    "FinancialsSettings",
    "InsiderPipeline",
    "InsiderSettings",
    "WarrantyConfig",
    "WarrantyPipeline",
)
