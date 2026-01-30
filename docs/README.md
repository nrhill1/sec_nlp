# sec-nlp

[![codecov](https://codecov.io/gh/nrhill1/sec_nlp/graph/badge.svg)](https://codecov.io/gh/nrhill1/sec_nlp) \
NLP tools for SEC filings. Analyze filings with local LLMs, run semantic search, and extract targeted signals (exhibits, warranty accruals) using a fast CLI.

## Highlights
- Local-first LLM analysis with Ollama (no hosted APIs)
- Topic/keyword filtering, chunking, and relevance scoring
- Optional semantic search and vector indexing with Qdrant (in-memory by default)
- Purpose-built pipelines: `analyze`, `exb`, `warranty`
- Structured outputs (YAML/JSON/CSV), run registry, and logs

## Requirements
- Python 3.13+
- Ollama running locally for LLM and embedding models (analyze, exb)
- Qdrant optional for persistent vector storage (in-memory by default)
- Docker (optional) for `sec-nlp qdrant up`

## Pipelines
| Pipeline | What it does | Notes |
| --- | --- | --- |
| `analyze` | Generalized topic analysis + LLM summaries and scores | Requires Ollama (LLM + embeddings). Vector DB optional; disable with `--vector-mode off`. |
| `exb` | Find and index exhibit documents by category | Uses embeddings + vector store; no LLM. |
| `warranty` | Extract warranty accrual/payout data from XBRL | Deterministic, no LLM. |

Docs:
- Analyze pipeline walkthrough: [docs/pipelines/analyze/README.md](docs/pipelines/analyze/README.md)

## Quickstart
### 1) Install
Using uv (recommended):
```
uv sync
uv run sec-nlp --help
```

Using pip:
```
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2) Set your SEC contact email
SEC EDGAR requests require a valid email address.
```
# .env
ANALYZE_EMAIL=you@example.com
EXB_EMAIL=you@example.com
WARRANTY_EMAIL=you@example.com
```

### 3) Start Ollama and pull models
Defaults:
- LLM: `llama3.2:1b`
- Analyze embeddings: `bge-m3`
- Exhibit embeddings: `mxbai-embed-large`

Example:
```
ollama serve
ollama pull llama3.2:1b
ollama pull bge-m3
ollama pull mxbai-embed-large
```

### 4) Run a pipeline
```
sec-nlp analyze AAPL --preset quick
sec-nlp analyze AAPL --topics warranty recall
sec-nlp analyze AAPL --section-type item --section-numbers 1A
sec-nlp exb DE --exhibit-categories subsidiaries consents
sec-nlp exb DE --search-terms exclusive aftermarket
sec-nlp warranty AAPL
```

Interactive analyze setup:
```
sec-nlp analyze
```

## Analyze presets
Use `--preset <name>` with `sec-nlp analyze`.
- `quick`: Fast analysis: small model, 1 filing, no vector DB
- `laptop`: Laptop-friendly analysis: small model, tighter caps, targeted search queries
- `thorough`: Balanced analysis: better model, 3 filings, vector DB enabled
- `comprehensive`: Full analysis: best model, 5 filings, all features enabled
- `rare_earths`: Focus on rare earth miners (8-K current reports) with finance-tuned LLM and search queries

## CLI overview
- `sec-nlp analyze` - Generalized LLM analysis (topics, keywords, section filters, vector search)
- `sec-nlp exb` - Exhibit indexing and search
- `sec-nlp warranty` - Warranty XBRL extraction
- `sec-nlp market` - Query the Rust-backed market extension for latest or historical quotes
- `sec-nlp qdrant` - Manage Qdrant collections and Docker container
- `sec-nlp runs` - List and inspect pipeline runs
- `sec-nlp clean` - Clear downloads, outputs, or logs
- `sec-nlp version` - Show version

Run `sec-nlp <command> --help` for full options.

## TUI dashboard
Run the Textual dashboard (UI layer shells out to the CLI and stays isolated from pipeline logic):
```
sec-nlp-tui
```

Using uv:
```
uv run sec-nlp-tui
```

## Configuration
Configuration is loaded in this order:
1) CLI arguments
2) Environment variables
3) `.env` file

Pipeline env prefixes:
- `ANALYZE_`
- `EXB_`
- `WARRANTY_`

Nested fields use double underscores. Examples:
```
ANALYZE_LLM__MODEL_NAME=llama3.2:1b
ANALYZE_LLM__BASE_URL=http://localhost:11434
ANALYZE_VDB__QDRANT_LOCATION=:memory:
EXB_VDB__QDRANT_URL=http://localhost:6333
```
Nested CLI fields use dot notation, e.g. `--llm.model-name` or `--vdb.embedding-model`.

Tips:
- Override the Ollama endpoint with `OLLAMA_BASE_URL` or `--llm.base-url`.
- Disable vector DB for analyze with `--vector-mode off`.
- Lists in `.env` should be JSON, e.g. `ANALYZE_TOPICS=["warranty","recall"]`.

## Outputs and data layout
Default directories (override with `--dl-path` and `--out-path`):

```
downloads/      # raw SEC downloads (sec-edgar-filings)
outputs/
  <SYMBOL>/
    analyze/<run_id>/<accession>/analysis.{yaml,json,csv}
    exhibit/<run_id>/<symbol>_exhibit_index_<run_id>.{yaml,json,csv}
    exhibit/<run_id>/<symbol>_exhibit_summary_<run_id>.{yaml,json}
    warranty/<run_id>/<symbol>_warranty_<accession>_<run_id>.json
    warranty/<run_id>/<symbol>_warranty_combined_<run_id>.csv
logs/
```

Run registry:
- Stored in `~/.cache/sec-nlp/runs.db`
- Manage with `sec-nlp runs ls` and `sec-nlp runs stats`

## Qdrant
By default, vector storage uses an in-memory Qdrant instance. For a persistent store:

```
sec-nlp qdrant up
```
This uses Docker and stores data in `./qdrant_storage`.

Then point pipelines to it:
```
ANALYZE_VDB__QDRANT_URL=http://localhost:6333
EXB_VDB__QDRANT_URL=http://localhost:6333
```

## Development
Common make targets:
```
make dev
make test
make lint
```

### Rust extensions
`make build-ext` builds the Rust extensions (market + EFTS) for local development. EFTS uses the Rust extension by default now, so ensure the extension is built before running Python tests or CLI commands that hit EFTS.

### Type stubs
`make stubs` regenerates Python stub files for the package and places them under `types/`. Three manual stubs are maintained for the new market integration—`types/market/__init__.pyi`, `types/sec_nlp/core/market.pyi`, and `types/sec_nlp/cli/commands/market.pyi`—so remember to preserve those files if you run stubgen (they document the Rust extension and CLI command explicitly).

## License
MIT
