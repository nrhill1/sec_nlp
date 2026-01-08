# src/sec_nlp/pipelines/presets/analyze/io/outputs.py
"""Output formatting and export for the analyze pipeline."""

import csv
from collections import defaultdict
from pathlib import Path
from typing import Literal

from sec_nlp.core.infra.logger import logger
from sec_nlp.pipelines.output_io import (
    build_accession_dir,
    write_json,
    write_yaml,
)
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataMap

from ..models import (
    Aggregates,
    AnalysisDiagnostics,
    AnalysisOutput,
    ExecutiveSummary,
    FilingInfo,
)


class OutputFormatter:
    """Formats and exports analysis results."""

    def __init__(
        self,
        export_format: Literal["json", "csv", "yaml", "both", "yaml_csv"],
        confidence_threshold: float,
        topics: list[str] | None = None,
        include_raw_chunks: bool = False,
    ) -> None:
        self.export_format = export_format
        self.confidence_threshold = confidence_threshold
        self.topics = topics or []
        self.include_raw_chunks = include_raw_chunks

    def is_relevant_result(self, result: AnalysisResultDict) -> bool:
        """Check if a result meets the relevance threshold."""
        has_error = bool(result.get("error") or result.get("exception"))
        is_relevant_flag = bool(result.get("is_relevant"))
        confidence = float(result.get("confidence_score", 0) or 0)
        return (
            not has_error
            and is_relevant_flag
            and confidence >= self.confidence_threshold
        )

    def build_output(
        self,
        symbol: str,
        filing_meta: MetadataMap,
        analysis_results: list[AnalysisResultDict],
        relevant_results: list[AnalysisResultDict],
        search_queries: list[str] | None = None,
        timings: dict[str, float] | None = None,
    ) -> AnalysisOutput:
        """Build structured output from analysis results.

        Args:
            symbol: Stock ticker symbol
            filing_meta: Filing metadata
            analysis_results: All analysis results (including failures)
            relevant_results: Filtered relevant results
            timings: Optional timing breakdown

        Returns:
            Structured AnalysisOutput model
        """
        # Compute statistics
        total_chunks = len(analysis_results)
        successful = sum(1 for r in analysis_results if "error" not in r)
        failed = total_chunks - successful
        relevant_count = len(relevant_results)

        confidence_scores = [
            score
            for result in relevant_results
            if (score := result.get("confidence_score")) is not None
        ]
        avg_confidence = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else 0.0
        )

        # Build aggregates
        aggregates = self._build_aggregates(relevant_results)

        # Build executive summary
        top_tags = list(aggregates.tag_frequency.keys())[:5]
        top_topics = list(aggregates.topic_hits_frequency.keys())[:5]

        # Extract key points (deduplicated, top 5)
        key_points: list[str] = []
        for r in relevant_results:
            for kp in r.get("key_points") or []:
                if kp and kp not in key_points:
                    key_points.append(kp)
                    if len(key_points) >= 5:
                        break
            if len(key_points) >= 5:
                break

        # Build one-line status
        if relevant_count == 0:
            status = "No relevant findings"
        elif relevant_count == 1:
            status = f"1 relevant finding (confidence {avg_confidence:.2f})"
        else:
            status = f"{relevant_count} relevant findings (avg confidence {avg_confidence:.2f})"

        executive_summary = ExecutiveSummary(
            status=status,
            total_chunks=total_chunks,
            relevant_count=relevant_count,
            average_confidence=avg_confidence,
            top_tags=top_tags,
            top_topics=top_topics,
            key_points=key_points,
        )

        # Build diagnostics
        diagnostics = AnalysisDiagnostics(
            chunks_analyzed=total_chunks,
            chunks_successful=successful,
            chunks_failed=failed,
            chunks_relevant=relevant_count,
            success_rate=(successful / total_chunks) if total_chunks else 0.0,
            relevant_rate=(relevant_count / total_chunks)
            if total_chunks
            else 0.0,
            timings=timings or {},
            confidence_threshold=self.confidence_threshold,
        )

        # Build filing info
        def _meta_str(key: str) -> str | None:
            value = filing_meta.get(key)
            if isinstance(value, (str, int, float, bool)):
                return str(value)
            return None

        filing = FilingInfo(
            accession_number=_meta_str("accession_number"),
            form_type=_meta_str("form_type"),
            acceptance_date=_meta_str("acceptance_date"),
            filing_date=_meta_str("filing_date"),
        )

        return AnalysisOutput(
            symbol=symbol,
            search_queries=search_queries or [],
            filing=filing,
            executive_summary=executive_summary,
            aggregates=aggregates,
            diagnostics=diagnostics,
            results=relevant_results,
        )

    def _build_aggregates(
        self, relevant_results: list[AnalysisResultDict]
    ) -> Aggregates:
        """Build aggregated statistics from results."""
        tag_counts: dict[str, int] = defaultdict(int)
        sentiment_counts: dict[str, int] = defaultdict(int)
        section_counts: dict[str, int] = defaultdict(int)
        topic_hit_counts: dict[str, int] = defaultdict(int)
        impact_channel_counts: dict[str, int] = defaultdict(int)
        impact_horizon_counts: dict[str, int] = defaultdict(int)
        impact_direction_counts: dict[str, int] = defaultdict(int)
        impact_magnitude_counts: dict[str, int] = defaultdict(int)
        binding_status_counts: dict[str, int] = defaultdict(int)
        forward_looking_count = 0

        for result in relevant_results:
            for tag in result.get("tags") or []:
                tag_counts[tag] += 1

            sentiment = result.get("sentiment")
            if sentiment:
                sentiment_counts[str(sentiment)] += 1

            if result.get("forward_looking"):
                forward_looking_count += 1

            section = (result.get("source_metadata") or {}).get(
                "section_number"
            )
            if section:
                section_counts[str(section)] += 1

            topic_hits = (result.get("source_metadata") or {}).get("topic_hits")
            if isinstance(topic_hits, list):
                for topic in topic_hits:
                    topic_hit_counts[str(topic)] += 1
            elif isinstance(topic_hits, str) and topic_hits:
                topic_hit_counts[topic_hits] += 1

            impact_channels = result.get("impact_channels") or []
            if isinstance(impact_channels, list):
                for channel in impact_channels:
                    if channel:
                        impact_channel_counts[str(channel)] += 1

            impact_horizon = result.get("impact_horizon")
            if impact_horizon:
                impact_horizon_counts[str(impact_horizon)] += 1

            impact_direction = result.get("impact_direction")
            if impact_direction:
                impact_direction_counts[str(impact_direction)] += 1

            impact_magnitude = result.get("impact_magnitude")
            if impact_magnitude:
                impact_magnitude_counts[str(impact_magnitude)] += 1

            binding_status = result.get("binding_status")
            if binding_status:
                binding_status_counts[str(binding_status)] += 1

        return Aggregates(
            tag_frequency=dict(
                sorted(tag_counts.items(), key=lambda t: t[1], reverse=True)
            ),
            sentiment_breakdown=dict(sentiment_counts),
            sections_covered=dict(section_counts),
            topic_hits_frequency=dict(topic_hit_counts),
            impact_channel_frequency=dict(
                sorted(
                    impact_channel_counts.items(),
                    key=lambda t: t[1],
                    reverse=True,
                )
            ),
            impact_horizon_frequency=dict(
                sorted(
                    impact_horizon_counts.items(),
                    key=lambda t: t[1],
                    reverse=True,
                )
            ),
            impact_direction_frequency=dict(
                sorted(
                    impact_direction_counts.items(),
                    key=lambda t: t[1],
                    reverse=True,
                )
            ),
            impact_magnitude_frequency=dict(
                sorted(
                    impact_magnitude_counts.items(),
                    key=lambda t: t[1],
                    reverse=True,
                )
            ),
            binding_status_frequency=dict(
                sorted(
                    binding_status_counts.items(),
                    key=lambda t: t[1],
                    reverse=True,
                )
            ),
            forward_looking_count=forward_looking_count,
        )

    def export(
        self,
        output: AnalysisOutput,
        output_dir: Path,
        accession: str,
    ) -> list[Path]:
        """Export output to configured formats.

        Args:
            output: Structured output to export
            output_dir: Directory to write files to
            accession: Accession number for filename

        Returns:
            List of written file paths
        """
        output_files: list[Path] = []
        accession_dir = build_accession_dir(output_dir, accession)
        base_name = "analysis"

        # Convert to dict for export
        # Export JSON
        if self.export_format in ("json", "both"):
            json_file = accession_dir / f"{base_name}.json"
            write_json(json_file, output)
            output_files.append(json_file)
            logger.debug("Analysis results written to %s", json_file)

        # Export YAML
        if self.export_format in ("yaml", "yaml_csv"):
            yaml_file = accession_dir / f"{base_name}.yaml"
            write_yaml(yaml_file, output, sort_keys=False)
            output_files.append(yaml_file)
            logger.debug("Analysis results written to %s", yaml_file)

        # Export CSV
        if self.export_format in ("csv", "both", "yaml_csv"):
            csv_file = accession_dir / f"{base_name}.csv"
            self._export_csv(output, csv_file)
            output_files.append(csv_file)
            logger.debug("CSV results written to %s", csv_file)

        return output_files

    def _export_csv(self, output: AnalysisOutput, csv_file: Path) -> None:
        """Export results to CSV format."""
        fieldnames = [
            "confidence_score",
            "summary",
            "key_points",
            "query_match_terms",
            "missing_query_terms",
            "binding_status",
            "contingencies",
            "impact_channels",
            "impact_direction",
            "impact_magnitude",
            "impact_horizon",
            "impact_confidence",
            "impact_rationale",
            "tags",
            "severity",
            "sentiment",
            "forward_looking",
            "source_excerpt",
            "follow_up_questions",
            "section_number",
        ]
        if self.include_raw_chunks:
            fieldnames.append("raw_chunk")

        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for result in output.results:
                tags = result.get("tags") or []
                followups = result.get("follow_up_questions") or []
                evidence_excerpt = result.get("source_excerpt") or next(
                    (
                        ev.get("text")
                        for ev in result.get("evidence_spans", [])
                        if isinstance(ev, dict) and ev.get("text")
                    ),
                    "",
                )
                row = {
                    "confidence_score": result.get("confidence_score"),
                    "summary": result.get("summary", ""),
                    "key_points": "; ".join(result.get("key_points", [])),
                    "query_match_terms": "; ".join(
                        result.get("query_match_terms") or []
                    ),
                    "missing_query_terms": "; ".join(
                        result.get("missing_query_terms") or []
                    ),
                    "binding_status": result.get("binding_status", ""),
                    "contingencies": "; ".join(
                        result.get("contingencies") or []
                    ),
                    "impact_channels": "; ".join(
                        result.get("impact_channels") or []
                    ),
                    "impact_direction": result.get("impact_direction", ""),
                    "impact_magnitude": result.get("impact_magnitude", ""),
                    "impact_horizon": result.get("impact_horizon", ""),
                    "impact_confidence": result.get("impact_confidence", ""),
                    "impact_rationale": result.get("impact_rationale", ""),
                    "tags": "; ".join(tags),
                    "severity": result.get("severity", ""),
                    "sentiment": result.get("sentiment", ""),
                    "forward_looking": result.get("forward_looking", ""),
                    "source_excerpt": evidence_excerpt,
                    "follow_up_questions": "; ".join(followups),
                    "section_number": result.get("source_metadata", {}).get(
                        "section_number", ""
                    ),
                }
                if self.include_raw_chunks:
                    row["raw_chunk"] = result.get("raw_chunk", "")
                writer.writerow(row)
