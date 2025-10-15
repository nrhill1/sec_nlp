# sec_nlp/llms/local_t5_wrapper.py
from __future__ import annotations

import logging
from typing import Any, Dict

from pydantic import Field
from sec_nlp.llms.local_llm_base import LocalLLM

logger = logging.getLogger(__name__)


class FlanT5LocalLLM(LocalLLM):
    """
    Local-only FLAN-T5 (seq2seq) wrapper.
    """

    model_name: str = Field(default="google/flan-t5-base")

    def _load_backend(self) -> None:
        # Import inside to keep optional deps lazy
        from transformers import AutoModelForSeq2SeqLM

        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)

    def _generate(self, prompt: str, gen_kwargs: Dict[str, Any]) -> str:
        assert (
            self._torch is not None
        ), "Torch not initialized; call after model_post_init"
        assert (
            self._tokenizer is not None
        ), "Tokenizer not initialized; call after model_post_init"
        assert (
            self._model is not None
        ), "Model not initialized; call after model_post_init"

        torch = self._torch
        tok = self._tokenizer
        model = self._model

        # Tokenize to PyTorch tensors
        inputs = tok(prompt, return_tensors="pt")  # type: ignore[call-arg]

        # Move to device if requested
        if self.device is not None:
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

        # Build generate() kwargs without passing Nones
        gen_args: Dict[str, Any] = {
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
        return tok.batch_decode(outputs, skip_special_tokens=True)[0]
