# llms/local_t5_wrapper.py
from transformers import pipeline


class LocalT5Wrapper:
    def __init__(self, model_name: str = "google/flan-t5-small",
                 max_new_tokens: int = 512):
        self.pipe = pipeline("text2text-generation", model=model_name)
        self.max_new_tokens = max_new_tokens

    def invoke(self, prompt: str) -> str:
        result = self.pipe(prompt, max_new_tokens=self.max_new_tokens)
        return result[0]["generated_text"]
