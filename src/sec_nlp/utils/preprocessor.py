# sec_nlp/utils/preprocessor.py
from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel, PrivateAttr, field_validator

from langchain_core.documents import Document
from langchain_community.document_loaders import BSHTMLLoader
from langchain_community.document_transformers import MarkdownifyTransformer
from langchain_core.documents.transformers import BaseDocumentTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters.base import TextSplitter

from sec_nlp.types import FilingMode

logger = logging.getLogger(__name__)


class Preprocessor(BaseModel):
    """
    Converts SEC filing HTML to cleaned text/markdown chunks.
    """

    downloads_folder: Path
    chunk_size: int = 1000
    chunk_overlap: int = 100
    splitter: str = "default"
    transformer: str = "default"

    _splitter_impl: TextSplitter = PrivateAttr()
    _transformer_impl: BaseDocumentTransformer = PrivateAttr()

    @field_validator("downloads_folder")
    @classmethod
    def _ensure_root(cls, v: Path) -> Path:
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator("chunk_size", "chunk_overlap")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("must be positive")
        return v

    def model_post_init(self, __ctx) -> None:
        self._splitter_impl = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )
        self._transformer_impl = MarkdownifyTransformer()

    def _filing_dir(self, symbol: str, mode: FilingMode) -> Path:
        filing_type = mode.form
        return (
            self.downloads_folder / "sec-edgar-filings" / symbol.upper() / filing_type
        )

    def html_paths_for_symbol(
        self,
        symbol: str,
        mode: FilingMode = FilingMode.annual,
        limit: int | None = None,
    ) -> list[Path]:
        base = self._filing_dir(symbol, mode)
        if not base.exists():
            raise FileNotFoundError(
                "No filings found for %s in mode %s at %s"
                % (symbol, mode.value, base.resolve())
            )
        html_files = sorted(base.rglob("*.html"), key=os.path.getmtime, reverse=True)
        return html_files[:limit] if limit else html_files

    def transform_html(self, html_path: Path) -> list[Document]:
        if not html_path.exists():
            raise FileNotFoundError("File not found: %s" % html_path.resolve())
        loader = BSHTMLLoader(file_path=html_path, bs_kwargs={"features": "lxml"})
        html_docs = loader.load_and_split(self._splitter_impl)
        finished_docs = self._transformer_impl.transform_documents(html_docs)
        logger.info(
            "Loaded %d transformed documents from %s",
            len(finished_docs),
            html_path.name,
        )
        return finished_docs

    def html_to_text(self, html_path: Path) -> list[str]:
        loader = BSHTMLLoader(file_path=html_path, bs_kwargs={"features": "lxml"})
        docs = loader.load_and_split(self._splitter_impl)
        logger.info("Loaded %d raw text chunks from %s", len(docs), html_path.name)
        return [doc.page_content for doc in docs]

    def batch_transform_html(self, html_paths: list[Path]) -> list[Document]:
        all_docs: list[Document] = []
        for path in html_paths:
            all_docs.extend(self.transform_html(path))
        logger.info(
            "Transformed a total of %d documents from %d files.",
            len(all_docs),
            len(html_paths),
        )
        return all_docs
