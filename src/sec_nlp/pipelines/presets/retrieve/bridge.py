# src/sec_nlp/pipelines/presets/retrieve/bridge.py
"""Compatibility aliases for retrieve-to-flow seeded context contracts.

The canonical models now live under `sec_nlp.app.flows.contracts`, but these
aliases keep older retrieve imports readable during migration.
"""

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
