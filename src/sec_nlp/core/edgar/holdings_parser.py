# src/sec_nlp/core/edgar/holdings_parser.py
"""Parse 13F holdings info tables into structured documents."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger
from sec_nlp.types import JsonDict, JsonValue


def _local_tag(tag: JsonValue) -> JsonValue:
    if isinstance(tag, str):
        if "}" in tag:
            return tag.split("}", 1)[1]
        if ":" in tag:
            return tag.split(":", 1)[1]
        return tag
    return tag


def _normalize_text(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
        return None
    return value


def _find_child(
    parent: ElementTree.Element, name: JsonValue
) -> ElementTree.Element | None:
    target = _local_tag(name)
    for child in list(parent):
        if _local_tag(child.tag) == target:
            return child
    return None


def _find_text(parent: ElementTree.Element, name: JsonValue) -> JsonValue:
    child = _find_child(parent, name)
    if child is None or child.text is None:
        return None
    return _normalize_text(child.text)


def _find_nested_text(
    parent: ElementTree.Element, first: JsonValue, second: JsonValue
) -> JsonValue:
    node = _find_child(parent, first)
    if node is None:
        return None
    return _find_text(node, second)


def _parse_int(value: JsonValue) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return int(float(cleaned))
        except ValueError:
            return None
    return None


def _parse_info_table(entry: ElementTree.Element) -> JsonDict:
    issuer = _find_text(entry, "nameOfIssuer")
    title = _find_text(entry, "titleOfClass")
    cusip = _find_text(entry, "cusip")
    value = _parse_int(_find_text(entry, "value"))
    shares = _parse_int(_find_nested_text(entry, "shrsOrPrnAmt", "sshPrnamt"))
    share_type = _find_nested_text(entry, "shrsOrPrnAmt", "sshPrnamtType")
    investment_discretion = _find_text(entry, "investmentDiscretion")
    other_manager = _find_text(entry, "otherManager")

    voting = _find_child(entry, "votingAuthority")
    voting_authority: JsonDict | None = None
    if voting is not None:
        sole = _parse_int(_find_text(voting, "Sole"))
        shared = _parse_int(_find_text(voting, "Shared"))
        none = _parse_int(_find_text(voting, "None"))
        voting_authority = {
            "sole": sole,
            "shared": shared,
            "none": none,
        }

    data: JsonDict = {
        "issuer": issuer,
        "title_of_class": title,
        "cusip": cusip,
        "value": value,
        "shares": shares,
        "share_type": share_type,
        "investment_discretion": investment_discretion,
        "other_manager": other_manager,
    }
    if voting_authority is not None:
        data["voting_authority"] = voting_authority
    return data


def _format_entry(entry: JsonDict) -> JsonValue:
    parts = []
    issuer = entry.get("issuer")
    if isinstance(issuer, str):
        parts.append(f"Issuer: {issuer}")
    title = entry.get("title_of_class")
    if isinstance(title, str):
        parts.append(f"Class: {title}")
    cusip = entry.get("cusip")
    if isinstance(cusip, str):
        parts.append(f"CUSIP: {cusip}")
    value = entry.get("value")
    if isinstance(value, (int, float)):
        parts.append(f"Value: {value}")
    shares = entry.get("shares")
    if isinstance(shares, (int, float)):
        parts.append(f"Shares: {shares}")
    share_type = entry.get("share_type")
    if isinstance(share_type, str):
        parts.append(f"Share type: {share_type}")
    return " | ".join(parts) if parts else "Holding entry"


def _extract_symbol(accession_dir: Path) -> JsonValue:
    parts = accession_dir.parts
    if "sec-edgar-filings" in parts:
        idx = parts.index("sec-edgar-filings")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _extract_form_type(accession_dir: Path) -> JsonValue:
    parent = accession_dir.parent
    if parent.name:
        return parent.name
    return None


def _parse_xml_text(xml_text: JsonValue) -> list[JsonDict]:
    if not isinstance(xml_text, str):
        return []
    text = xml_text.strip()
    if not text:
        return []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return []

    entries: list[JsonDict] = []
    for node in root.iter():
        tag = _local_tag(node.tag)
        if isinstance(tag, str) and tag.lower() == "infotable":
            entries.append(_parse_info_table(node))
    return entries


def _is_info_table_file(path: Path) -> bool:
    if not path.is_file():
        return False
    suffix = path.suffix.lower()
    if suffix not in {".xml", ".txt", ".htm", ".html"}:
        return False
    name = path.name.lower()
    if "infotable" in name or "informationtable" in name:
        return True
    if "info-table" in name:
        return True
    return "13f" in name and "table" in name


class HoldingsParser:
    """Parse 13F info tables into LangChain Documents."""

    def parse_accession_dir(self, accession_dir: Path) -> list[Document]:
        table_files = [
            path
            for path in accession_dir.rglob("*")
            if _is_info_table_file(path)
        ]
        if not table_files:
            fallback = accession_dir / "full-submission.txt"
            if fallback.exists():
                table_files = [fallback]

        if not table_files:
            logger.debug("No holdings tables found in %s", accession_dir)
            return []

        base_meta = self._build_base_metadata(accession_dir)
        docs: list[Document] = []
        for table_file in table_files:
            entries = self._parse_table_file(table_file)
            if not entries:
                continue
            for idx, entry in enumerate(entries, start=1):
                metadata = dict(base_meta)
                metadata.update(entry)
                metadata["source"] = str(table_file)
                metadata["holding_index"] = idx
                content = _format_entry(entry)
                if not isinstance(content, str):
                    content = "Holding entry"
                docs.append(
                    Document(
                        page_content=content,
                        metadata=metadata,
                    )
                )
        return docs

    def _build_base_metadata(self, accession_dir: Path) -> JsonDict:
        # Local import avoids ingest/loader circular imports at module load.
        from sec_nlp.core.ingest import filings

        filing_date = filings.get_filing_date_from_dir(accession_dir)
        filed_date = filing_date.isoformat() if filing_date else None
        return {
            "accession_number": accession_dir.name,
            "symbol": _extract_symbol(accession_dir),
            "form_type": _extract_form_type(accession_dir),
            "filed_date": filed_date,
        }

    def _parse_table_file(self, table_file: Path) -> list[JsonDict]:
        try:
            xml_text = table_file.read_text(errors="ignore")
        except OSError as exc:
            logger.debug("Failed to read %s: %s", table_file, exc)
            return []
        return _parse_xml_text(xml_text)


def parse_holdings_documents(accession_dir: Path) -> list[Document]:
    """Parse a 13F accession directory into holdings Documents."""
    return HoldingsParser().parse_accession_dir(accession_dir)
