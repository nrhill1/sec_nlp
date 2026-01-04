# src/sec_nlp/pipelines/presets/warranty/__init__.py
"""Warranty data (accruals, etc.) extraction pipeline."""

from .config import WarrantyConfig
from .models import WarrantyInput, WarrantyResult
from .pipeline import WarrantyPipeline

__all__: tuple[str, ...] = (
    "WarrantyInput",
    "WarrantyConfig",
    "WarrantyPipeline",
    "WarrantyResult",
)
