"""Typed in-memory artifact storage for flow stage handoff."""

from __future__ import annotations

from sec_nlp.app.flows.contracts import FlowSeedBundle


class FlowArtifactStore:
    """Stage-scoped in-memory artifact store for local flow runs."""

    def __init__(self) -> None:
        self._seed_by_stage: dict[str, FlowSeedBundle] = {}

    def put_retrieve_seed(self, stage_id: str, bundle: FlowSeedBundle) -> None:
        """Store retrieve handoff bundle keyed by stage ID."""
        self._seed_by_stage[stage_id] = bundle

    def get_retrieve_seed(self, stage_id: str) -> FlowSeedBundle | None:
        """Load retrieve seed bundle for a stage ID."""
        return self._seed_by_stage.get(stage_id)

    def get_chat_seed(self, stage_id: str) -> FlowSeedBundle | None:
        """Return seeded bundle for chat stage execution."""
        return self._seed_by_stage.get(stage_id)
