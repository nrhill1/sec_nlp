import pytest

from sec_nlp.core.types import FilingMode


def test_enum_values_are_expected() -> None:
    assert FilingMode.annual.value == "annual"
    assert FilingMode.quarterly.value == "quarterly"
    assert set(FilingMode) == {FilingMode.annual, FilingMode.quarterly}


def test_form_property_returns_correct_form_codes() -> None:
    assert FilingMode.annual.form == "10-K"
    assert FilingMode.quarterly.form == "10-Q"


@pytest.mark.parametrize(
    "mode,expected", [(FilingMode.annual, "10-K"), (FilingMode.quarterly, "10-Q")]
)
def test_form_property_consistency(mode, expected) -> None:
    assert mode.form == expected
    assert mode.form == expected


def test_enum_string_behavior() -> None:
    assert isinstance(FilingMode.annual, str)
    assert FilingMode.annual.lower() == "annual"
    assert str(FilingMode.annual) == "annual"


def test_invalid_enum_access_raises() -> None:
    with pytest.raises(ValueError):
        FilingMode("monthly")
