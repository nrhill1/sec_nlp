# src/sec_nlp/pipelines/presets/analyze/io/enhancements.py
"""Analysis enhancement outputs for sentiment trends and comparisons."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.types import coerce_json_dict
from sec_nlp.pipelines.metadata.accession import group_results_by_accession
from sec_nlp.pipelines.output_io import write_yaml
from sec_nlp.pipelines.presets.analyze.market import _parse_date_value
from sec_nlp.pipelines.types import AnalysisResultDict, MetadataRecord
from sec_nlp.types import JsonDict, JsonValue

_DATE_KEYS = (
    "filing_date",
    "acceptance_date",
    "period_end",
    "period_of_report",
    "document_date",
)

_SENTIMENT_SCORE_MAP = {
    "positive": 1.0,
    "bullish": 1.0,
    "negative": -1.0,
    "bearish": -1.0,
    "neutral": 0.0,
}

_ENTITY_NAME_KEYS = (
    "name",
    "issuer",
    "company",
    "symbol",
    "ticker",
    "cusip",
)


def write_symbol_summary(
    *,
    output_dir: Path,
    symbol,
    run_id,
    analysis_results: list[AnalysisResultDict],
    relevant_results: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
) -> Path | None:
    summary = build_symbol_summary(
        symbol=symbol,
        run_id=run_id,
        analysis_results=analysis_results,
        relevant_results=relevant_results,
        fallback_meta=fallback_meta,
    )
    if not summary:
        return None
    output_path = output_dir / "analysis_summary.yaml"
    write_yaml(output_path, summary, sort_keys=False)
    logger.info("Analysis summary written to %s", output_path)
    return output_path


def build_symbol_summary(
    *,
    symbol,
    run_id,
    analysis_results: list[AnalysisResultDict],
    relevant_results: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
) -> JsonDict:
    summary: JsonDict = {
        "symbol": symbol,
        "run_id": run_id,
        "sentiment_trends": build_sentiment_trends(
            results=relevant_results,
            fallback_meta=fallback_meta,
        ),
        "entity_rollup": build_entity_rollup(relevant_results),
        "filing_comparisons": build_filing_comparisons(
            relevant_results, fallback_meta
        ),
    }
    if analysis_results:
        summary["total_chunks"] = len(analysis_results)
    if relevant_results:
        summary["relevant_chunks"] = len(relevant_results)
    return summary


def build_sentiment_trends(
    *,
    results: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
) -> list[JsonDict]:
    if not results:
        return []
    grouped = group_results_by_accession(results, fallback_meta)
    rows: list[JsonDict] = []
    for accession, accession_results in grouped.items():
        meta = _select_filing_meta(
            results_for_filing=accession_results,
            fallback_meta=fallback_meta,
            accession=accession,
        )
        filing_date = _extract_filing_date(meta)
        sentiment_counts, net_sentiment, dominant = _aggregate_sentiment(
            accession_results
        )
        row: JsonDict = {
            "accession": accession,
            "filing_date": filing_date.isoformat()
            if filing_date is not None
            else None,
            "form_type": meta.get("form_type"),
            "sentiment_breakdown": sentiment_counts,
            "net_sentiment": net_sentiment,
            "dominant_sentiment": dominant,
            "relevant_chunks": len(accession_results),
        }
        rows.append(row)

    rows.sort(key=_trend_sort_key)
    return rows


def _trend_sort_key(row: JsonDict) -> tuple[int, JsonValue]:
    value = row.get("filing_date")
    if isinstance(value, str) and value:
        return (0, value)
    accession = row.get("accession")
    return (1, accession if accession is not None else "")


def _select_filing_meta(
    *,
    results_for_filing: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
    accession,
) -> MetadataRecord:
    if results_for_filing:
        meta: MetadataRecord = (
            results_for_filing[0].get("source_metadata") or {}
        )
    else:
        meta = {}
    merged_meta: MetadataRecord = {**fallback_meta, **meta}
    if accession and merged_meta.get("accession_number") is None:
        merged_meta["accession_number"] = accession
    return merged_meta


def _extract_filing_date(meta: MetadataRecord) -> date | None:
    for key in _DATE_KEYS:
        parsed = _parse_date_value(meta.get(key))
        if parsed is not None:
            return parsed
    source_meta = meta.get("source_metadata")
    if isinstance(source_meta, dict):
        for key in _DATE_KEYS:
            parsed = _parse_date_value(source_meta.get(key))
            if parsed is not None:
                return parsed
    return None


def _aggregate_sentiment(
    results: list[AnalysisResultDict],
) -> tuple[JsonDict, float | None, JsonValue]:
    counts: Counter = Counter()
    for result in results:
        sentiment = result.get("sentiment")
        if isinstance(sentiment, str):
            cleaned = sentiment.strip().lower()
            if cleaned:
                counts[cleaned] += 1

    sentiment_counts: JsonDict = dict(counts)
    if not sentiment_counts:
        return sentiment_counts, None, None

    score_sum = 0.0
    total_scored = 0
    for label, count in counts.items():
        weight = _SENTIMENT_SCORE_MAP.get(label)
        if weight is None:
            continue
        score_sum += weight * count
        total_scored += count
    net_sentiment = score_sum / total_scored if total_scored > 0 else None
    dominant = counts.most_common(1)[0][0] if counts else None
    return sentiment_counts, net_sentiment, dominant


def _extract_entity_names(value: JsonValue) -> list:
    names: list = []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, dict):
        mapping = coerce_json_dict(value)
        if mapping is None:
            return names
        for key in _ENTITY_NAME_KEYS:
            candidate = mapping.get(key)
            if isinstance(candidate, str):
                cleaned = candidate.strip()
                if cleaned:
                    names.append(cleaned)
        if names:
            return names
        for item in mapping.values():
            names.extend(_extract_entity_names(item))
        return names
    if isinstance(value, list):
        for item in value:
            names.extend(_extract_entity_names(item))
    return names


def build_entity_rollup(
    results: list[AnalysisResultDict],
    *,
    top_n: int = 10,
) -> JsonDict:
    if not results:
        return {}
    counts_by_type: dict = defaultdict(Counter)
    for result in results:
        if "extracted_entities" not in result:
            continue
        entities = result["extracted_entities"]
        entities_dict = coerce_json_dict(entities)
        if entities_dict is None:
            continue
        for entity_type, value in entities_dict.items():
            for name in _extract_entity_names(value):
                counts_by_type[entity_type][name] += 1

    rollup: JsonDict = {}
    total_unique = 0
    for entity_type, counter in counts_by_type.items():
        if not counter:
            continue
        entries: list[JsonDict] = []
        for name, count in counter.most_common(top_n):
            entries.append({"entity": name, "count": count})
        total_unique += len(counter)
        rollup[entity_type] = {
            "unique": len(counter),
            "top": entries,
        }
    if rollup:
        rollup["total_unique"] = total_unique
    return rollup


def build_filing_comparisons(
    results: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
) -> list[JsonDict]:
    if not results:
        return []
    grouped = group_results_by_accession(results, fallback_meta)
    if len(grouped) < 2:
        return []

    filing_summaries: list[JsonDict] = []
    for accession, accession_results in grouped.items():
        meta = _select_filing_meta(
            results_for_filing=accession_results,
            fallback_meta=fallback_meta,
            accession=accession,
        )
        filing_date = _extract_filing_date(meta)
        tags = _collect_unique_values(accession_results, "tags")
        channels = _collect_unique_values(accession_results, "impact_channels")
        sentiment_counts, net_sentiment, dominant = _aggregate_sentiment(
            accession_results
        )
        filing_summaries.append(
            {
                "accession": accession,
                "filing_date": filing_date.isoformat()
                if filing_date is not None
                else None,
                "tags": sorted(tags),
                "impact_channels": sorted(channels),
                "sentiment_breakdown": sentiment_counts,
                "net_sentiment": net_sentiment,
                "dominant_sentiment": dominant,
            }
        )

    filing_summaries.sort(key=_trend_sort_key)
    comparisons: list[JsonDict] = []
    for previous, current in zip(
        filing_summaries, filing_summaries[1:], strict=False
    ):
        previous_tags = set(previous.get("tags") or [])
        current_tags = set(current.get("tags") or [])
        previous_channels = set(previous.get("impact_channels") or [])
        current_channels = set(current.get("impact_channels") or [])
        previous_score = previous.get("net_sentiment")
        current_score = current.get("net_sentiment")
        sentiment_shift = None
        if isinstance(previous_score, (int, float)) and isinstance(
            current_score, (int, float)
        ):
            sentiment_shift = current_score - previous_score
        comparisons.append(
            {
                "old_accession": previous.get("accession"),
                "new_accession": current.get("accession"),
                "old_date": previous.get("filing_date"),
                "new_date": current.get("filing_date"),
                "tags_added": sorted(current_tags - previous_tags),
                "tags_removed": sorted(previous_tags - current_tags),
                "impact_channels_added": sorted(
                    current_channels - previous_channels
                ),
                "impact_channels_removed": sorted(
                    previous_channels - current_channels
                ),
                "sentiment_shift": sentiment_shift,
            }
        )
    return comparisons


def _collect_unique_values(results: list[AnalysisResultDict], field) -> set:
    values: set = set()
    for result in results:
        items = result.get(field)
        if isinstance(items, list):
            for item in items:
                if isinstance(item, str) and item:
                    values.add(item)
        elif isinstance(items, str) and items:
            values.add(items)
    return values


def build_symbol_profile(
    *,
    symbol,
    results: list[AnalysisResultDict],
) -> JsonDict:
    tags = Counter()
    sentiments = Counter()
    topics = Counter()
    impact_channels = Counter()
    for result in results:
        for tag in result.get("tags") or []:
            if isinstance(tag, str):
                tags[tag] += 1
        sentiment = result.get("sentiment")
        if isinstance(sentiment, str) and sentiment:
            sentiments[sentiment] += 1
        for channel in result.get("impact_channels") or []:
            if isinstance(channel, str):
                impact_channels[channel] += 1
        topic_hits = (result.get("source_metadata") or {}).get("topic_hits")
        if isinstance(topic_hits, list):
            for topic in topic_hits:
                if isinstance(topic, str):
                    topics[topic] += 1
        elif isinstance(topic_hits, str) and topic_hits:
            topics[topic_hits] += 1

    return {
        "symbol": symbol,
        "relevant_chunks": len(results),
        "top_tags": [tag for tag, _ in tags.most_common(5)],
        "top_topics": [topic for topic, _ in topics.most_common(5)],
        "sentiment_breakdown": dict(sentiments),
        "impact_channel_frequency": dict(impact_channels.most_common(10)),
    }


def build_peer_comparison(profiles: dict) -> JsonDict:
    if not profiles:
        return {}
    common_tags = _common_items(
        [set(profile.get("top_tags") or []) for profile in profiles.values()]
    )
    sentiment_rank: list[JsonDict] = []
    for symbol, profile in profiles.items():
        breakdown = profile.get("sentiment_breakdown")
        if not isinstance(breakdown, dict):
            breakdown = {}
        net_sentiment = _compute_net_sentiment(breakdown)
        sentiment_rank.append(
            {
                "symbol": symbol,
                "net_sentiment": net_sentiment,
                "relevant_chunks": profile.get("relevant_chunks", 0),
            }
        )
    sentiment_rank.sort(
        key=lambda item: item.get("net_sentiment") or 0, reverse=True
    )
    return {
        "symbols": sorted(profiles.keys()),
        "profiles": profiles,
        "common_tags": sorted(common_tags),
        "sentiment_rank": sentiment_rank,
    }


def write_peer_summary(
    *,
    output_dir: Path,
    summary: JsonDict,
) -> Path | None:
    if not summary:
        return None
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "peer_summary.yaml"
    write_yaml(output_path, summary, sort_keys=False)
    logger.info("Peer comparison summary written to %s", output_path)
    return output_path


def _common_items(sets: list[set]) -> set:
    if not sets:
        return set()
    common = sets[0].copy()
    for item_set in sets[1:]:
        common &= item_set
    return common


def _compute_net_sentiment(breakdown: JsonValue) -> float | None:
    if not isinstance(breakdown, dict):
        return None
    total_scored = 0
    score_sum = 0.0
    for label, count in breakdown.items():
        if not isinstance(label, str):
            continue
        if not isinstance(count, (int, float)):
            continue
        weight = _SENTIMENT_SCORE_MAP.get(label.lower())
        if weight is None:
            continue
        score_sum += weight * float(count)
        total_scored += int(count)
    if total_scored <= 0:
        return None
    return score_sum / total_scored
