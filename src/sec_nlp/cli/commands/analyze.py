# src/sec_nlp/cli/commands/analyze.py
"""CLI command for generalized document analysis pipeline."""

from pydantic import Field, model_validator
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.cli.formatting import (
    format_key_value,
    format_status,
)
from sec_nlp.core.infra.logger import (
    color_text,
    logger,
)
from sec_nlp.core.types import coerce_json_dict
from sec_nlp.pipelines.base.result import BasePipelineResult
from sec_nlp.pipelines.presets.analyze import (
    AnalyzeConfig,
    AnalyzePipeline,
    AnalyzeResult,
)
from sec_nlp.types import JsonValue


class AnalyzeCommand(AnalyzeConfig, BasePipelineCommand):
    """Analyze SEC filings with section/topic filters, LLM analysis, and optional vector search.

    Presets provide quick configuration:
        --preset quick          Fast: small model, 1 filing, no vector DB
        --preset laptop         Laptop-friendly: small model, tighter caps, targeted search
        --preset thorough       Balanced: better model, 3 filings, vector DB
        --preset comprehensive  Full: best model, 5 filings, all features
        --preset deep           Full-field extraction profile (verbose output)
        --preset sentiment      Production baseline: compact sentiment/impact signal pack

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

    def cli_cmd(self) -> None:
        """Execute the configured pipeline, applying preset defaults if set."""
        if self.preset:
            from sec_nlp.cli.presets import AnalyzePreset, get_preset_config

            preset = AnalyzePreset(self.preset)
            preset_overrides = get_preset_config(preset)

            base_dict = self.model_dump()
            fields_set = set(getattr(self, "model_fields_set", set()))

            for key, value in preset_overrides.items():
                if key == "symbols":
                    if not base_dict.get("symbols"):
                        base_dict[key] = value
                    continue
                if key not in fields_set:
                    base_dict[key] = value

            merged = AnalyzeCommand.model_validate(base_dict)
            return BasePipelineCommand.cli_cmd(merged)

        return BasePipelineCommand.cli_cmd(self)

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=list,
        description="Ticker symbols to analyze (e.g., AAPL MSFT GOOGL). Omit for interactive mode.",
    )
    cli_queries: list[str] = Field(
        default_factory=list,
        description="Queries supplied via CLI (helper for --queries).",
        json_schema_extra={
            "cli_args": {
                "nargs": "+",
                "action": "extend",
                "aliases": ["--queries"],
            }
        },
    )

    def _supports_interactive(self) -> bool:
        # If a preset is explicitly provided, don't enter interactive mode.
        """Return whether analyze command supports interactive mode."""
        return not bool(self.preset)

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
            BasePipelineCommand.cli_cmd(new_config)
        except Exception as e:
            logger.error(color_text(f"Configuration error: {e}", color="red"))

    @model_validator(mode="before")
    @classmethod
    def _merge_cli_queries(
        cls, values: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        """Merge CLI query arguments into a normalized query list."""
        cli_queries = values.get("cli_queries")
        if isinstance(cli_queries, list) and cli_queries:
            raw_search = values.get("search")
            search_values: dict[str, JsonValue] = {}
            if isinstance(raw_search, dict):
                search_dict = coerce_json_dict(raw_search)
                if search_dict is not None:
                    search_values.update(search_dict)
            search_values["queries"] = cli_queries
            values["search"] = search_values
        return values

    def _handle_missing_symbols(self) -> None:
        """Emit an error when required analyze symbols are missing."""
        logger.error(color_text("No symbols provided.", color="red"))
        logger.info("Usage: sec-nlp analyze SYMBOL [SYMBOL ...] [OPTIONS]")
        logger.info("Run 'sec-nlp analyze --help' for more information.")

    def _get_header_subtitle(self) -> str:
        """Build subtitle text for the analyze command header."""
        return "Topic Scoring + LLM"

    # Backwards compatibility: keep legacy class name

    def _log_config_details(self) -> None:
        """Log analyze-specific configuration."""
        super()._log_config_details()
        items: list[tuple[str, str | None]] = []

        # Show preset if used
        if self.preset:
            items.append(("Preset", self.preset))

        items.append(
            (
                "LLM",
                f"{self.llm.model_name} @ T={self.llm.temperature} (json={self.llm.require_json})",
            )
        )
        items.append(
            (
                "Batching",
                f"chunks={self.batch_size} top_k={self.top_k_chunks or 'all'}",
            )
        )
        items.append(("Vector DB", f"mode={self.vector_mode}"))
        items.append(
            (
                "Timeline",
                "enabled" if self.show_timeline else "disabled",
            )
        )

        has_queries = bool(self.search.queries)
        search_status = (
            f"configured ({len(self.search.queries)} queries, "
            f"{('<=' if self.vdb.qdrant_distance in ('Cosine', 'Euclid') else '>=')}"
            f"{self.search.score_threshold})"
            if has_queries
            else "disabled (no queries)"
        )
        items.append(("Search", f"{search_status} | limit={self.search.limit}"))

        if self.topics:
            items.append(("Topics", ", ".join(self.topics)))
        elif self.keywords:
            items.append(("Keywords", ", ".join(self.keywords)))

        for label, value in items:
            formatted = format_key_value(label, value)
            logger.info(formatted)

    def _handle_result(self, result: BasePipelineResult) -> None:
        """Handle analyze-specific result output."""
        if not isinstance(result, AnalyzeResult):
            super()._handle_result(result)
            return
        if result.error is not None:
            logger.error(
                format_status(
                    f"Analysis failed: {result.error}", status="error"
                )
            )
            return

        if not result.success:
            logger.error(format_status("Analysis failed", status="error"))
            return

        if result.outputs:
            logger.info(format_status("Analysis complete", status="success"))
            logger.info(
                color_text(f"Outputs: {len(result.outputs)}", color="cyan")
            )
            for output_path in result.outputs:
                logger.info(color_text(f"  → {output_path}", color="cyan"))
        else:
            logger.info(
                format_status(
                    "Analysis complete: no outputs generated", status="warning"
                )
            )
