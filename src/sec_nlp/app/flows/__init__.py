# src/sec_nlp/app/flows/__init__.py
"""Public flow orchestration API for multi-pipeline runs.

Exports here represent the user-facing flow contract: validated specs in,
typed stage results out, with execution details delegated to compile/runner.
"""

from .models import (
    FlowDefaults,
    FlowRunResult,
    FlowSpec,
    FlowStageResult,
    FlowStageSpec,
)

__all__: tuple[str, ...] = (
    "FlowDefaults",
    "FlowRunResult",
    "FlowSpec",
    "FlowStageResult",
    "FlowStageSpec",
)
