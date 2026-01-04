# tests/core/test_loader_optimization_integration.py
"""Integration-style tests for optimized loader paths."""

import time
from pathlib import Path

from langchain_core.documents import Document

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.core.ingest.loader import Loader
from sec_nlp.core.text.filters import SectionFilter, create_item_filter
from tests.utils.performance import measure_duration
from tests.utils.typing import BenchmarkCompare, MemoryTracker


def test_async_vs_sequential_equivalence(
    sample_filings_dir: Path,
    benchmark_compare: BenchmarkCompare,
    track_memory: MemoryTracker,
) -> None:
    """Async batch processing should mirror sequential output."""

    class FakeLoader(Loader):
        def transform_html(
            self,
            html_path: Path,
            keywords: list[str] | None = None,
            section_filter: SectionFilter | None = None,
        ) -> list[Document]:
            text = html_path.read_text()
            time.sleep(0.1)  # simulate heavier work to exercise concurrency
            return [
                Document(
                    page_content=text.strip(),
                    metadata={"source": html_path.name},
                )
            ]

    loader = FakeLoader(
        email="test@example.com",
        downloads_folder=sample_filings_dir,
        use_async=True,
        max_workers=4,
    )
    loader.add_symbol("AAPL")

    html_paths = loader.html_paths_for_symbol(
        symbol="AAPL",
        mode=FilingMode.annual,
        base=sample_filings_dir,
    )

    with track_memory() as metrics:
        async_docs, async_time = measure_duration(
            loader.batch_transform_html,
            html_paths,
            None,
            None,
            True,
        )

    sequential_docs, sequential_time = measure_duration(
        loader.batch_transform_html,
        html_paths,
        None,
        None,
        False,
    )

    assert len(async_docs) == len(sequential_docs)
    assert {d.metadata["source"] for d in async_docs} == {
        d.metadata["source"] for d in sequential_docs
    }
    assert benchmark_compare(async_time, sequential_time, tolerance=0.50)
    assert metrics["peak"] >= 0


def test_streaming_matches_batch_with_filters(
    sample_filings_dir: Path,
) -> None:
    """Streaming path should return the same docs as batch mode with filters applied."""
    section_filter = create_item_filter(["1A"])

    class FakeLoader(Loader):
        def transform_html(
            self,
            html_path: Path,
            keywords: list[str] | None = None,
            section_filter: SectionFilter | None = None,
        ) -> list[Document]:
            text = html_path.read_text()
            docs = [
                Document(
                    page_content=text.strip(),
                    metadata={"source": html_path.name},
                )
            ]
            if keywords:
                docs = self._filter_documents_by_keywords(docs, keywords)
            if section_filter:
                docs = section_filter.filter_documents(docs)
            return docs

    loader = FakeLoader(
        email="test@example.com",
        downloads_folder=sample_filings_dir,
        use_async=True,
        keywords=["risk"],
    )
    loader.add_symbol("AAPL")

    batch_docs = loader.load_documents(
        mode=FilingMode.annual,
        perform_download=False,
        section_filter=section_filter,
    )
    stream_docs = list(
        loader.load_documents_stream(
            mode=FilingMode.annual,
            perform_download=False,
            section_filter=section_filter,
        )
    )

    assert len(batch_docs) == len(stream_docs)
    assert [d.metadata["source"] for d in batch_docs] == [
        d.metadata["source"] for d in stream_docs
    ]
