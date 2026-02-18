# tests/pipelines/base/test_forms_config.py
"""Tests for forms field configuration and effective_forms property."""

from sec_nlp.core.edgar.filing_mode import FilingMode
from sec_nlp.pipelines.presets.analyze.config import AnalyzeConfig


class TestFormsField:
    """Test forms field behavior."""

    def test_forms_none_uses_mode_default(self) -> None:
        """Test that when forms is None, effective_forms uses mode."""
        config = AnalyzeConfig(
            mode=FilingMode.annual,
            forms=None,
        )
        assert config.effective_forms == ["10-K"]

    def test_forms_overrides_mode(self) -> None:
        """Test that forms field overrides mode when specified."""
        config = AnalyzeConfig(
            mode=FilingMode.annual,  # Would give ["10-K"]
            forms=["8-K", "10-Q"],  # Override with different forms
        )
        assert config.effective_forms == ["8-K", "10-Q"]

    def test_forms_single_value(self) -> None:
        """Test forms with single value."""
        config = AnalyzeConfig(forms=["10-K"])
        assert config.effective_forms == ["10-K"]

    def test_forms_multiple_values(self) -> None:
        """Test forms with multiple values."""
        config = AnalyzeConfig(forms=["10-K", "10-Q", "8-K"])
        assert config.effective_forms == ["10-K", "10-Q", "8-K"]


class TestFormsNormalization:
    """Test forms normalization and validation."""

    def test_normalize_10k_to_10_k(self) -> None:
        """Test that 10K is normalized to 10-K."""
        config = AnalyzeConfig(forms=["10K"])
        assert config.forms == ["10-K"]

    def test_normalize_10q_to_10_q(self) -> None:
        """Test that 10Q is normalized to 10-Q."""
        config = AnalyzeConfig(forms=["10Q"])
        assert config.forms == ["10-Q"]

    def test_normalize_8k_to_8_k(self) -> None:
        """Test that 8K is normalized to 8-K."""
        config = AnalyzeConfig(forms=["8K"])
        assert config.forms == ["8-K"]

    def test_normalize_6k_to_6_k(self) -> None:
        """Test that 6K is normalized to 6-K."""
        config = AnalyzeConfig(forms=["6K"])
        assert config.forms == ["6-K"]

    def test_normalize_lowercase(self) -> None:
        """Test that lowercase forms are uppercased."""
        config = AnalyzeConfig(forms=["10k", "8k"])
        assert config.forms == ["10-K", "8-K"]

    def test_normalize_mixed_case(self) -> None:
        """Test normalization with mixed case."""
        config = AnalyzeConfig(forms=["10k", "10-K", "8K"])
        assert config.forms == ["10-K", "10-K", "8-K"]

    def test_comma_separated_string(self) -> None:
        """Test that comma-separated string is split."""
        # Type ignore needed because forms accepts list[str] at runtime via validator
        config = AnalyzeConfig(forms="10-K,8-K,10-Q")  # type: ignore[arg-type]
        assert config.forms == ["10-K", "8-K", "10-Q"]

    def test_space_separated_string(self) -> None:
        """Test that space-separated string is split."""
        # Type ignore needed because forms accepts list[str] at runtime via validator
        config = AnalyzeConfig(forms="10-K 8-K 10-Q")  # type: ignore[arg-type]
        assert config.forms == ["10-K", "8-K", "10-Q"]

    def test_comma_and_space_separated(self) -> None:
        """Test mixed comma and space separation."""
        # Type ignore needed because forms accepts list[str] at runtime via validator
        config = AnalyzeConfig(forms="10-K, 8-K 10-Q")  # type: ignore[arg-type]
        assert config.forms == ["10-K", "8-K", "10-Q"]

    def test_preserve_other_forms(self) -> None:
        """Test that non-standard forms are preserved."""
        config = AnalyzeConfig(forms=["S-1", "DEF 14A", "13F-HR"])
        assert config.forms == ["S-1", "DEF 14A", "13F-HR"]


class TestModeFormsProperty:
    """Test FilingMode.forms property."""

    def test_annual_mode_forms(self) -> None:
        """Test annual mode returns 10-K."""
        mode = FilingMode.annual
        assert mode.forms == ("10-K",)

    def test_quarterly_mode_forms(self) -> None:
        """Test quarterly mode returns 10-Q."""
        mode = FilingMode.quarterly
        assert mode.forms == ("10-Q",)

    def test_current_mode_forms(self) -> None:
        """Test current mode returns current-report forms."""
        mode = FilingMode.current
        assert mode.forms == ("8-K", "6-K")

    def test_insider_mode_forms(self) -> None:
        """Test insider mode returns multiple forms."""
        mode = FilingMode.insider
        assert mode.forms == ("3", "4")

    def test_effective_forms_from_mode(self) -> None:
        """Test effective_forms derives from mode when forms is None."""
        config = AnalyzeConfig(mode=FilingMode.annual)
        assert config.effective_forms == ["10-K"]

        config = AnalyzeConfig(mode=FilingMode.insider)
        assert config.effective_forms == ["3", "4"]


class TestSummaryDisplay:
    """Test that summary displays forms correctly."""

    def test_summary_shows_single_form(self) -> None:
        """Test summary displays single form."""
        config = AnalyzeConfig(mode=FilingMode.annual)
        summary = config.summary()
        assert "Forms: 10-K" in summary

    def test_summary_shows_multiple_forms(self) -> None:
        """Test summary displays multiple forms."""
        config = AnalyzeConfig(forms=["10-K", "10-Q", "8-K"])
        summary = config.summary()
        assert "Forms: 10-K, 10-Q, 8-K" in summary

    def test_summary_shows_forms_from_mode(self) -> None:
        """Test summary shows forms derived from mode."""
        config = AnalyzeConfig(mode=FilingMode.insider)
        summary = config.summary()
        assert "Forms: 3, 4" in summary


class TestBackwardCompatibility:
    """Test backward compatibility with mode-only configs."""

    def test_mode_only_config_works(self) -> None:
        """Test that configs with only mode (no forms) still work."""
        config = AnalyzeConfig(mode=FilingMode.annual)
        assert config.mode == FilingMode.annual
        assert config.forms is None
        assert config.effective_forms == ["10-K"]

    def test_default_mode_without_forms(self) -> None:
        """Test default mode is used when neither mode nor forms specified."""
        config = AnalyzeConfig()
        assert config.mode == FilingMode.annual
        assert config.forms is None
        assert config.effective_forms == ["10-K"]

    def test_mode_changes_with_forms_none(self) -> None:
        """Test changing mode works when forms is None."""
        config = AnalyzeConfig(mode=FilingMode.quarterly)
        assert config.effective_forms == ["10-Q"]

        config = AnalyzeConfig(mode=FilingMode.current)
        assert config.effective_forms == ["8-K", "6-K"]
