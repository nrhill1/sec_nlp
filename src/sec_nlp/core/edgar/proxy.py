# src/sec_nlp/core/edgar/proxy.py
"""Proxy statement (DEF 14A) parsing helpers."""

from __future__ import annotations

import re
from datetime import date

from lxml import html
from pydantic import BaseModel, ConfigDict, Field

_WS_RE = re.compile(r"\s+")
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")
_PROPOSAL_RE = re.compile(
    r"\bproposal\s*(\d+)\b|\bitem\s*(\d+)\b|^\s*(\d+)\b",
    flags=re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


class ExecutiveCompensation(BaseModel):
    """Normalized summary-compensation row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    title: str
    salary: float
    bonus: float
    stock_awards: float
    option_awards: float
    non_equity_incentive: float
    other_compensation: float
    total: float
    fiscal_year: str


class ShareholderProposal(BaseModel):
    """Normalized shareholder proposal vote result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_number: int
    description: str
    proponent: str
    vote_for: int
    vote_against: int
    vote_abstain: int
    passed: bool


class BoardMember(BaseModel):
    """Normalized board-member row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    role: str
    committees: list[str] = Field(default_factory=list)
    independent: bool
    tenure_years: int | None = None


class SayOnPayResult(BaseModel):
    """Say-on-pay vote rollup."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    vote_for: int
    vote_against: int
    vote_abstain: int
    approval_percentage: float


class ProxyData(BaseModel):
    """Parsed DEF 14A payload."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accession_number: str
    filing_date: str
    compensation: list[ExecutiveCompensation]
    proposals: list[ShareholderProposal]
    board: list[BoardMember]
    say_on_pay: SayOnPayResult | None = None


def _normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return _WS_RE.sub(" ", value).strip()


def _normalize_header(value: str) -> str:
    cleaned = _normalize_text(value).lower()
    return re.sub(r"[^a-z0-9]+", " ", cleaned).strip()


def _parse_money(value: str | None) -> float:
    text = _normalize_text(value)
    if not text or text in {"-", "--", "—", "n/a", "na"}:
        return 0.0

    negative = "(" in text and ")" in text
    text = text.replace("$", "").replace(",", "")
    text = text.replace("(", "").replace(")", "")
    match = _NUM_RE.search(text)
    if match is None:
        return 0.0

    number = float(match.group(0))
    return -abs(number) if negative else number


def _parse_int(value: str | None) -> int:
    text = _normalize_text(value)
    if not text or text in {"-", "--", "—", "n/a", "na"}:
        return 0
    text = text.replace(",", "")
    match = _NUM_RE.search(text)
    if match is None:
        return 0
    return int(round(float(match.group(0))))


def _extract_year(text: str, fallback: str) -> str:
    match = _YEAR_RE.search(text)
    if match is not None:
        return match.group(0)
    return fallback


def _split_name_title(value: str) -> tuple[str, str]:
    cleaned = _normalize_text(value)
    if not cleaned:
        return "", ""

    if "\n" in value:
        parts = [
            _normalize_text(part) for part in value.splitlines() if part.strip()
        ]
        if parts:
            name = parts[0]
            title = _normalize_text(" ".join(parts[1:]))
            return name, title

    if "," in cleaned:
        name, title = cleaned.split(",", 1)
        return _normalize_text(name), _normalize_text(title)

    if " - " in cleaned:
        name, title = cleaned.split(" - ", 1)
        return _normalize_text(name), _normalize_text(title)

    tokens = cleaned.split()
    title_tokens = {
        "chief",
        "president",
        "director",
        "officer",
        "chair",
        "chairman",
        "chairwoman",
        "ceo",
        "cfo",
        "coo",
        "vice",
        "executive",
    }
    for index, token in enumerate(tokens):
        if index < 2:
            continue
        if token.lower() in title_tokens:
            return (
                _normalize_text(" ".join(tokens[:index])),
                _normalize_text(" ".join(tokens[index:])),
            )

    return cleaned, ""


def _parse_html(html_text: str):
    if not html_text.strip():
        return html.fromstring("<html></html>")

    try:
        return html.fromstring(
            html_text, parser=html.HTMLParser(encoding="utf-8")
        )
    except Exception:
        return html.fromstring("<html></html>")


def _table_rows(table) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in table.xpath(".//tr"):
        cells = tr.xpath("./th|./td")
        if not cells:
            continue
        values = [_normalize_text(" ".join(cell.itertext())) for cell in cells]
        if any(values):
            rows.append(values)
    return rows


def _column_index(
    headers: list[str], token_groups: tuple[tuple[str, ...], ...]
) -> int | None:
    normalized = [_normalize_header(header) for header in headers]
    for index, header in enumerate(normalized):
        for tokens in token_groups:
            if all(token in header for token in tokens):
                return index
    return None


def _cell(row: list[str], index: int | None) -> str:
    if index is None or index < 0 or index >= len(row):
        return ""
    return row[index]


def _extract_compensation(
    root, *, filing_date: str
) -> list[ExecutiveCompensation]:
    default_year = str(date.fromisoformat(filing_date).year)
    extracted: list[ExecutiveCompensation] = []

    for table in root.xpath("//table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue

        headers = rows[0]
        has_name = (
            _column_index(headers, (("name",), ("principal", "position")))
            is not None
        )
        has_salary = _column_index(headers, (("salary",),)) is not None
        has_total = _column_index(headers, (("total",),)) is not None
        if not (has_name and has_salary and has_total):
            continue

        name_idx = _column_index(
            headers, (("name",), ("principal", "position"))
        )
        title_idx = _column_index(headers, (("title",), ("position",)))
        if title_idx == name_idx:
            title_idx = None
        salary_idx = _column_index(headers, (("salary",),))
        bonus_idx = _column_index(headers, (("bonus",),))
        stock_idx = _column_index(headers, (("stock", "award"),))
        option_idx = _column_index(headers, (("option", "award"),))
        incentive_idx = _column_index(
            headers, (("non", "equity", "incentive"), ("incentive",))
        )
        other_idx = _column_index(
            headers, (("other", "compensation"), ("all", "other"))
        )
        total_idx = _column_index(headers, (("total",),))

        heading_nodes = table.xpath(
            "preceding::*[self::h1 or self::h2 or self::h3][1]"
        )
        heading_text = ""
        if heading_nodes:
            heading_text = _normalize_text(
                " ".join(heading_nodes[0].itertext())
            )
        table_year = _extract_year(
            f"{heading_text} {' '.join(headers)}", default_year
        )
        for row in rows[1:]:
            raw_name = _cell(row, name_idx)
            if not raw_name:
                continue
            lowered_name = raw_name.strip().lower()
            if lowered_name in {"total", "totals"}:
                continue

            name, parsed_title = _split_name_title(raw_name)
            title = _cell(row, title_idx) or parsed_title
            if not name:
                continue

            salary = _parse_money(_cell(row, salary_idx))
            bonus = _parse_money(_cell(row, bonus_idx))
            stock_awards = _parse_money(_cell(row, stock_idx))
            option_awards = _parse_money(_cell(row, option_idx))
            non_equity_incentive = _parse_money(_cell(row, incentive_idx))
            other_compensation = _parse_money(_cell(row, other_idx))
            total = _parse_money(_cell(row, total_idx))
            if total == 0.0:
                total = (
                    salary
                    + bonus
                    + stock_awards
                    + option_awards
                    + non_equity_incentive
                    + other_compensation
                )

            extracted.append(
                ExecutiveCompensation(
                    name=name,
                    title=_normalize_text(title),
                    salary=salary,
                    bonus=bonus,
                    stock_awards=stock_awards,
                    option_awards=option_awards,
                    non_equity_incentive=non_equity_incentive,
                    other_compensation=other_compensation,
                    total=total,
                    fiscal_year=table_year,
                )
            )

    deduped: list[ExecutiveCompensation] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in extracted:
        key = (entry.name.casefold(), entry.title.casefold(), entry.fiscal_year)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)

    return deduped


def _proposal_number(value: str) -> int | None:
    match = _PROPOSAL_RE.search(value)
    if match is None:
        return None
    for group in match.groups():
        if group:
            return int(group)
    return None


def _extract_proposals(root) -> list[ShareholderProposal]:
    proposals: list[ShareholderProposal] = []

    for table in root.xpath("//table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue

        headers = rows[0]
        proposal_idx = _column_index(headers, (("proposal",), ("item",)))
        desc_idx = _column_index(headers, (("description",), ("matter",)))
        prop_idx = _column_index(headers, (("proponent",),))
        for_idx = _column_index(headers, (("for",),))
        against_idx = _column_index(headers, (("against",),))
        abstain_idx = _column_index(headers, (("abstain",),))

        if for_idx is None or against_idx is None:
            continue

        for row in rows[1:]:
            proposal_field = _cell(row, proposal_idx)
            description_field = _cell(row, desc_idx)

            proposal_number = _proposal_number(proposal_field)
            if proposal_number is None:
                proposal_number = _proposal_number(description_field)
            if proposal_number is None:
                continue

            description = _normalize_text(description_field or proposal_field)
            description = re.sub(
                r"^proposal\s*\d+\s*[-:]*\s*",
                "",
                description,
                flags=re.IGNORECASE,
            )

            proponent = _normalize_text(_cell(row, prop_idx)).lower()
            if not proponent:
                proponent = (
                    "management"
                    if "management" in description.lower()
                    else "shareholder"
                )

            vote_for = _parse_int(_cell(row, for_idx))
            vote_against = _parse_int(_cell(row, against_idx))
            vote_abstain = _parse_int(_cell(row, abstain_idx))

            proposals.append(
                ShareholderProposal(
                    proposal_number=proposal_number,
                    description=description,
                    proponent=proponent,
                    vote_for=vote_for,
                    vote_against=vote_against,
                    vote_abstain=vote_abstain,
                    passed=vote_for > vote_against,
                )
            )

    deduped: list[ShareholderProposal] = []
    seen: set[int] = set()
    for proposal in sorted(
        proposals, key=lambda current: current.proposal_number
    ):
        if proposal.proposal_number in seen:
            continue
        seen.add(proposal.proposal_number)
        deduped.append(proposal)

    return deduped


def _split_committees(value: str) -> list[str]:
    cleaned = _normalize_text(value)
    if not cleaned:
        return []
    items = re.split(r"[,;/]", cleaned)
    return [entry.strip() for entry in items if entry.strip()]


def _parse_independent(value: str) -> bool:
    lowered = _normalize_text(value).lower()
    if lowered in {"y", "yes", "true", "independent"}:
        return True
    if lowered in {"n", "no", "false", "not independent"}:
        return False
    return "independent" in lowered


def _extract_board(root) -> list[BoardMember]:
    members: list[BoardMember] = []

    for table in root.xpath("//table"):
        rows = _table_rows(table)
        if len(rows) < 2:
            continue

        headers = rows[0]
        name_idx = _column_index(headers, (("name",), ("director", "nominee")))
        if name_idx is None:
            continue

        has_board_signal = (
            _column_index(headers, (("committee",),)) is not None
            or _column_index(headers, (("independent",),)) is not None
            or _column_index(headers, (("role",), ("title",))) is not None
        )
        if not has_board_signal:
            continue

        role_idx = _column_index(
            headers, (("role",), ("title",), ("position",))
        )
        committee_idx = _column_index(headers, (("committee",),))
        independent_idx = _column_index(headers, (("independent",),))
        tenure_idx = _column_index(headers, (("tenure",), ("years",)))

        for row in rows[1:]:
            name = _normalize_text(_cell(row, name_idx))
            if not name:
                continue

            role = _normalize_text(_cell(row, role_idx)) or "director"
            committees = _split_committees(_cell(row, committee_idx))
            independent_raw = _cell(row, independent_idx)
            independent = _parse_independent(independent_raw)
            tenure_text = _cell(row, tenure_idx)
            tenure_years = _parse_int(tenure_text) if tenure_text else None

            members.append(
                BoardMember(
                    name=name,
                    role=role,
                    committees=committees,
                    independent=independent,
                    tenure_years=tenure_years,
                )
            )

    deduped: list[BoardMember] = []
    seen: set[str] = set()
    for member in members:
        key = member.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(member)

    return deduped


def _say_on_pay_from_proposals(
    proposals: list[ShareholderProposal],
) -> SayOnPayResult | None:
    for proposal in proposals:
        description = proposal.description.lower()
        if (
            "say on pay" not in description
            and "advisory vote on executive compensation" not in description
        ):
            continue

        total_votes = (
            proposal.vote_for + proposal.vote_against + proposal.vote_abstain
        )
        approval_percentage = (
            (proposal.vote_for / total_votes) * 100.0
            if total_votes > 0
            else 0.0
        )
        return SayOnPayResult(
            vote_for=proposal.vote_for,
            vote_against=proposal.vote_against,
            vote_abstain=proposal.vote_abstain,
            approval_percentage=approval_percentage,
        )
    return None


def parse_proxy(
    filing_html: str,
    accession_number: str,
    filing_date: str,
) -> ProxyData:
    """Extract structured data from a DEF 14A filing HTML."""

    root = _parse_html(filing_html)
    compensation = _extract_compensation(root, filing_date=filing_date)
    proposals = _extract_proposals(root)
    board = _extract_board(root)
    say_on_pay = _say_on_pay_from_proposals(proposals)

    return ProxyData(
        accession_number=accession_number,
        filing_date=filing_date,
        compensation=compensation,
        proposals=proposals,
        board=board,
        say_on_pay=say_on_pay,
    )


__all__: tuple[str, ...] = (
    "BoardMember",
    "ExecutiveCompensation",
    "ProxyData",
    "SayOnPayResult",
    "ShareholderProposal",
    "parse_proxy",
)
