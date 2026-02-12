# pipeline: `financials` — Financial Fact Extraction Pipeline

## Purpose

Extract structured financial data from XBRL-tagged filings (10-K, 10-Q) and produce normalized time-series tables with derived ratios. Replaces manual XBRL parsing with a repeatable, CLI-driven pipeline.

## Existing Implementations — Build vs. Reuse

**`edgartools`** (PyPI, `dgunning/edgartools`) is the most complete Python EDGAR library. It already provides `filing.xbrl()` → statements API, maps ~2,000 XBRL tags to 95 standardized concepts, supports multi-period stitching via `XBRLS`, and exports to pandas DataFrames.

**`sec-api`** (PyPI, `janlukasschroeder/sec-api-python`) provides XBRL-to-JSON conversion as a hosted SaaS API. Requires API key and network calls.

**`pysec`** (GitHub, `lukerosiak/pysec`) is a Django-based XBRL parser extracting 50+ accounting terms. Dated but functional.

**Recommendation: Build on top of `crates/xbrl` (which wraps `crabrl`), not `edgartools`.** `edgartools` is a full-stack EDGAR client that overlaps with our existing `crates/efts` and download infrastructure — pulling it in would duplicate our HTTP/download layer and introduce a competing Company/Filing model hierarchy. Instead, use our own download + `crates/xbrl` for parsing, and reimplement the taxonomy normalization (mapping tag variants to canonical concepts) as a Python-side mapping dict. This keeps the architecture consistent with the existing `sec-nlp` pattern where Rust handles the heavy lifting and Python orchestrates. Reference `edgartools`' 95-concept mapping as a design guide for which financial line items to normalize.

## Existing Code to Study

- `src/sec_nlp/pipelines/presets/warranty/` — reference pipeline structure (config, models, pipeline, steps, io).
- `src/sec_nlp/pipelines/presets/warranty/steps/extract/xbrl.py` — current XBRL extraction (warranty-specific).
- `src/sec_nlp/core/ingest/downloader.py` — reuse for filing download.
- `src/sec_nlp/cli/commands/warranty.py` — reference CLI command (27 lines).

## File Structure

```
src/sec_nlp/pipelines/presets/financials/
├── __init__.py
├── config.py           # FinancialsSettings(BasePipelineSettings)
├── models.py           # FinancialFact, FinancialStatement, FinancialsResult
├── pipeline.py         # FinancialsPipeline(BasePipeline)
├── steps/
│   ├── __init__.py
│   ├── download.py     # Reuse existing downloader for 10-K/10-Q
│   ├── extract.py      # Call crates/xbrl, normalize tags to canonical names
│   └── aggregate.py    # Pivot to period table, compute derived ratios
└── io/
    ├── __init__.py
    └── formats/
        ├── __init__.py
        ├── csv_writer.py
        └── json_writer.py
```

## Pipeline Steps

### 1. `download`
Reuse `sec_nlp.core.ingest.downloader` to fetch 10-K/10-Q filings for the target symbol. Accept `--periods N` to control how many quarters/years to fetch.

### 2. `extract`
Call `crates/xbrl` via the Python wrapper (`sec_nlp.core.edgar.xbrl_facts`) to parse each filing's XBRL. Returns raw facts as `list[FinancialFact]` with fields: `concept`, `value`, `unit`, `decimals`, `period_start`, `period_end`, `segment`.

Apply taxonomy normalization: map raw US-GAAP/IFRS concept names to canonical labels. The mapping dict should cover at minimum:
- Revenue (RevenueFromContractWithCustomerExcludingAssessedTax, Revenues, SalesRevenueNet, ...)
- NetIncome (NetIncomeLoss, ProfitLoss, ...)
- EPS (EarningsPerShareBasic, EarningsPerShareDiluted)
- TotalAssets, TotalLiabilities, StockholdersEquity, CashAndCashEquivalents, LongTermDebt, OperatingIncome, GrossProfit

### 3. `aggregate`
Pivot facts into a per-period table (rows = periods, columns = financial line items). Compute derived ratios:
- CurrentRatio = CurrentAssets / CurrentLiabilities
- DebtToEquity = TotalLiabilities / StockholdersEquity
- GrossMargin = GrossProfit / Revenue
- OperatingMargin = OperatingIncome / Revenue
- ROE = NetIncome / StockholdersEquity

Optionally emit a delta report comparing latest period to prior periods (absolute and percentage change).

### 4. `output`
Write to CSV, JSON, or YAML via the io/ formatters. CSV uses one row per period, one column per metric.

## Config (Pydantic)

```python
class FinancialsSettings(BasePipelineSettings):
    model_config = SettingsConfigDict(env_prefix="SEC_NLP_FINANCIALS_")
    symbol: str
    form_types: list[str] = ["10-K", "10-Q"]
    periods: int = 8
    compute_ratios: bool = True
    output_format: str = "csv"
```

## CLI Command

```
sec-nlp financials AAPL --periods 8 --ratios --output-format csv
```

Inherit `FinancialsSettings` and `BasePipelineCommand`. Register in `root.py`.

## Implementation Steps

1. Create `financials/` directory with `__init__.py`, `config.py`, `models.py`.
2. Implement `FinancialFact` and `FinancialStatement` Pydantic models (frozen, extra="forbid").
3. Implement `download.py` step — thin adapter calling existing downloader.
4. Implement `extract.py` step — call `crates/xbrl` wrapper, apply taxonomy mapping.
5. Implement `aggregate.py` step — pivot, compute ratios.
6. Implement `pipeline.py` — wire steps together following `BasePipeline` pattern.
7. Implement CSV/JSON output formatters.
8. Add CLI command in `sec_nlp/cli/commands/financials.py`.
9. Register in `root.py`.
10. Write tests: mock the XBRL crate, verify taxonomy mapping, verify ratio computation with known values. No network.

## Dependencies

- `crates/xbrl` (via `sec_nlp.core.edgar.xbrl_facts`)
- Existing download/ingest infrastructure
- No new PyPI dependencies
