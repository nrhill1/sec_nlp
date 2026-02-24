# src/sec_nlp/app/flows/contracts/__init__.py
"""Typed contracts shared across flow runtime and pipeline bridges."""

from .analysis import AnalysisEvidenceBundle, CandidateHitBundle
from .events import (
    EventTimelineBundle,
    FinancialStatementBundle,
    HeadlineBundle,
    OwnershipSignalBundle,
)
from .seed import FlowSeedBundle, FlowSeedChunk

type FlowArtifactValue = (
    FlowSeedBundle
    | CandidateHitBundle
    | AnalysisEvidenceBundle
    | HeadlineBundle
    | EventTimelineBundle
    | FinancialStatementBundle
    | OwnershipSignalBundle
)

__all__: tuple[str, ...] = (
    "AnalysisEvidenceBundle",
    "CandidateHitBundle",
    "EventTimelineBundle",
    "FinancialStatementBundle",
    "FlowArtifactValue",
    "FlowSeedBundle",
    "FlowSeedChunk",
    "HeadlineBundle",
    "OwnershipSignalBundle",
)
