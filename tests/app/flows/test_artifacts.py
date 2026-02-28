# tests/app/flows/test_artifacts.py
"""Tests for flow artifact store typed handoff behavior."""

from sec_nlp.app.flows.artifacts import FlowArtifactStore
from sec_nlp.app.flows.contracts import (
    ContractEvidenceBundle,
    ContractEvidenceChunk,
    FlowRetrievedChunk,
    FlowSeedBundle,
    FlowSeedChunk,
)


def test_stage_artifact_prefers_seed_bundle() -> None:
    store = FlowArtifactStore()
    store.put_seed_bundle(
        "retrieve_stage",
        FlowSeedBundle(
            upstream_pipeline="retrieve",
            upstream_run_id="11111111-1111-1111-1111-111111111111",
            symbols=["AEM"],
            queries=["q"],
            chunks=[
                FlowSeedChunk(
                    collection="retrieve",
                    symbol="AEM",
                    score=0.9,
                    snippet="snippet",
                )
            ],
        ),
    )

    artifact = store.stage_artifact("retrieve_stage")
    assert artifact is not None
    assert isinstance(artifact, FlowSeedBundle)
    assert artifact.upstream_pipeline == "retrieve"
    assert store.has_artifact("retrieve_stage")


def test_contract_evidence_roundtrip() -> None:
    store = FlowArtifactStore()
    bundle = ContractEvidenceBundle(
        upstream_pipeline="exhibit",
        upstream_run_id="22222222-2222-2222-2222-222222222222",
        symbols=["MP"],
        queries=["exclusive agreement"],
        chunks=[
            ContractEvidenceChunk(
                symbol="MP",
                accession_number="0000000000-00-000001",
                snippet="contract clause text",
            )
        ],
    )
    store.put_contract_evidence("exb_stage", bundle)

    assert store.get_contract_evidence("exb_stage") == bundle
    artifact = store.stage_artifact("exb_stage")
    assert artifact == bundle
    assert store.has_artifact("exb_stage")


def test_retrieve_seed_chunks_roundtrip() -> None:
    store = FlowArtifactStore()
    chunks = [
        FlowRetrievedChunk(
            collection="retrieve",
            score=0.88,
            symbol="AEM",
            accession_number="0000000000-00-000002",
            form_type="10-K",
            filed_date="2025-12-31",
            source="https://www.sec.gov/example",
            snippet="Liquidity risk increased due to refinancing costs.",
            vector=None,
        )
    ]
    store.put_seed_chunks("retrieve_stage", chunks)

    loaded = store.get_seed_chunks("retrieve_stage")
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0].collection == "retrieve"
    assert store.has_artifact("retrieve_stage")


def test_contract_seed_chunks_roundtrip() -> None:
    store = FlowArtifactStore()
    chunks = (
        FlowRetrievedChunk(
            collection="exhibit",
            score=0.87,
            symbol="MP",
            accession_number="0000000000-00-000003",
            form_type="8-K",
            filed_date="2025-12-31",
            source="https://www.sec.gov/exhibit",
            snippet="Supplier must provide NdPr oxide volumes quarterly.",
            vector=None,
        ),
    )
    store.put_seed_chunks("exhibit_stage", chunks)

    loaded = store.get_seed_chunks("exhibit_stage")
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded[0].collection == "exhibit"
    assert store.has_artifact("exhibit_stage")
