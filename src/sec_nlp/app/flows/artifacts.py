# src/sec_nlp/app/flows/artifacts.py
"""In-memory artifact store for typed stage-to-stage handoff.

The store keeps artifact families keyed by stage ID so downstream stages can
consume upstream outputs by reference during a single process run, minimizing
serialization and conversion overhead.
"""

from __future__ import annotations

from sec_nlp.app.flows.contracts import (
    ContractEvidenceBundle,
    FlowArtifactValue,
    FlowRetrievedChunk,
    FlowSeedBundle,
)
from sec_nlp.app.flows.models import FlowStageInputBinding


class FlowArtifactStore:
    """In-memory artifact registry keyed by flow stage ID.

    The store is optimized for local single-process execution, where downstream
    stages consume upstream artifacts by reference rather than via JSON files.
    """

    def __init__(self) -> None:
        """Construct an empty artifact store with seed, chunk, and evidence registries."""
        self._seed_by_stage: dict[str, FlowSeedBundle] = {}
        self._seed_chunks_by_stage: dict[
            str, tuple[FlowRetrievedChunk, ...]
        ] = {}
        self._contract_evidence_by_stage: dict[str, ContractEvidenceBundle] = {}

    def put_seed_bundle(self, stage_id: str, bundle: FlowSeedBundle) -> None:
        """Register a retrieve-style seed bundle for a producing stage."""
        self._seed_by_stage[stage_id] = bundle

    def get_seed_bundle(self, stage_id: str) -> FlowSeedBundle | None:
        """Return a previously stored seed bundle for `stage_id`."""
        return self._seed_by_stage.get(stage_id)

    def put_seed_chunks(
        self,
        stage_id: str,
        chunks: tuple[FlowRetrievedChunk, ...] | list[FlowRetrievedChunk],
    ) -> None:
        """Store prebuilt chat chunks for zero-copy stage handoff.

        Tuple inputs are preserved as-is to avoid extra allocations when
        upstream already materialized an immutable chunk tuple.
        """
        if isinstance(chunks, tuple):
            self._seed_chunks_by_stage[stage_id] = chunks
            return
        self._seed_chunks_by_stage[stage_id] = tuple(chunks)

    def get_seed_chunks(
        self,
        stage_id: str,
    ) -> tuple[FlowRetrievedChunk, ...] | None:
        """Return prebuilt chat chunks for `stage_id`, if available."""
        return self._seed_chunks_by_stage.get(stage_id)

    def put_contract_evidence(
        self, stage_id: str, bundle: ContractEvidenceBundle
    ) -> None:
        """Register an EXB contract-evidence bundle for a producing stage."""
        self._contract_evidence_by_stage[stage_id] = bundle

    def get_contract_evidence(
        self, stage_id: str
    ) -> ContractEvidenceBundle | None:
        """Return contract evidence for `stage_id`, if one was stored."""
        return self._contract_evidence_by_stage.get(stage_id)

    def has_artifact(self, stage_id: str) -> bool:
        """Return whether any artifact family exists for `stage_id`."""
        return (
            stage_id in self._seed_by_stage
            or stage_id in self._seed_chunks_by_stage
            or stage_id in self._contract_evidence_by_stage
        )

    def stage_artifact(self, stage_id: str) -> FlowArtifactValue | None:
        """Return the primary typed artifact for a stage.

        Current precedence is seed bundle first, then contract evidence.
        """
        seed = self.get_seed_bundle(stage_id)
        if seed is not None:
            return seed
        return self.get_contract_evidence(stage_id)

    def resolve_chat_seed_input(
        self,
        binding: FlowStageInputBinding,
    ) -> tuple[FlowSeedBundle | None, tuple[FlowRetrievedChunk, ...]]:
        """Resolve one chat input binding into seed bundle + prebuilt chunks.

        For `retrieve_seed`, this returns the stored seed bundle.
        For `contract_evidence`, this projects EXB evidence into a seed-like
        bundle while preserving any prebuilt chunks from the same stage.
        """
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
        """Project EXB contract evidence into chat's seed-bundle shape."""
        return FlowSeedBundle(
            upstream_pipeline=evidence.upstream_pipeline,
            upstream_run_id=evidence.upstream_run_id,
            upstream_short_id=evidence.upstream_short_id,
            symbols=evidence.symbols,
            queries=evidence.queries,
            chunks=[],
        )
