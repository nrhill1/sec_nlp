# src/sec_nlp/pipelines/presets/__init__.py
"""Out of the box pipelines."""

from .analyze import AnalyzeConfig, AnalyzePipeline
from .exb_10 import Exhibit10Config, Exhibit10Pipeline
from .warranty import WarrantyConfig, WarrantyPipeline

__all__: tuple[str, ...] = (
    "AnalyzeConfig",
    "AnalyzePipeline",
    "Exhibit10Config",
    "Exhibit10Pipeline",
    "WarrantyConfig",
    "WarrantyPipeline",
)
