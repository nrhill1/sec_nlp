from __future__ import annotations
import logging
from typing import Any

from pydantic import Field
from sec_nlp.llms.local_llm_base import LocalLLM

logger = logging.getLogger(__name__)


class FlanT5LocalLLM(LocalLLM):
    """
    Local-only FLAN-T5 (seq2seq) wrapper.
    """

    model_name: str = Field(default="google/flan-t5-base")

    def _load_backend(self) -> None:
        from transformers import AutoModelForSeq2SeqLM

        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)

    def _generate(self, prompt: str, gen_kwargs: dict[str, Any]) -> str:
        torch = self._torch
        tok = self._tokenizer

        inputs = tok(prompt, return_tensors="pt")
        if self.device is not None:
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=int(self.max_new_tokens),
                do_sample=bool(self.do_sample),
                temperature=float(self.temperature) if self.do_sample else None,
                top_p=float(self.top_p) if self.do_sample else None,
                eos_token_id=self.eos_token_id,
                **gen_kwargs,
            )
        return tok.decode(outputs[0], skip_special_tokens=True)
