# tests/app/workspace/test_benchmark_matrix_job_specs.py
"""Tests for aligned benchmark matrix flow specs used in branch reporting."""

from pathlib import Path

import pytest

from sec_nlp.app.workspace.recipes import load_recipe
from sec_nlp.core.types import as_json_dict


def _repo_root() -> Path:
    """Return the repository root for loading benchmark flow specs."""
    return Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    ("relative_path", "collection_name", "expected_symbols"),
    [
        (
            "jobs/benchmark_matrix_flows/01_rems_large_merged_aligned.yaml",
            "benchmark_rems_large_merged_aligned",
            ["MP", "LAC", "UUUU", "TMRC", "AREC", "USAR"],
        ),
        (
            "jobs/benchmark_matrix_flows/02_rems_high_qwen_aligned.yaml",
            "benchmark_rems_high_qwen_aligned",
            ["MP", "LAC", "UUUU", "TMRC", "AREC", "USAR"],
        ),
        (
            "jobs/benchmark_matrix_flows/03_quantum_large_merged_aligned.yaml",
            "benchmark_quantum_large_merged_aligned",
            ["IONQ", "RGTI", "QBTS", "QUBT", "IBM", "HON"],
        ),
        (
            "jobs/benchmark_matrix_flows/04_quantum_high_qwen_ministral_aligned.yaml",
            "benchmark_quantum_high_qwen_ministral_aligned",
            ["IONQ", "RGTI", "QBTS", "QUBT", "IBM", "HON"],
        ),
    ],
)
def test_benchmark_matrix_specs_align_basket_window_and_timeout(
    relative_path: str,
    collection_name: str,
    expected_symbols: list[str],
) -> None:
    """Load aligned benchmark specs and verify benchmark-critical overrides."""
    spec = load_recipe(_repo_root() / relative_path)

    assert [stage.id for stage in spec.stages] == [
        "retrieve_seed",
        "chat_answer",
    ]
    retrieve_overrides = spec.stages[0].overrides
    chat_overrides = spec.stages[1].overrides

    assert retrieve_overrides["start_date"] == "2023-03-12"
    assert chat_overrides["start_date"] == "2023-03-12"
    assert retrieve_overrides["symbols"] == expected_symbols
    assert chat_overrides["symbols"] == expected_symbols
    assert chat_overrides["llm_timeout_seconds"] == 360
    assert chat_overrides["collections"] == [collection_name]

    retrieve_vdb = as_json_dict(retrieve_overrides["vdb"])
    chat_vdb = as_json_dict(chat_overrides["vdb"])
    assert retrieve_vdb is not None
    assert chat_vdb is not None
    assert retrieve_vdb["collection_name"] == collection_name
    assert chat_vdb["collection_name"] == collection_name
