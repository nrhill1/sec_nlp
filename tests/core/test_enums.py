# tests/core/test_enums.py
"""Unit tests for sec_nlp.core.edgar.filing_mode module."""

import pytest

from sec_nlp.core.edgar.filing_mode import FilingMode


class TestFilingMode:
    """Tests for FilingMode enum."""

    def test_filing_mode_values(self) -> None:
        """Test that FilingMode has correct string values."""
        assert FilingMode.annual.value == "annual"
        assert FilingMode.quarterly.value == "quarterly"

    def test_filing_mode_str_representation(self) -> None:
        """Test string representation of FilingMode."""
        assert str(FilingMode.annual) == "annual"
        assert str(FilingMode.quarterly) == "quarterly"

    def test_filing_mode_str_equals_value(self) -> None:
        assert FilingMode.annual.value == str(FilingMode.annual)
        assert FilingMode.quarterly.value == str(FilingMode.quarterly)

    def test_filing_mode_form_property_annual(self) -> None:
        """Test that annual mode returns correct SEC form code."""
        assert FilingMode.annual.form == "10-K"

    def test_filing_mode_form_property_quarterly(self) -> None:
        """Test that quarterly mode returns correct SEC form code."""
        assert FilingMode.quarterly.form == "10-Q"

    def test_filing_mode_string_comparison(self) -> None:
        """Test that FilingMode can be compared to strings."""
        assert FilingMode.annual.value == "annual"
        assert FilingMode.quarterly.value == "quarterly"

    def test_filing_mode_iteration(self) -> None:
        """Test that all FilingMode values can be iterated."""
        modes = list(FilingMode)
        assert len(modes) == 5
        assert FilingMode.annual in modes
        assert FilingMode.quarterly in modes
        assert FilingMode.current in modes
        assert FilingMode.proxy in modes
        assert FilingMode.holdings in modes

    def test_filing_mode_from_string(self) -> None:
        """Test creating FilingMode from string."""
        assert FilingMode("annual") == FilingMode.annual
        assert FilingMode("quarterly") == FilingMode.quarterly

    def test_filing_mode_invalid_value(self) -> None:
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError):
            FilingMode("invalid")

    def test_filing_mode_membership(self) -> None:
        """Test checking if value is in FilingMode."""
        assert "annual" in FilingMode.__members__.values()
        assert "quarterly" in FilingMode.__members__.values()

    def test_filing_mode_names(self) -> None:
        """Test that FilingMode member names are correct."""
        assert "annual" in FilingMode.__members__
        assert "quarterly" in FilingMode.__members__

    def test_filing_mode_is_enum_member(self) -> None:
        """Test that FilingMode values are enum members."""
        assert isinstance(FilingMode.annual, FilingMode)
        assert isinstance(FilingMode.quarterly, FilingMode)

    def test_filing_mode_hash(self) -> None:
        """Test that FilingMode values are hashable."""
        modes_set = {FilingMode.annual, FilingMode.quarterly}
        assert len(modes_set) == 2
        assert FilingMode.annual in modes_set
        assert FilingMode.quarterly in modes_set

    def test_filing_mode_repr(self) -> None:
        """Test repr of FilingMode."""
        # Enum repr typically includes class name
        repr_annual = repr(FilingMode.annual)
        assert "FilingMode" in repr_annual
        assert "annual" in repr_annual

    def test_filing_mode_proxy(self) -> None:
        """Test proxy filing mode for DEF 14A."""
        assert FilingMode.proxy.value == "proxy"
        assert FilingMode.proxy.form == "DEF 14A"
        assert str(FilingMode.proxy) == "proxy"
        assert FilingMode("proxy") == FilingMode.proxy

    def test_filing_mode_holdings(self) -> None:
        """Test holdings filing mode for 13F-HR."""
        assert FilingMode.holdings.value == "holdings"
        assert FilingMode.holdings.form == "13F-HR"
        assert str(FilingMode.holdings) == "holdings"
        assert FilingMode("holdings") == FilingMode.holdings

    def test_filing_mode_description(self) -> None:
        """Test description property for all filing modes."""
        assert FilingMode.annual.description == "Annual Report"
        assert FilingMode.quarterly.description == "Quarterly Report"
        assert (
            FilingMode.current.description == "Current Report (Material Events)"
        )
        assert (
            FilingMode.proxy.description
            == "Proxy Statement (Shareholder Meeting)"
        )
        assert (
            FilingMode.holdings.description == "Institutional Holdings Report"
        )
