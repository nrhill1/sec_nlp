"""Flow orchestration primitives for multi-pipeline runs."""

from .models import (
    FlowDefaults,
    FlowResult,
    FlowRunResult,
    FlowSpec,
    FlowStageResult,
    FlowStageSpec,
)

__all__: tuple[str, ...] = (
    "FlowDefaults",
    "FlowResult",
    "FlowRunResult",
    "FlowRunner",
    "FlowSpec",
    "FlowStageResult",
    "FlowStageSpec",
    "load_flow_spec",
)


def __getattr__(name: str):
    """Lazily load heavy flow modules to avoid import cycles."""
    if name == "FlowRunner":
        from .runner import FlowRunner

        return FlowRunner
    if name == "load_flow_spec":
        from .spec import load_flow_spec

        return load_flow_spec
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
