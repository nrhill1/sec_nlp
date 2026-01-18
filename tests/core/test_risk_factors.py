# tests/core/test_risk_factors.py
"""Tests for risk factor extraction and clustering utilities."""

from langchain_core.documents import Document

from sec_nlp.core.text.risk_factors import (
    RiskFactorClusterConfig,
    build_risk_factor_clusters,
    cluster_risk_factors,
    dedupe_risk_factor_statements,
    extract_risk_factor_statements,
)


def test_extract_risk_factor_statements_skips_headers() -> None:
    content = (
        "Item 1A. Risk Factors\n\n"
        "We may be unable to retain key suppliers, which could delay shipments "
        "and harm revenue.\n\n"
        "Our business depends on a limited number of customers, and demand "
        "could decline unexpectedly."
    )
    doc = Document(
        page_content=content,
        metadata={
            "symbol": "ACME",
            "form_type": "10-K",
            "accession_number": "0000000000-24-000010",
        },
    )
    config = RiskFactorClusterConfig(
        min_statement_length=20,
        min_token_count=3,
    )

    statements = extract_risk_factor_statements([doc], config=config)

    assert len(statements) == 2
    texts = [statement.get("statement") for statement in statements]
    assert all(isinstance(text, str) for text in texts)
    assert not any("Item 1A" in text for text in texts if isinstance(text, str))
    for statement in statements:
        assert statement.get("symbol") == "ACME"
        assert statement.get("form_type") == "10-K"
        assert statement.get("accession_number") == "0000000000-24-000010"


def test_cluster_risk_factors_groups_similar_statements() -> None:
    statements = [
        {
            "statement": "Supply chain disruptions could delay shipments.",
            "normalized": "supply chain disruptions could delay shipments.",
            "symbol": "AAA",
        },
        {
            "statement": "Disruptions in our supply chain may delay shipments.",
            "normalized": "disruptions in our supply chain may delay shipments.",
            "symbol": "BBB",
        },
        {
            "statement": "Regulatory changes could increase costs.",
            "normalized": "regulatory changes could increase costs.",
            "symbol": "CCC",
        },
    ]
    config = RiskFactorClusterConfig(
        min_statement_length=10,
        min_token_count=2,
        cluster_distance=10,
    )

    payload = cluster_risk_factors(statements, config=config)

    assert isinstance(payload, dict)
    clusters_value = payload.get("clusters")
    assert isinstance(clusters_value, list)
    sizes: list[int] = []
    for cluster in clusters_value:
        if not isinstance(cluster, dict):
            continue
        size_value = cluster.get("size")
        if isinstance(size_value, int):
            sizes.append(size_value)
    assert sorted(sizes) == [1, 2]
    stats_value = payload.get("stats")
    assert isinstance(stats_value, dict)
    total_statements = None
    for key, value in stats_value.items():
        if key == "total_statements" and isinstance(value, int):
            total_statements = value
    assert total_statements == 3


def test_dedupe_and_build_clusters() -> None:
    docs = [
        Document(
            page_content=(
                "Risk Factors\n\n"
                "Supply chain disruptions could delay shipments."
            ),
            metadata={"symbol": "AAA", "form_type": "10-K"},
        ),
        Document(
            page_content=(
                "Risk Factors\n\n"
                "Supply chain disruptions could delay shipments."
            ),
            metadata={"symbol": "BBB", "form_type": "10-K"},
        ),
    ]
    config = RiskFactorClusterConfig(
        min_statement_length=10,
        min_token_count=2,
    )

    extracted = extract_risk_factor_statements(docs, config=config)
    deduped = dedupe_risk_factor_statements(extracted, config=config)
    payload = build_risk_factor_clusters(docs, config=config)

    assert len(extracted) == 2
    assert len(deduped) == 1
    assert isinstance(payload, dict)
    stats_value = payload.get("stats")
    assert isinstance(stats_value, dict)
    unique_statements = None
    for key, value in stats_value.items():
        if key == "unique_statements" and isinstance(value, int):
            unique_statements = value
    assert unique_statements == 1
