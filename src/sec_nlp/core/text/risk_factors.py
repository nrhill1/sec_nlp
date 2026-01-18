# src/sec_nlp/core/text/risk_factors.py
"""Utilities for extracting and clustering risk factor statements."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from langchain_core.documents import Document
from simhash import Simhash

from sec_nlp.core.text.deduplication import SimHashConfig, SimHashDeduplicator
from sec_nlp.types import JsonDict, JsonValue

_HEADER_PATTERN = re.compile(r"^\s*(item\s+1a|risk\s+factors)\b", re.IGNORECASE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}")

_STOPWORDS = {
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "if",
    "in",
    "is",
    "it",
    "its",
    "may",
    "not",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "there",
    "these",
    "this",
    "to",
    "was",
    "we",
    "will",
    "with",
}


@dataclass(frozen=True)
class RiskFactorClusterConfig:
    """Configuration for risk factor clustering."""

    min_statement_length: int = 80
    max_statement_length: int = 1200
    min_token_count: int = 6
    dedupe_distance: int = 2
    cluster_distance: int = 4
    num_bits: int = 64
    min_cluster_size: int = 2


@dataclass
class _ClusterState:
    simhash: Simhash
    statements: list[JsonDict]
    hashes: list[Simhash]


def _normalize_text(text: JsonValue) -> JsonValue:
    if not isinstance(text, str):
        return text
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned


def _split_sentences(text: JsonValue) -> list[JsonValue]:
    if not isinstance(text, str):
        return []
    cleaned = _normalize_text(text)
    if not isinstance(cleaned, str) or not cleaned:
        return []
    sentences = _SENTENCE_SPLIT.split(cleaned)
    return [s.strip() for s in sentences if s.strip()]


def _split_statements(text: JsonValue) -> list[JsonValue]:
    if not isinstance(text, str):
        return []
    raw = text.replace("\r", "\n")
    blocks = re.split(r"\n{2,}", raw)
    statements: list[JsonValue] = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        if len(lines) == 1 and _HEADER_PATTERN.match(lines[0]):
            continue
        combined = _normalize_text(" ".join(lines))
        if not isinstance(combined, str) or not combined:
            continue
        sentences = _split_sentences(combined)
        if sentences:
            statements.extend(sentences)
        else:
            statements.append(combined)
    return statements


def _tokenize(text: JsonValue) -> list[JsonValue]:
    if not isinstance(text, str):
        return []
    tokens = _TOKEN_PATTERN.findall(text.lower())
    return [token for token in tokens if token not in _STOPWORDS]


def _build_cluster_label(statements: Sequence[JsonDict]) -> JsonValue:
    counter: Counter = Counter()
    for statement in statements:
        text = statement.get("statement")
        tokens = _tokenize(text)
        counter.update(tokens)
    if not counter:
        return "misc"
    top_tokens = [token for token, _count in counter.most_common(3)]
    return " ".join(top_tokens) if top_tokens else "misc"


def _statement_metadata(doc: Document) -> JsonDict:
    meta = doc.metadata or {}
    symbol = meta.get("symbol") or meta.get("ticker")
    accession = meta.get("accession_number") or meta.get("accession")
    form_type = meta.get("form_type") or meta.get("form")
    filed_date = meta.get("filed_date")
    source = meta.get("source") or meta.get("file_path")
    section_type = meta.get("section_type")
    section_number = meta.get("section_number")
    return {
        "symbol": symbol,
        "accession_number": accession,
        "form_type": form_type,
        "filed_date": filed_date,
        "source": source,
        "section_type": section_type,
        "section_number": section_number,
    }


def extract_risk_factor_statements(
    docs: Sequence[Document],
    *,
    config: RiskFactorClusterConfig | None = None,
) -> list[JsonDict]:
    """Extract clause-level risk factor statements from section docs."""
    config = config or RiskFactorClusterConfig()
    results: list[JsonDict] = []
    for doc in docs:
        statements = _split_statements(doc.page_content)
        if not statements:
            continue
        base_meta = _statement_metadata(doc)
        for statement in statements:
            normalized = _normalize_text(statement)
            if not isinstance(normalized, str):
                continue
            length = len(normalized)
            if length < config.min_statement_length:
                continue
            if length > config.max_statement_length:
                normalized = normalized[: config.max_statement_length].strip()
            tokens = _tokenize(normalized)
            if len(tokens) < config.min_token_count:
                continue
            results.append(
                {
                    "statement": normalized,
                    "normalized": normalized.lower(),
                    "token_count": len(tokens),
                    **base_meta,
                }
            )
    return results


def dedupe_risk_factor_statements(
    statements: Sequence[JsonDict],
    *,
    config: RiskFactorClusterConfig | None = None,
) -> list[JsonDict]:
    """Remove near-duplicate statements using SimHash."""
    config = config or RiskFactorClusterConfig()
    deduper = SimHashDeduplicator(
        SimHashConfig(
            num_bits=config.num_bits,
            max_distance=config.dedupe_distance,
        )
    )
    unique: list[JsonDict] = []
    for statement in statements:
        text = statement.get("normalized") or statement.get("statement")
        if not isinstance(text, str) or not text.strip():
            continue
        is_unique, hash_value = deduper.add_if_unique(text)
        if not is_unique:
            continue
        updated = dict(statement)
        updated["simhash"] = hash_value
        unique.append(updated)
    return unique


def cluster_risk_factors(
    statements: Sequence[JsonDict],
    *,
    config: RiskFactorClusterConfig | None = None,
) -> JsonDict:
    """Cluster risk factor statements using SimHash distance."""
    config = config or RiskFactorClusterConfig()
    clusters: list[_ClusterState] = []

    for statement in statements:
        text = statement.get("normalized") or statement.get("statement")
        tokens = _tokenize(text)
        if len(tokens) < config.min_token_count:
            continue
        simhash = Simhash(tokens, f=config.num_bits)

        assigned: _ClusterState | None = None
        for cluster in clusters:
            distance = simhash.distance(cluster.simhash)
            if distance <= config.cluster_distance:
                assigned = cluster
                break

        if assigned is None:
            clusters.append(
                _ClusterState(
                    simhash=simhash,
                    statements=[statement],
                    hashes=[simhash],
                )
            )
        else:
            assigned.statements.append(statement)
            assigned.hashes.append(simhash)

    clustered_statements: list[JsonDict] = []
    cluster_payloads: list[JsonDict] = []
    cluster_sizes: list[int] = []

    for idx, cluster in enumerate(clusters, start=1):
        cluster_statements = cluster.statements
        if not cluster_statements:
            continue
        label = _build_cluster_label(cluster_statements)
        symbol_counts: dict[str, int] = defaultdict(int)
        for statement in cluster_statements:
            symbol_value = statement.get("symbol")
            symbol = (
                symbol_value.strip().upper()
                if isinstance(symbol_value, str) and symbol_value.strip()
                else "unknown"
            )
            symbol_counts[symbol] += 1

        rep_hash = cluster.simhash
        distances: list[int] = []
        for stmt_hash in cluster.hashes:
            distances.append(rep_hash.distance(stmt_hash))
        avg_distance = sum(distances) / len(distances) if distances else 0.0

        cluster_size = len(cluster_statements)
        cluster_sizes.append(cluster_size)
        novelty = cluster_size < config.min_cluster_size
        examples = [
            stmt.get("statement")
            for stmt in cluster_statements[:2]
            if isinstance(stmt.get("statement"), str)
        ]

        cluster_payloads.append(
            {
                "cluster_id": idx,
                "label": label,
                "size": cluster_size,
                "avg_distance": avg_distance,
                "novelty": novelty,
                "symbols": dict(symbol_counts),
                "examples": examples,
            }
        )

        for statement in cluster_statements:
            updated = dict(statement)
            updated["cluster_id"] = idx
            clustered_statements.append(updated)

    total_clusters = len(cluster_payloads)
    total_statements = len(clustered_statements)
    singleton_clusters = len([size for size in cluster_sizes if size == 1])
    avg_cluster_size = (
        sum(cluster_sizes) / total_clusters if total_clusters else 0.0
    )

    return {
        "stats": {
            "total_statements": total_statements,
            "total_clusters": total_clusters,
            "singleton_clusters": singleton_clusters,
            "avg_cluster_size": avg_cluster_size,
        },
        "clusters": cluster_payloads,
        "statements": clustered_statements,
    }


def build_risk_factor_clusters(
    docs: Sequence[Document],
    *,
    config: RiskFactorClusterConfig | None = None,
) -> JsonDict:
    """Extract, dedupe, and cluster risk factor statements."""
    config = config or RiskFactorClusterConfig()
    raw_statements = extract_risk_factor_statements(docs, config=config)
    unique_statements = dedupe_risk_factor_statements(
        raw_statements, config=config
    )
    payload = cluster_risk_factors(unique_statements, config=config)
    stats_value = payload.get("stats")
    stats = dict(stats_value) if isinstance(stats_value, dict) else {}
    stats["raw_statements"] = len(raw_statements)
    stats["unique_statements"] = len(unique_statements)
    clusters_value = payload.get("clusters")
    statements_value = payload.get("statements")
    return {
        "stats": stats,
        "clusters": clusters_value if isinstance(clusters_value, list) else [],
        "statements": statements_value
        if isinstance(statements_value, list)
        else [],
    }
