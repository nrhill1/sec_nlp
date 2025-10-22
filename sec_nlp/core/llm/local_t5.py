# sec_nlp/core/llm/local_t5.py
from __future__ import annotations

from typing import Any

from langchain_core.callbacks.manager import CallbackManagerForLLMRun
from langchain_core.language_models.llms import LLM
from pydantic import Field, PrivateAttr

from sec_nlp.core.config import get_logger

logger = get_logger(__name__)


class FlanT5LocalLLM(LLM):
    """
    Local-only FLAN-T5 (seq2seq) wrapper for LangChain.
    Inherits from LLM to provide full compatibility with LangChain ecosystem.
    """

    model_name: str = Field(default="google/flan-t5-base", description="HuggingFace model ID")
    max_new_tokens: int = Field(default=512, description="Maximum number of tokens to generate")
    do_sample: bool = Field(default=False, description="Enable sampling")
    temperature: float = Field(default=0.0, ge=0.0, description="Sampling temperature")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0, description="Nucleus sampling")
    device: str | None = Field(default=None, description="Device: 'cpu', 'cuda', 'mps'")
    eos_token_id: int | None = Field(default=None, description="End-of-sequence token ID")

    _torch: Any = PrivateAttr(default=None)
    _tokenizer: Any = PrivateAttr(default=None)
    _model: Any = PrivateAttr(default=None)

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the model and load weights."""
        super().__init__(**kwargs)
        self._initialize_model()

    def _initialize_model(self) -> None:
        """Load the model and tokenizer."""
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)  # type: ignore[no-untyped-call]
            self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)

            if self.device is not None and self._model is not None:
                self._model.to(self.device)

            logger.info("Initialized %s with model %s", self.__class__.__name__, self.model_name)

        except Exception as e:
            logger.error("Failed to initialize FlanT5 model: %s", e)
            raise

    @property
    def _llm_type(self) -> str:
        """Return type of LLM."""
        return "flan-t5"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        """Get the identifying parameters."""
        return {
            "model_name": self.model_name,
            "max_new_tokens": self.max_new_tokens,
            "do_sample": self.do_sample,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "device": self.device,
        }

    def _call(
        self,
        prompt: str,
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        """Run the LLM on the given prompt.

        Args:
            prompt: The prompt to generate from
            stop: Optional list of stop sequences
            run_manager: Optional callback manager
            **kwargs: Additional generation arguments

        Returns:
            Generated text string
        """
        if self._model is None or self._tokenizer is None or self._torch is None:
            raise RuntimeError("Model not initialized. Call _initialize_model() first.")

        # Generate text
        torch = self._torch
        tok = self._tokenizer
        model = self._model

        # Tokenize input
        inputs = tok(prompt, return_tensors="pt")

        if self.device is not None:
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Prepare generation arguments
        gen_args: dict[str, Any] = {
            "max_new_tokens": int(self.max_new_tokens),
            "eos_token_id": self.eos_token_id,
            **kwargs,
        }

        if self.do_sample:
            gen_args.update(
                do_sample=True,
                temperature=float(self.temperature),
                top_p=float(self.top_p),
            )
        else:
            gen_args["do_sample"] = False

        # Generate
        with torch.no_grad():
            outputs = model.generate(**inputs, **gen_args)

        # Decode and return first sequence
        result = tok.batch_decode(outputs, skip_special_tokens=True)[0]
        return str(result)
