# src/sec_nlp/pipelines/presets/chat/bridge.py
"""Compatibility aliases for chat flow handoff contract models.

These aliases map chat-facing names to canonical flow contracts so stage
handoff code can migrate without duplicating model definitions.
"""

from sec_nlp.app.flows.contracts import (
    FlowRetrievedChunk,
    FlowSeedBundle,
    FlowSeedChunk,
)

# NOTE:
# Keep these names for backward compatibility while flow seed contracts are
# consolidated under ``sec_nlp.app.flows.contracts``.
ChatSeedChunk = FlowSeedChunk
ChatSeedBundle = FlowSeedBundle
ChatRetrievedChunk = FlowRetrievedChunk

__all__: tuple[str, ...] = (
    "ChatRetrievedChunk",
    "ChatSeedBundle",
    "ChatSeedChunk",
)
