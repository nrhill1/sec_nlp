# src/sec_nlp/prompts/paths.py
"""Prompt file paths for LLM pipelines."""

from pathlib import Path

PROMPTS_DIR: Path = Path(__file__).parent

ANALYZE_PROMPT_PATH: Path = PROMPTS_DIR / "analyze.yaml"
PROXY_PROMPT_PATH: Path = PROMPTS_DIR / "proxy.yaml"
HOLDINGS_PROMPT_PATH: Path = PROMPTS_DIR / "holdings.yaml"
