# tests/app/workspace/test_conflict_monopoly_job_specs.py
"""Tests for specialized conflict and monopoly flow job specs."""

from pathlib import Path

import pytest

from sec_nlp.app.workspace.recipes import load_recipe
from sec_nlp.core.types import as_json_dict


def _repo_root() -> Path:
    """Return the repository root for loading job specs."""
    return Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("relative_path", "collection_name"),
    [
        (
            "jobs/conflict_monopoly_flows/01_rems_conflict_monopoly_large.yaml",
            "thematic_rems_conflict_monopoly_large",
        ),
        (
            "jobs/conflict_monopoly_flows/02_quantum_conflict_monopoly_large.yaml",
            "thematic_quantum_conflict_monopoly_large",
        ),
    ],
)
def test_conflict_monopoly_specs_load_with_shared_collection(
    relative_path: str,
    collection_name: str,
) -> None:
    """Load each specialized flow spec and verify shared-collection wiring."""
    spec = load_recipe(_repo_root() / relative_path)

    assert [stage.id for stage in spec.stages] == [
        "retrieve_simple_terms",
        "retrieve_conflict_terms",
        "retrieve_monopoly_terms",
        "retrieve_complex_terms",
        "chat_answer",
    ]
    assert all(stage.pipeline == "retrieve" for stage in spec.stages[:-1])
    assert spec.stages[-1].pipeline == "chat"
    assert spec.stages[-1].inputs == []

    for stage in spec.stages[:-1]:
        assert stage.overrides["start_date"] == "2023-03-12"
        vdb = as_json_dict(stage.overrides["vdb"])
        assert vdb is not None
        assert vdb["collection_name"] == collection_name

    chat_overrides = spec.stages[-1].overrides
    assert chat_overrides["collections"] == [collection_name]
    assert chat_overrides["start_date"] == "2023-03-12"
