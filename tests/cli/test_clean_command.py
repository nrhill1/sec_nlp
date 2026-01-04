# tests/cli/test_clean_command.py
"""Tests for the workspace cleanup CLI command."""

from pathlib import Path

from sec_nlp.cli.commands.clean import Clean


def _seed_path(path: Path) -> None:
    """Create a directory with sample contents."""
    path.mkdir(parents=True, exist_ok=True)
    (path / "file.txt").write_text("data")
    nested = path / "nested"
    nested.mkdir()
    (nested / "inner.txt").write_text("more data")


def test_clean_all_targets_clears_and_recreates(tmp_path: Path) -> None:
    """Cleaning all targets should empty downloads, outputs, and logs paths."""
    workspace = tmp_path / "workspace"
    downloads = workspace / "downloads"
    outputs = workspace / "outputs"
    logs = workspace / "logs"

    for p in (downloads, outputs, logs):
        _seed_path(p)

    cmd = Clean(root=workspace, force=True)
    cmd.cli_cmd()

    for path in (downloads, outputs, logs):
        assert path.exists()
        assert not any(path.iterdir())


def test_clean_specific_target_leaves_others_alone(tmp_path: Path) -> None:
    """Cleaning a single target should not modify the others."""
    downloads = tmp_path / "downloads"
    outputs = tmp_path / "outputs"
    _seed_path(downloads)
    _seed_path(outputs)

    cmd = Clean(root=tmp_path, target="downloads", force=True)
    cmd.cli_cmd()

    assert downloads.exists()
    assert not any(downloads.iterdir())

    # Outputs should remain unchanged
    assert outputs.exists()
    assert any(outputs.iterdir())


def test_clean_creates_missing_path(tmp_path: Path) -> None:
    """Cleaning should create missing target directories."""
    workspace = tmp_path / "workspace"

    cmd = Clean(root=workspace, target="logs", force=True)
    cmd.cli_cmd()

    logs_dir = workspace / "logs"
    assert logs_dir.exists()
    assert not any(logs_dir.iterdir())
