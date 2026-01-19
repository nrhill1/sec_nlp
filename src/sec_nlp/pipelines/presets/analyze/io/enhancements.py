# src/sec_nlp/pipelines/presets/analyze/io/enhancements.py
"""Analysis enhancement outputs for sentiment trends and comparisons."""

from __future__ import annotations

import json
import re
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

_EXEC_COMP_TAGS = {
    "executive_compensation",
    "director_compensation",
    "equity_compensation",
    "say_on_pay",
}

_AMOUNT_RE = re.compile(
    r"(?P<value>\d+(?:,\d{3})*(?:\.\d+)?)\s*(?P<unit>million|billion|thousand|m|bn|k)?",
    re.IGNORECASE,
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


def write_executive_comp_summary(
    *,
    output_dir: Path,
    symbol,
    run_id,
    analysis_results: list[AnalysisResultDict],
    relevant_results: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
) -> Path | None:
    summary = build_executive_comp_summary(
        symbol=symbol,
        run_id=run_id,
        analysis_results=analysis_results,
        relevant_results=relevant_results,
        fallback_meta=fallback_meta,
    )
    if not summary:
        return None
    output_path = output_dir / "executive_compensation.yaml"
    write_yaml(output_path, summary, sort_keys=False)
    logger.info("Executive compensation summary written to %s", output_path)
    return output_path


def build_executive_comp_summary(
    *,
    symbol,
    run_id,
    analysis_results: list[AnalysisResultDict],
    relevant_results: list[AnalysisResultDict],
    fallback_meta: MetadataRecord,
) -> JsonDict:
    if not relevant_results:
        return {}

    grouped = group_results_by_accession(relevant_results, fallback_meta)
    filings: list[JsonDict] = []
    for accession, results_for_filing in grouped.items():
        meta = _select_filing_meta(
            results_for_filing=results_for_filing,
            fallback_meta=fallback_meta,
            accession=accession,
        )
        filing_entry = _build_exec_comp_filing_entry(
            accession=accession,
            results_for_filing=results_for_filing,
            meta=meta,
        )
        if filing_entry:
            filings.append(filing_entry)

    if not filings:
        return {}

    yoy_changes = _build_exec_comp_yoy(filings)
    peer_deltas = _build_exec_comp_peer_deltas(filings)

    summary: JsonDict = {
        "symbol": symbol,
        "run_id": run_id,
        "filings": filings,
        "yoy_changes": yoy_changes,
        "peer_deltas": peer_deltas,
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


def _coerce_amount(value: JsonValue) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.replace(",", "").strip()
    if not cleaned:
        return None
    match = _AMOUNT_RE.search(cleaned)
    if match is None:
        return None
    raw_value = match.group("value")
    unit = (match.group("unit") or "").lower()
    try:
        numeric = float(raw_value.replace(",", ""))
    except ValueError:
        return None
    multiplier = 1.0
    if unit in ("m", "million"):
        multiplier = 1_000_000.0
    elif unit in ("bn", "billion"):
        multiplier = 1_000_000_000.0
    elif unit in ("k", "thousand"):
        multiplier = 1_000.0
    return numeric * multiplier


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


def _build_exec_comp_filing_entry(
    *,
    accession,
    results_for_filing: list[AnalysisResultDict],
    meta: MetadataRecord,
) -> JsonDict:
    executives: list[JsonDict] = []
    compensation_items: list[JsonDict] = []
    performance_metrics: list[JsonValue] = []
    peer_set: list[JsonValue] = []
    pay_flags: list[JsonValue] = []

    seen_execs: set[int] = set()
    seen_comp: set[int] = set()
    seen_metrics: set[int] = set()
    seen_peers: set[int] = set()
    seen_flags: set[int] = set()

    has_exec_comp = False

    for result in results_for_filing:
        tags = result.get("tags") or []
        if isinstance(tags, list):
            for tag in tags:
                if (
                    isinstance(tag, str)
                    and tag.strip().lower() in _EXEC_COMP_TAGS
                ):
                    has_exec_comp = True
                    break

        entities = coerce_json_dict(result.get("extracted_entities"))
        if entities is not None:
            exec_list = entities.get("executives")
            if isinstance(exec_list, list):
                for entry in exec_list:
                    entry_dict = coerce_json_dict(entry)
                    if entry_dict is None:
                        continue
                    name_value = entry_dict.get("name")
                    name_key = _key_hash(name_value)
                    if name_key is not None and name_key in seen_execs:
                        continue
                    if name_key is not None:
                        seen_execs.add(name_key)
                    executives.append(entry_dict)
                    has_exec_comp = True

        comp_data = coerce_json_dict(result.get("compensation_data"))
        if comp_data is not None:
            key = _key_hash(comp_data)
            if key is None:
                continue
            if key not in seen_comp:
                seen_comp.add(key)
                compensation_items.append(comp_data)
                has_exec_comp = True

        metrics = result.get("performance_metrics")
        if isinstance(metrics, list):
            for metric in metrics:
                key = _key_hash(metric)
                if key is None:
                    continue
                if key in seen_metrics:
                    continue
                seen_metrics.add(key)
                performance_metrics.append(metric)
                has_exec_comp = True

        peers = result.get("peer_set")
        if isinstance(peers, list):
            for peer in peers:
                key = _key_hash(peer)
                if key is None:
                    continue
                if key in seen_peers:
                    continue
                seen_peers.add(key)
                peer_set.append(peer)
                has_exec_comp = True

        flags = result.get("pay_for_performance_flags")
        if isinstance(flags, list):
            for flag in flags:
                key = _key_hash(flag)
                if key is None:
                    continue
                if key in seen_flags:
                    continue
                seen_flags.add(key)
                pay_flags.append(flag)
                has_exec_comp = True

    if not has_exec_comp:
        return {}

    filing_date = _extract_filing_date(meta)
    filing_entry: JsonDict = {
        "accession": accession,
        "filing_date": filing_date.isoformat()
        if filing_date is not None
        else None,
        "form_type": meta.get("form_type"),
        "executives": executives,
        "compensation_items": compensation_items,
        "performance_metrics": performance_metrics,
        "peer_set": peer_set,
        "pay_for_performance_flags": pay_flags,
    }
    return filing_entry


def _build_exec_comp_yoy(filings: list[JsonDict]) -> list[JsonDict]:
    if len(filings) < 2:
        return []

    ordered = sorted(filings, key=_exec_comp_sort_key)
    series_by_exec: dict[JsonValue, list[tuple[JsonValue, float]]] = {}

    for entry in ordered:
        exec_list = entry.get("executives")
        if not isinstance(exec_list, list):
            continue
        filing_date = entry.get("filing_date")
        if not isinstance(filing_date, str) or not filing_date:
            continue
        for exec_entry in exec_list:
            exec_dict = coerce_json_dict(exec_entry)
            if exec_dict is None:
                continue
            name_value = exec_dict.get("name")
            if not isinstance(name_value, str) or not name_value.strip():
                continue
            comp_value = exec_dict.get("compensation")
            total = _coerce_amount(comp_value)
            if total is None:
                continue
            series_by_exec.setdefault(name_value, []).append(
                (filing_date, total)
            )

    changes: list[JsonDict] = []
    for exec_name, series in series_by_exec.items():
        series.sort(key=lambda item: item[0])
        for idx in range(1, len(series)):
            prev_date, prev_total = series[idx - 1]
            next_date, next_total = series[idx]
            delta = next_total - prev_total
            pct = None
            if prev_total != 0:
                pct = delta / prev_total
            changes.append(
                {
                    "name": exec_name,
                    "from_date": prev_date,
                    "to_date": next_date,
                    "from_total": prev_total,
                    "to_total": next_total,
                    "delta": delta,
                    "percent_change": pct,
                }
            )
    return changes


def _exec_comp_sort_key(item: JsonDict) -> tuple[int, JsonValue]:
    raw_date = item.get("filing_date")
    parsed = _parse_date_value(raw_date)
    if parsed is not None:
        return (0, parsed.isoformat())
    accession_value = item.get("accession")
    return (1, accession_value if accession_value is not None else "")


def _collect_peer_map(peers_value: JsonValue) -> dict[int, JsonValue]:
    peers: dict[int, JsonValue] = {}
    if isinstance(peers_value, list):
        candidates = peers_value
    elif peers_value is None:
        return peers
    else:
        candidates = [peers_value]
    for candidate in candidates:
        key = _key_hash(candidate)
        if key is None or key in peers:
            continue
        peers[key] = candidate
    return peers


def _build_exec_comp_peer_deltas(filings: list[JsonDict]) -> list[JsonDict]:
    if len(filings) < 2:
        return []
    ordered = sorted(filings, key=_exec_comp_sort_key)
    deltas: list[JsonDict] = []
    for previous, current in zip(ordered, ordered[1:], strict=False):
        previous_map = _collect_peer_map(previous.get("peer_set"))
        current_map = _collect_peer_map(current.get("peer_set"))
        added_keys = set(current_map) - set(previous_map)
        removed_keys = set(previous_map) - set(current_map)
        if not added_keys and not removed_keys:
            continue
        added = [current_map[key] for key in added_keys]
        removed = [previous_map[key] for key in removed_keys]
        added_sorted = sorted(added, key=lambda item: str(item))
        removed_sorted = sorted(removed, key=lambda item: str(item))
        deltas.append(
            {
                "from_accession": previous.get("accession"),
                "to_accession": current.get("accession"),
                "from_date": previous.get("filing_date"),
                "to_date": current.get("filing_date"),
                "added": added_sorted,
                "removed": removed_sorted,
            }
        )
    return deltas


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
