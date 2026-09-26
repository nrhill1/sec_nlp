# src/sec_nlp/pipelines/presets/retrieve/bridge.py
"""Retrieve-side compatibility shim for flow contract imports.

Purpose:
1. Preserve stable import paths in retrieve callers that still reference
   preset-local bridge names.
2. Delegate all actual model definitions to `sec_nlp.app.workspace.evidence`.

This module should remain thin by design; adding new fields or behavior here
would reintroduce duplicate model families.
"""

from sec_nlp.app.workspace.evidence import FlowSeedBundle, FlowSeedChunk

# NOTE:
# Keep these names for backward compatibility while flow seed contracts are
# consolidated under ``sec_nlp.app.workspace.evidence``.
RetrieveChatSeedChunk = FlowSeedChunk
RetrieveChatSeedBundle = FlowSeedBundle

__all__: tuple[str, ...] = (
    "RetrieveChatSeedBundle",
    "RetrieveChatSeedChunk",
)
