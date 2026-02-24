# src/sec_nlp/app/flows/artifacts.py
"""Typed in-memory artifact storage for flow stage handoff."""

from __future__ import annotations

from sec_nlp.app.flows.contracts import (
    ContractEvidenceBundle,
    FlowArtifactValue,
    FlowSeedBundle,
)


class FlowArtifactStore:
    """Stage-scoped in-memory artifact store for local flow runs."""

    def __init__(self) -> None:
        self._seed_by_stage: dict[str, FlowSeedBundle] = {}
        self._contract_evidence_by_stage: dict[str, ContractEvidenceBundle] = {}

    def put_retrieve_seed(self, stage_id: str, bundle: FlowSeedBundle) -> None:
        """Store retrieve handoff bundle keyed by stage ID."""
        self._seed_by_stage[stage_id] = bundle

    def get_retrieve_seed(self, stage_id: str) -> FlowSeedBundle | None:
        """Load retrieve seed bundle for a stage ID."""
        return self._seed_by_stage.get(stage_id)

    def get_chat_seed(self, stage_id: str) -> FlowSeedBundle | None:
        """Return seeded bundle for chat stage execution."""
        return self._seed_by_stage.get(stage_id)

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
            or stage_id in self._contract_evidence_by_stage
        )

    def stage_artifact(self, stage_id: str) -> FlowArtifactValue | None:
        """Return the first available typed artifact for a stage ID."""
        seed = self.get_retrieve_seed(stage_id)
        if seed is not None:
            return seed
        return self.get_contract_evidence(stage_id)
