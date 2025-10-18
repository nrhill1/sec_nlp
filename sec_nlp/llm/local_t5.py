# sec_nlp/llms/local_t5_wrapper.py
from __future__ import annotations

import logging
from typing import Any

from pydantic import Field

from .base import LocalLLM

logger = logging.getLogger(__name__)


class FlanT5LocalLLM(LocalLLM):
    """
    Local-only FLAN-T5 (seq2seq) wrapper.
    """

    model_name: str = Field(default="google/flan-t5-base")
    do_sample: bool = Field(default=False, description="Enable sampling")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0, description="Nucleus sampling")s
    device: str | None = Field(default=None, description="Device: 'cpu', 'cuda', 'mps'")
    eos_token_id: int | None = Field(default=None, description="End-of-sequence token ID")

    _torch = PrivateAttr(default=None)
    _tokenizer = PrivateAttr(default=None)
    _model = PrivateAttr(default=None)

    def model_post_init(self, _ctx: Any) -> None:
        try:
            import torch
            from transformers import AutoTokenizer

            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)

            self._load_model()

            if self.device is not None and self._model is not None:
                self._model.to(self.device)

            logger.info("Initialized %s with model %s", self.__class__.__name__, self.model_name)

        except Exception as e:
            logger.error("Failed to initialize FlanT5 model: %s", e)
            raise

    def _load_model(self) -> None:
        from transformers import AutoModelForSeq2SeqLM

        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        logger.info("Loaded FLAN-T5 model: %s", self.model_name)

    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str:
        assert self._torch is not None, "Torch not initialized"
        assert self._tokenizer is not None, "Tokenizer not initialized"
        assert self._model is not None, "Model not initialized"

        torch = self._torch
        tok = self._tokenizer
        model = self._model

        inputs = tok(prompt, return_tensors="pt")  # type: ignore[call-arg]

        if self.device is not None:
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

        gen_args: dict[str, Any] = {
            "max_new_tokens": int(self.max_new_tokens),
            "eos_token_id": self.eos_token_id,
            **gen_kwargs,
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

        # Decode first sequence; batch_decode handles tensors directly
        return str(tok.batch_decode(outputs, skip_special_tokens=True)[0])
