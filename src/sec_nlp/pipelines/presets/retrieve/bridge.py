"""Deprecated retrieve bridge aliases for flow seeded-context contracts."""

from sec_nlp.app.flows.contracts import FlowSeedBundle, FlowSeedChunk

# NOTE:
# Keep these names for backward compatibility while flow seed contracts are
# consolidated under ``sec_nlp.app.flows.contracts``.
RetrieveChatSeedChunk = FlowSeedChunk
RetrieveChatSeedBundle = FlowSeedBundle

__all__: tuple[str, ...] = (
    "RetrieveChatSeedBundle",
    "RetrieveChatSeedChunk",
)
