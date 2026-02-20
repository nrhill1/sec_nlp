"""Retrieve pipeline CLI command."""

from pydantic import Field
from pydantic_settings import CliPositionalArg

from sec_nlp.cli.command import BasePipelineCommand
from sec_nlp.cli.formatting import format_key_value
from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.presets.retrieve import (
    RetrievePipeline,
    RetrieveSettings,
)


class Retrieve(RetrieveSettings, BasePipelineCommand):
    """Retrieve ranked filing hits from EFTS candidate search."""

    @classmethod
    def pipeline_class(cls) -> type[RetrievePipeline]:
        return RetrievePipeline

    symbols: CliPositionalArg[list[str]] = Field(
        default_factory=list,
        description=(
            "Optional ticker symbols to process (e.g., AAPL MSFT). "
            "Omit to run unscoped retrieval."
        ),
    )

    def _get_header_subtitle(self) -> str:
        return "Retrieval"

    def _log_pipeline_run_details(self) -> None:
        logger.info(format_key_value("Queries", str(len(self.queries))))
        logger.info(format_key_value("Top K", str(self.top_k)))
        logger.info(
            format_key_value("EFTS Candidates", str(self.efts_candidates))
        )
        logger.info(
            format_key_value(
                "Index Results", "yes" if self.index_results else "no"
            )
        )

        collection_name = self.vdb.collection_name
        if collection_name:
            logger.info(format_key_value("Collection", collection_name))
