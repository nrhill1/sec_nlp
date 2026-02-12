# src/sec_nlp/pipelines/observability/profiling.py
"""Lightweight profiling helpers automatically applied to pipeline runs."""

from __future__ import annotations

import os
import time
import tracemalloc
from collections.abc import Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from types import TracebackType
from uuid import UUID

from scripts.profile.utils import Profiler
from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.types import JsonDict, JsonObject


class PipelineProfiler(AbstractContextManager):
    """Capture CPU and memory profiling data for a pipeline run."""

    def __init__(
        self,
        pipeline_name: str = "pipeline",
        run_id: UUID | None = None,
        output_root: Path | None = None,
        tracemalloc_frames: int = 8,
    ) -> None:
        self.pipeline_name = pipeline_name
        self.run_id = (
            str(run_id)
            if run_id is not None
            else time.strftime("%Y%m%dT%H%M%S")
        )
        self.output_root = (
            Path(output_root) if output_root is not None else Path("profiling")
        ).resolve()
        self.profile_dir = self.output_root / self.pipeline_name
        self.profile_dir.mkdir(parents=True, exist_ok=True)

        self.profile_path = (
            self.profile_dir / f"{self.pipeline_name}_{self.run_id}.prof"
        )
        self.tracemalloc_path = (
            self.profile_dir
            / f"{self.pipeline_name}_{self.run_id}_tracemalloc.snap"
        )

        self.tracemalloc_frames: int = tracemalloc_frames
        self._cpu_profiler: Profiler | None = None
        self._tracemalloc_started = False
        self._tracemalloc_captured = False
        self._memory_samples: list[float] = []
        self._memory_failed = False
        self._tracemalloc_top: list[str] = []

    # Context manager protocol -------------------------------------------------
    def __enter__(self) -> PipelineProfiler:
        self._cpu_profiler = Profiler(
            output_file=self.profile_path, print_stats=True, top_n=30
        )
        self._cpu_profiler.__enter__()
        self._start_tracemalloc()
        self.sample_memory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Always attempt to capture ending stats even if an exception is raised
        self.sample_memory()
        if self._cpu_profiler:
            self._cpu_profiler.__exit__(exc_type, exc, tb)
        self._finalize_tracemalloc()
        self._log_summary()

    # Memory -------------------------------------------------------------------
    def sample_memory(self) -> None:
        """Record current RSS in MB if psutil is available."""
        if self._memory_failed:
            return

        try:
            import psutil

            rss_mb = psutil.Process(os.getpid()).memory_info().rss / (
                1024 * 1024
            )
            self._memory_samples.append(rss_mb)
        except Exception as exc:  # pragma: no cover - best effort
            self._memory_failed = True
            logger.debug("Memory sampling unavailable: %s", exc)

    @property
    def peak_memory_mb(self) -> float | None:
        """Get peak sampled memory in MB."""
        if not self._memory_samples:
            return None
        return max(self._memory_samples)

    # Tracemalloc --------------------------------------------------------------
    def _start_tracemalloc(self) -> None:
        if self.tracemalloc_frames <= 0:
            return

        try:
            tracemalloc.start(self.tracemalloc_frames)
            self._tracemalloc_started = True
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug("Failed to start tracemalloc: %s", exc)

    def _finalize_tracemalloc(self) -> None:
        if not self._tracemalloc_started or not tracemalloc.is_tracing():
            return

        try:
            snapshot = tracemalloc.take_snapshot()
            snapshot.dump(str(self.tracemalloc_path))
            self._tracemalloc_captured = True
            top = snapshot.statistics("lineno")[:8]
            top_entries: list[str] = []
            for stat in top:
                frame = stat.traceback[0]
                location = f"{Path(frame.filename).name}:{frame.lineno}"
                size_mb = stat.size / (1024 * 1024)
                top_entries.append(
                    f"{size_mb:.2f} MB ({stat.count} allocs) at {location}"
                )
            self._tracemalloc_top = top_entries
        except Exception as exc:  # pragma: no cover - best effort
            logger.debug("Failed to capture tracemalloc snapshot: %s", exc)
        finally:
            try:
                tracemalloc.stop()
            except RuntimeError:
                logger.debug("Failed to stop tracemalloc")

    # Reporting ----------------------------------------------------------------
    def to_metadata(self) -> JsonObject:
        """Build a concise metadata mapping for logs/results."""
        data: JsonDict = {
            "profile_file": str(self.profile_path),
            "tracemalloc_snapshot": str(self.tracemalloc_path)
            if self._tracemalloc_captured
            else None,
            "tracemalloc_top": self._tracemalloc_top or None,
        }
        if self._memory_samples:
            data["memory_mb"] = {
                "samples": len(self._memory_samples),
                "peak": self.peak_memory_mb,
                "last": self._memory_samples[-1],
            }
        return {k: v for k, v in data.items() if v is not None}

    def _log_summary(self) -> None:
        meta = self.to_metadata()
        if not meta:
            return

        peak = None
        mem = meta.get("memory_mb")
        if isinstance(mem, Mapping):
            mem_dict = {str(k): v for k, v in mem.items()}
            peak_value = mem_dict.get("peak")
            if isinstance(peak_value, (int, float)):
                peak = float(peak_value)

        logger.info(
            "Profiling Summary: pipeline=%s run_id=%s cpu_profile=%s",
            self.pipeline_name,
            self.run_id,
            self.profile_path,
        )
        if self._memory_samples:
            mean_mb = sum(self._memory_samples) / len(self._memory_samples)
            last_mb = self._memory_samples[-1]
            logger.info(
                "  Memory: samples=%d mean=%.2f MB peak=%s MB last=%.2f MB",
                len(self._memory_samples),
                mean_mb,
                f"{peak:.2f}" if peak is not None else "n/a",
                last_mb,
            )
        else:
            logger.info("  Memory: samples=0")
        if meta.get("tracemalloc_snapshot"):
            logger.info(
                "  Tracemalloc snapshot: %s",
                meta["tracemalloc_snapshot"],
            )
            if self._tracemalloc_top:
                logger.info("  Top allocations:")
                for idx, line in enumerate(self._tracemalloc_top, start=1):
                    logger.info("    %d) %s", idx, line)

    # Result helpers -----------------------------------------------------------
    def attach_metadata(
        self, result: BasePipelineResult | None
    ) -> BasePipelineResult | None:
        """Attach profiling metadata to a BasePipelineResult (via model_copy)."""
        if result is None:
            return None

        meta = self.to_metadata()
        if not meta:
            return result

        updated_meta = dict(getattr(result, "metadata", {}) or {})
        updated_meta["profiling"] = meta

        try:
            return result.model_copy(update={"metadata": updated_meta})
        except Exception:
            # Fallback to in-place update if model_copy is unavailable
            try:
                result.metadata.update({"profiling": meta})
            except Exception:
                logger.debug("Unable to attach profiling metadata to result")
            return result
