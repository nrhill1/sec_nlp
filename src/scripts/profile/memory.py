# src/scripts/profile/memory.py
"""Profile memory usage of pipelines."""

import signal
import sys
import tracemalloc
from pathlib import Path
from typing import Literal

# Add src to path before other imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.utils import setup_import_path  # noqa: E402

# Setup import path securely
setup_import_path()

from pydantic import Field  # noqa: E402
from pydantic_settings import (  # noqa: E402
    BaseSettings,
    CliApp,
    SettingsConfigDict,
)

from sec_nlp.core.infra.logger import logger, setup_logging  # noqa: E402
from sec_nlp.pipelines.base.result import BaseResult  # noqa: E402
from sec_nlp.pipelines.presets.analyze import (  # noqa: E402
    AnalyzeConfig,
    AnalyzePipeline,
)
from sec_nlp.pipelines.presets.exb_10 import (  # noqa: E402
    Exhibit10Config,
    Exhibit10Pipeline,
)
from sec_nlp.pipelines.presets.warranty import (  # noqa: E402
    WarrantyConfig,
    WarrantyPipeline,
)

try:
    from memory_profiler import (
        profile as memory_profile,
    )
except ImportError:
    print(
        "memory_profiler not installed. Install with: uv pip install memory-profiler"
    )
    sys.exit(1)


class MemoryProfileConfig(BaseSettings):
    model_config = SettingsConfigDict(
        cli_prog_name="profile_memory",
        cli_enforce_required=False,
        cli_exit_on_error=True,
        cli_implicit_flags=True,
        extra="ignore",
    )

    pipeline: Literal["exb-10", "warranty", "analyze"] = Field(
        default="analyze",
        description="Pipeline to profile",
    )
    symbols: list[str] = Field(
        default=["AAPL"],
        description="Stock symbols to profile",
    )
    limit: int = Field(
        default=1,
        ge=1,
        description="Number of filings to process",
    )
    batch_size: int = Field(
        default=8,
        ge=1,
        description="Batch size for processing",
    )
    fresh: bool = Field(
        default=False,
        description="If true, clear download/output folders before run",
    )
    dry_run: bool = Field(
        default=True,
        description="Run pipelines in dry-run mode where supported (e.g., skip vector writes)",
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level",
    )
    tracemalloc_frames: int = Field(
        default=25,
        ge=0,
        description="Enable tracemalloc with the specified frame depth (0 to disable)",
    )

    def cli_cmd(self) -> None:
        """Run memory profiling."""
        setup_logging(level=self.log_level, format_type="simple")

        logger.info("Starting memory profiling...")
        logger.info("Note: This will be slower due to line-by-line tracking")

        if self.tracemalloc_frames > 0 and not tracemalloc.is_tracing():
            tracemalloc.start(self.tracemalloc_frames)
            logger.info(
                "Tracemalloc started (frames=%d)", self.tracemalloc_frames
            )

        self.run_pipeline_with_memory_profiling()

    @memory_profile
    def run_pipeline_with_memory_profiling(self) -> None:
        """Run pipeline with memory profiling."""
        logger.info("Creating pipeline... (%s)", self.pipeline)

        result: BaseResult
        if self.pipeline == "exb-10":
            exb_cfg = Exhibit10Config(
                verbose=True,
                email="test@example.com",
                symbols=self.symbols,
                limit=self.limit,
                fresh=self.fresh,
                dry_run=self.dry_run,
                batch_size=self.batch_size,
            )
            exb_pipeline = Exhibit10Pipeline(config=exb_cfg)
            logger.info("Running pipeline...")
            result = exb_pipeline.run()
        elif self.pipeline == "warranty":
            war_cfg = WarrantyConfig(
                verbose=True,
                email="test@example.com",
                symbols=self.symbols,
                limit=self.limit,
                fresh=self.fresh,
                dry_run=self.dry_run,
            )
            war_pipeline = WarrantyPipeline(config=war_cfg)
            logger.info("Running pipeline...")
            result = war_pipeline.run()
        elif self.pipeline == "analyze":
            ana_cfg = AnalyzeConfig(
                verbose=True,
                email="test@example.com",
                symbols=self.symbols,
                limit=self.limit,
                fresh=self.fresh,
                dry_run=self.dry_run,
                batch_size=self.batch_size,
            )
            ana_pipeline = AnalyzePipeline(config=ana_cfg)
            logger.info("Running pipeline...")
            result = ana_pipeline.run()
        else:
            raise ValueError(f"Unsupported pipeline: {self.pipeline}")

        logger.info("Pipeline complete: success=%s", result.success)
        self._log_tracemalloc_snapshot()

    def _log_tracemalloc_snapshot(self) -> None:
        """Emit a concise tracemalloc summary if tracing is active."""
        if not tracemalloc.is_tracing():
            return

        try:
            current, peak = tracemalloc.get_traced_memory()
            logger.info("Tracemalloc Summary:")
            logger.info(
                "  current=%.2f MB  peak=%.2f MB  frames=%d",
                current / (1024 * 1024),
                peak / (1024 * 1024),
                self.tracemalloc_frames,
            )
            snap = tracemalloc.take_snapshot()
            top = snap.statistics("lineno")[:8]
            if top:
                logger.info("  top allocations:")
                for idx, stat in enumerate(top, start=1):
                    size_mb = stat.size / (1024 * 1024)
                    frame = stat.traceback[0]
                    location = f"{Path(frame.filename).name}:{frame.lineno}"
                    logger.info(
                        "    %2d) %6.2f MB  %6d allocs  %s",
                        idx,
                        size_mb,
                        stat.count,
                        location,
                    )
            # Save snapshot for offline inspection
            dump_path = Path("logs") / f"tracemalloc_{self.pipeline}.snap"
            dump_path.parent.mkdir(parents=True, exist_ok=True)
            snap.dump(str(dump_path))
            logger.info("Tracemalloc snapshot saved to %s", dump_path)
        except Exception as exc:  # pragma: no cover - best-effort logging
            logger.debug("Tracemalloc summary failed: %s", exc)


def main() -> None:
    """Run memory profiling CLI."""
    signal.signal(signal.SIGINT, lambda *_: sys.exit(130))
    CliApp.run(MemoryProfileConfig)


if __name__ == "__main__":
    main()
