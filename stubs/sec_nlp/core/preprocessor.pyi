from _typeshed import Incomplete
from langchain_core.documents import Document as Document
from langchain_core.documents.transformers import BaseDocumentTransformer as BaseDocumentTransformer
from langchain_text_splitters.base import TextSplitter as TextSplitter
from pathlib import Path
from pydantic import BaseModel
from sec_nlp.core.config import get_logger as get_logger
from sec_nlp.core.types import FilingMode as FilingMode

logger: Incomplete

class Preprocessor(BaseModel):
    downloads_folder: Path
    chunk_size: int
    chunk_overlap: int
    splitter: str
    transformer: str
    def model_post_init(self, /, __ctx) -> None: ...
    def html_paths_for_symbol(self, symbol: str, mode: FilingMode = ..., limit: int | None = None) -> list[Path]: ...
    def transform_html(self, html_path: Path) -> list[Document]: ...
    def html_to_text(self, html_path: Path) -> list[str]: ...
    def batch_transform_html(self, html_paths: list[Path]) -> list[Document]: ...
