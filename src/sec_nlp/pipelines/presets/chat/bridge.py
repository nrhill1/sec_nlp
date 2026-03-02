# src/sec_nlp/pipelines/presets/chat/bridge.py
"""Chat-side compatibility shim for flow handoff contracts.

Purpose:
1. Keep chat module imports stable while flow contracts live centrally.
2. Avoid local duplicate model definitions in chat preset code.

Like retrieve bridge, this file should stay alias-only.
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
