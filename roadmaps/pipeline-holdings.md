# pipeline: `holdings` — Institutional Holdings Pipeline

## Purpose

Analyze 13F institutional ownership over time using the existing `holdings_parser.py`. Compute position changes, ownership concentration, and quarter-over-quarter diffs.

## Existing Implementations — Build vs. Reuse

**`edgartools`** (PyPI) provides 13F parsing and institutional ownership data. `company.get_filings(form="13F-HR")` returns structured info tables.

**`sec-api`** (PyPI) provides a 13F Holdings API for real-time monitoring of institutional ownership. Requires paid API key.

**`13f-filing-parser`** (various GitHub repos) — ad-hoc Python parsers for 13F XML info tables.

**Recommendation: Use the existing `holdings_parser.py` already in this project.** Same rationale as the insider pipeline — the parser is already implemented. The pipeline adds download orchestration, quarterly diff computation, and concentration analysis on top.

## Existing Code to Study

- `src/sec_nlp/core/edgar/holdings_parser.py` — existing `HoldingsParser` class.
- `src/sec_nlp/pipelines/presets/warranty/` — reference pipeline structure.
- `crates/efts` — for CUSIP-based filer lookup.

## File Structure

```
src/sec_nlp/pipelines/presets/holdings/
├── __init__.py
├── config.py           # HoldingsSettings(BasePipelineSettings)
├── models.py           # HoldingPosition, HoldingsDiff, OwnershipSummary
├── pipeline.py         # HoldingsPipeline(BasePipeline)
├── steps/
│   ├── __init__.py
│   ├── download.py     # Fetch 13F-HR filings
│   ├── parse.py        # Call existing HoldingsParser
│   ├── diff.py         # Quarter-over-quarter position changes
│   └── aggregate.py    # Ownership concentration, Herfindahl index
└── io/
    ├── __init__.py
    └── formats/
        ├── __init__.py
        ├── snapshot.py  # CSV holdings snapshot
        └── diff_report.py  # YAML/JSON diff report
```

## Pipeline Steps

### 1. `download`
Two modes:
- **By filer**: Given a list of institutional CIKs, fetch their 13F-HR filings for N quarters.
- **By CUSIP**: Given a target company's CUSIP, use EFTS to find all 13F filers holding that security, then fetch their filings.

### 2. `parse`
Call `HoldingsParser` on each filing. Extract info table entries: issuer name, CUSIP, title class, value (thousands), shares, share type (SH/PRN), investment discretion, voting authority.

### 3. `diff`
Compare consecutive quarterly filings from the same filer to compute position changes:
- New positions (present in Q2, absent in Q1).
- Exits (present in Q1, absent in Q2).
- Increases / decreases (share count delta).
- Position value change (using reported value or market price if available).

### 4. `aggregate`
Summarize across all filers for a target CUSIP:
- Top N holders by value.
- Total institutional ownership (shares held / shares outstanding, if available from XBRL).
- Herfindahl-Hirschman Index (HHI) of ownership concentration.
- Quarter-over-quarter change in total institutional ownership.

### 5. `output`
- Holdings snapshot (CSV): one row per position per filer.
- Diff report (YAML/JSON): per-filer position changes.
- Summary (YAML/JSON): top holders, HHI, total ownership percentage.

## Config (Pydantic)

```python
class HoldingsSettings(BasePipelineSettings):
    model_config = SettingsConfigDict(env_prefix="SEC_NLP_HOLDINGS_")
    symbol: str                      # Target company (used to resolve CUSIP)
    cusip: str = ""                  # Direct CUSIP override
    filer_ciks: list[str] = []       # Specific institutional filers
    quarters: int = 4
    top_holders: int = 20
    output_format: str = "csv"
```

## CLI Command

```
sec-nlp holdings AAPL --quarters 4 --top-holders 20
```

## Implementation Steps

- [x] Create `holdings/` directory with boilerplate.
- [x] Implement Pydantic models: `HoldingPosition`, `HoldingsDiff`, `OwnershipSummary` (frozen, extra="forbid").
- [x] Implement `download.py` — fetch 13F-HR filings.
- [x] Implement `parse.py` — call existing `HoldingsParser`, map to Pydantic models.
- [x] Implement `diff.py` — quarter-over-quarter comparison (adds/exits/increases/decreases).
- [x] Implement `aggregate.py` — compute top holdings, concentration HHI, and totals.
- [x] Implement output formatters.
- [x] Add CLI command, register in `root.py`.
- [x] Write tests: mock parser output, verify diff logic (add/exit/increase/decrease), verify HHI computation. No network.

## Dependencies

- Existing `holdings_parser.py`
- `crates/efts` (for CUSIP-based filer lookup)
- `sec_nlp.core.market` (optional, for position value calculation)
- No new PyPI dependencies
