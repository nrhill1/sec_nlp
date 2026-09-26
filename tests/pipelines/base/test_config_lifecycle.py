# tests/pipelines/base/test_config_lifecycle.py
"""Test that specialist settings validation never registers an execution.

The terminal uses the same settings for previews and execution, so inspecting a
configuration must not create run records or output directories.
"""

from pathlib import Path
from unittest.mock import patch

from sec_nlp.pipelines.presets.financials.config import FinancialsSettings


def test_config_validation_is_pure_and_registration_is_explicit(
    tmp_path: Path,
) -> None:
    """Create no run or directories until an operation is explicitly started."""
    with patch(
        "sec_nlp.pipelines.observability.run_registry.get_registry"
    ) as get_registry:
        settings = FinancialsSettings(
            symbols=["AAPL"],
            out_path=tmp_path / "outputs",
            dl_path=tmp_path / "downloads",
        )
        settings.model_dump(mode="json")
        assert settings.short_id == 0
        get_registry.assert_not_called()
        assert not settings.out_path.exists()
        assert not settings.dl_path.exists()
        get_registry.return_value.register_run.return_value = 12
        settings.start_run()
        settings.start_run()
        get_registry.return_value.register_run.assert_called_once()
        assert settings.short_id == 12
