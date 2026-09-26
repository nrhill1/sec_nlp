# tests/core/edgar/test_discovery.py
"""Tests for SEC Atom/index identities and on-demand document selection."""

import asyncio
from datetime import date
from unittest.mock import AsyncMock

import pytest
from pydantic import HttpUrl

from sec_nlp.core.edgar import discovery
from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.edgar.filing_models import FilingDocument
from sec_nlp.core.edgar.transport import SecTransport

ACC = "0001234567-26-000001"
BASE = "https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/"


def _entry(cik: str, role: str) -> str:
    """Build a source entry with an explicit entity role."""
    return f'''<entry><title>4 - Example ({cik}) ({role})</title>
    <id>urn:tag:{ACC}</id><link href="{BASE}{ACC}-index.html"/>
    <category term="4"/><updated>2026-09-25T12:00:00-04:00</updated>
    <summary>&lt;b&gt;Filed:&lt;/b&gt; 2026-09-25</summary></entry>'''


def _feed(entries: str) -> bytes:
    """Wrap source entries in an Atom feed."""
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom">' + entries + "</feed>"
    ).encode()


def test_atom_merges_accession_roles_without_acceptance_inference() -> None:
    page = discovery.parse_atom(
        _feed(_entry("1234567", "Issuer") + _entry("987654", "Reporting")),
        count=2,
    )
    assert page.raw_entries == 2 and page.next_start == 2
    assert len(page.filings) == 1
    filing = page.filings[0]
    assert len(filing.entities) == 2
    assert filing.filed_date == date(2026, 9, 25)
    assert filing.accepted_at is None
    assert filing.entities[1].role == "reporting"


@pytest.mark.parametrize("content", [b"<broken", b"<html>Forbidden</html>"])
def test_atom_errors_are_not_empty_success(content: bytes) -> None:
    with pytest.raises(ValueError):
        discovery.parse_atom(content)


def test_master_index_preserves_forms_and_multiple_entities() -> None:
    content = f"""Description: Master Index
CIK|Company Name|Form Type|Date Filed|Filename
---------------------------------------------
1234567|Example|4/A|2026-09-25|edgar/data/1234567/{ACC}.txt
987654|Owner|4/A|2026-09-25|edgar/data/1234567/{ACC}.txt
""".encode()
    records = discovery.parse_master_index(content)
    assert len(records) == 1 and len(records[0].entities) == 2
    assert records[0].form_type == "4/A"
    assert str(records[0].filing_url).endswith(f"{ACC}-index.html")
    with pytest.raises(ValueError):
        discovery.parse_master_index(b"Access Denied")


def test_manifest_includes_extra_documents_and_unwraps_ixviewer() -> None:
    filing = discovery.parse_atom(_feed(_entry("1234567", "Issuer"))).filings[0]
    html = f'''<table><tr><th>Seq</th><th>Description</th><th>Document</th><th>Type</th><th>Size</th></tr>
<tr><td>1</td><td>Report</td><td><a href="/ix?doc=/Archives/edgar/data/1234567/000123456726000001/main.htm">main</a></td><td>4</td><td>1,024</td></tr>
<tr><td>2</td><td>Exhibit</td><td><a href="{BASE}exhibit.htm">exhibit</a></td><td>EX-10.1</td><td>512</td></tr></table>'''.encode()
    manifest = discovery.parse_filing_manifest(html, filing)
    assert [document.filename for document in manifest.documents] == [
        "main.htm",
        "exhibit.htm",
    ]
    assert manifest.documents[0].size_bytes == 1024
    assert manifest.documents[1].document_type == "EX-10.1"


def test_filing_from_hit_keeps_unknown_entity_unknown() -> None:
    hit = EFTSHit(
        accession_number=ACC,
        cik="0000000000",
        company_name="Unknown",
        form_type="4",
        filed_date=date(2026, 9, 25),
        filing_url=BASE + "primary.xml",
    )
    assert discovery.filing_from_hit(hit).entities == ()
    with pytest.raises(ValueError, match="no explicit"):
        discovery.filing_from_hit(hit.model_copy(update={"filing_url": None}))


def test_document_reader_fetches_only_selected_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch = AsyncMock(
        return_value=b"<html><body><p>Full selected evidence</p><script>ignore</script></body></html>"
    )
    monkeypatch.setattr(SecTransport, "get_bytes", fetch)
    document = FilingDocument(
        filename="exhibit.htm", url=HttpUrl(BASE + "exhibit.htm")
    )

    async def read():
        async with SecTransport("Test test@example.com") as transport:
            return await discovery.read_filing_document(transport, document)

    content = asyncio.run(read())
    assert content.text == "Full selected evidence"
    fetch.assert_awaited_once_with(str(document.url))
