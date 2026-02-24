# src/sec_nlp/pipelines/presets/chat/bridge.py
"""Deprecated chat bridge aliases for flow seeded-context contracts."""

from sec_nlp.app.flows.contracts import FlowSeedBundle, FlowSeedChunk

# NOTE:
# Keep these names for backward compatibility while flow seed contracts are
# consolidated under ``sec_nlp.app.flows.contracts``.
ChatSeedChunk = FlowSeedChunk
ChatSeedBundle = FlowSeedBundle

__all__: tuple[str, ...] = ("ChatSeedBundle", "ChatSeedChunk")
