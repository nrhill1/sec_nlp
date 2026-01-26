from sec_nlp.tui.specs import find_pipeline_spec, get_pipeline_specs


def test_pipeline_specs_include_expected() -> None:
    specs = get_pipeline_specs()
    keys = [spec.key for spec in specs]
    assert "analyze" in keys
    assert "exb" in keys
    assert "warranty" in keys


def test_find_pipeline_spec() -> None:
    spec = find_pipeline_spec("analyze")
    assert spec is not None
    assert spec.command == "analyze"
