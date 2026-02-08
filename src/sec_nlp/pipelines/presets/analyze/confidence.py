# src/sec_nlp/pipelines/presets/analyze/confidence.py
"""Confidence scoring helpers for analyze pipeline results."""

from __future__ import annotations

import re
from statistics import mean

from sec_nlp.core.types import coerce_json_dict
from sec_nlp.pipelines.serialization import round_score
from sec_nlp.pipelines.types import AnalysisResultDict
from sec_nlp.types import JsonDict

from .utils import normalize_query_terms

_NUMERIC_SIGNAL_RE = re.compile(r"[$€£]?\d")


def compute_market_confidence_signal(
    market_correlation: JsonDict | None,
) -> float | None:
    if market_correlation is None:
        return None
    metrics_value = market_correlation.get("metrics")
    metrics = coerce_json_dict(metrics_value)
    if metrics is None:
        return None

    scores: list[float] = []
    for key in ("car_post5", "car_post30", "car_pre5"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            scores.append(min(abs(float(value)) / 0.1, 1.0))

    volume_spike = metrics.get("volume_spike")
    if isinstance(volume_spike, (int, float)):
        spike = max(float(volume_spike) - 1.0, 0.0)
        scores.append(min(spike / 1.5, 1.0))

    volatility_change = metrics.get("volatility_change")
    if isinstance(volatility_change, (int, float)):
        scores.append(min(abs(float(volatility_change)) / 0.05, 1.0))

    if not scores:
        return None
    return float(mean(scores))


def score_query_relevance(result: AnalysisResultDict) -> float:
    matched = result.get("query_match_terms")
    missing = result.get("missing_query_terms")
    matched_count = len(matched) if isinstance(matched, list) else 0
    missing_count = len(missing) if isinstance(missing, list) else 0
    total = matched_count + missing_count
    if total == 0:
        return 0.0
    return matched_count / total


def score_match_strength(result: AnalysisResultDict) -> float | None:
    matched_queries = result.get("matched_queries")
    if not isinstance(matched_queries, list):
        return None
    scores: list[float] = []
    for item in matched_queries:
        if not isinstance(item, dict):
            continue
        score = item.get("score")
        if isinstance(score, (int, float)):
            scores.append(float(score))
    if not scores:
        return None
    best = max(scores)
    if best < 0:
        return 0.0
    return min(best, 1.0)


def collect_query_terms(result: AnalysisResultDict) -> list[str]:
    matched = result.get("query_match_terms")
    missing = result.get("missing_query_terms")
    terms: list[str] = []
    seen: set[str] = set()
    for item in (matched, missing):
        if not isinstance(item, list):
            continue
        for term in item:
            if not isinstance(term, str):
                continue
            cleaned = term.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            terms.append(cleaned)
    return terms


def extract_yake_terms(result: AnalysisResultDict) -> list[str]:
    source_meta = result.get("source_metadata")
    if not isinstance(source_meta, dict):
        return []
    yake_keywords = source_meta.get("yake_keywords")
    if not isinstance(yake_keywords, list):
        return []
    terms: list[str] = []
    seen: set[str] = set()
    for keyword in yake_keywords:
        if not isinstance(keyword, str):
            continue
        for term in normalize_query_terms(keyword, min_len=3):
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)
    return terms


def score_yake_overlap(result: AnalysisResultDict) -> float | None:
    query_terms = collect_query_terms(result)
    if not query_terms:
        return None
    yake_terms = extract_yake_terms(result)
    if not yake_terms:
        return None
    matches = [term for term in query_terms if term in yake_terms]
    return len(matches) / len(query_terms) if query_terms else None


def has_evidence(result: AnalysisResultDict) -> bool:
    evidence = result.get("evidence_spans")
    if isinstance(evidence, list) and evidence:
        return True
    excerpt = result.get("source_excerpt")
    return isinstance(excerpt, str) and excerpt.strip() != ""


def has_numeric_signal(result: AnalysisResultDict) -> bool:
    summary = result.get("summary")
    if isinstance(summary, str) and _NUMERIC_SIGNAL_RE.search(summary):
        return True
    key_points = result.get("key_points")
    if isinstance(key_points, list):
        joined = " ".join(str(item) for item in key_points)
        return _NUMERIC_SIGNAL_RE.search(joined) is not None
    return False


def derive_confidence_score(
    result: AnalysisResultDict,
    *,
    market_signal: float | None,
    yake_overlap: float | None = None,
) -> tuple[float, str]:
    query_relevance = score_query_relevance(result)
    match_strength = score_match_strength(result)
    if yake_overlap is None:
        yake_overlap = score_yake_overlap(result)
    evidence = has_evidence(result)
    numeric = has_numeric_signal(result)

    overlap_weight = (
        yake_overlap if yake_overlap is not None else query_relevance
    )
    base = 0.2 + (0.4 * overlap_weight)
    if match_strength is not None:
        base += 0.2 * match_strength
    if evidence:
        base += 0.1
    if numeric:
        base += 0.1

    if market_signal is not None and result.get("is_relevant"):
        base += 0.1 * market_signal

    if result.get("missing_query_terms"):
        base -= 0.1
    if not result.get("is_relevant"):
        base = min(base, 0.4)

    score = max(0.05, min(base, 0.99))

    rationale_parts = [
        f"yake_overlap={(yake_overlap if yake_overlap is not None else query_relevance):.2f}",
        f"match_score={(match_strength if match_strength is not None else 0.0):.2f}",
        f"evidence={'yes' if evidence else 'no'}",
        f"numeric={'yes' if numeric else 'no'}",
    ]
    if market_signal is not None:
        rationale_parts.append(f"market_signal={market_signal:.2f}")
    rationale = ", ".join(rationale_parts)
    return score, rationale


def apply_confidence_derivation(
    analysis_results: list[AnalysisResultDict],
    market_correlation: JsonDict | None,
) -> None:
    market_signal = compute_market_confidence_signal(market_correlation)
    for result in analysis_results:
        if result.get("error") or result.get("exception"):
            continue
        yake_overlap = score_yake_overlap(result)
        derived_score, rationale = derive_confidence_score(
            result,
            market_signal=market_signal,
            yake_overlap=yake_overlap,
        )
        existing = result.get("confidence_score")
        if isinstance(existing, (int, float)):
            result["confidence_score"] = round_score(
                min(float(existing), derived_score)
            )
        else:
            result["confidence_score"] = round_score(derived_score)
        result["confidence_rationale"] = rationale
        if yake_overlap is not None:
            result["yake_overlap"] = round_score(yake_overlap)
