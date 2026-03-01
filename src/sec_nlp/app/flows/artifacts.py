# src/sec_nlp/app/flows/artifacts.py
"""Typed in-memory artifact storage for flow stage handoff."""

from __future__ import annotations

from sec_nlp.app.flows.contracts import (
    ContractEvidenceBundle,
    FlowArtifactValue,
    FlowRetrievedChunk,
    FlowSeedBundle,
)
from sec_nlp.app.flows.models import FlowStageInputBinding


class FlowArtifactStore:
    """Stage-scoped in-memory artifact store for local flow runs."""

    def __init__(self) -> None:
        """Initialize an in-memory artifact store for flow stage handoffs."""
        self._seed_by_stage: dict[str, FlowSeedBundle] = {}
        self._seed_chunks_by_stage: dict[
            str, tuple[FlowRetrievedChunk, ...]
        ] = {}
        self._contract_evidence_by_stage: dict[str, ContractEvidenceBundle] = {}

    def put_seed_bundle(self, stage_id: str, bundle: FlowSeedBundle) -> None:
        """Store seeded bundle keyed by stage ID."""
        self._seed_by_stage[stage_id] = bundle

    def get_seed_bundle(self, stage_id: str) -> FlowSeedBundle | None:
        """Load seeded bundle for one stage."""
        return self._seed_by_stage.get(stage_id)

    def put_seed_chunks(
        self,
        stage_id: str,
        chunks: tuple[FlowRetrievedChunk, ...] | list[FlowRetrievedChunk],
    ) -> None:
        """Store prebuilt seed chunks for zero-copy chat handoff."""
        self._seed_chunks_by_stage[stage_id] = tuple(chunks)

    def get_seed_chunks(
        self,
        stage_id: str,
    ) -> tuple[FlowRetrievedChunk, ...] | None:
        """Load prebuilt seed chunks for one stage."""
        return self._seed_chunks_by_stage.get(stage_id)

    def put_contract_evidence(
        self, stage_id: str, bundle: ContractEvidenceBundle
    ) -> None:
        """Store EXB contract evidence bundle keyed by stage ID."""
        self._contract_evidence_by_stage[stage_id] = bundle

    def get_contract_evidence(
        self, stage_id: str
    ) -> ContractEvidenceBundle | None:
        """Load EXB contract evidence bundle for a stage ID."""
        return self._contract_evidence_by_stage.get(stage_id)

    def has_artifact(self, stage_id: str) -> bool:
        """Return True when any artifact exists for the provided stage ID."""
        return (
            stage_id in self._seed_by_stage
            or stage_id in self._seed_chunks_by_stage
            or stage_id in self._contract_evidence_by_stage
        )

    def stage_artifact(self, stage_id: str) -> FlowArtifactValue | None:
        """Return the first available typed artifact for a stage ID."""
        seed = self.get_seed_bundle(stage_id)
        if seed is not None:
            return seed
        return self.get_contract_evidence(stage_id)

    def resolve_chat_seed_input(
        self,
        binding: FlowStageInputBinding,
    ) -> tuple[FlowSeedBundle | None, tuple[FlowRetrievedChunk, ...]]:
        """Resolve one chat-stage input binding into seeded context and chunks."""
        seed_chunks = self.get_seed_chunks(binding.from_stage) or ()
        if binding.artifact == "retrieve_seed":
            return self.get_seed_bundle(binding.from_stage), seed_chunks

        contract_bundle = self.get_contract_evidence(binding.from_stage)
        if contract_bundle is None:
            return None, seed_chunks
        return self._seed_from_contract_evidence(contract_bundle), seed_chunks

    @staticmethod
    def _seed_from_contract_evidence(
        evidence: ContractEvidenceBundle,
    ) -> FlowSeedBundle:
        """Project contract evidence into a chat seed bundle shape."""
        return FlowSeedBundle(
            upstream_pipeline=evidence.upstream_pipeline,
            upstream_run_id=evidence.upstream_run_id,
            upstream_short_id=evidence.upstream_short_id,
            symbols=list(evidence.symbols),
            queries=list(evidence.queries),
            chunks=[],
        )
