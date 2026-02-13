"""Tests for the XBRL Rust extension Python wrapper."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sec_nlp.core.edgar import xbrl_facts


def test_load_xbrl_module_raises_clear_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    xbrl_facts._load_xbrl_module.cache_clear()

    def fail_import(_name: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(xbrl_facts, "import_module", fail_import)

    with pytest.raises(
        xbrl_facts.XbrlExtensionError,
        match="xbrl extension is not available",
    ):
        xbrl_facts._load_xbrl_module()

    xbrl_facts._load_xbrl_module.cache_clear()


def test_parser_methods_and_top_level_extractors_use_extension(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, object] = {}
    raw_fact = SimpleNamespace(
        tag="us-gaap:Revenues",
        namespace="us-gaap",
        local_name="Revenues",
        value=1234.0,
        raw_value="1234",
        scale=0,
        decimals=-3,
        unit="USD",
        context_ref="ctx_20241231",
        period_start="2024-01-01",
        period_end="2024-12-31",
        period_instant=None,
        entity_id="0000000001",
        segment=None,
    )

    parser_impl = SimpleNamespace(
        parse_ixbrl=lambda html: (
            calls.setdefault("parse_ixbrl", html),
            [raw_fact],
        )[1],
        parse_instance=lambda xml: (
            calls.setdefault("parse_instance", xml),
            [raw_fact],
        )[1],
        parse_auto=lambda content: (
            calls.setdefault("parse_auto", content),
            [raw_fact],
        )[1],
        parse_file=lambda path: (
            calls.setdefault("parse_file", path),
            [raw_fact],
        )[1],
    )

    fake_module = SimpleNamespace(
        PyXbrlParser=lambda: parser_impl,
        extract_facts=lambda content: (
            calls.setdefault("extract_facts", content),
            [raw_fact],
        )[1],
        extract_facts_from_file=lambda path: (
            calls.setdefault("extract_facts_from_file", path),
            [raw_fact],
        )[1],
    )
    monkeypatch.setattr(xbrl_facts, "_load_xbrl_module", lambda: fake_module)

    parser = xbrl_facts.create_xbrl_parser()
    ixbrl_facts = parser.parse_ixbrl("<ix:nonFraction/>")
    instance_facts = parser.parse_instance("<xbrl/>")
    auto_facts = parser.parse_auto("content")
    file_facts = parser.parse_file(Path("filing.xml"))
    extracted_facts = xbrl_facts.extract_facts("content")
    extracted_file_facts = xbrl_facts.extract_facts_from_file(
        Path("filing.xml")
    )

    assert ixbrl_facts[0].tag == "us-gaap:Revenues"
    assert instance_facts[0].value == 1234.0
    assert auto_facts[0].period_end == "2024-12-31"
    assert file_facts[0].entity_id == "0000000001"
    assert extracted_facts[0].namespace == "us-gaap"
    assert extracted_file_facts[0].local_name == "Revenues"

    assert calls["parse_ixbrl"] == "<ix:nonFraction/>"
    assert calls["parse_instance"] == "<xbrl/>"
    assert calls["parse_auto"] == "content"
    assert calls["parse_file"] == "filing.xml"
    assert calls["extract_facts"] == "content"
    assert calls["extract_facts_from_file"] == "filing.xml"
