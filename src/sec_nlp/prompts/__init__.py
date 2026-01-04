"""Prompts for LLM pipelines."""

from .loader import load_prompt_template
from .paths import (
    ANALYZE_PROMPT_PATH,
    HOLDINGS_PROMPT_PATH,
    PROXY_PROMPT_PATH,
)

__all__: tuple[str, ...] = (
    "ANALYZE_PROMPT_PATH",
    "HOLDINGS_PROMPT_PATH",
    "PROXY_PROMPT_PATH",
    "load_prompt_template",
)
