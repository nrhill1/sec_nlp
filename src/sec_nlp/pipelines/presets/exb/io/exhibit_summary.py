# src/sec_nlp/pipelines/presets/exb/io/exhibit_summary.py
"""Structured exhibit summaries for exhibit outputs."""

from __future__ import annotations

import hashlib
import html
import re
from datetime import date
from pathlib import Path

from langchain_core.documents import Document

from sec_nlp.core.infra.logger import logger
from sec_nlp.core.types import as_json_dict
from sec_nlp.pipelines.output_io import (
    build_run_file_stem,
    write_json,
    write_yaml,
)
from sec_nlp.types import JsonDict, JsonValue

from ..config import ExhibitConfig

_DATE_RE = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r")\s+\d{1,2},\s+\d{4}\b",
    re.IGNORECASE,
)

_FIRM_RE = re.compile(
    r"\b([A-Z][A-Za-z&.,' -]+?(?:LLP|LLC|L\.L\.P\.|L\.L\.C\.|P\.C\.|"
    r"P\.A\.|Inc\.|Incorporated|Corp\.|Corporation|Company|Co\.|S\.A\.|"
    r"B\.V\.|AG))\b"
)

_FIRM_PREFIXES = [
    "consent of the independent registered public accounting firm",
    "independent registered public accounting firm",
    "consent of",
    "we hereby consent",
    "we consent",
]

_OBLIGATION_TERMS = [
    "shall",
    "must",
    "agrees to",
    "agree to",
    "required to",
    "obligated to",
    "covenant",
    "undertakes to",
    "will",
]

_PARTY_SUFFIXES = [
    "inc",
    "corp",
    "corporation",
    "ltd",
    "llc",
    "llp",
    "l.p.",
    "co.",
    "company",
    "plc",
    "gmbh",
    "s.a.",
    "ag",
    "b.v.",
]


def write_exhibit_summary(
    *,
    symbol: JsonValue,
    docs: list[Document],
    config: ExhibitConfig,
) -> list[Path]:
    summary = build_exhibit_summary(
        symbol=symbol,
        docs=docs,
        config=config,
    )
    if not summary:
        return []

    output_files: list[Path] = []
    symbol_value = _normalize_symbol(symbol)
    output_dir = config.get_symbol_output_dir(symbol_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = build_run_file_stem(symbol_value, "exhibits", config.run_id)

    if config.export_format in ("yaml", "both"):
        yaml_file = output_dir / f"{base_name}.yaml"
        write_yaml(yaml_file, summary, sort_keys=False)
        output_files.append(yaml_file)
        logger.info("Exhibit summary written to %s", yaml_file)

    if config.export_format in ("json",):
        json_file = output_dir / f"{base_name}.json"
        write_json(json_file, summary)
        output_files.append(json_file)
        logger.info("Exhibit summary written to %s", json_file)

    return output_files


def build_exhibit_summary(
    *,
    symbol: JsonValue,
    docs: list[Document],
    config: ExhibitConfig,
) -> JsonDict:
    if not docs:
        return {}

    expected_exhibits = _normalize_exhibit_numbers(config.get_exhibit_numbers())
    expected_bases = _collect_exhibit_bases(expected_exhibits)
    grouped = _group_docs_by_accession(docs)

    accessions_payload: list[JsonDict] = []
    for accession, accession_docs in grouped.items():
        meta = _select_accession_meta(accession_docs)
        exhibits = _group_docs_by_exhibit(accession_docs)
        exhibit_details: JsonDict = {}
        present_exhibits: list[JsonValue] = []

        exhibit_categories_present: list[JsonValue] = []
        for exhibit_number, exhibit_docs in exhibits.items():
            base = _exhibit_base(exhibit_number) or exhibit_number
            if base and base not in present_exhibits:
                present_exhibits.append(base)
            details = _build_exhibit_details(base, exhibit_docs)
            if details:
                category = config.classify_exhibit_number(base)
                if category is not None:
                    details["category"] = category
                exhibit_details[str(base)] = details
            if base:
                category = config.classify_exhibit_number(base)
                if (
                    category is not None
                    and category not in exhibit_categories_present
                ):
                    exhibit_categories_present.append(category)

        accessions_payload.append(
            {
                "accession_number": accession,
                "filing_date": meta.get("filing_date"),
                "form_type": meta.get("form_type"),
                "exhibits_present": present_exhibits,
                "exhibit_categories": exhibit_categories_present,
                "exhibit_details": exhibit_details,
            }
        )

    accessions_payload.sort(key=_accession_sort_key)
    coverage_gaps = _build_coverage_gaps(accessions_payload, expected_bases)
    changes = _build_change_tracking(accessions_payload)

    summary: JsonDict = {
        "symbol": _normalize_symbol(symbol),
        "expected_exhibits": expected_bases,
        "expected_categories": config.get_exhibit_categories(),
        "accessions": accessions_payload,
        "coverage_gaps": coverage_gaps,
        "changes": changes,
    }
    return summary


def _normalize_symbol(value: JsonValue):
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned.upper() if cleaned else "unknown"
    if isinstance(value, (int, float)):
        return str(value)
    return "unknown"


def _normalize_exhibit_numbers(values: list[JsonValue]) -> list[JsonValue]:
    cleaned: list[JsonValue] = []
    seen = set()
    for item in values:
        if not isinstance(item, str):
            continue
        raw = item.strip()
        if not raw:
            continue
        normalized = raw.replace("_", ".").replace("-", ".")
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
    return cleaned


def _collect_exhibit_bases(values: list[JsonValue]) -> list[JsonValue]:
    bases: list[JsonValue] = []
    for item in values:
        if not isinstance(item, str):
            continue
        base = item.split(".")[0].strip()
        if base and base not in bases:
            bases.append(base)
    return bases


def _group_docs_by_accession(docs: list[Document]):
    grouped = {}
    for doc in docs:
        meta = doc.metadata or {}
        accession = _as_str(meta.get("accession_number")) or "unknown"
        grouped.setdefault(accession, []).append(doc)
    return grouped


def _group_docs_by_exhibit(docs: list[Document]):
    grouped = {}
    for doc in docs:
        meta = doc.metadata or {}
        exhibit = _as_str(meta.get("exhibit_number")) or _as_str(
            meta.get("section_number")
        )
        exhibit = exhibit or "unknown"
        grouped.setdefault(exhibit, []).append(doc)
    return grouped


def _select_accession_meta(docs: list[Document]) -> JsonDict:
    if not docs:
        return {}
    meta = docs[0].metadata or {}
    return {
        "filing_date": _as_str(meta.get("filing_date")),
        "form_type": _as_str(meta.get("form_type")),
    }


def _accession_sort_key(entry: JsonDict):
    raw_date = entry.get("filing_date")
    parsed = _parse_date(raw_date)
    if parsed is not None:
        return (0, parsed.isoformat())
    accession = entry.get("accession_number")
    return (1, accession if accession is not None else "")


def _build_exhibit_details(exhibit_number: JsonValue, docs: list[Document]):
    if not docs:
        return {}
    combined = _collect_text(docs)
    filenames = _collect_meta_values(docs, "filename")
    descriptions = _collect_meta_values(docs, "description")
    sources = _collect_meta_values(docs, "source")

    details: JsonDict = {
        "filenames": filenames,
        "descriptions": descriptions,
        "sources": sources,
    }

    base = _exhibit_base(exhibit_number)
    if base == "21":
        subsidiaries = _extract_subsidiaries(combined)
        details["subsidiary_count"] = len(subsidiaries)
        details["subsidiaries"] = subsidiaries
    elif base == "23":
        consent = _extract_auditor_consent(combined)
        details.update(consent)
    elif base == "10":
        details["counterparties"] = _extract_counterparties(combined)
        details["key_obligations"] = _extract_obligations(combined)
    elif base == "99":
        headline = _extract_press_release_headline(combined)
        if headline:
            details["headline"] = headline
    elif base == "101":
        details["xbrl_files"] = filenames

    return details


def _build_coverage_gaps(
    accessions: list[JsonDict],
    expected: list[JsonValue],
) -> list[JsonDict]:
    gaps: list[JsonDict] = []
    for entry in accessions:
        present = entry.get("exhibits_present")
        if not isinstance(present, list):
            present = []
        missing = [value for value in expected if value not in present]
        if missing:
            gaps.append(
                {
                    "accession_number": entry.get("accession_number"),
                    "missing_exhibits": missing,
                }
            )
    return gaps


def _build_change_tracking(accessions: list[JsonDict]) -> JsonDict:
    if len(accessions) < 2:
        return {}

    ordered = sorted(accessions, key=_accession_sort_key)
    previous = ordered[-2]
    current = ordered[-1]

    previous_subs = _collect_subsidiary_names(previous)
    current_subs = _collect_subsidiary_names(current)
    subs_changes = _diff_sets(previous_subs, current_subs)

    previous_auditor = _extract_auditor_name(previous)
    current_auditor = _extract_auditor_name(current)
    auditor_change: JsonDict = {}
    if previous_auditor != current_auditor:
        auditor_change = {
            "from_accession": previous.get("accession_number"),
            "to_accession": current.get("accession_number"),
            "from_auditor": previous_auditor,
            "to_auditor": current_auditor,
        }

    changes: JsonDict = {}
    if subs_changes:
        changes["subsidiaries"] = {
            "from_accession": previous.get("accession_number"),
            "to_accession": current.get("accession_number"),
            **subs_changes,
        }
    if auditor_change:
        changes["auditor"] = auditor_change
    return changes


def _collect_subsidiary_names(entry: JsonDict):
    details = as_json_dict(entry.get("exhibit_details"))
    if details is None:
        return set()
    exhibit = as_json_dict(details.get("21"))
    if exhibit is None:
        return set()
    subsidiaries = exhibit.get("subsidiaries")
    if not isinstance(subsidiaries, list):
        return set()
    names = set()
    for sub in subsidiaries:
        sub_dict = as_json_dict(sub)
        if sub_dict is None:
            continue
        name = sub_dict.get("name")
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return names


def _extract_auditor_name(entry: JsonDict):
    details = as_json_dict(entry.get("exhibit_details"))
    if details is None:
        return None
    exhibit = as_json_dict(details.get("23"))
    if exhibit is None:
        return None
    name = exhibit.get("auditor_name")
    return name if isinstance(name, str) and name.strip() else None


def _diff_sets(previous: set, current: set) -> JsonDict:
    added = sorted(current - previous)
    removed = sorted(previous - current)
    if not added and not removed:
        return {}
    return {"added": added, "removed": removed}


def _collect_text(docs: list[Document]):
    parts: list[JsonValue] = []
    seen = set()
    for doc in docs:
        text = (doc.page_content or "").strip()
        if not text:
            continue
        digest = hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()
        if digest in seen:
            continue
        seen.add(digest)
        parts.append(text)
    return "\n".join([part for part in parts if isinstance(part, str)])


def _collect_meta_values(docs: list[Document], key):
    values: list[JsonValue] = []
    seen = set()
    for doc in docs:
        meta = doc.metadata or {}
        raw = _as_str(meta.get(key))
        if not raw or raw in seen:
            continue
        seen.add(raw)
        values.append(raw)
    return [value for value in values if isinstance(value, str)]


def _exhibit_base(value: JsonValue):
    if isinstance(value, str):
        cleaned = value.split(".")[0].strip()
        return cleaned if cleaned else None
    return None


def _extract_subsidiaries(value: JsonValue) -> list[JsonDict]:
    text = _text_from_html(value)
    if not text:
        return []

    subsidiaries: list[JsonDict] = []
    seen = set()
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if "subsidiary" in lower and "jurisdiction" in lower:
            continue
        if lower.startswith("exhibit") or lower.startswith("schedule"):
            continue
        parts = [part.strip() for part in re.split(r"\t|\s{2,}", cleaned)]
        parts = [part for part in parts if part]
        name = None
        jurisdiction = None
        if len(parts) >= 2:
            name = _strip_footnote(parts[0])
            jurisdiction = _strip_footnote(parts[1])
        else:
            tokens = cleaned.split()
            if len(tokens) >= 2:
                name = _strip_footnote(" ".join(tokens[:-1]))
                jurisdiction = _strip_footnote(tokens[-1])
        if not name or not jurisdiction:
            continue
        key = f"{name.lower()}|{jurisdiction.lower()}"
        if key in seen:
            continue
        seen.add(key)
        subsidiaries.append({"name": name, "jurisdiction": jurisdiction})
    return subsidiaries


def _extract_auditor_consent(value: JsonValue) -> JsonDict:
    text = _text_from_html(value)
    if not text or "consent" not in text.lower():
        return {}

    firm = _find_auditor_name(text)
    consent_date = _find_consent_date(text)
    payload: JsonDict = {}
    if firm:
        payload["auditor_name"] = firm
    if consent_date:
        payload["consent_date"] = consent_date
    return payload


def _find_auditor_name(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for idx, line in enumerate(lines):
        lower = line.lower()
        if "independent registered public accounting firm" in lower:
            candidate = _scan_firm_lines(lines[max(0, idx - 2) : idx + 3])
            if candidate:
                return candidate
    return _scan_firm_lines(lines)


def _scan_firm_lines(lines):
    for line in lines:
        match = _FIRM_RE.search(line)
        if match:
            candidate = _clean_firm_name(match.group(1))
            if candidate:
                return candidate
    return None


def _clean_firm_name(value):
    cleaned = value.strip()
    if ". " in cleaned:
        cleaned = cleaned.split(". ")[-1].strip()
    lowered = cleaned.lower()
    for prefix in _FIRM_PREFIXES:
        if lowered.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip(" ,.-")
            break
    return cleaned.strip()


def _find_consent_date(text):
    match = _DATE_RE.search(text)
    if match:
        return match.group(0)
    return None


def _extract_counterparties(value: JsonValue) -> list[JsonValue]:
    text = _text_from_html(value)
    if not text:
        return []

    parties = set()
    for match in re.finditer(
        r"\b(?:between|among)\s+(.+?)(?:\.|\n|;)",
        text,
        re.IGNORECASE,
    ):
        segment = match.group(1)
        for part in re.split(r"\band\b|,", segment, flags=re.IGNORECASE):
            cleaned = _cleanup_party(part)
            if _looks_like_party(cleaned):
                parties.add(cleaned)

    return sorted(parties)


def _extract_obligations(value: JsonValue) -> list[JsonValue]:
    text = _text_from_html(value)
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    obligations: list[JsonValue] = []
    for sentence in sentences:
        cleaned = sentence.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if not any(term in lower for term in _OBLIGATION_TERMS):
            continue
        if len(cleaned) > 400:
            cleaned = cleaned[:397].rstrip() + "..."
        obligations.append(cleaned)
        if len(obligations) >= 8:
            break
    return obligations


def _extract_press_release_headline(value: JsonValue) -> JsonValue:
    text = _text_from_html(value)
    if not text:
        return None
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        lower = cleaned.lower()
        if lower.startswith("exhibit") or lower.startswith("table of contents"):
            continue
        if 10 <= len(cleaned) <= 160:
            return cleaned
    return None


def _looks_like_party(value) -> bool:
    if not value:
        return False
    lower = value.lower()
    if lower in ("the company", "company", "the parties"):
        return False
    if any(suffix in lower for suffix in _PARTY_SUFFIXES):
        return True
    return sum(1 for char in value if char.isupper()) >= 2


def _cleanup_party(value):
    cleaned = value.strip().strip('"')
    cleaned = re.sub(r"\s*\(.*?\)", "", cleaned)
    return cleaned.strip()


def _strip_footnote(value):
    cleaned = re.sub(r"\s*[\*]+", "", value)
    cleaned = re.sub(r"\s*\(\d+\)$", "", cleaned)
    return cleaned.strip()


def _text_from_html(value: JsonValue):
    if not isinstance(value, str):
        return ""
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)</tr>", "\n", text)
    text = re.sub(r"(?i)<t[dh][^>]*>", "\t", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def _as_str(value: JsonValue):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (str, int, float)):
        cleaned = str(value).strip()
        return cleaned if cleaned else None
    return None


def _parse_date(value: JsonValue) -> date | None:
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, date):
        return value
    return None
