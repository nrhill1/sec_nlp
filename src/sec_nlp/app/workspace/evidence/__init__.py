# src/sec_nlp/app/workspace/evidence/__init__.py
"""Typed evidence contracts used by specialist services."""

from .contracts import ContractEvidenceBundle, ContractEvidenceChunk
from .seed import FlowRetrievedChunk, FlowSeedBundle, FlowSeedChunk

type FlowArtifactValue = FlowSeedBundle | ContractEvidenceBundle

__all__ = (
    "ContractEvidenceBundle",
    "ContractEvidenceChunk",
    "FlowRetrievedChunk",
    "FlowSeedBundle",
    "FlowSeedChunk",
    "FlowArtifactValue",
)
