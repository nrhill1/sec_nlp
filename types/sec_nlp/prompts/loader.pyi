from pathlib import Path

from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate

from sec_nlp.core.infra.logger import logger as logger

def load_prompt_template(prompt_path: Path) -> BasePromptTemplate: ...
