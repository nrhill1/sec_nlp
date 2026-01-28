# tests/integration/test_efts_integration.py
"""Integration tests for EFTS Rust extension (SEC.gov only)."""

from __future__ import annotations

import os

import pytest

from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonDict, JsonValue


def _coerce_json_value(value: object) -> JsonValue | None:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        items: list[JsonValue] = []
        for item in value:
            normalized = _coerce_json_value(item)
            if normalized is None:
                return None
            items.append(normalized)
        return items
    if isinstance(value, dict):
        normalized_dict: JsonDict = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return None
            normalized_item = _coerce_json_value(item)
            if normalized_item is None:
                return None
            normalized_dict[key] = normalized_item
        return normalized_dict
    return None


@pytest.mark.integration
def test_efts_allowlist_rejects_non_sec_hosts() -> None:
    import efts

    with pytest.raises(ValueError):
        efts.EFTSClient(
            user_agent="SEC NLP Tool (test@example.com)",
            base_url="https://example.com",
            allowed_hosts=["sec.gov"],
        )


@pytest.mark.integration
@pytest.mark.network
def test_efts_secgov_query_returns_hits(socket_enabled: None) -> None:
    if os.environ.get("SEC_NLP_NETWORK_TESTS") != "1":
        pytest.skip("SEC_NLP_NETWORK_TESTS is not enabled")

    import efts

    client = efts.EFTSClient(
        user_agent="SEC NLP Tool (test@example.com)",
        allowed_hosts=["sec.gov"],
    )
    result: JsonDict = client.search("warranty", limit=1)
    assert "hits" in result
    hits_value = _coerce_json_value(result["hits"])
    assert isinstance(hits_value, list)
    assert hits_value
    first_value = _coerce_json_value(hits_value[0])
    assert first_value is not None
    first: JsonValue = first_value
    assert isinstance(first, dict)
    first_dict = as_json_dict(first)
    assert first_dict is not None
    accession = first_dict.get("accession_number")
    assert isinstance(accession, str)
    assert accession
