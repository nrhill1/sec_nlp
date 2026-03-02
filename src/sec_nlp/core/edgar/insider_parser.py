# src/sec_nlp/core/edgar/insider_parser.py
"""Parse Forms 3/4 ownership XML into structured documents."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.types import as_json_dict
from sec_nlp.types import JsonDict, JsonValue


def _local_tag(tag: JsonValue) -> JsonValue:
    """Return an element tag name without namespace prefixes."""
    if isinstance(tag, str):
        if "}" in tag:
            return tag.split("}", 1)[1]
        if ":" in tag:
            return tag.split(":", 1)[1]
        return tag
    return tag


def _normalize_text(value: JsonValue) -> JsonValue:
    """Normalize text."""
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
        return None
    return value


def _find_child(
    parent: ElementTree.Element, name: JsonValue
) -> ElementTree.Element | None:
    """Find child."""
    target = _local_tag(name)
    for child in list(parent):
        if _local_tag(child.tag) == target:
            return child
    return None


def _find_children(
    parent: ElementTree.Element, name: JsonValue
) -> list[ElementTree.Element]:
    """Find children."""
    target = _local_tag(name)
    matches: list[ElementTree.Element] = []
    for child in list(parent):
        if _local_tag(child.tag) == target:
            matches.append(child)
    return matches


def _find_text(parent: ElementTree.Element, name: JsonValue) -> JsonValue:
    """Find text."""
    child = _find_child(parent, name)
    if child is None or child.text is None:
        return None
    return _normalize_text(child.text)


def _find_path_text(
    parent: ElementTree.Element, *names: JsonValue
) -> JsonValue:
    """Find path text."""
    node = parent
    for name in names:
        next_node = _find_child(node, name)
        if next_node is None:
            return None
        node = next_node
    if node.text is None:
        return None
    return _normalize_text(node.text)


def _parse_number(value: JsonValue) -> JsonValue:
    """Parse number."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            if "." in cleaned:
                return float(cleaned)
            return int(cleaned)
        except ValueError:
            try:
                return float(cleaned)
            except ValueError:
                return None
    return None


def _parse_bool(value: JsonValue) -> bool | None:
    """Parse bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"1", "true", "yes"}:
            return True
        if cleaned in {"0", "false", "no"}:
            return False
    return None


def _extract_node_text(node: ElementTree.Element) -> JsonValue:
    """Extract node text."""
    text = "".join(node.itertext()).strip()
    if not text:
        return None
    return _normalize_text(text)


def _extract_ownership_xml(text: JsonValue) -> JsonValue:
    """Extract ownership xml."""
    if not isinstance(text, str):
        return None
    start = text.find("<ownershipDocument")
    if start == -1:
        return None
    end = text.find("</ownershipDocument>")
    if end == -1:
        return None
    return text[start : end + len("</ownershipDocument>")]


def _find_ownership_root(
    root: ElementTree.Element,
) -> ElementTree.Element | None:
    """Find ownership root."""
    if _local_tag(root.tag) == "ownershipDocument":
        return root
    for node in root.iter():
        if _local_tag(node.tag) == "ownershipDocument":
            return node
    return None


def _collect_footnotes(root: ElementTree.Element) -> JsonDict:
    """Collect footnotes."""
    footnotes_node = _find_child(root, "footnotes")
    if footnotes_node is None:
        return {}
    mapping: JsonDict = {}
    for footnote in list(footnotes_node):
        if _local_tag(footnote.tag) != "footnote":
            continue
        footnote_id = footnote.attrib.get("id") or footnote.attrib.get("Id")
        if not footnote_id:
            continue
        text = _extract_node_text(footnote)
        if text is not None:
            mapping[footnote_id] = text
    return mapping


def _collect_footnote_ids(entry: ElementTree.Element) -> list[JsonValue]:
    """Collect footnote ids."""
    footnote_ids: list[JsonValue] = []
    seen: set[JsonValue] = set()
    for node in entry.iter():
        if _local_tag(node.tag) != "footnoteId":
            continue
        footnote_id = node.attrib.get("id") or node.attrib.get("Id")
        if not footnote_id or footnote_id in seen:
            continue
        seen.add(footnote_id)
        footnote_ids.append(footnote_id)
    return footnote_ids


def _classify_transaction_type(code: JsonValue) -> JsonValue:
    """Classify insider transaction codes into normalized transaction types."""
    if not isinstance(code, str):
        return None
    normalized = code.strip().upper()
    if normalized in {"P", "S"}:
        return "open_market"
    if normalized == "A":
        return "grant"
    return None


def _parse_reporting_owner(owner: ElementTree.Element) -> JsonDict:
    """Parse reporting owner."""
    data: JsonDict = {}
    owner_id = _find_child(owner, "reportingOwnerId")
    if owner_id is not None:
        owner_cik = _find_text(owner_id, "rptOwnerCik")
        owner_name = _find_text(owner_id, "rptOwnerName")
        if owner_cik is not None:
            data["owner_cik"] = owner_cik
        if owner_name is not None:
            data["owner_name"] = owner_name

    relationship = _find_child(owner, "reportingOwnerRelationship")
    roles: list[JsonValue] = []
    relationship_details: JsonDict = {}
    if relationship is not None:
        is_director = _parse_bool(_find_text(relationship, "isDirector"))
        if isinstance(is_director, bool):
            relationship_details["is_director"] = is_director
            if is_director:
                roles.append("director")

        is_officer = _parse_bool(_find_text(relationship, "isOfficer"))
        if isinstance(is_officer, bool):
            relationship_details["is_officer"] = is_officer
            if is_officer:
                roles.append("officer")

        is_ten_percent = _parse_bool(
            _find_text(relationship, "isTenPercentOwner")
        )
        if isinstance(is_ten_percent, bool):
            relationship_details["is_ten_percent_owner"] = is_ten_percent
            if is_ten_percent:
                roles.append("ten_percent_owner")

        is_other = _parse_bool(_find_text(relationship, "isOther"))
        if isinstance(is_other, bool):
            relationship_details["is_other"] = is_other
            if is_other:
                roles.append("other")

        officer_title = _find_text(relationship, "officerTitle")
        if officer_title is not None:
            relationship_details["officer_title"] = officer_title

        other_text = _find_text(relationship, "otherText")
        if other_text is not None:
            relationship_details["other_text"] = other_text

    if relationship_details:
        data["relationship"] = relationship_details
    if roles:
        data["relationship_roles"] = roles
    return data


def _parse_document_metadata(root: ElementTree.Element) -> JsonDict:
    """Parse document metadata."""
    doc_meta: JsonDict = {}
    document_type = _find_text(root, "documentType")
    if document_type is not None:
        doc_meta["document_type"] = document_type

    period_of_report = _find_text(root, "periodOfReport")
    if period_of_report is not None:
        doc_meta["period_of_report"] = period_of_report

    issuer = _find_child(root, "issuer")
    if issuer is not None:
        issuer_cik = _find_text(issuer, "issuerCik")
        issuer_name = _find_text(issuer, "issuerName")
        issuer_ticker = _find_text(issuer, "issuerTradingSymbol")
        if issuer_cik is not None:
            doc_meta["issuer_cik"] = issuer_cik
        if issuer_name is not None:
            doc_meta["issuer_name"] = issuer_name
        if issuer_ticker is not None:
            doc_meta["issuer_ticker"] = issuer_ticker

    owners = _find_children(root, "reportingOwner")
    reporting_owners: list[JsonValue] = []
    for owner in owners:
        reporting_owners.append(_parse_reporting_owner(owner))
    if reporting_owners:
        doc_meta["reporting_owners"] = reporting_owners
        primary = reporting_owners[0]
        primary_dict = as_json_dict(primary)
        if primary_dict is not None:
            primary_name = primary_dict.get("owner_name")
            primary_cik = primary_dict.get("owner_cik")
            if primary_name is not None:
                doc_meta["reporting_owner_name"] = primary_name
            if primary_cik is not None:
                doc_meta["reporting_owner_cik"] = primary_cik
            primary_roles = primary_dict.get("relationship_roles")
            if primary_roles is not None:
                doc_meta["relationship_to_issuer"] = primary_roles
            relationship = as_json_dict(primary_dict.get("relationship"))
            if relationship is not None:
                officer_title = relationship.get("officer_title")
                if officer_title is not None:
                    doc_meta["officer_title"] = officer_title

    return doc_meta


def _parse_entry(
    entry: ElementTree.Element,
    *,
    entry_kind: JsonValue,
    derivative: bool,
    is_holding: bool,
    document_type: JsonValue,
    footnotes: JsonDict,
    sequence: int,
) -> JsonDict:
    """Parse entry."""
    data: JsonDict = {
        "entry_type": entry_kind,
        "derivative": derivative,
        "security_type": "derivative" if derivative else "non-derivative",
    }

    security_title = _find_path_text(entry, "securityTitle", "value")
    if security_title is None:
        security_title = _find_text(entry, "securityTitle")
    if security_title is not None:
        data["security_title"] = security_title

    transaction_date = _find_path_text(entry, "transactionDate", "value")
    if transaction_date is not None:
        data["transaction_date"] = transaction_date

    transaction_code = _find_path_text(
        entry, "transactionCoding", "transactionCode"
    )
    if transaction_code is not None:
        data["transaction_code"] = transaction_code
        transaction_type = _classify_transaction_type(transaction_code)
        if transaction_type is not None:
            data["transaction_type"] = transaction_type

    transaction_form_type = _find_path_text(
        entry, "transactionCoding", "transactionFormType"
    )
    if transaction_form_type is not None:
        data["transaction_form_type"] = transaction_form_type

    transaction_shares = _parse_number(
        _find_path_text(
            entry, "transactionAmounts", "transactionShares", "value"
        )
    )
    if transaction_shares is not None:
        data["transaction_shares"] = transaction_shares

    transaction_price = _parse_number(
        _find_path_text(
            entry, "transactionAmounts", "transactionPricePerShare", "value"
        )
    )
    if transaction_price is not None:
        data["transaction_price"] = transaction_price

    acquired_disposed_code = _find_path_text(
        entry, "transactionAmounts", "transactionAcquiredDisposedCode", "value"
    )
    if acquired_disposed_code is not None:
        data["ownership_type"] = acquired_disposed_code

    shares_owned = _parse_number(
        _find_path_text(
            entry,
            "postTransactionAmounts",
            "sharesOwnedFollowingTransaction",
            "value",
        )
    )
    if shares_owned is not None:
        data["shares_owned_following_transaction"] = shares_owned

    direct_or_indirect = _find_path_text(
        entry, "ownershipNature", "directOrIndirectOwnership", "value"
    )
    if direct_or_indirect is not None:
        data["direct_or_indirect"] = direct_or_indirect

    nature_of_ownership = _find_path_text(
        entry, "ownershipNature", "natureOfOwnership", "value"
    )
    if nature_of_ownership is not None:
        data["nature_of_ownership"] = nature_of_ownership

    conversion_price = _parse_number(
        _find_path_text(entry, "conversionOrExercisePrice", "value")
    )
    if conversion_price is not None:
        data["conversion_or_exercise_price"] = conversion_price

    transaction_id = _find_text(entry, "transactionId")
    if transaction_id is None:
        transaction_id = _find_text(entry, "transactionSequence")
    if transaction_id is None:
        transaction_id = _find_text(entry, "transactionNumber")
    if transaction_id is None:
        transaction_id = f"{entry_kind}-{sequence}"
    data["transaction_id"] = transaction_id

    initial_holding = False
    if isinstance(document_type, str) and document_type.strip().startswith("3"):
        initial_holding = is_holding
    if initial_holding:
        data["initial_holding"] = True
    elif is_holding:
        data["initial_holding"] = False

    footnote_ids = _collect_footnote_ids(entry)
    if footnote_ids:
        data["footnote_ids"] = footnote_ids
        footnote_texts: list[JsonValue] = []
        for footnote_id in footnote_ids:
            if not isinstance(footnote_id, str):
                continue
            text = footnotes.get(footnote_id)
            if text is not None:
                footnote_texts.append(text)
        if footnote_texts:
            data["footnotes"] = footnote_texts

    return data


def _parse_ownership_document(xml_text: JsonValue) -> list[JsonDict]:
    """Parse ownership document."""
    if not isinstance(xml_text, str):
        return []
    text = xml_text.strip()
    if not text:
        return []
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        extracted = _extract_ownership_xml(text)
        if not extracted:
            return []
        if not isinstance(extracted, str):
            return []
        try:
            root = ElementTree.fromstring(extracted)
        except ElementTree.ParseError:
            return []

    ownership_root = _find_ownership_root(root)
    if ownership_root is None:
        return []

    doc_meta = _parse_document_metadata(ownership_root)
    document_type = doc_meta.get("document_type")
    footnotes = _collect_footnotes(ownership_root)

    entries: list[JsonDict] = []
    table_configs = (
        ("nonDerivativeTable", "nonDerivativeTransaction", False, False),
        ("nonDerivativeTable", "nonDerivativeHolding", False, True),
        ("derivativeTable", "derivativeTransaction", True, False),
        ("derivativeTable", "derivativeHolding", True, True),
    )

    for table_name, entry_name, derivative, is_holding in table_configs:
        table = _find_child(ownership_root, table_name)
        if table is None:
            continue
        entry_nodes = _find_children(table, entry_name)
        for idx, entry in enumerate(entry_nodes, start=1):
            entry_kind = f"{table_name}:{entry_name}"
            parsed = _parse_entry(
                entry,
                entry_kind=entry_kind,
                derivative=derivative,
                is_holding=is_holding,
                document_type=document_type,
                footnotes=footnotes,
                sequence=idx,
            )
            parsed.update(doc_meta)
            entries.append(parsed)

    return entries


def _format_entry(entry: JsonDict) -> JsonValue:
    """Format entry."""
    parts: list[JsonValue] = []
    security_title = entry.get("security_title")
    if isinstance(security_title, str):
        parts.append(f"Security: {security_title}")
    transaction_code = entry.get("transaction_code")
    if isinstance(transaction_code, str):
        parts.append(f"Code: {transaction_code}")
    transaction_shares = entry.get("transaction_shares")
    if isinstance(transaction_shares, (int, float)):
        parts.append(f"Shares: {transaction_shares}")
    transaction_price = entry.get("transaction_price")
    if isinstance(transaction_price, (int, float)):
        parts.append(f"Price: {transaction_price}")
    transaction_date = entry.get("transaction_date")
    if isinstance(transaction_date, str):
        parts.append(f"Date: {transaction_date}")
    transaction_type = entry.get("transaction_type")
    if isinstance(transaction_type, str):
        parts.append(f"Type: {transaction_type}")
    if entry.get("initial_holding") is True:
        parts.append("Initial holding")
    text_parts = [part for part in parts if isinstance(part, str)]
    return " | ".join(text_parts) if text_parts else "Insider transaction"


def _extract_symbol(accession_dir: Path) -> JsonValue:
    """Extract symbol."""
    parts = accession_dir.parts
    if "sec-edgar-filings" in parts:
        idx = parts.index("sec-edgar-filings")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _extract_form_type(accession_dir: Path) -> JsonValue:
    """Extract form type."""
    parent = accession_dir.parent
    if parent.name:
        return parent.name
    return None


class InsiderParser:
    """Parse Form 3/4 ownership documents into LangChain Documents."""

    def parse_accession_dir(self, accession_dir: Path) -> list[Document]:
        xml_files = list(accession_dir.rglob("*.xml"))
        if not xml_files:
            fallback = accession_dir / "full-submission.txt"
            if fallback.exists():
                xml_files = [fallback]

        if not xml_files:
            logger.debug("No ownership XML found in %s", accession_dir)
            return []

        base_meta = self._build_base_metadata(accession_dir)
        docs: list[Document] = []
        for xml_file in xml_files:
            entries = self._parse_xml_file(xml_file)
            if not entries:
                continue
            for idx, entry in enumerate(entries, start=1):
                metadata = dict(base_meta)
                metadata.update(entry)
                metadata["source"] = str(xml_file)
                metadata["transaction_index"] = idx
                content = _format_entry(entry)
                if not isinstance(content, str):
                    content = "Insider transaction"
                docs.append(
                    Document(
                        page_content=content,
                        metadata=metadata,
                    )
                )
        return docs

    def _build_base_metadata(self, accession_dir: Path) -> JsonDict:
        # Local import avoids ingest/loader circular imports at module load.
        """Build base metadata."""
        from sec_nlp.core.ingest import filings

        filing_date = filings.get_filing_date_from_dir(accession_dir)
        filed_date = filing_date.isoformat() if filing_date else None
        return {
            "accession_number": accession_dir.name,
            "symbol": _extract_symbol(accession_dir),
            "form_type": _extract_form_type(accession_dir),
            "filed_date": filed_date,
        }

    def _parse_xml_file(self, xml_file: Path) -> list[JsonDict]:
        """Parse xml file."""
        try:
            xml_text = xml_file.read_text(errors="ignore")
        except OSError as exc:
            logger.debug("Failed to read %s: %s", xml_file, exc)
            return []
        return _parse_ownership_document(xml_text)


def parse_insider_documents(accession_dir: Path) -> list[Document]:
    """Parse a Form 3/4 accession directory into transaction Documents."""
    return InsiderParser().parse_accession_dir(accession_dir)
