# src/sec_nlp/prompts/loader.py
"""Prompt loading helpers for LLM pipelines."""

from __future__ import annotations

from pathlib import Path

from langchain_core.prompts.base import BasePromptTemplate
from langchain_core.prompts.loading import load_prompt

from sec_nlp.core.infra.logger import logger


def load_prompt_template(prompt_path: Path) -> BasePromptTemplate:
    """Load a LangChain prompt template from disk."""

    try:
        template = load_prompt(str(prompt_path))
    except Exception as exc:
        raise ValueError(f"Failed to load prompt from {prompt_path}") from exc

    logger.info("Loaded prompt from: %s", prompt_path)
    return template
