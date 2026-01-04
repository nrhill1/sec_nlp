# src/sec_nlp/cli/commands/analyze.py
"""CLI command for generalized document analysis pipeline."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import PipelineCommand
from sec_nlp.core.infra.logger import (
    bullet_line,
    color_text,
    logger,
)
from sec_nlp.pipelines.base.result import BaseResult
from sec_nlp.pipelines.presets.analyze import (
    AnalyzeConfig,
    AnalyzePipeline,
    AnalyzeResult,
)


class AnalyzeCommand(AnalyzeConfig, PipelineCommand):
    """Analyze SEC filings with section/topic filters, LLM analysis, and optional vector search.

    Presets provide quick configuration:
        --preset quick          Fast: small model, 1 filing, no vector DB
        --preset laptop         Laptop-friendly: small model, tighter caps, targeted search
        --preset thorough       Balanced: better model, 3 filings, vector DB
        --preset comprehensive  Full: best model, 5 filings, all features

    Interactive mode:
        Run 'sec-nlp analyze' without arguments to launch interactive setup.

    Examples:
        sec-nlp analyze                     # Interactive setup
        sec-nlp analyze AAPL --preset quick # Quick analysis
        sec-nlp analyze AAPL --topics warranty --topics recall
        sec-nlp analyze AAPL MSFT GOOGL --section-type item --section-numbers 1A
    """

    @classmethod
    def pipeline_class(cls) -> type[AnalyzePipeline]:
        return AnalyzePipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=list,
        description="Ticker symbols to analyze (e.g., AAPL MSFT GOOGL). Omit for interactive mode.",
    )

    def _supports_interactive(self) -> bool:
        return True

    def _run_interactive(self) -> None:
        """Run interactive setup and execute pipeline."""
        from sec_nlp.cli.interactive import run_interactive_setup
        from sec_nlp.cli.presets import AnalyzePreset, get_preset_config

        config_dict = run_interactive_setup()
        if config_dict is None:
            return

        # Apply preset if selected
        if "preset" in config_dict:
            preset = AnalyzePreset(config_dict.pop("preset"))
            preset_overrides = get_preset_config(preset)
            for key, value in preset_overrides.items():
                if key not in config_dict or (
                    key == "symbols" and not config_dict.get("symbols")
                ):
                    config_dict[key] = value

        try:
            base_dict = self.model_dump()
            base_dict.update(config_dict)
            new_config = AnalyzeCommand.model_validate(base_dict)
            PipelineCommand.cli_cmd(new_config)
        except Exception as e:
            logger.error(color_text(f"Configuration error: {e}", color="red"))

    def _handle_missing_symbols(self) -> None:
        logger.error(color_text("No symbols provided.", color="red"))
        logger.info("Usage: sec-nlp analyze SYMBOL [SYMBOL ...] [OPTIONS]")
        logger.info("Run 'sec-nlp analyze --help' for more information.")

    def _get_header_subtitle(self) -> str:
        return "Topic Scoring + LLM"

    # Backwards compatibility: keep legacy class name

    def _log_config_details(self) -> None:
        """Log analyze-specific configuration."""
        # Show preset if used
        if self.preset:
            logger.info(bullet_line("Preset", self.preset, color="magenta"))

        logger.info(bullet_line("Symbols", ", ".join(self.symbols)))
        logger.info(
            bullet_line(
                "LLM",
                f"{self.llm.model_name} @ T={self.llm.temperature} (json={self.llm.require_json})",
            )
        )
        logger.info(
            bullet_line(
                "Batching",
                f"chunks={self.batch_size} top_k={self.top_k_chunks or 'all'}",
                color="cyan",
            )
        )
        logger.info(
            bullet_line(
                "Vector DB",
                f"mode={self.vector_mode}",
                color="blue",
            )
        )
        search_status = (
            f"enabled ({('<=' if self.vdb.qdrant_distance in ('Cosine', 'Euclid') else '>=')}"
            f"{self.search.score_threshold})"
            if self.search.enabled
            else "disabled"
        )
        logger.info(
            bullet_line(
                "Search",
                f"{search_status} | limit={self.search.limit}",
                color="magenta",
            )
        )
        if self.topics:
            logger.info(
                bullet_line("Topics", ", ".join(self.topics), color="green")
            )
        elif self.keywords:
            logger.info(
                bullet_line("Keywords", ", ".join(self.keywords), color="green")
            )

    def _handle_result(self, result: BaseResult) -> None:
        """Handle analyze-specific result output."""
        if not isinstance(result, AnalyzeResult):
            super()._handle_result(result)
            return
        if result.error is not None:
            logger.error(
                color_text(f"✗ Analysis failed: {result.error}", color="red")
            )
            return

        if not result.success:
            logger.error(color_text("✗ Analysis failed", color="red"))
            return

        if result.outputs:
            logger.info(color_text("✓ Analysis complete", color="green"))
            logger.info(
                color_text(f"Outputs: {len(result.outputs)}", color="cyan")
            )
            for output_path in result.outputs:
                logger.info(color_text(f"  → {output_path}", color="cyan"))
        else:
            logger.info(
                color_text(
                    "✓ Analysis complete: no outputs generated", color="yellow"
                )
            )
