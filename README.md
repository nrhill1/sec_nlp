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
- `sec-nlp flow` - run multi-stage flow specs (for example `retrieve -> chat`)
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
SEC_NLP_OLLAMA_BASE_URL=http://localhost:11434
SEC_NLP_ANALYZE_EMAIL=you@example.com
SEC_NLP_EXB_EMAIL=you@example.com
SEC_NLP_WARRANTY_EMAIL=you@example.com
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

### 4b) Run the local Docker stack

This repo now includes a background-friendly Docker Compose stack with:

- `benchmark-runner`: repo-mounted app container that idles after syncing
  dependencies and building Rust extensions when needed
- `qdrant`: local Qdrant sidecar exposed on `localhost:6335` by default

Start it with one command:

```bash
docker compose up -d --build
```

Or via make:

```bash
make docker-up
```

Then exec into the app container:

```bash
docker compose exec benchmark-runner bash
```

Inside the container, run the usual commands:

```bash
uv run sec-nlp --help
uv run pytest tests/benchmarks -q
```

Notes:

- The app container defaults `SEC_NLP_OLLAMA_BASE_URL` to
  `http://host.docker.internal:11434`, so Ollama can stay on the host.
- The runner image and startup metadata carry the current git commit hash when
  you start the stack with `make docker-up`. The entrypoint also writes
  `logs/container/benchmark-runner/metadata.json` and
  `logs/container/benchmark-runner/bootstrap.log` inside the Docker-backed log
  volume.
- The Compose-managed Qdrant sidecar uses `localhost:6335` and `localhost:6336`
  by default so it does not collide with an existing `sec-nlp qdrant up`
  container on `6333/6334`. Override with
  `SEC_NLP_DOCKER_QDRANT_HTTP_PORT` and `SEC_NLP_DOCKER_QDRANT_GRPC_PORT`
  if you want different host bindings.
- Runtime state (`.venv`, `.cache`, `outputs`, `downloads`, `logs`, `.qdrant`,
  and `target`) is kept in Docker volumes so the background container can run
  without churning host-owned files in the repo checkout, and the bootstrap
  logs stay isolated under `logs/container/benchmark-runner/`.
- Stop the stack with `docker compose down` or `make docker-down`.

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

### 6) Run a single multi-pipeline flow (retrieve -> chat)

Create a flow spec (YAML or JSON), then validate/run it:

```bash
cat > flow_retrieve_chat.yaml <<'YAML'
name: retrieve_chat
defaults:
  email: you@example.com
  symbols: [AAPL]
stages:
  - id: retrieve_seed
    pipeline: retrieve
    overrides:
      queries: ["supply chain risk", "pricing pressure"]
      output_format: json
  - id: chat_answer
    pipeline: chat
    inputs:
    - from_stage: retrieve_seed
      artifact: retrieve_seed
      target_field: seed_context
    overrides:
      question: "Summarize supply-chain and pricing risks with citations."
      interactive: false
      output_format: json
YAML

sec-nlp flow validate --spec flow_retrieve_chat.yaml
sec-nlp flow run --spec flow_retrieve_chat.yaml
```

Prebuilt flow packs:

- `/Users/nicolashill/Projects/sec/jobs/multi_jobs`:
  30 retrieve->chat specs across baskets and size tiers.
- `/Users/nicolashill/Projects/sec/jobs/merged_basket_high_models`:
  higher-parameter specs that merge runs into one shared collection per basket
  (`qwen3-embedding:4b` + `qwen3:8b`).
- `/Users/nicolashill/Projects/sec/jobs/industry_tier_jobs`:
  mixed retrieve/chat/flow presets with standardized industry collections split
  by low/medium/high model tiers.
- `/Users/nicolashill/Projects/sec/jobs/conflict_monopoly_flows`:
  two multi-stage large flows for REMs and quantum, each spanning simple terms,
  geopolitical-conflict retrieval, monopoly/concentration retrieval, and
  complex synthesis queries over filings from March 12, 2023 through the run
  date.

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

- `SEC_NLP_ANALYZE_`
- `SEC_NLP_EXB_`
- `SEC_NLP_WARRANTY_`
- `SEC_NLP_FINANCIALS_`
- `SEC_NLP_HOLDINGS_`
- `SEC_NLP_INSIDER_`
- `SEC_NLP_NEWS_`
- `SEC_NLP_EVENTS_`
- `SEC_NLP_RETRIEVE_`
- `SEC_NLP_CHAT_`

Global runtime environment variables:

- `SEC_NLP_OLLAMA_BASE_URL` (preferred)
- `OLLAMA_BASE_URL` (legacy fallback)

Nested fields:

- Env: `__` delimiters, e.g. `SEC_NLP_ANALYZE_LLM__MODEL_NAME=llama3.2:1b`
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
- [src/sec_nlp/pipelines/presets/README.md](src/sec_nlp/pipelines/presets/README.md)
- [src/sec_nlp/pipelines/presets/analyze/README.md](src/sec_nlp/pipelines/presets/analyze/README.md)
- [crates/README.md](crates/README.md)
- [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md)

## License

MIT
