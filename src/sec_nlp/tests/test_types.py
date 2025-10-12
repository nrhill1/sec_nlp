import pytest
from sec_nlp.types import FilingMode


def test_enum_values_are_expected():
    assert FilingMode.annual.value == "annual"
    assert FilingMode.quarterly.value == "quarterly"
    assert set(FilingMode) == {FilingMode.annual, FilingMode.quarterly}


def test_form_property_returns_correct_form_codes():
    assert FilingMode.annual.form == "10-K"
    assert FilingMode.quarterly.form == "10-Q"


@pytest.mark.parametrize("mode,expected", [(FilingMode.annual, "10-K"), (FilingMode.quarterly, "10-Q")])
def test_form_property_consistency(mode, expected):
    assert mode.form == expected
    assert mode.form == expected


def test_enum_string_behavior():
    assert isinstance(FilingMode.annual, str)
    assert FilingMode.annual.lower() == "annual"
    assert str(FilingMode.annual) == "annual"


def test_invalid_enum_access_raises():
    with pytest.raises(ValueError):
        FilingMode("monthly")
