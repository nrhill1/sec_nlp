from __future__ import annotations

import logging
from typing import Any

from langchain_core import Runnable
from langchain_ollama import OllamaLLM

from pydantic import Field



logger = logging.getLogger(__name__)


def get_ollama_runnable() -> Runnable[str, str]:
    return OllamaLLM(
        model="llama3.1",
        temperature=0.7,
        num_predict=256,
    )
