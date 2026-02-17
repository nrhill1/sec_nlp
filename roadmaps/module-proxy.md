# module: `sec_nlp/core/edgar/proxy.py` — Proxy Statement (DEF 14A) Parser

## Purpose

Parse proxy statements (DEF 14A) to extract executive compensation tables, shareholder proposals, board composition, and say-on-pay vote results.

## Existing Implementations — Build vs. Reuse

**`edgartools`** (PyPI) provides DEF 14A parsing. `company.get_filings(form="DEF 14A")` retrieves proxy filings, though the depth of structured extraction for compensation tables varies.

**`sec-api`** (PyPI) provides proxy statement data via its SaaS API. Not local.

**No mature open-source Python library focuses specifically on DEF 14A structured extraction.** Proxy statements are notoriously inconsistent in HTML formatting — compensation tables, proposal descriptions, and vote tallies lack XBRL tagging (SEC requires XBRL for proxy only since 2024, and adoption is uneven).

**Recommendation: Custom implementation using HTML parsing + regex.** DEF 14A extraction is primarily an HTML table parsing problem. Use `lxml` (already in the project's dependency tree via other components) for table extraction, with regex patterns for compensation-specific patterns (salary, bonus, stock awards columns). XBRL-tagged proxy data can be handled via `crates/xbrl` when available. This is a domain-specific parser that doesn't exist as a reusable library.

## File Structure

```
src/sec_nlp/core/edgar/proxy.py   # Single file module
```

## Key APIs

```python
class ExecutiveCompensation(BaseModel):
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
    model_config = ConfigDict(frozen=True, extra="forbid")
    proposal_number: int
    description: str
    proponent: str        # "management" or shareholder name
    vote_for: int
    vote_against: int
    vote_abstain: int
    passed: bool

class BoardMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    role: str                          # "director", "chairman", etc.
    committees: list[str]              # "audit", "compensation", "nominating"
    independent: bool
    tenure_years: int | None = None

class SayOnPayResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    vote_for: int
    vote_against: int
    vote_abstain: int
    approval_percentage: float

class ProxyData(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    accession_number: str
    filing_date: str
    compensation: list[ExecutiveCompensation]
    proposals: list[ShareholderProposal]
    board: list[BoardMember]
    say_on_pay: SayOnPayResult | None = None


def parse_proxy(filing_html: str, accession_number: str, filing_date: str) -> ProxyData:
    """Extract structured data from a DEF 14A filing HTML."""
    ...
```

## Implementation Details

### Compensation Table Extraction
1. Parse HTML with `lxml.html`.
2. Find tables containing compensation-related headers (regex match for "salary", "bonus", "stock awards", "total", "name and principal position").
3. Extract rows, mapping columns to `ExecutiveCompensation` fields.
4. Normalize dollar values (remove "$", ",", handle "()" for negatives).

### Shareholder Proposal Extraction
1. Search for "Proposal" or "Item" headings in the document.
2. Extract proposal description text.
3. Find associated vote tallies (for/against/abstain) from nearby tables or text.

### Board Composition
1. Find "Board of Directors" or "Director Nominees" sections.
2. Extract names, roles, committee memberships.
3. Detect independence status from biographical text.

### Say-on-Pay
1. Find "Say-on-Pay" or "Advisory Vote on Executive Compensation" proposal.
2. Extract vote tallies and compute approval percentage.

## Implementation Steps

- [x] Implement all Pydantic models (frozen, extra="forbid").
- [x] Implement compensation table finder and parser.
- [x] Implement proposal extractor.
- [x] Implement board composition extractor.
- [x] Implement say-on-pay detector.
- [x] Wire into `parse_proxy()` top-level function.
- [x] Write tests: use fixture HTML files (sanitized excerpts from real proxy statements). Verify extraction accuracy against known values. No network.

## Dependencies

- `lxml` (likely already in dependency tree)
- No new PyPI dependencies beyond what's already used
- Optionally integrates with `crates/xbrl` for XBRL-tagged proxy data (2024+ filings)
