from _typeshed import Incomplete
from langchain_huggingface import HuggingFacePipeline
from sec_nlp.core.config import get_logger as get_logger

logger: Incomplete

def build_hf_pipeline(model_name: str) -> HuggingFacePipeline: ...
