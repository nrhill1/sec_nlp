"""Pipeline for EFTS-first retrieval and ranked hit exports."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar, Literal, cast

from pydantic import PrivateAttr
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.infra.rich_console import get_rich_console
from sec_nlp.core.market_analytics import build_market_context
from sec_nlp.pipelines import BasePipeline
from sec_nlp.pipelines.output_io import (
    build_run_file_stem,
    build_run_header_fields,
)
from sec_nlp.types import JsonDict, JsonValue, ResultDict

from .config import RetrieveSettings
from .io import (
    RankedResultsPayload,
    write_ranked_results_csv,
    write_ranked_results_json,
    write_ranked_results_yaml,
)
from .models import RetrievalHit, RetrieveResult
from .steps import (
    download_and_chunk_hits,
    index_retrieval_hits,
    rank_retrieval_hits,
    rerank_with_embeddings,
    run_candidate_search,
)


class RetrievePipeline(BasePipeline):
    """Retrieve filing candidates and emit ranked results."""

    pipeline_type: ClassVar[Literal["retrieve"]] = "retrieve"
    description: ClassVar[str] = (
        "Run EFTS candidate search and return ranked filing hits"
    )
    requires_llm: ClassVar[bool] = False

    config: RetrieveSettings
    _embedder: Any | None = PrivateAttr(default=None)
    _embedding_dim: int | None = PrivateAttr(default=None)
    _qdrant_client: Any | None = PrivateAttr(default=None)

    @classmethod
    def config_model(cls) -> type[RetrieveSettings]:
        return RetrieveSettings

    @classmethod
    def result_model(cls) -> type[RetrieveResult]:
        return RetrieveResult

    def _build_components(self) -> None:
        if self.config.rerank_with_embeddings or self.config.index_results:
            try:
                self._embedder, self._embedding_dim = (
                    self.config.vdb.setup_embedding_model()
                )
            except Exception as exc:
                logger.warning(
                    "Retrieve embedding model prewarm failed; will fallback to lazy setup: %s",
                    exc,
                )
                self._embedder = None
                self._embedding_dim = None

        if self.config.index_results:
            try:
                self._qdrant_client = self.config.vdb.setup_qdrant_client()
            except Exception as exc:
                logger.warning(
                    "Retrieve Qdrant preconnect failed; will fallback to lazy setup: %s",
                    exc,
                )
                self._qdrant_client = None

    def run(self) -> RetrieveResult:
        try:
            self.config.setup_paths()
            if not self.config.queries:
                raise ValueError(
                    "Retrieve pipeline requires at least one --queries value"
                )

            outputs: list[Path] = []
            metadata: ResultDict = {}
            total_queries = 0
            total_hits = 0
            symbol_targets: list[tuple[str | None, str]]
            if self.config.symbols:
                symbol_targets = [
                    (symbol.upper(), symbol.upper())
                    for symbol in self.config.symbols
                ]
            else:
                symbol_targets = [(None, "ALL")]

            console = get_rich_console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold cyan]{task.description}"),
                BarColumn(complete_style="green", finished_style="bold green"),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                TextColumn("[dim]-[/dim]"),
                TimeRemainingColumn(),
                console=console,
                transient=True,
            ) as progress:
                overall_task = progress.add_task(
                    "Processing symbols",
                    total=len(symbol_targets),
                )
                phase_task = progress.add_task("", total=None, visible=False)

                for search_symbol, output_symbol in symbol_targets:
                    progress.update(
                        overall_task,
                        description=f"Processing {output_symbol}",
                    )

                    (
                        symbol_outputs,
                        symbol_meta,
                        queries_processed,
                        hits_count,
                    ) = self._process_symbol(
                        search_symbol=search_symbol,
                        output_symbol=output_symbol,
                        progress=progress,
                        phase_task=phase_task,
                    )

                    outputs.extend(symbol_outputs)
                    metadata[output_symbol] = symbol_meta
                    total_queries += queries_processed
                    total_hits += hits_count

                    progress.update(phase_task, visible=False)
                    progress.advance(overall_task)

            self.config.complete_run(
                success=True,
                metadata=cast(JsonDict, metadata),
            )
            return RetrieveResult(
                success=True,
                outputs=outputs,
                metadata=metadata,
                symbols_processed=len(symbol_targets),
                queries_processed=total_queries,
                hits_returned=total_hits,
            )
        except Exception as exc:
            logger.exception("Retrieve pipeline failed")
            self.config.complete_run(success=False)
            return RetrieveResult(
                success=False,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _process_symbol(
        self,
        *,
        search_symbol: str | None,
        output_symbol: str,
        progress: Progress | None = None,
        phase_task: TaskID | None = None,
    ) -> tuple[list[Path], dict[str, JsonValue], int, int]:
        self._update_phase(
            progress,
            phase_task,
            output_symbol,
            "Candidate search",
        )
        candidates_by_query = run_candidate_search(
            symbol=search_symbol,
            queries=self.config.queries,
            settings=self.config,
        )

        candidate_count = sum(
            len(hits) for hits in candidates_by_query.values()
        )

        self._update_phase(progress, phase_task, output_symbol, "Ranking")
        ranked_hits = rank_retrieval_hits(
            symbol=output_symbol,
            candidates_by_query=candidates_by_query,
            top_k=self.config.top_k,
        )

        # Keep the stage boundaries explicit for future retrieve pipeline expansion.
        ranked_hits = download_and_chunk_hits(
            symbol=output_symbol,
            hits=ranked_hits,
            settings=self.config,
        )
        ranked_hits = rerank_with_embeddings(
            hits=ranked_hits,
            settings=self.config,
            embedder=self._embedder,
        )
        market_context_metadata = self._market_context_metadata(
            output_symbol=output_symbol,
        )
        market_signals = self._market_signals_for_payload(
            market_context_metadata
        )
        ranked_hits = index_retrieval_hits(
            symbol=output_symbol,
            hits=ranked_hits,
            settings=self.config,
            qdrant_client=self._qdrant_client,
            embedder=self._embedder,
            embedding_dim=self._embedding_dim,
            market_signals=market_signals,
        )

        self._update_phase(progress, phase_task, output_symbol, "Writing")
        outputs = self._write_outputs(
            symbol=output_symbol,
            hits=ranked_hits,
            extra_metadata=market_context_metadata,
        )

        metadata: dict[str, JsonValue] = {
            "queries_processed": len(self.config.queries),
            "candidate_hits": candidate_count,
            "ranked_hits": len(ranked_hits),
            "chunk_snippets": sum(
                1 for hit in ranked_hits if hit.chunk_index is not None
            ),
            "top_k": self.config.top_k,
            "efts_candidates": self.config.efts_candidates,
        }
        if market_context_metadata:
            metadata["market_context"] = market_context_metadata

        return outputs, metadata, len(self.config.queries), len(ranked_hits)

    def _market_context_metadata(
        self,
        *,
        output_symbol: str,
    ) -> dict[str, JsonValue]:
        if not self.config.include_market_signals:
            return {}
        if output_symbol == "ALL":
            return {}

        start_date, end_date = self.config.date_range
        try:
            bundle = build_market_context(
                symbols=[output_symbol],
                start_date=start_date,
                end_date=end_date,
                benchmark="SPY",
            )
        except Exception as exc:
            logger.warning(
                "Failed to compute market signals for %s: %s",
                output_symbol,
                exc,
            )
            return {}

        return cast(
            dict[str, JsonValue],
            bundle.model_dump(mode="json", exclude_none=True),
        )

    @staticmethod
    def _market_signals_for_payload(
        market_context: dict[str, JsonValue],
    ) -> dict[str, JsonValue] | None:
        metrics_raw = market_context.get("metrics")
        if not isinstance(metrics_raw, list) or not metrics_raw:
            return None
        metric = metrics_raw[0]
        if not isinstance(metric, dict):
            return None
        metric_payload = cast(dict[str, JsonValue], metric)
        payload: dict[str, JsonValue] = {
            "window": market_context.get("window"),
            "benchmark": market_context.get("benchmark"),
        }
        for key, value in metric_payload.items():
            payload[key] = value
        return payload

    def _update_phase(
        self,
        progress: Progress | None,
        phase_task: TaskID | None,
        symbol: str,
        phase: str,
    ) -> None:
        if progress is None or phase_task is None:
            return

        progress.reset(
            phase_task,
            start=True,
            description=f"  - {symbol}: {phase}",
            visible=True,
            completed=0,
        )
        progress.update(
            phase_task,
            total=None,
            completed=0,
        )

    def _write_outputs(
        self,
        *,
        symbol: str,
        hits: list[RetrievalHit],
        extra_metadata: dict[str, JsonValue] | None = None,
    ) -> list[Path]:
        symbol_out = self.config.get_symbol_output_dir(symbol)
        base_stem = build_run_file_stem(symbol, "retrieve", self.config.run_id)
        run_header = build_run_header_fields(
            run_timestamp=self.config.run_timestamp,
            run_id=self.config.run_id,
            run_short_id=self.config.short_id,
        )
        run_short_id_raw = run_header.get("run_short_id")
        run_short_id = (
            run_short_id_raw if isinstance(run_short_id_raw, int) else None
        )

        payload = RankedResultsPayload(
            run_timestamp=str(run_header["run_timestamp"]),
            run_short_id=run_short_id,
            run_id=str(run_header["run_id"]),
            run_short_id_display=str(run_header["run_short_id_display"]),
            symbol=symbol,
            queries=self.config.queries,
            hits=hits,
            metadata={
                "forms": self.config.forms or ["10-K", "10-Q"],
                "sections": self.config.sections,
                "top_k": self.config.top_k,
                "efts_candidates": self.config.efts_candidates,
                "download_missing": self.config.download_missing,
                "rerank_with_embeddings": self.config.rerank_with_embeddings,
                "embedding_weight": self.config.embedding_weight,
                "index_results": self.config.index_results,
                "embedding_cache": self.config.embedding_cache,
                "embedding_cache_file": str(self.config.embedding_cache_file),
                "embedding_cache_max_entries": self.config.embedding_cache_max_entries,
                "chunk_size": self.config.chunk_size,
                "chunk_overlap": self.config.chunk_overlap,
                "max_chunks_per_accession": self.config.max_chunks_per_accession,
                **(
                    {"market_context": extra_metadata} if extra_metadata else {}
                ),
            },
        )

        outputs: list[Path] = []
        if self.config.output_format in ("csv", "all"):
            csv_path = symbol_out / f"{base_stem}_ranked.csv"
            write_ranked_results_csv(
                csv_path,
                hits,
                header_fields=run_header,
            )
            outputs.append(csv_path)

        if self.config.output_format in ("json", "all"):
            json_path = symbol_out / f"{base_stem}_summary.json"
            write_ranked_results_json(json_path, payload)
            outputs.append(json_path)

        if self.config.output_format in ("yaml", "all"):
            yaml_path = symbol_out / f"{base_stem}_summary.yaml"
            write_ranked_results_yaml(yaml_path, payload)
            outputs.append(yaml_path)

        return outputs
