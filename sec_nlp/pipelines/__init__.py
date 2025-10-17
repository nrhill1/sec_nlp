# ==============================================================================
# sec_nlp/pipelines/__init__.py
# ==============================================================================
"""SEC filing processing pipelines."""

from .pipeline import Pipeline, _default_prompt_path

__all__: list[str] = ["Pipeline", "_default_prompt_path"]
