# src/sec_nlp/app/workspace/legacy_cache.py
"""Recover readable SEC evidence from preserved legacy submission caches.

Only SEC submission headers establish identity. Directory names and accession
prefixes never supply a missing CIK. Recognized documents are normalized into
the workspace cache without editing originals or replacing existing evidence.
"""

import logging
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from sec_nlp.app.workspace.store import WorkspaceStore
from sec_nlp.core.edgar.discovery import _document_content
from sec_nlp.core.edgar.filing_models import (
    DocumentContent,
    FilingDocument,
    FilingEntity,
    FilingManifest,
    FilingRecord,
)

logger = logging.getLogger(__name__)
_ACCESSION = re.compile(r"\d{10}-\d{2}-\d{6}")
_PARTIES = re.compile(
    r"^\s*(FILER|FILED BY|REPORTING-OWNER|SUBJECT COMPANY|ISSUER):\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _header_field(header: str, label: str) -> str:
    """Read a labeled SEC header value without consuming adjacent lines."""
    match = re.search(
        rf"^\s*{re.escape(label)}:[ \t]*([^\r\n]+)",
        header,
        re.IGNORECASE | re.MULTILINE,
    )
    return match.group(1).strip() if match else ""


def _header_entities(header: str) -> tuple[FilingEntity, ...]:
    """Retain explicitly declared CIKs and their surrounding SEC party roles."""
    boundaries = list(_PARTIES.finditer(header))
    entities: dict[tuple[str, str], FilingEntity] = {}
    sections = (
        (
            match.group(1).lower().replace("-", " "),
            header[match.end() : boundaries[index + 1].start()]
            if index + 1 < len(boundaries)
            else header[match.end() :],
        )
        for index, match in enumerate(boundaries)
    )
    for role, section in sections:
        for match in re.finditer(
            r"CENTRAL INDEX KEY:[ \t]*(\d+)", section, re.IGNORECASE
        ):
            entity = FilingEntity(
                cik=match.group(1),
                name=_header_field(
                    section[: match.start()], "COMPANY CONFORMED NAME"
                ),
                role="filer" if role == "filed by" else role,
            )
            entities[(entity.cik, entity.role)] = entity
    return tuple(entities.values())


def _submission_filing(text: str) -> FilingRecord:
    """Require accession, form, declared entity, and an SEC header before import."""
    match = re.search(
        r"<SEC-HEADER>.*?</SEC-HEADER>", text, re.IGNORECASE | re.DOTALL
    )
    if not match:
        raise ValueError("no complete SEC submission header")
    header = match.group()
    accession = _header_field(header, "ACCESSION NUMBER")
    form = _header_field(header, "CONFORMED SUBMISSION TYPE")
    entities = _header_entities(header)
    if not _ACCESSION.fullmatch(accession) or not form or not entities:
        raise ValueError(
            "SEC header lacks an accession, form, or declared party CIK"
        )
    filers = tuple(entity for entity in entities if entity.role == "filer")
    if len({entity.cik for entity in filers}) == 1:
        archive_cik = filers[0].cik
    elif len({entity.cik for entity in entities}) == 1:
        archive_cik = entities[0].cik
    else:
        raise ValueError("SEC header does not establish one archive filer CIK")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(archive_cik)}/{accession.replace('-', '')}"
    filed = _header_field(header, "FILED AS OF DATE")
    acceptance = re.search(
        r"<ACCEPTANCE-DATETIME>(\d{14})", header, re.IGNORECASE
    )
    return FilingRecord(
        accession_number=accession,
        entities=entities,
        form_type=form,
        filed_date=datetime.strptime(filed, "%Y%m%d").date() if filed else None,
        accepted_at=(
            datetime.strptime(acceptance.group(1), "%Y%m%d%H%M%S").replace(
                tzinfo=ZoneInfo("America/New_York")
            )
            if acceptance
            else None
        ),
        filing_url=HttpUrl(f"{base}/{accession}-index.html"),
        submission_url=HttpUrl(f"{base}/{accession}.txt"),
    )


def _sgml_field(block: str, label: str) -> str:
    """Read a document metadata tag preceding its TEXT payload."""
    metadata = re.split(r"<TEXT>", block, maxsplit=1, flags=re.IGNORECASE)[0]
    match = re.search(rf"<{label}>([^\r\n<]+)", metadata, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _submission_documents(
    text: str, filing: FilingRecord
) -> tuple[
    tuple[FilingDocument, ...], tuple[DocumentContent, ...], tuple[str, ...]
]:
    """Retain all document sources and extract each readable document independently."""
    contents: dict[str, DocumentContent] = {}
    documents: dict[str, FilingDocument] = {}
    warnings: list[str] = []
    base = str(filing.submission_url).rsplit("/", 1)[0]
    for block in re.findall(
        r"<DOCUMENT>(.*?)</DOCUMENT>", text, re.IGNORECASE | re.DOTALL
    ):
        filename = _sgml_field(block, "FILENAME")
        payload = re.search(
            r"<TEXT>(.*?)</TEXT>", block, re.IGNORECASE | re.DOTALL
        )
        if (
            not filename
            or filename in {".", ".."}
            or "/" in filename
            or "\\" in filename
            or payload is None
        ):
            continue
        sequence = _sgml_field(block, "SEQUENCE")
        document = FilingDocument(
            filename=filename,
            url=HttpUrl(f"{base}/{quote(filename, safe='._-')}"),
            sequence=int(sequence) if sequence.isdigit() else None,
            description=_sgml_field(block, "DESCRIPTION"),
            document_type=_sgml_field(block, "TYPE"),
        )
        documents[str(document.url)] = document
        try:
            contents[str(document.url)] = _document_content(
                payload.group(1).encode(), document
            )
        except ValueError as error:
            logger.debug(
                "Cannot extract legacy document %s", document.url, exc_info=True
            )
            warnings.append(f"Preserved source {document.url}: {error}")
    complete = FilingDocument(
        filename=f"{filing.accession_number}.txt",
        url=filing.submission_url,
        description="Complete submission preserved from legacy cache",
        document_type=filing.form_type,
    )
    documents[str(complete.url)] = complete
    try:
        contents[str(complete.url)] = _document_content(text.encode(), complete)
    except ValueError as error:
        logger.debug(
            "Cannot extract complete submission %s", complete.url, exc_info=True
        )
        warnings.append(f"Preserved source {complete.url}: {error}")
    return tuple(documents.values()), tuple(contents.values()), tuple(warnings)


def import_legacy_caches(
    roots: Sequence[Path], store: WorkspaceStore
) -> tuple[int, int, tuple[str, ...]]:
    """Import identified submissions and report files left as external pointers.

    Args:
        roots: Preserved legacy cache trees, which may overlap.
        store: Destination for offline filing metadata and document snapshots.

    Returns:
        New filing count, new document count, and visible ambiguity warnings.
    """
    seen: set[Path] = set()
    warnings: list[str] = []
    filings_imported = documents_imported = 0
    for root in roots:
        unrecognized = 0
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.resolve() in seen:
                continue
            seen.add(path.resolve())
            if path.name != "full-submission.txt" and not (
                path.suffix.lower() == ".txt"
                and _ACCESSION.fullmatch(path.stem)
            ):
                unrecognized += 1
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                filing = _submission_filing(text)
                imported_documents, contents, document_warnings = (
                    _submission_documents(text, filing)
                )
            except (OSError, ValueError) as error:
                logger.debug(
                    "Cannot identify legacy SEC cache %s", path, exc_info=True
                )
                warnings.append(f"Preserved {path}: {error}")
                continue
            warnings.extend(document_warnings)
            filings_imported += store.upsert_filings(
                (filing,), source=f"legacy-cache:{path}"
            )
            for content in contents:
                if store.load_document(content.document) is None:
                    store.cache_document(content)
                    documents_imported += 1
            existing = store.get_manifest(filing.accession_number)
            documents = (
                {str(item.url): item for item in existing.documents}
                if existing
                else {}
            )
            for document in imported_documents:
                documents.setdefault(str(document.url), document)
            store.save_manifest(
                FilingManifest(
                    filing=store.get_filing(filing.accession_number) or filing,
                    documents=tuple(documents.values()),
                )
            )
        if unrecognized:
            warnings.append(
                f"Preserved {unrecognized} additional file(s) under {root} as external cache pointers; no unambiguous SEC submission header was available for import."
            )
    return filings_imported, documents_imported, tuple(warnings)
