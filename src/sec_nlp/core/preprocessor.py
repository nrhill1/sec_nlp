# src/sec_nlp/core/preprocessor.py
from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_community.document_loaders import BSHTMLLoader
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, PrivateAttr, field_validator

from sec_nlp.core.enums import FilingMode
from sec_nlp.core.logging import get_logger

logger = get_logger(__name__)


class Preprocessor(BaseModel):
    """
    Converts SEC filing HTML to cleaned text/markdown chunks.
    """

    downloads_folder: Path
    chunk_size: int = 1000
    chunk_overlap: int = 100
    splitter: str = "default"
    transformer: str = "default"

    _splitter_impl: RecursiveCharacterTextSplitter = PrivateAttr()

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

    def model_post_init(self, __ctx: Any) -> None:
        self._splitter_impl = RecursiveCharacterTextSplitter(
            chunk_size=2000, chunk_overlap=200, add_start_index=True
        )

    def _filing_dir(self, symbol: str, mode: FilingMode) -> Path:
        filing_type = mode.form
        return (
            self.downloads_folder
            / "sec-edgar-filings"
            / symbol.upper()
            / filing_type
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
                "No filings found for %s in mode %s at %s",
                symbol,
                mode.value,
                base.resolve(),
            )

        html_files = sorted(
            base.rglob("*.html"), key=os.path.getmtime, reverse=True
        )
        return html_files[:limit] if limit else html_files

    def transform_html(self, html_path: Path) -> Sequence[Document]:
        if not html_path.exists():
            raise FileNotFoundError("File not found: %s", html_path.resolve())
        loader = BSHTMLLoader(file_path=html_path)
        html_docs = loader.load_and_split(self._splitter_impl)
        finished_docs = self._splitter_impl.transform_documents(html_docs)
        logger.info(
            "Loaded %d transformed documents from %s",
            len(finished_docs),
            html_path.name,
        )
        return finished_docs

    def html_to_text(self, html_path: Path) -> list[str]:
        loader = BSHTMLLoader(
            file_path=html_path, bs_kwargs={"features": "lxml"}
        )
        docs = loader.load_and_split(self._splitter_impl)
        logger.info(
            "Loaded %d raw text chunks from %s", len(docs), html_path.name
        )
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
