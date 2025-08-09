# utils/parse/preprocessor.py
import os
from pathlib import Path
from typing import List, Sequence, Optional

from langchain_core.documents import Document
from langchain_community.document_loaders import BSHTMLLoader
from langchain_core.documents.transformers import BaseDocumentTransformer
from langchain_community.document_transformers import MarkdownifyTransformer
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_text_splitters.base import TextSplitter


class PreProcessor:
    """
    Convert HTML SEC filings into Markdown or raw text, chunked for NLP use.

    Args:
        downloads_folder (Path): Base folder containing 'sec-edgar-filings/<SYMBOL>/(10-K|10-Q)'
        chunk_size (int): Max characters per chunk
        chunk_overlap (int): Overlap between chunks
        splitter (TextSplitter): Optional custom text splitter
        transformer (BaseDocumentTransformer): Optional document transformer (default: Markdownify)
    """

    SUPPORTED_MODES = {
        "annual": "10-K",
        "quarterly": "10-Q",
    }

    def __init__(
        self,
        downloads_folder: Path,
        chunk_size: int = 1000,
        chunk_overlap: int = 100,
        splitter: Optional[TextSplitter] = None,
        transformer: Optional[BaseDocumentTransformer] = None,
    ):
        self._filings_folder = downloads_folder / "sec-edgar-filings"
        self._html_splitter = splitter or RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

        self._transformer = transformer or MarkdownifyTransformer()

    def _filing_dir(self, symbol: str, mode: str) -> Path:
        mode = mode.lower()
        if mode not in self.SUPPORTED_MODES:
            raise ValueError(
                f"Unsupported mode: {mode}. Must be one of: {list(self.SUPPORTED_MODES)}")
        filing_type = self.SUPPORTED_MODES[mode]
        return self._filings_folder / symbol / filing_type

    def html_paths_for_symbol(
        self,
        symbol: str,
        mode: str = "annual",
        limit: Optional[int] = None
    ) -> List[Path]:
        """
        List HTML filing paths for a given symbol & mode (10-K or 10-Q),
        sorted by most recently modified.

        Args:
            symbol (str): Stock ticker
            mode (str): 'annual' or 'quarterly'
            limit (Optional[int]): Return only the N most recent filings

        Returns:
            List[Path]: File paths to matching HTML documents
        """
        if mode not in self.SUPPORTED_MODES:
            raise ValueError(
                f"Unsupported mode: {mode}. Must be one of: {list(self.SUPPORTED_MODES)}")

        dir_path = self._filing_dir(symbol, mode)
        if not dir_path.exists():
            raise FileNotFoundError(
                f"No filings found for {symbol} in mode {mode}")

        html_files = sorted(dir_path.rglob("*.html"),
                            key=os.path.getmtime, reverse=True)
        return html_files[:limit] if limit else html_files

    def transform_html(self, html_path: Path) -> Sequence[Document]:
        """
        Converts an HTML filing into Markdown chunks using the configured transformer.

        Args:
            html_path (Path): Path to an HTML filing

        Returns:
            Sequence[Document]: Transformed LangChain Documents
        """
        if not html_path.exists():
            raise FileNotFoundError(f"File not found: {html_path}")
        loader = BSHTMLLoader(file_path=html_path,
                              bs_kwargs={"features": "xml"})
        html_docs = loader.load_and_split(self._html_splitter)
        finished_docs = self._transformer.transform_documents(html_docs)
        print(
            f"Loaded {len(finished_docs)} transformed documents from {html_path.name}")
        return finished_docs

    def html_to_text(self, html_path: Path) -> List[str]:
        """
        Loads an HTML filing and returns raw chunked text (not transformed).

        Args:
            html_path (Path): Path to the HTML document

        Returns:
            List[str]: Raw page_content strings from chunked HTML
        """
        loader = BSHTMLLoader(file_path=html_path,
                              bs_kwargs={"features": "xml"})
        docs = loader.load_and_split(self._html_splitter)
        print(f"Loaded {len(docs)} raw text chunks from {html_path.name}")
        return [doc.page_content for doc in docs]
