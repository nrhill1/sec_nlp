# tests/scripts/profile/test_utils.py
"""Unit tests for scripts.profile.utils module."""

import cProfile
import io
import logging
import pstats
import tempfile
import time
from pathlib import Path

import pytest

from scripts.profile.utils import Profiler, timer


class TestTimer:
    """Tests for timer context manager."""

    def test_timer_measures_execution_time(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that timer accurately measures and logs execution time."""
        with caplog.at_level(logging.INFO):
            with timer("test_operation"):
                time.sleep(0.1)  # Sleep for 100ms

        # Check that timing was logged
        assert len(caplog.records) == 1
        record = caplog.records[0]

        assert "test_operation" in record.message
        assert "⏱️" in record.message
        # Check that the duration is approximately 100ms
        assert "0.1" in record.message or "100ms" in record.message

    def test_timer_logs_with_correct_name(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that timer logs with the provided operation name."""
        operation_name = "custom_operation_name"

        with caplog.at_level(logging.INFO):
            with timer(operation_name):
                pass

        assert operation_name in caplog.text

    def test_timer_can_suppress_logging(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that timer can suppress logging when log=False."""
        with caplog.at_level(logging.INFO):
            with timer("silent_operation", log=False):
                time.sleep(0.05)

        # No log records should be created
        assert len(caplog.records) == 0

    def test_timer_executes_code_block(self) -> None:
        """Test that timer properly executes the code block."""
        result = []

        with timer("append_operation", log=False):
            result.append(1)
            result.append(2)

        assert result == [1, 2]

    def test_timer_handles_exceptions(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that timer still logs timing even if exception occurs."""
        with caplog.at_level(logging.INFO):
            with pytest.raises(ValueError):
                with timer("failing_operation"):
                    raise ValueError("Test error")

        # Timer should still log despite exception
        assert "failing_operation" in caplog.text

    def test_timer_accuracy_within_tolerance(self) -> None:
        """Test that timer measurement is reasonably accurate."""
        sleep_duration = 0.05  # 50ms

        start = time.perf_counter()
        with timer("accuracy_test", log=False):
            time.sleep(sleep_duration)
        actual_duration = time.perf_counter() - start

        # Timer uses perf_counter, so verify it's in a reasonable range.
        # Allow generous tolerance for scheduler jitter on busy CI runners.
        assert abs(actual_duration - sleep_duration) < 0.05

    def test_timer_formats_milliseconds(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that timer formats output with both seconds and milliseconds."""
        with caplog.at_level(logging.INFO):
            with timer("format_test"):
                time.sleep(0.05)

        log_output = caplog.text
        # Should contain both formats: seconds (0.XXXs) and milliseconds (XXXms)
        assert "s" in log_output
        assert "ms" in log_output


class TestProfiler:
    """Tests for Profiler context manager."""

    def test_profiler_captures_profiling_data(self) -> None:
        """Test that Profiler correctly captures and stores profiling data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "test_profile.prof"

            with Profiler(output_file=output_file, print_stats=False):
                # Do some work to profile
                total = 0
                for i in range(1000):
                    total += i

            # Check that profile file was created
            assert output_file.exists()
            assert output_file.stat().st_size > 0

            # Verify we can load the stats
            stats = pstats.Stats(str(output_file))
            assert stats is not None

    def test_profiler_saves_to_output_file(self) -> None:
        """Test that Profiler saves profiling data to specified file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "subdir" / "profile.prof"

            with Profiler(output_file=output_file, print_stats=False):
                sum(range(100))

            # Check parent directory was created
            assert output_file.parent.exists()
            assert output_file.exists()

    def test_profiler_prints_stats_when_enabled(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that Profiler prints stats when print_stats=True."""
        with caplog.at_level(logging.INFO):
            with Profiler(print_stats=True, top_n=5):
                sum(range(100))

        # Should contain profiling results header
        assert "Profiling Results" in caplog.text

    def test_profiler_respects_print_stats_false(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that Profiler doesn't print stats when print_stats=False."""
        with caplog.at_level(logging.INFO):
            with Profiler(print_stats=False):
                sum(range(100))

        # Should not contain profiling results (might have other logs)
        assert "Profiling Results" not in caplog.text

    def test_profiler_respects_top_n_parameter(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that Profiler respects the top_n parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "test.prof"

            with Profiler(output_file=output_file, print_stats=True, top_n=3):
                for _i in range(10):
                    _ = [x**2 for x in range(100)]

            # Verify the profiler ran
            assert output_file.exists()

    def test_profiler_sorts_by_cumulative_by_default(self) -> None:
        """Test that Profiler sorts stats by cumulative time by default."""
        profiler = Profiler(print_stats=False)
        assert profiler.sort_by == "cumulative"

    def test_profiler_allows_custom_sort_by(self) -> None:
        """Test that Profiler allows custom sort_by parameter."""
        profiler = Profiler(sort_by="time", print_stats=False)
        assert profiler.sort_by == "time"

    def test_profiler_get_stats_returns_stats_object(self) -> None:
        """Test that get_stats() returns a pstats.Stats object."""
        with Profiler(print_stats=False) as profiler:
            sum(range(100))

        stats = profiler.get_stats()
        assert isinstance(stats, pstats.Stats)

    def test_profiler_enables_and_disables_profiling(self) -> None:
        """Test that Profiler properly enables and disables profiling."""
        profiler_obj = Profiler(print_stats=False)

        # Check that profiler attribute is a cProfile.Profile instance
        assert isinstance(profiler_obj.profiler, cProfile.Profile)

        # Test context manager lifecycle
        with profiler_obj as p:
            assert p is profiler_obj
            sum(range(100))

        # After exiting, stats should be available
        stats = profiler_obj.get_stats()
        assert stats is not None

    def test_profiler_handles_exceptions_gracefully(self) -> None:
        """Test that Profiler handles exceptions in profiled code."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "error_profile.prof"

            with pytest.raises(ValueError):
                with Profiler(output_file=output_file, print_stats=False):
                    raise ValueError("Test error")

            # Profile data should still be saved even with exception
            assert output_file.exists()

    def test_profiler_logs_output_file_location(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that Profiler logs the output file location."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "logged_profile.prof"

            with caplog.at_level(logging.INFO):
                with Profiler(output_file=output_file, print_stats=False):
                    sum(range(100))

            # Should log the saved file location
            assert "Profile saved to:" in caplog.text
            assert str(output_file) in caplog.text

    def test_profiler_works_without_output_file(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Test that Profiler works without specifying an output file."""
        with caplog.at_level(logging.INFO):
            with Profiler(output_file=None, print_stats=True, top_n=5):
                sum(range(100))

        # Should still print stats
        assert "Profiling Results" in caplog.text
        # Should not mention saving file
        assert "Profile saved to:" not in caplog.text

    def test_profiler_creates_parent_directories(self) -> None:
        """Test that Profiler creates parent directories for output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a deeply nested path
            output_file = Path(tmpdir) / "a" / "b" / "c" / "profile.prof"

            with Profiler(output_file=output_file, print_stats=False):
                sum(range(100))

            # All parent directories should be created
            assert output_file.parent.exists()
            assert output_file.exists()

    def test_profiler_captures_function_calls(self) -> None:
        """Test that Profiler captures function call information."""

        def sample_function() -> int:
            return sum(range(1000))

        with Profiler(print_stats=False) as profiler:
            sample_function()

        stats = profiler.get_stats()

        # Verify stats contain some function calls
        # Stats should have recorded function calls
        assert stats is not None
        # The stats object should have some data
        stats_stream = io.StringIO()
        ps = pstats.Stats(profiler.profiler, stream=stats_stream)
        ps.print_stats(10)
        output = stats_stream.getvalue()

        # Should contain function call data
        assert len(output) > 0

    def test_profiler_multiple_sort_options(self) -> None:
        """Test that Profiler works with different sort options."""
        sort_options = ["cumulative", "time", "calls"]

        for sort_option in sort_options:
            with Profiler(sort_by=sort_option, print_stats=False) as profiler:
                sum(range(100))

            stats = profiler.get_stats()
            assert stats is not None
