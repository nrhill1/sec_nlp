# src/sec_nlp/pipelines/presets/analyze/io/outputs.py
"""Output formatting and export for the analyze pipeline."""

import csv
import json
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Literal
from uuid import UUID

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.types import coerce_float, coerce_json_dict
from sec_nlp.pipelines.metadata.normalize import (
    get_meta_str,
    get_meta_str_any,
)
from sec_nlp.pipelines.output_io import (
    build_accession_dir,
    write_json,
    write_yaml,
)
from sec_nlp.pipelines.serialization import (
    is_score_key,
    round_score,
    round_timing,
    serialize_payload,
)
from sec_nlp.pipelines.types import (
    AnalysisResultDict,
    MetadataMap,
    MetadataRecord,
    MetadataScalar,
    MetadataValue,
)
from sec_nlp.types import JsonDict, JsonValue

from ..market import MarketEnrichment
from ..models import (
    Aggregates,
    AnalysisDiagnostics,
    AnalysisOutput,
    ExecutiveCompSummary,
    ExecutiveSummary,
    FilingInfo,
    OutputProvenance,
)


class OutputFormatter:
    """Formats and exports analysis results."""

    def __init__(
        self,
        export_format: Literal["json", "csv", "yaml", "both", "yaml_csv"],
        confidence_threshold: float,
        topics: list[str] | None = None,
        include_raw_chunks: bool = False,
        run_id: UUID | None = None,
        model_name: str | None = None,
        confidence_mode: str | None = None,
        prompt_path: Path | None = None,
        prompt_version: str | None = None,
        pipeline_version: str | None = None,
    ) -> None:
        self.export_format = export_format
        self.confidence_threshold = confidence_threshold
        self.topics = topics or []
        self.include_raw_chunks = include_raw_chunks
        self.run_id = run_id
        self.model_name = model_name
        self.confidence_mode = confidence_mode
        self.prompt_path = prompt_path
        self.prompt_version = prompt_version or self._hash_prompt_file(
            prompt_path
        )
        self.pipeline_version = pipeline_version

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

    @staticmethod
    def _hash_prompt_file(prompt_path: Path | None) -> str | None:
        if prompt_path is None:
            return None
        try:
            return sha256(prompt_path.read_bytes()).hexdigest()
        except OSError:
            return None

    def _confidence_bucket(self, score: float | None) -> str:
        if score is None:
            return "unknown"
        if score >= 0.85:
            return "high"
        if score >= self.confidence_threshold:
            return "medium"
        return "low"

    def _rank_results(
        self, results: list[AnalysisResultDict]
    ) -> list[AnalysisResultDict]:
        def sort_score(result: AnalysisResultDict) -> float:
            score = coerce_float(result.get("confidence_score"))
            return score if score is not None else -1.0

        def round_score_value(value: float | None) -> float | None:
            return round_score(value)

        sorted_results = sorted(
            results,
            key=sort_score,
            reverse=True,
        )
        ranked: list[AnalysisResultDict] = []
        for idx, result in enumerate(sorted_results, start=1):
            score = coerce_float(result.get("confidence_score"))
            enriched: AnalysisResultDict = {**result}
            if score is not None:
                enriched["confidence_score"] = round_score_value(score)
            impact_confidence = coerce_float(result.get("impact_confidence"))
            if impact_confidence is not None:
                enriched["impact_confidence"] = round_score_value(
                    impact_confidence
                )
            yake_overlap = coerce_float(result.get("yake_overlap"))
            if yake_overlap is not None:
                enriched["yake_overlap"] = round_score_value(yake_overlap)
            source_meta = enriched.get("source_metadata")
            if isinstance(source_meta, dict):
                enriched["source_metadata"] = self._round_metadata_scores(
                    source_meta
                )
            enriched["rank"] = idx
            enriched["confidence_bucket"] = self._confidence_bucket(score)
            ranked.append(enriched)
        return ranked

    @classmethod
    def _round_metadata_scores(cls, metadata: MetadataRecord) -> MetadataRecord:
        rounded: dict[str, MetadataValue] = {}
        for key, value in metadata.items():
            if isinstance(key, str):
                rounded[key] = cls._round_metadata_value(key, value)
        return rounded

    @classmethod
    def _round_metadata_value(
        cls, key: str, value: MetadataValue
    ) -> MetadataValue:
        if isinstance(value, (int, float)) and cls._is_score_key(key):
            return round_score(value)
        if isinstance(value, (str, bool)) or value is None:
            return value
        if isinstance(value, dict):
            if cls._is_dict_list_map(value):
                return cls._round_metadata_dict_list(
                    cls._as_dict_list_map(value)
                )
            return cls._round_metadata_dict(cls._as_dict_scalar_map(value))
        if isinstance(value, list):
            return cls._round_metadata_list(key, value)
        return value

    @classmethod
    def _round_metadata_dict(
        cls, value: dict[str, MetadataScalar]
    ) -> dict[str, MetadataScalar]:
        nested: dict[str, MetadataScalar] = {}
        for nested_key, nested_value in value.items():
            if isinstance(nested_value, (int, float)) and cls._is_score_key(
                nested_key
            ):
                nested[nested_key] = round_score(nested_value)
            else:
                nested[nested_key] = nested_value
        return nested

    @classmethod
    def _round_metadata_dict_list(
        cls, value: dict[str, list[dict[str, MetadataScalar]]]
    ) -> dict[str, list[dict[str, MetadataScalar]]]:
        nested: dict[str, list[dict[str, MetadataScalar]]] = {}
        for nested_key, nested_value in value.items():
            if isinstance(nested_value, list):
                nested[nested_key] = [
                    cls._round_metadata_dict(item)
                    for item in nested_value
                    if isinstance(item, dict)
                ]
        return nested

    @staticmethod
    def _is_dict_list_map(value: MetadataMap) -> bool:
        if not value:
            return False
        for item in value.values():
            if isinstance(item, list):
                return True
        return False

    @staticmethod
    def _as_dict_scalar_map(
        value: MetadataMap,
    ) -> dict[str, MetadataScalar]:
        return {
            key: item
            for key, item in value.items()
            if isinstance(item, (str, int, float, bool)) or item is None
        }

    @staticmethod
    def _as_dict_list_map(
        value: MetadataMap,
    ) -> dict[str, list[dict[str, MetadataScalar]]]:
        filtered: dict[str, list[dict[str, MetadataScalar]]] = {}
        for key, item in value.items():
            if not isinstance(item, list):
                continue
            filtered[key] = [
                {
                    nested_key: nested_value
                    for nested_key, nested_value in entry.items()
                    if isinstance(nested_value, (str, int, float, bool))
                    or nested_value is None
                }
                for entry in item
                if isinstance(entry, dict)
            ]
        return filtered

    @classmethod
    def _round_metadata_list(
        cls,
        key: str,
        value: list[MetadataScalar] | list[dict[str, MetadataScalar]],
    ) -> list[MetadataScalar] | list[dict[str, MetadataScalar]]:
        if not value:
            return value
        if isinstance(value[0], dict):
            return [
                cls._round_metadata_dict(item)
                for item in value
                if isinstance(item, dict)
            ]
        rounded: list[MetadataScalar] = []
        for item in value:
            if isinstance(item, (int, float)) and cls._is_score_key(key):
                rounded.append(round_score(item))
            elif isinstance(item, (str, bool)) or item is None:
                rounded.append(item)
        return rounded

    @staticmethod
    def _is_score_key(key: str) -> bool:
        return is_score_key(key)

    @staticmethod
    def _extract_queries(result: AnalysisResultDict) -> list[str]:
        matched_queries = result.get("matched_queries")
        if not isinstance(matched_queries, list):
            return []
        queries: list[str] = []
        seen: set[str] = set()
        for item in matched_queries:
            if not isinstance(item, dict):
                continue
            query = item.get("query")
            if not isinstance(query, str):
                continue
            cleaned = query.strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            queries.append(cleaned)
        return queries

    @staticmethod
    def _extract_section(result: AnalysisResultDict) -> str | None:
        metadata = result.get("source_metadata") or {}
        section = metadata.get("section_number")
        if isinstance(section, (int, float)):
            return str(section)
        if isinstance(section, str):
            cleaned = section.strip()
            return cleaned if cleaned else None
        return None

    def _group_by_query(
        self, results: list[AnalysisResultDict]
    ) -> dict[str, list[AnalysisResultDict]]:
        grouped: dict[str, list[AnalysisResultDict]] = {}
        for result in results:
            for query in self._extract_queries(result):
                grouped.setdefault(query, []).append(result)
        return grouped

    def _group_by_section(
        self, results: list[AnalysisResultDict]
    ) -> dict[str, list[AnalysisResultDict]]:
        grouped: dict[str, list[AnalysisResultDict]] = {}
        for result in results:
            section = self._extract_section(result)
            if section is None:
                continue
            grouped.setdefault(section, []).append(result)
        return grouped

    @staticmethod
    def _timeline_sort_key(item: JsonDict) -> str:
        value = item.get("filed_date")
        return value if isinstance(value, str) else ""

    def _build_relationship_timeline(
        self,
        filing_meta: MetadataMap,
    ) -> dict[str, list[JsonDict]]:
        related = filing_meta.get("related_filings")
        if not isinstance(related, list):
            return {}
        grouped: dict[str, list[JsonDict]] = {}
        for item in related:
            if not isinstance(item, dict):
                continue
            relation_type = item.get("relation_type")
            if not isinstance(relation_type, str):
                continue
            record: JsonDict = {}
            for key, value in item.items():
                if isinstance(key, str):
                    record[key] = value
            grouped.setdefault(relation_type, []).append(record)
        for relation_type, items in grouped.items():
            items.sort(key=self._timeline_sort_key, reverse=True)
            grouped[relation_type] = items
        return grouped

    def build_output(
        self,
        symbol: str,
        filing_meta: MetadataMap,
        analysis_results: list[AnalysisResultDict],
        relevant_results: list[AnalysisResultDict],
        search_queries: list[str] | None = None,
        timings: dict[str, float] | None = None,
        market_data: MarketEnrichment | None = None,
        market_context: str | None = None,
        market_correlation: JsonDict | None = None,
    ) -> AnalysisOutput:
        """Build structured output from analysis results.

        Args:
            symbol: Stock ticker symbol
            filing_meta: Filing metadata
            analysis_results: All analysis results (including failures)
            relevant_results: Filtered relevant results
            timings: Optional timing breakdown
            market_data: Optional market enrichment metadata to attach to the output
            market_context: Legacy correlation string (ignored; kept for compatibility)

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

        ranked_results = self._rank_results(relevant_results)

        # Build aggregates
        aggregates = self._build_aggregates(relevant_results)

        # Build executive summary
        top_tags = list(aggregates.tag_frequency.keys())[:5]
        top_topics = list(aggregates.topic_hits_frequency.keys())[:5]

        # Extract key points (deduplicated, top 5)
        key_points: list[str] = []
        for r in ranked_results:
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
        rounded_timings = (
            {key: round_timing(value) or 0.0 for key, value in timings.items()}
            if isinstance(timings, dict)
            else {}
        )
        diagnostics = AnalysisDiagnostics(
            chunks_analyzed=total_chunks,
            chunks_successful=successful,
            chunks_failed=failed,
            chunks_relevant=relevant_count,
            success_rate=(successful / total_chunks) if total_chunks else 0.0,
            relevant_rate=(relevant_count / total_chunks)
            if total_chunks
            else 0.0,
            timings=rounded_timings,
            confidence_threshold=self.confidence_threshold,
        )

        provenance = OutputProvenance(
            run_id=self.run_id,
            pipeline_version=self.pipeline_version,
            model_name=self.model_name,
            confidence_mode=self.confidence_mode,
            prompt_path=str(self.prompt_path)
            if self.prompt_path is not None
            else None,
            prompt_version=self.prompt_version,
        )

        # Build filing info
        filing = FilingInfo(
            accession_number=get_meta_str(filing_meta, "accession_number"),
            form_type=get_meta_str_any(
                filing_meta, ("form_type", "form", "formType")
            ),
            acceptance_date=get_meta_str_any(
                filing_meta,
                (
                    "acceptance_date",
                    "accepted_date",
                    "filed_date",
                    "filing_date",
                ),
            ),
            filing_date=get_meta_str_any(
                filing_meta, ("filing_date", "filed_date")
            ),
        )
        relationship_timeline = self._build_relationship_timeline(filing_meta)
        executive_comp_summary = self._build_exec_comp_summary(ranked_results)
        return AnalysisOutput(
            symbol=symbol,
            search_queries=search_queries or [],
            filing=filing,
            executive_summary=executive_summary,
            executive_comp_summary=executive_comp_summary,
            aggregates=aggregates,
            diagnostics=diagnostics,
            provenance=provenance,
            market_enrichment=market_data,
            market_correlation=market_correlation,
            results=ranked_results,
            results_by_query=self._group_by_query(ranked_results),
            results_by_section=self._group_by_section(ranked_results),
            relationship_timeline=relationship_timeline,
        )

    def _build_exec_comp_summary(
        self, results: list[AnalysisResultDict]
    ) -> ExecutiveCompSummary | None:
        if not results:
            return None

        executives: list[JsonDict] = []
        compensation_items: list[JsonDict] = []
        performance_metrics: list[JsonValue] = []
        peer_set: list[JsonValue] = []
        pay_flags: list[JsonValue] = []
        notes: list[JsonValue] = []

        seen_execs: set[int] = set()
        seen_comp: set[int] = set()
        seen_metrics: set[int] = set()
        seen_peers: set[int] = set()
        seen_flags: set[int] = set()
        seen_notes: set[int] = set()

        def _key_hash(value: JsonValue) -> int | None:
            if isinstance(value, str):
                cleaned = value.strip().lower()
                return hash(cleaned) if cleaned else None
            if isinstance(value, (int, float, bool)):
                return hash(value)
            try:
                encoded = json.dumps(value, sort_keys=True, ensure_ascii=True)
            except Exception:
                return None
            return hash(encoded)

        def _append_unique(
            bucket: list[JsonValue], seen: set[int], value: JsonValue
        ) -> None:
            key = _key_hash(value)
            if key is None or key in seen:
                return
            seen.add(key)
            bucket.append(value)

        def _append_unique_dict(
            bucket: list[JsonDict], seen: set[int], value: JsonValue
        ) -> None:
            mapping = coerce_json_dict(value)
            if mapping is None:
                return
            key = _key_hash(mapping)
            if key is None or key in seen:
                return
            seen.add(key)
            bucket.append(mapping)

        has_comp_data = False

        for result in results:
            entities = coerce_json_dict(result.get("extracted_entities"))
            if entities is not None:
                exec_list = entities.get("executives")
                if isinstance(exec_list, list):
                    for entry in exec_list:
                        entry_dict = coerce_json_dict(entry)
                        if entry_dict is None:
                            continue
                        name_value = entry_dict.get("name")
                        name_key = (
                            _key_hash(name_value)
                            if isinstance(name_value, str)
                            else None
                        )
                        if name_key is not None and name_key in seen_execs:
                            continue
                        if name_key is not None:
                            seen_execs.add(name_key)
                        executives.append(entry_dict)
                        has_comp_data = True

            comp_data = result.get("compensation_data")
            if comp_data is not None:
                _append_unique_dict(compensation_items, seen_comp, comp_data)
                if compensation_items:
                    has_comp_data = True

            metrics = result.get("performance_metrics")
            if isinstance(metrics, list):
                for metric in metrics:
                    _append_unique(performance_metrics, seen_metrics, metric)
                if performance_metrics:
                    has_comp_data = True

            peers = result.get("peer_set")
            if isinstance(peers, list):
                for peer in peers:
                    _append_unique(peer_set, seen_peers, peer)
                if peer_set:
                    has_comp_data = True

            flags = result.get("pay_for_performance_flags")
            if isinstance(flags, list):
                for flag in flags:
                    _append_unique(pay_flags, seen_flags, flag)
                if pay_flags:
                    has_comp_data = True

            summary = result.get("summary")
            if isinstance(summary, str):
                cleaned = summary.strip()
                if cleaned:
                    _append_unique(notes, seen_notes, cleaned)

        if not has_comp_data:
            return None

        return ExecutiveCompSummary(
            executives=executives,
            compensation_items=compensation_items,
            performance_metrics=performance_metrics,
            peer_set=peer_set,
            pay_for_performance_flags=pay_flags,
            notes=notes,
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
            topic_hits_frequency=dict(
                sorted(
                    topic_hit_counts.items(),
                    key=lambda t: t[1],
                    reverse=True,
                )
            ),
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
        payload = serialize_payload(output, exclude_none=True)

        # Convert to dict for export
        # Export JSON
        if self.export_format in ("json", "both"):
            json_file = accession_dir / f"{base_name}.json"
            write_json(json_file, output, payload=payload)
            output_files.append(json_file)
            logger.debug("Analysis results written to %s", json_file)

        # Export YAML
        if self.export_format in ("yaml", "yaml_csv"):
            yaml_file = accession_dir / f"{base_name}.yaml"
            write_yaml(yaml_file, output, payload=payload, sort_keys=False)
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
