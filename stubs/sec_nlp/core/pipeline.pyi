from .downloader import SECFilingDownloader as SECFilingDownloader
from .preprocessor import Preprocessor as Preprocessor
from _typeshed import Incomplete
from datetime import date
from langchain_core.prompts.base import BasePromptTemplate as BasePromptTemplate
from langchain_core.runnables import Runnable as Runnable
from pathlib import Path
from pydantic import BaseModel, computed_field
from sec_nlp import __version__ as __version__
from sec_nlp.core.config import get_logger as get_logger
from sec_nlp.core.llm.chains import SummarizationInput as SummarizationInput, SummarizationOutput as SummarizationOutput, SummarizationResult as SummarizationResult, build_summarization_runnable as build_summarization_runnable
from sec_nlp.core.types import FilingMode as FilingMode
from typing import Any

logger: Incomplete

def default_prompt_path() -> Path: ...

class Pipeline(BaseModel):
    mode: FilingMode
    start_date: date
    end_date: date
    keyword: str
    model_name: str
    prompt_file: Path
    out_path: Path
    dl_path: Path
    limit: int | None
    max_new_tokens: int
    require_json: bool
    max_retries: int
    batch_size: int
    email: str | None
    pinecone_api_key: str | None
    pinecone_model: str | None
    pinecone_metric: str | None
    pinecone_cloud: str | None
    pinecone_region: str | None
    pinecone_dimension: int | None
    pinecone_namespace: str | None
    dry_run: bool
    @computed_field
    @property
    def keyword_lower(self) -> str: ...
    def model_post_init(self, /, __ctx: Any) -> None: ...
    def reload_prompt(self, path: Path | None = None) -> None: ...
    def run_all(self, symbols: list[str]) -> dict[str, list[Path]]: ...
    def run(self, symbol: str) -> list[Path]: ...
