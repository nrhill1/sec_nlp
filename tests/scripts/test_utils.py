# tests/scripts/test_utils.py
"""Unit tests for scripts.utils module."""

import sys
import tomllib
from pathlib import Path

import pytest

from scripts import utils


class TestFindProjectRoot:
    """Tests for find_project_root function."""

    def test_finds_project_root_from_scripts_dir(self) -> None:
        """Test that find_project_root correctly identifies the project root."""
        root = utils.find_project_root()

        # Should return a Path object
        assert isinstance(root, Path)

        # Should contain pyproject.toml
        assert (root / "pyproject.toml").exists()

        # Should be the sec-nlp project
        with open(root / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
            assert data.get("project", {}).get("name") == "sec-nlp"

        # Should contain expected directories
        assert (root / "src").exists()
        assert (root / "src" / "scripts").exists()
        assert (root / "tests").exists()

    def test_finds_project_root_idempotent(self) -> None:
        """Test that multiple calls return the same root."""
        root1 = utils.find_project_root()
        root2 = utils.find_project_root()

        assert root1 == root2
        assert root1.resolve() == root2.resolve()


class TestGetSrcPath:
    """Tests for get_src_path function."""

    def test_returns_src_directory(self) -> None:
        """Test that get_src_path returns the correct src directory."""
        src_path = utils.get_src_path()

        assert isinstance(src_path, Path)
        assert src_path.name == "src"
        assert src_path.exists()
        assert (src_path / "sec_nlp").exists()

    def test_src_path_is_child_of_project_root(self) -> None:
        """Test that src path is a child of project root."""
        root = utils.find_project_root()
        src = utils.get_src_path()

        assert src.parent == root
        assert src == root / "src"


class TestSetupImportPath:
    """Tests for setup_import_path function."""

    def test_adds_src_to_sys_path(self) -> None:
        """Test that setup_import_path correctly adds src directory to sys.path."""
        # Store original sys.path
        original_path = sys.path.copy()

        try:
            # Remove src path if it exists
            src_path = str(utils.get_src_path())
            sys.path = [p for p in sys.path if p != src_path]

            # Call setup_import_path
            utils.setup_import_path()

            # Verify src path was added
            assert src_path in sys.path
            assert sys.path[0] == src_path  # Should be first in path

        finally:
            # Restore original sys.path
            sys.path = original_path

    def test_does_not_duplicate_src_in_path(self) -> None:
        """Test that setup_import_path doesn't add duplicate entries."""
        # Store original sys.path
        original_path = sys.path.copy()

        try:
            # Call setup_import_path twice
            utils.setup_import_path()
            initial_length = len(sys.path)
            src_path = str(utils.get_src_path())
            count_before = sys.path.count(src_path)

            utils.setup_import_path()

            # Verify no duplicate was added
            assert len(sys.path) == initial_length
            assert sys.path.count(src_path) == count_before

        finally:
            # Restore original sys.path
            sys.path = original_path

    def test_allows_importing_sec_nlp_after_setup(self) -> None:
        """Test that sec_nlp can be imported after setup_import_path."""
        # Store original sys.path
        original_path = sys.path.copy()

        try:
            # Setup import path
            utils.setup_import_path()

            # Should be able to import sec_nlp
            import sec_nlp

            assert sec_nlp is not None

        finally:
            # Restore original sys.path
            sys.path = original_path

    def test_inserts_at_beginning_of_path(self) -> None:
        """Test that src is inserted at the beginning of sys.path."""
        original_path = sys.path.copy()

        try:
            # Remove src from path
            src_path = str(utils.get_src_path())
            sys.path = [p for p in sys.path if p != src_path]

            utils.setup_import_path()

            # Should be at index 0
            assert sys.path[0] == src_path

        finally:
            sys.path = original_path


class TestGetProjectInfo:
    """Tests for get_project_info function."""

    def test_returns_project_metadata(self) -> None:
        """Test that get_project_info returns correct metadata."""
        info = utils.get_project_info()

        assert isinstance(info, dict)
        assert "name" in info
        assert "version" in info
        assert "description" in info

        assert info["name"] == "sec-nlp"
        assert len(info["version"]) > 0
        assert len(info["description"]) > 0


class TestCachedFunctions:
    """Tests for cached helper functions."""

    def test_get_cached_project_root_returns_same_object(self) -> None:
        """Test that cached project root returns the same object."""
        # Reset cache
        utils._PROJECT_ROOT_CACHE = None

        root1 = utils.get_cached_project_root()
        root2 = utils.get_cached_project_root()

        assert root1 is root2  # Same object, not just equal
        assert root1 == utils.find_project_root()

    def test_get_cached_src_path_returns_same_object(self) -> None:
        """Test that cached src path returns the same object."""
        # Reset cache
        utils._SRC_PATH_CACHE = None

        src1 = utils.get_cached_src_path()
        src2 = utils.get_cached_src_path()

        assert src1 is src2  # Same object, not just equal
        assert src1 == utils.get_src_path()

    def test_cached_functions_improve_performance(self) -> None:
        """Test that cached functions avoid repeated filesystem operations."""
        import time

        # Reset caches
        utils._PROJECT_ROOT_CACHE = None
        utils._SRC_PATH_CACHE = None

        # First call (uncached)
        start = time.perf_counter()
        utils.get_cached_project_root()
        first_duration = time.perf_counter() - start

        # Second call (cached)
        start = time.perf_counter()
        utils.get_cached_project_root()
        second_duration = time.perf_counter() - start

        # Cached call should be significantly faster
        # (this might be flaky on slow systems, but generally holds)
        assert second_duration < first_duration or second_duration < 0.001
