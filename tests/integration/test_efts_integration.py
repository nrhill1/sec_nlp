# tests/integration/test_efts_integration.py
"""Offline integration checks for native parsing and Python SEC transport."""

import json

import efts
import pytest

from sec_nlp.core.edgar.transport import fetch_sec_bytes


@pytest.mark.integration
def test_efts_allowlist_rejects_non_sec_hosts() -> None:
    with pytest.raises(ValueError):
        fetch_sec_bytes("https://example.com", "Test test@example.com")


@pytest.mark.integration
def test_native_parser_retains_source_metadata_without_http() -> None:
    payload = {
        "hits": {
            "total": {"value": 1},
            "hits": [
                {
                    "_source": {
                        "adsh": "0001234567-26-000001",
                        "cik": "1234567",
                        "display_names": ["Example"],
                        "form": "10-K",
                        "file_date": "2026-09-25",
                    }
                }
            ],
        }
    }
    parsed = json.loads(efts.parse_response_json(json.dumps(payload), "test"))
    assert parsed["hits"][0]["cik"] == "0001234567"
