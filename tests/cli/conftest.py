# tests/cli/conftest.py
import pytest

from sec_nlp.pipelines.base.config import BasePipelineSettings
from sec_nlp.pipelines.base.validation import ValidationReport


@pytest.fixture(autouse=True)
def _stub_validate_pipeline(monkeypatch):
    def _fake_validate_pipeline(
        config: BasePipelineSettings,
        print_report: bool = True,
    ) -> ValidationReport:
        _ = config
        _ = print_report
        return ValidationReport()

    monkeypatch.setattr(
        "sec_nlp.cli.command.validate_pipeline", _fake_validate_pipeline
    )
