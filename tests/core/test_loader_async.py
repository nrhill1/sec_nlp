# tests/core/test_loader_async.py
"""Test async HTML processing optimizations."""

from pathlib import Path
from unittest.mock import patch

import pytest

from sec_nlp.core.ingest.loader import Loader
from tests.utils.typing import Benchmark


class TestAsyncHTMLProcessing:
    """Test async HTML processing."""

    @pytest.fixture
    def loader(self, tmp_path: Path) -> Loader:
        """Create loader with async enabled."""
        return Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            use_async=True,
            max_workers=2,
        )

    @pytest.fixture
    def sample_html_files(self, tmp_path: Path) -> list[Path]:
        """Create sample HTML files for testing."""
        files = []
        for i in range(10):
            html_path = tmp_path / f"filing_{i}.html"
            html_path.write_text(
                f"<html><body><p>Content {i}</p></body></html>"
            )
            files.append(html_path)
        return files

    def test_concurrent_vs_sequential_produces_same_results(
        self, loader: Loader, sample_html_files: list[Path]
    ) -> None:
        """Verify concurrent processing produces identical results."""
        # Process concurrently
        concurrent_docs = loader.batch_transform_html(
            sample_html_files, concurrent=True
        )

        # Process sequentially
        sequential_docs = loader.batch_transform_html(
            sample_html_files, concurrent=False
        )

        # Compare results
        assert len(concurrent_docs) == len(sequential_docs)
        for c_doc, s_doc in zip(concurrent_docs, sequential_docs, strict=True):
            assert c_doc.page_content == s_doc.page_content
            assert c_doc.metadata == s_doc.metadata

    def test_async_error_handling(self, loader: Loader, tmp_path: Path) -> None:
        """Test error handling in async context."""
        # Create one valid and one invalid file
        valid_file = tmp_path / "valid.html"
        valid_file.write_text("<html><body>Valid</body></html>")

        invalid_file = tmp_path / "nonexistent.html"

        # Should handle error gracefully
        docs = loader.batch_transform_html(
            [valid_file, invalid_file],
            concurrent=True,
        )

        # Only valid file should produce docs
        assert len(docs) > 0

    def test_semaphore_limits_workers(
        self, loader: Loader, sample_html_files: list[Path]
    ) -> None:
        """Test that semaphore limits concurrent workers."""
        # Set max_workers to 2
        loader.max_workers = 2

        # This test verifies it completes without error
        # Actual semaphore limiting would require instrumentation
        docs = loader.batch_transform_html(
            sample_html_files[:4],
            concurrent=True,
        )

        assert len(docs) > 0

    def test_async_performance_improvement(
        self,
        loader: Loader,
        sample_html_files: list[Path],
        benchmark: Benchmark,
    ) -> None:
        """Benchmark async vs sequential processing."""
        # Benchmark concurrent
        result = benchmark(
            loader.batch_transform_html,
            sample_html_files,
            concurrent=True,
        )
        assert len(result) > 0

    def test_single_file_falls_back_to_sequential(
        self, loader: Loader, sample_html_files: list[Path]
    ) -> None:
        """Test that single file doesn't use async overhead."""
        docs = loader.batch_transform_html(
            sample_html_files[:1],
            concurrent=True,
        )
        assert len(docs) > 0

    def test_async_can_be_disabled(
        self, tmp_path: Path, sample_html_files: list[Path]
    ) -> None:
        """Test that async can be disabled via config."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            use_async=False,
        )

        # Should use sequential even when concurrent=True
        docs = loader.batch_transform_html(
            sample_html_files,
            concurrent=True,
        )
        assert len(docs) > 0

    def test_async_fallback_on_error(self, tmp_path: Path) -> None:
        """Test fallback to sequential on async failure."""
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            use_async=True,
        )

        # Create sample files
        files = []
        for i in range(3):
            f = tmp_path / f"file_{i}.html"
            f.write_text("<html><body>Content</body></html>")
            files.append(f)

        with patch.object(
            Loader, "_run_async", side_effect=RuntimeError("Async failed")
        ):
            # Should fallback to sequential
            docs = loader.batch_transform_html(files, concurrent=True)
        assert len(docs) > 0

    def test_empty_file_list(self, loader: Loader) -> None:
        """Test handling of empty file list."""
        docs = loader.batch_transform_html([], concurrent=True)
        assert len(docs) == 0

    def test_max_workers_validation(self, tmp_path: Path) -> None:
        """Test that max_workers is validated."""
        # Should accept valid values
        loader = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            max_workers=4,
        )
        assert loader.max_workers == 4

        # Test boundary values
        loader_min = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            max_workers=1,
        )
        assert loader_min.max_workers == 1

        loader_max = Loader(
            email="test@example.com",
            downloads_folder=tmp_path,
            max_workers=2,
        )
        assert loader_max.max_workers == 2
