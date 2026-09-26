# src/sec_nlp/core/edgar/discovery.py
"""Discover market-wide SEC metadata and read selected filing documents.

Latest Filings Atom supplies a bounded current view. Published master indexes
supply catch-up metadata without issuer crawling. The caller persists coverage
only after these parsers finish successfully; neither empty feeds nor missing
HTTP resources imply complete historical coverage.
"""

import re
from datetime import date, datetime
from html import unescape
from pathlib import PurePosixPath
from typing import Literal
from urllib.parse import parse_qs, urljoin, urlsplit
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from pydantic import HttpUrl

from sec_nlp.core.edgar.efts_models import EFTSHit
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingEntity,
    FilingManifest,
    FilingPage,
    FilingRecord,
    IndexArtifact,
)
from sec_nlp.core.edgar.transport import SecTransport

_ATOM = "{http://www.w3.org/2005/Atom}"
_ACC = re.compile(r"\b(\d{10}-\d{2}-\d{6})\b")


def _sec_url(value: str) -> HttpUrl:
    """Require a credential-free SEC URL before returning a navigable resource."""
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not (host == "sec.gov" or host.endswith(".sec.gov"))
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Filing links must be HTTPS SEC URLs")
    return HttpUrl(value)


def _merge_records(records: list[FilingRecord]) -> tuple[FilingRecord, ...]:
    """Merge entity-role listings under their unique accession identities."""
    merged: dict[str, FilingRecord] = {}
    for record in records:
        previous = merged.get(record.accession_number)
        if previous is None:
            merged[record.accession_number] = record
            continue
        entities = tuple(dict.fromkeys((*previous.entities, *record.entities)))
        merged[record.accession_number] = previous.model_copy(
            update={"entities": entities}
        )
    return tuple(merged.values())


def parse_atom(
    content: bytes, *, start: int = 0, count: int = 100
) -> FilingPage:
    """Parse one SEC Atom page while retaining accession and entity identities.

    Args:
        content: Original Atom XML bytes.
        start: Requested ephemeral page offset.
        count: Requested maximum feed entries.

    Returns:
        Metadata with same-accession roles merged and a conservative next offset.

    Raises:
        ValueError: If required identities, URLs, or publication dates are malformed.
    """
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise ValueError("Malformed SEC Atom XML") from exc
    if root.tag != f"{_ATOM}feed":
        raise ValueError("Expected an Atom feed, not an error page")
    entries = root.findall(f"{_ATOM}entry")
    records: list[FilingRecord] = []
    for entry in entries:
        title = entry.findtext(f"{_ATOM}title", "")
        summary = entry.findtext(f"{_ATOM}summary", "")
        entry_id = entry.findtext(f"{_ATOM}id", "")
        links = entry.findall(f"{_ATOM}link")
        link = next(
            (
                element.attrib.get("href", "")
                for element in links
                if element.attrib.get("rel", "alternate") == "alternate"
            ),
            "",
        )
        accession_match = _ACC.search(f"{entry_id} {link} {summary}")
        entity_match = re.search(r"\((\d{1,10})\)\s*(?:\(([^)]+)\))?", title)
        archive_match = re.search(r"/Archives/edgar/data/(\d{1,10})/", link)
        if accession_match is None or (
            entity_match is None and archive_match is None
        ):
            raise ValueError(
                "SEC Atom entry is missing its accession or explicit CIK"
            )
        accession = accession_match.group(1)
        cik = (
            entity_match.group(1)
            if entity_match
            else archive_match.group(1)
            if archive_match
            else ""
        )
        category = entry.find(f"{_ATOM}category")
        form_type = (
            category.attrib.get("term", "") if category is not None else ""
        )
        prefix, separator, remainder = title.partition(" - ")
        form_type = form_type or (prefix.strip() if separator else "")
        if not form_type:
            raise ValueError("SEC Atom entry is missing its form type")
        company_name = (
            (remainder if separator else title).split(f"({cik})", 1)[0].strip()
        )
        plain_summary = unescape(re.sub(r"<[^>]+>", " ", summary))
        filed_match = re.search(
            r"Filed\s*:\s*(\d{4}-\d{2}-\d{2})", plain_summary, re.IGNORECASE
        )
        filed = (
            date.fromisoformat(filed_match.group(1)) if filed_match else None
        )
        archive_cik = (
            archive_match.group(1) if archive_match else cik.lstrip("0")
        )
        records.append(
            FilingRecord(
                accession_number=accession,
                entities=(
                    FilingEntity(
                        cik=cik,
                        name=company_name,
                        role=entity_match.group(2).casefold()
                        if entity_match and entity_match.group(2)
                        else "unknown",
                    ),
                ),
                form_type=form_type,
                filed_date=filed,
                accepted_at=None,
                filing_url=_sec_url(link),
                submission_url=_sec_url(
                    f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession.replace('-', '')}/{accession}.txt"
                ),
            )
        )
    next_start = start + len(entries) if len(entries) >= count else None
    for link_element in root.findall(f"{_ATOM}link"):
        if link_element.attrib.get("rel") == "next":
            target = _sec_url(link_element.attrib.get("href", ""))
            offsets = parse_qs(urlsplit(str(target)).query).get("start", [])
            if offsets and offsets[0].isdigit() and int(offsets[0]) > start:
                next_start = int(offsets[0])
    return FilingPage(
        filings=_merge_records(records),
        next_start=next_start,
        raw_entries=len(entries),
    )


async def fetch_latest_filings(
    transport: SecTransport,
    *,
    start: int = 0,
    count: int = 100,
    owner: Literal["include", "exclude", "only"] = "include",
) -> FilingPage:
    """Fetch one market-wide metadata page without downloading any documents.

    Args:
        transport: Shared SEC client owned by the application.
        start: Current refresh's page offset; never a durable checkpoint.
        count: Entries requested, bounded to 1–100.
        owner: Whether to include, exclude, or select ownership filings.

    Returns:
        Parsed metadata and conservative pagination information.

    Raises:
        ValueError: If pagination or ownership arguments are invalid.
    """
    if (
        start < 0
        or not 1 <= count <= 100
        or owner not in {"include", "exclude", "only"}
    ):
        raise ValueError(
            "Invalid Latest Filings pagination or ownership selection"
        )
    payload = await transport.get_bytes(
        "https://www.sec.gov/cgi-bin/browse-edgar",
        params={
            "action": "getcurrent",
            "output": "atom",
            "owner": owner,
            "start": start,
            "count": count,
        },
    )
    return parse_atom(payload, start=start, count=count)


def parse_master_index(content: bytes) -> tuple[FilingRecord, ...]:
    """Parse a complete SEC master index without inventing missing row metadata.

    Args:
        content: Original SEC pipe-delimited master-index bytes.

    Returns:
        Accession records retaining all listed CIK associations.

    Raises:
        ValueError: If the header or any filing row is malformed.
    """
    lines = content.decode("utf-8-sig", errors="replace").splitlines()
    header = next(
        (
            position
            for position, line in enumerate(lines)
            if line.strip().casefold()
            == "cik|company name|form type|date filed|filename"
        ),
        None,
    )
    if header is None:
        raise ValueError("SEC master index header is missing")
    records: list[FilingRecord] = []
    for line in lines[header + 1 :]:
        if not line.strip() or set(line.strip()) == {"-"}:
            continue
        columns = line.split("|")
        if len(columns) != 5:
            raise ValueError("Malformed master-index row")
        cik, company, form_type, filed, filename = (
            column.strip() for column in columns
        )
        accession_match = _ACC.search(filename)
        if accession_match is None or not re.fullmatch(
            r"edgar/data/\d{1,10}/\d{10}-\d{2}-\d{6}\.txt", filename
        ):
            raise ValueError("Invalid master-index submission path")
        accession = accession_match.group(1)
        records.append(
            FilingRecord(
                accession_number=accession,
                entities=(FilingEntity(cik=cik, name=company, role="indexed"),),
                form_type=form_type,
                filed_date=date.fromisoformat(filed),
                filing_url=_sec_url(
                    f"https://www.sec.gov/Archives/{filename[:-4]}-index.html"
                ),
                submission_url=_sec_url(
                    f"https://www.sec.gov/Archives/{filename}"
                ),
            )
        )
    return _merge_records(records)


async def list_daily_indexes(
    transport: SecTransport, *, year: int, quarter: int
) -> tuple[IndexArtifact, ...]:
    """List only published daily master indexes from an SEC directory manifest.

    Args:
        transport: Shared SEC client.
        year: Calendar year of the listing.
        quarter: Calendar quarter from one through four.

    Returns:
        Available daily index artifacts ordered by date.

    Raises:
        ValueError: If the directory payload is malformed.
    """
    base = (
        f"https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{quarter}/"
    )
    full_index_artifact(year=year, quarter=quarter)
    payload = await transport.get_json(base + "index.json")
    if (
        not isinstance(payload, dict)
        or not isinstance(directory := payload.get("directory"), dict)
        or not isinstance(items := directory.get("item"), list)
    ):
        raise ValueError("SEC index directory payload is malformed")
    artifacts: list[IndexArtifact] = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(
            name := item.get("name"), str
        ):
            raise ValueError("SEC index directory item is malformed")
        match = re.fullmatch(r"master\.(\d{8})\.idx", name)
        if match:
            published = datetime.strptime(match.group(1), "%Y%m%d").date()
            artifacts.append(
                IndexArtifact(
                    url=_sec_url(base + name),
                    year=year,
                    quarter=quarter,
                    kind="daily",
                    published_date=published,
                )
            )
    return tuple(
        sorted(artifacts, key=lambda artifact: str(artifact.published_date))
    )


def full_index_artifact(*, year: int, quarter: int) -> IndexArtifact:
    """Describe a quarter-wide master index without claiming it is published.

    Args:
        year: Calendar year requested.
        quarter: Calendar quarter requested.

    Returns:
        An artifact whose availability must be established by successful fetch.
    """
    return IndexArtifact(
        url=_sec_url(
            f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{quarter}/master.idx"
        ),
        year=year,
        quarter=quarter,
        kind="full",
    )


async def fetch_index(
    transport: SecTransport, artifact: IndexArtifact
) -> tuple[FilingRecord, ...]:
    """Fetch and fully validate an index before the caller commits coverage.

    Args:
        transport: Shared SEC client.
        artifact: Published daily or requested quarter-wide master index.

    Returns:
        Parsed metadata; HTTP and parse failures propagate without false emptiness.
    """
    return parse_master_index(await transport.get_bytes(str(artifact.url)))


def parse_filing_manifest(
    content: bytes, filing: FilingRecord
) -> FilingManifest:
    """Parse official document tables and preserve declared document types.

    Args:
        content: Filing-detail HTML bytes.
        filing: Parent accession metadata.

    Returns:
        Documents ordered by their provider table sequence.

    Raises:
        ValueError: If the response contains no usable document manifest.
    """
    soup = BeautifulSoup(content, "html.parser")
    documents: list[FilingDocument] = []
    seen: set[str] = set()
    for table in soup.find_all("table"):
        headers = [
            cell.get_text(" ", strip=True).casefold()
            for cell in table.find_all("th")
        ]
        if not {"seq", "description", "document", "type", "size"}.issubset(
            headers
        ):
            continue
        for row in table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 5:
                continue
            anchor = cells[2].find("a", href=True)
            if anchor is None:
                continue
            href = anchor.get("href")
            if not isinstance(href, str):
                continue
            url = urljoin(str(filing.filing_url), href)
            parsed = urlsplit(url)
            if parsed.path in {"/ix", "/ixviewer/doc/action"}:
                original = parse_qs(parsed.query).get("doc", [])
                if original:
                    url = urljoin("https://www.sec.gov", original[0])
            validated = _sec_url(url)
            filename = PurePosixPath(urlsplit(str(validated)).path).name
            if not filename or filename in seen:
                continue
            sequence = cells[0].get_text(strip=True)
            size = cells[4].get_text(strip=True).replace(",", "")
            documents.append(
                FilingDocument(
                    filename=filename,
                    url=validated,
                    sequence=int(sequence) if sequence.isdigit() else None,
                    description=cells[1].get_text(" ", strip=True),
                    document_type=cells[3].get_text(" ", strip=True),
                    size_bytes=int(size) if size.isdigit() else None,
                )
            )
            seen.add(filename)
    if not documents:
        raise ValueError("SEC filing document manifest was not found")
    return FilingManifest(filing=filing, documents=tuple(documents))


async def fetch_filing_manifest(
    transport: SecTransport, filing: FilingRecord
) -> FilingManifest:
    """Retrieve the document manifest only when its filing is selected.

    Args:
        transport: Shared SEC client.
        filing: Filing to inspect.

    Returns:
        All selectable document-table entries with original links.
    """
    return parse_filing_manifest(
        await transport.get_bytes(str(filing.filing_url)), filing
    )


async def read_filing_document(
    transport: SecTransport, document: FilingDocument
) -> DocumentContent:
    """Retrieve full readable text without keyword filtering or chunk truncation.

    Args:
        transport: Shared SEC client.
        document: Selected manifest entry.

    Returns:
        Full text plus original HTML when applicable.

    Raises:
        ValueError: If the selected resource is binary rather than readable text.
    """
    content = await transport.get_bytes(str(document.url))
    if content.startswith(b"%PDF") or b"\x00" in content[:4096]:
        raise ValueError(
            "This binary document must be opened through its source link"
        )
    text = content.decode("utf-8", errors="replace")
    if re.search(
        r"<(?:html|body|div|table|document|\?xml)\b", text, re.IGNORECASE
    ):
        soup = BeautifulSoup(text, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        return DocumentContent(
            document=document, text=soup.get_text("\n", strip=True), html=text
        )
    return DocumentContent(document=document, text=text)


def filing_from_hit(hit: EFTSHit) -> FilingRecord:
    """Convert search metadata without treating an accession prefix as an issuer.

    Args:
        hit: Validated EFTS hit with source-provided company identity and URL.

    Returns:
        An accession record with the explicitly identified entity, if known.

    Raises:
        ValueError: If neither an explicit CIK nor an SEC archive URL is usable.
    """
    accession = hit.accession_number
    if hit.filing_url:
        _sec_url(hit.filing_url)
    entities = (
        (FilingEntity(cik=hit.cik, name=hit.company_name),)
        if re.fullmatch(r"\d{1,10}", hit.cik) and int(hit.cik) > 0
        else ()
    )
    archive = re.search(
        r"/Archives/edgar/data/(\d{1,10})/", hit.filing_url or ""
    )
    archive_cik = (
        archive.group(1)
        if archive
        else (entities[0].cik.lstrip("0") if entities else "")
    )
    if not archive_cik:
        raise ValueError("Search hit has no explicit SEC archive identity")
    directory = f"https://www.sec.gov/Archives/edgar/data/{archive_cik}/{accession.replace('-', '')}/"
    return FilingRecord(
        accession_number=accession,
        entities=entities,
        form_type=hit.form_type,
        filed_date=hit.filed_date,
        filing_url=_sec_url(directory + accession + "-index.html"),
        submission_url=_sec_url(directory + accession + ".txt"),
    )
