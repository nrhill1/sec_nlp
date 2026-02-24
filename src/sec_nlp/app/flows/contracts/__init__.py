# src/sec_nlp/app/flows/contracts/__init__.py
"""Typed contracts shared across flow runtime and pipeline bridges."""

from .analysis import AnalysisEvidenceBundle, CandidateHitBundle
from .contracts import (
    ContextPack,
    ContractEvidenceBundle,
    ContractEvidenceChunk,
)
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
    | ContractEvidenceBundle
    | HeadlineBundle
    | EventTimelineBundle
    | FinancialStatementBundle
    | OwnershipSignalBundle
    | ContextPack
)

__all__: tuple[str, ...] = (
    "AnalysisEvidenceBundle",
    "CandidateHitBundle",
    "ContextPack",
    "ContractEvidenceBundle",
    "ContractEvidenceChunk",
    "EventTimelineBundle",
    "FinancialStatementBundle",
    "FlowArtifactValue",
    "FlowSeedBundle",
    "FlowSeedChunk",
    "HeadlineBundle",
    "OwnershipSignalBundle",
)
