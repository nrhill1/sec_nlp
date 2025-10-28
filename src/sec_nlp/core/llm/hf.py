# sec_nlp/core/llm/hf.py
from __future__ import annotations

from langchain_huggingface import HuggingFacePipeline

from sec_nlp.core.config import get_logger

logger = get_logger(__name__)


def build_hf_pipeline(
    model_name: str,
) -> HuggingFacePipeline:
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, pipeline

        tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)  # type: ignore[no-untyped-call]
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)

        hf_pipeline = HuggingFacePipeline(pipeline=pipe)

        logger.info("Initialized HuggingFace Pipeline with model %s", model_name)

        return hf_pipeline

    except ImportError as e:
        raise ImportError(
            f"{type(e).__name__}: HuggingFace Pipeline failed to initialize -- Attempted to import {e.name} from location {e.path}"
        ) from e
