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
from sec_nlp.app.flows.models import FlowStageInputBinding


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


def test_resolve_chat_seed_input_for_retrieve_seed() -> None:
    store = FlowArtifactStore()
    seed_bundle = FlowSeedBundle(
        upstream_pipeline="retrieve",
        upstream_run_id="33333333-3333-3333-3333-333333333333",
        symbols=["LAC"],
        queries=["capital expenditures"],
        chunks=[],
    )
    store.put_seed_bundle("retrieve_stage", seed_bundle)
    chunks = (
        FlowRetrievedChunk(
            collection="retrieve",
            score=0.91,
            symbol="LAC",
            accession_number="0000000000-00-000004",
            form_type="10-Q",
            filed_date="2025-12-31",
            source="https://www.sec.gov/retrieve",
            snippet="Capital expenditures increased due to expansion.",
            vector=None,
        ),
    )
    store.put_seed_chunks("retrieve_stage", chunks)

    resolved_seed, resolved_chunks = store.resolve_chat_seed_input(
        FlowStageInputBinding(
            from_stage="retrieve_stage",
            artifact="retrieve_seed",
        )
    )

    assert resolved_seed == seed_bundle
    assert resolved_chunks == chunks


def test_resolve_chat_seed_input_for_contract_evidence() -> None:
    store = FlowArtifactStore()
    evidence_bundle = ContractEvidenceBundle(
        upstream_pipeline="exhibit",
        upstream_run_id="44444444-4444-4444-4444-444444444444",
        symbols=["MP"],
        queries=["offtake agreement"],
        chunks=[
            ContractEvidenceChunk(
                symbol="MP",
                accession_number="0000000000-00-000005",
                snippet="Offtake agreement with minimum annual tonnage.",
            )
        ],
    )
    store.put_contract_evidence("exhibit_stage", evidence_bundle)
    chunks = (
        FlowRetrievedChunk(
            collection="exhibit",
            score=0.87,
            symbol="MP",
            accession_number="0000000000-00-000005",
            form_type="8-K",
            filed_date="2025-12-31",
            source="https://www.sec.gov/exhibit",
            snippet="Offtake agreement with minimum annual tonnage.",
            vector=None,
        ),
    )
    store.put_seed_chunks("exhibit_stage", chunks)

    resolved_seed, resolved_chunks = store.resolve_chat_seed_input(
        FlowStageInputBinding(
            from_stage="exhibit_stage",
            artifact="contract_evidence",
        )
    )

    assert resolved_seed is not None
    assert resolved_seed.upstream_pipeline == "exhibit"
    assert resolved_seed.symbols == ["MP"]
    assert resolved_seed.queries == ["offtake agreement"]
    assert resolved_seed.chunks == []
    assert resolved_chunks == chunks
