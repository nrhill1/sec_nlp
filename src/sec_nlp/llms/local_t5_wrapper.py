# src/sec_nlp/llms/local_t5_wrapper.py
import logging
from pydantic import BaseModel, Field, PrivateAttr

logger = logging.getLogger(__name__)


class LocalModelWrapper(BaseModel):
    """
    Minimal local FLAN-T5 wrapper with Pydantic config.
    """

    model_name: str = "google/flan-t5-base"
    max_new_tokens: int = 512
    device: str | None = None

    _tokenizer = PrivateAttr(default=None)
    _model = PrivateAttr(default=None)

    @staticmethod
    def _lazy_imports():
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer  # noqa: F401
            import torch  # noqa: F401

            return True
        except Exception as e:
            logger.error("Transformers/torch not available: %s", e)
            return False

    def model_post_init(self, __ctx):
        if not self._lazy_imports():
            return
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        import torch

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
        if self.device is not None:
            self._model.to(self.device)
        logger.info("Initialized LocalModelWrapper with model %s", self.model_name)

    def invoke(self, prompt: str) -> str:
        if self._model is None or self._tokenizer is None:
            logger.warning("Model not initialized; returning prompt passthrough.")
            return prompt
        import torch

        inputs = self._tokenizer(prompt, return_tensors="pt")
        if self.device is not None:
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model.generate(
                **inputs,
                max_new_tokens=int(self.max_new_tokens),
                do_sample=False,
            )
        text = self._tokenizer.decode(outputs[0], skip_special_tokens=True)
        return text
