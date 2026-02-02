"""Shared utilities for CLI pipeline commands."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel

from sec_nlp.cli.formatting import (
    format_divider,
    format_key_value,
    format_section_header,
    format_status,
)
from sec_nlp.core.infra.logger import (
    color_text,
    logger,
)
from sec_nlp.pipelines.base import BasePipeline
from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.pipelines.base.validation import validate_pipeline
from sec_nlp.pipelines.observability.metrics import track_pipeline_metrics
from sec_nlp.pipelines.observability.profiling import PipelineProfiler

__all__ = ("BasePipelineCommand",)


class BasePipelineCommand(BaseModel, ABC):
    """Base behavior for CLI commands that wrap a pipeline."""

    @classmethod
    @abstractmethod
    def pipeline_class(cls) -> type[BasePipeline]:
        """Return the pipeline class for this CLI command."""
        raise NotImplementedError

    @classmethod
    def __pydantic_init_subclass__(
        cls, **kwargs: bool | str | int | float
    ) -> None:
        """Validate CLI command wiring after Pydantic model construction."""
        super().__pydantic_init_subclass__(**kwargs)

        if not issubclass(cls, BasePipelineSettings):
            raise TypeError(
                f"{cls.__name__} must inherit from BasePipelineSettings to be used as a CLI command"
            )

        if "pipeline_class" in cls.__abstractmethods__:
            return

        try:
            pipeline_cls = cls.pipeline_class()
        except Exception as exc:
            raise TypeError(
                f"{cls.__name__} must implement pipeline_class() returning a BasePipeline subclass"
            ) from exc

        if not issubclass(pipeline_cls, BasePipeline):
            raise TypeError(
                f"{cls.__name__}.pipeline_class() must return a BasePipeline subclass"
            )

    def cli_cmd(self) -> None:
        """Execute the configured pipeline."""
        if (
            self._supports_interactive()
            and not self._has_symbols()
            and sys.stdin.isatty()
        ):
            self._run_interactive()
            return

        if not self._has_symbols():
            self._handle_missing_symbols()
            return

        self._log_header()
        self._log_config_details()

        if self._should_validate():
            report = validate_pipeline(
                self._validation_config(), print_report=True
            )
            if report.has_errors():
                return

        if self._should_collect_metrics():
            with track_pipeline_metrics(
                self._pipeline_type(), auto_report=True
            ) as metrics:
                metrics.increment(
                    "symbols_count", len(getattr(self, "symbols", []))
                )
                result = self._run_pipeline()
                if result.success:
                    metrics.increment("successful_runs")
                    if result.outputs:
                        metrics.set_gauge("output_files", len(result.outputs))
                    total_chunks = result.metadata.get("total_chunks_analyzed")
                    if isinstance(total_chunks, int):
                        metrics.set_gauge("total_chunks_analyzed", total_chunks)
                else:
                    metrics.increment("failed_runs")
        else:
            result = self._run_pipeline()

        self._handle_result(result)

    def _get_pipeline_class(self) -> type[BasePipeline]:
        return type(self).pipeline_class()

    def _has_symbols(self) -> bool:
        symbols = getattr(self, "symbols", [])
        return bool(symbols)

    def _log_header(self) -> None:
        title = (
            self._pipeline_type().replace("_", " ").title()
            if self._pipeline_type()
            else "Pipeline"
        )
        header = format_section_header(
            title,
            subtitle=self._get_header_subtitle(),
            style="box",
        )
        logger.info(header)

    def _get_header_subtitle(self) -> str:
        pipeline_cls = self._get_pipeline_class()
        return getattr(pipeline_cls, "description", "")

    def _log_config_details(self) -> None:
        items: list[tuple[str, str | None]] = []

        symbols = getattr(self, "symbols", [])
        if symbols:
            items.append(("Symbols", ", ".join(symbols)))

        mode = getattr(self, "mode", None)
        if mode is not None:
            items.append(("Mode", str(mode)))

        batch_size = getattr(self, "batch_size", None)
        if batch_size is not None:
            items.append(("Batch size", str(batch_size)))

        if items:
            for label, value in items:
                logger.info(format_key_value(label, value))

    def _validation_config(self) -> BasePipelineSettings:
        if isinstance(self, BasePipelineSettings):
            return self
        raise TypeError(
            f"{type(self).__name__} must inherit from BasePipelineSettings to validate"
        )

    def _handle_result(self, result: BasePipelineResult) -> None:
        pipeline_name = self._pipeline_type() or "Pipeline"
        logger.info(format_divider())

        if result.error is not None:
            logger.error(
                format_status(
                    f"{pipeline_name} failed: {result.error}",
                    status="error",
                )
            )
            return

        if not result.success:
            logger.error(
                format_status(f"{pipeline_name} failed", status="error")
            )
            return

        if result.outputs:
            logger.info(
                format_status(f"{pipeline_name} complete", status="success")
            )
            for output_path in result.outputs:
                logger.info(color_text(f"  → {output_path}", color="cyan"))
            return

        logger.info(
            format_status(
                f"{pipeline_name} complete: no outputs generated",
                status="warning",
            )
        )

    def _should_validate(self) -> bool:
        return True

    def _should_collect_metrics(self) -> bool:
        return bool(getattr(self, "collect_metrics", False))

    def _supports_interactive(self) -> bool:
        return False

    def _run_interactive(self) -> None:
        self._handle_missing_symbols()

    def _handle_missing_symbols(self) -> None:
        logger.error(color_text("No symbols provided.", color="red"))

    def _run_pipeline(self) -> BasePipelineResult:
        pipeline_cls = self._get_pipeline_class()
        profile_root = getattr(self, "profile_dir", None)
        profiler = PipelineProfiler(
            pipeline_name=self._pipeline_type() or pipeline_cls.__name__,
            run_id=getattr(self, "run_id", None),
            output_root=Path(profile_root) if profile_root else None,
        )

        result: BasePipelineResult | None = None
        try:
            with profiler:
                if isinstance(self, BasePipelineSettings):
                    config: BasePipelineSettings = self
                    pipeline = pipeline_cls(config=config)
                    result = pipeline.run()
                else:
                    raise TypeError(
                        f"{type(self).__name__} must inherit from BasePipelineSettings to run pipeline validation"
                    )
        except Exception as e:
            logger.error(
                color_text(
                    f"✗ Error during pipeline execution: {e}",
                    color="red",
                )
            )
        finally:
            # Attach profiling metadata to the result and config (if possible)
            result = profiler.attach_metadata(result)
            self._capture_profiling_metadata(profiler)
            self._record_run_completion(result)

        if result is None:
            raise RuntimeError("Pipeline did not return a result")

        return result

    def _capture_profiling_metadata(self, profiler: PipelineProfiler) -> None:
        """Persist profiling metadata onto the config for registry updates."""
        meta = profiler.to_metadata()
        if not meta:
            return
        try:
            config = self._validation_config()
            config._profiling_metadata = dict(meta)
        except Exception:
            logger.debug("Unable to stash profiling metadata on config")

    def _record_run_completion(self, result: BasePipelineResult | None) -> None:
        """Update the run registry with profiling metadata if available."""
        complete_run = getattr(self, "complete_run", None)
        if complete_run is None:
            return
        if result is None:
            try:
                complete_run(success=False)
            except Exception:
                logger.debug("Run registry update skipped")
            return
        try:
            complete_run(success=bool(result.success))
        except Exception:
            logger.debug("Run registry update skipped")

    def _pipeline_type(self) -> str:
        pipeline_cls = self._get_pipeline_class()
        return getattr(pipeline_cls, "pipeline_type", "")
