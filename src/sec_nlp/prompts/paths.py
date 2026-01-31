# src/sec_nlp/prompts/paths.py
"""Prompt file paths for LLM pipelines."""

from pathlib import Path

PROMPTS_DIR: Path = Path(__file__).parent

ANALYZE_PROMPT_PATH: Path = PROMPTS_DIR / "analyze" / "default.yaml"
ANALYZE_MARKET_CORRELATION_PROMPT_PATH: Path = (
    PROMPTS_DIR / "analyze" / "market_correlation.yaml"
)
PROXY_PROMPT_PATH: Path = PROMPTS_DIR / "proxy" / "default.yaml"
HOLDINGS_PROMPT_PATH: Path = PROMPTS_DIR / "holdings" / "default.yaml"
