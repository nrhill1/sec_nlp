# sec-nlp

[![codecov](https://codecov.io/gh/nrhill1/sec_nlp/graph/badge.svg)](https://codecov.io/gh/nrhill1/sec_nlp)

SEC/market intelligence toolkit with Python pipeline orchestration and Rust-backed extensions. It supports local LLM analysis, deterministic extraction pipelines, filing retrieval, and timeline/correlation workflows from a single CLI.

## Highlights
- Local-first filing analysis with Ollama-backed models
- Deterministic pipelines for XBRL, 13F, insider, news, and event workflows
- EFTS-first retrieval and optional Qdrant vector indexing/search
- Rust extensions for EFTS and market data access
- Run-scoped outputs with run registry metadata

## Requirements
- Python 3.13+
- `uv` (recommended) or `pip`
- Ollama for LLM/embedding flows (`analyze`, `chat`, and embedding-indexed workflows)
- Docker (optional) for `sec-nlp qdrant up`
- Rust toolchain + `maturin` when building extensions from source

## Pipeline Commands
| Command | Purpose | LLM Required |
| --- | --- | --- |
| `analyze` | Topic/query-driven filing analysis with optional market correlation | Yes |
| `exb` | Exhibit extraction, indexing, and semantic search | No (embeddings only) |
| `warranty` | Warranty extraction from XBRL and normalized period outputs | No |
| `financials` | Structured financial statement extraction from filing XBRL | No |
| `holdings` | 13F holdings snapshots and quarter-over-quarter diffs | No |
| `insider` | Form 3/4/5 transaction analysis and alerting | No |
| `news` | Headline ingestion + filing/market correlation timeline | No |
| `events` | 8-K/6-K event detection with optional news/market context | No |
| `retrieve` | EFTS-first ranked retrieval and optional vector indexing | No (unless embedding rerank/index enabled) |
| `chat` | Retrieval-augmented Q&A over indexed filing chunks | Yes |

## Utility Commands
- `sec-nlp efts` - direct SEC EDGAR Full-Text Search queries
- `sec-nlp market` - Yahoo-backed market extension lookups (latest/range)
- `sec-nlp qdrant` - Qdrant container + collection management
- `sec-nlp runs` - run registry inspection/pruning
- `sec-nlp clean` - remove downloads/outputs/logs
- `sec-nlp version` - current package version

## Quickstart
### 1) Install
Using `uv`:
```bash
uv sync
uv run sec-nlp --help
```

Using `pip`:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2) Build Rust extensions (source checkout)
```bash
make build-ext
```

### 3) Set SEC contact email(s)
At minimum, set email for whichever pipeline(s) you run.

```bash
# .env examples
ANALYZE_EMAIL=you@example.com
EXB_EMAIL=you@example.com
WARRANTY_EMAIL=you@example.com
SEC_NLP_FINANCIALS_EMAIL=you@example.com
SEC_NLP_HOLDINGS_EMAIL=you@example.com
SEC_NLP_INSIDER_EMAIL=you@example.com
SEC_NLP_NEWS_EMAIL=you@example.com
SEC_NLP_EVENTS_EMAIL=you@example.com
SEC_NLP_RETRIEVE_EMAIL=you@example.com
SEC_NLP_CHAT_EMAIL=you@example.com
```

### 4) Start local services as needed
```bash
ollama serve
ollama pull llama3.2:1b
ollama pull bge-m3
ollama pull mxbai-embed-large
```

Optional persistent Qdrant:
```bash
sec-nlp qdrant up
```

### 5) Run examples
```bash
sec-nlp analyze AAPL --preset quick
sec-nlp exb DE --exhibit-categories subsidiaries consents
sec-nlp warranty AAPL
sec-nlp financials AAPL --periods 4
sec-nlp holdings AAPL --quarters 4
sec-nlp insider AAPL --lookback-months 12
sec-nlp news AAPL --topics tariffs supply_chain
sec-nlp events AAPL --event-types merger restatement
sec-nlp retrieve AAPL --queries "supply chain" "pricing pressure"
sec-nlp chat AAPL --question "What did management say about warranty risk?"
```

## Analyze Presets
Use `--preset <name>` with `sec-nlp analyze`.
- `quick`
- `laptop`
- `thorough`
- `comprehensive`
- `rare_earths`

Run `sec-nlp analyze --help` for full preset effects.

## Configuration
Config precedence:
1. CLI args
2. Environment variables
3. `.env`

Pipeline env prefixes:
- `ANALYZE_`
- `EXB_`
- `WARRANTY_`
- `SEC_NLP_FINANCIALS_`
- `SEC_NLP_HOLDINGS_`
- `SEC_NLP_INSIDER_`
- `SEC_NLP_NEWS_`
- `SEC_NLP_EVENTS_`
- `SEC_NLP_RETRIEVE_`
- `SEC_NLP_CHAT_`

Nested fields:
- Env: `__` delimiters, e.g. `ANALYZE_LLM__MODEL_NAME=llama3.2:1b`
- CLI: dot notation, e.g. `--llm.model-name`, `--search.queries`, `--vdb.collection-name`

## Outputs and Run Layout
Run-scoped outputs are written under:

```text
outputs/<run_timestamp>/<pipeline_type>/<SYMBOL>/...
```

Representative artifacts:
- Analyze: `<accession>/analysis.{yaml,json,csv}`, `analysis_summary.yaml`, `search/summary.yaml`
- Exhibit: `<symbol>_exhibit_index_<run_id>.{yaml,json,csv}`, `<symbol>_exhibit_summary_<run_id>.{yaml,json}`
- Warranty: `<symbol>_warranty_<accession>_<run_id>.json`, `<symbol>_warranty_combined_<run_id>.csv`
- Financials: `<symbol>_financials_<run_id>.{csv,json,yaml}`
- Holdings: `<symbol>_holdings_<run_id>_snapshot.csv`, `_summary.{json,yaml}`, `_diff.{json,yaml}`
- Insider: `<symbol>_insider_<run_id>_ledger.csv`, `_summary.{json,yaml}`, `_alerts.{json,yaml}`
- News/Events/Retrieve/Chat: timeline or summary files with run_id-stamped stems in each symbol directory

Run registry database:
- `.cache/sec-nlp/runs.db`
- Inspect with `sec-nlp runs ls`, `sec-nlp runs info`, `sec-nlp runs stats`

## Development
```bash
make dev
make lint
make test
make build-ext
make stubs
```

## Additional Docs
- [docs/README.md](docs/README.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/pipelines/analyze/README.md](docs/pipelines/analyze/README.md)
- [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md)

## License
MIT
