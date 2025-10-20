from _typeshed import Incomplete
from langchain_core.runnables import Runnable as Runnable
from sec_nlp.core.config import get_logger as get_logger

logger: Incomplete

def build_ollama_llm(model_name: str, base_url: str | None = None, temperature: float = 0.1, **kwargs) -> Runnable[str, str]: ...
