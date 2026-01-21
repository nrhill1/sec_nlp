from sec_nlp.tui.interfaces import build_cli_args, get_form_spec


def test_build_cli_args_handles_lists_and_extra_args() -> None:
    form_spec = get_form_spec("analyze")
    assert form_spec is not None
    values = {
        "symbols": "AAPL MSFT",
        "topics": "pricing, margin pressure",
        "preset": "",
    }
    args = build_cli_args(
        form_spec, values, "--market-limit 10 --search.limit 5"
    )

    assert args[:2] == ["AAPL", "MSFT"]
    assert "--topics" in args
    assert "pricing" in args
    assert "margin" in args
    assert "pressure" in args
    assert "--market-limit" in args
    assert "10" in args
    assert "--search.limit" in args
    assert "5" in args


def test_build_cli_args_disables_default_true_bool() -> None:
    form_spec = get_form_spec("analyze")
    assert form_spec is not None
    values = {"symbols": "AAPL", "market_enabled": False}
    args = build_cli_args(form_spec, values)
    assert "--no-market-enabled" in args
