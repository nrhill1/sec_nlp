# sec_nlp/llm/local_t5_wrapper.py
from __future__ import annotations

from typing import Any

from pydantic import Field, PrivateAttr

from sec_nlp.core.config import get_logger
from sec_nlp.core.llm.base import LocalLLMBase

logger = get_logger(__name__)


class FlanT5LocalLLM(LocalLLMBase):
    """
    Local-only FLAN-T5 (seq2seq) wrapper.
    """

    model_name: str = Field(default="google/flan-t5-base")
    do_sample: bool = Field(default=False, description="Enable sampling")
    top_p: float = Field(default=1.0, ge=0.0, le=1.0, description="Nucleus sampling")
    device: str | None = Field(default=None, description="Device: 'cpu', 'cuda', 'mps'")
    eos_token_id: int | None = Field(default=None, description="End-of-sequence token ID")

    _torch = PrivateAttr(default=None)
    _tokenizer = PrivateAttr(default=None)
    _model = PrivateAttr(default=None)

    def model_post_init(self, _ctx: Any) -> None:
        self._load_backend()

    def _load_backend(self) -> None:
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            self._torch = torch
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, use_fast=True)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)

            logger.info("Loaded FLAN-T5 model: %s", self.model_name)

            if self.device is not None:
                self._model.to(self.device)

            logger.info("Initialized %s with model %s", self.__class__.__name__, self.model_name)
        except ImportError as e:
            logger.error("%s: %s was not found -- %s", type(e).__name__, e.name, e)
            raise ImportError from e
        except Exception as e:
            logger.error("%s while initializing FlanT5 -- %s", type(e).__name__, e)
            raise Exception from e

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
