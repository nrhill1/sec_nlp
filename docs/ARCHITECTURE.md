# Architecture Overview

`sec-nlp` is a Python-first orchestration system with Rust extensions for performance-critical integration points (EFTS and market data). It supports both LLM-driven and deterministic SEC/market workflows behind one CLI.

## Code Layout

- `src/sec_nlp/cli/` - command models, argument normalization, and command dispatch.
- `src/sec_nlp/app/flows/` - typed multi-stage flow specs, in-memory artifacts, and runnable adapters.
- `src/sec_nlp/app/investing/` - portable investing profiles, sourced daily briefs, offline reports, and research journals.
- `src/sec_nlp/pipelines/base/` - shared pipeline lifecycle, config, validation, and result models.
- `src/sec_nlp/pipelines/presets/` - production pipeline implementations (`analyze`, `exb`, `warranty`, `financials`, `holdings`, `insider`, `news`, `events`, `retrieve`, `chat`).
- `src/sec_nlp/pipelines/tools/` - reusable LangChain `StructuredTool` wrappers (`market_context_tool`, `retrieve_hits_tool`, `qdrant_search_tool`, `news_context_tool`).
- `src/sec_nlp/core/` - EDGAR ingestion, text processing, stats, market/news helpers, and infra services.
- `src/sec_nlp/pipelines/observability/` - run registry + metrics/profiling.
- `crates/` - Rust crates (`efts`, `market`, `xbrl`, `corr`, `entity`, `newswatch`).

## Runtime Layers

1. CLI layer: parses/normalizes args and instantiates command config.
2. Flow orchestration layer (optional): executes multi-stage specs and passes typed in-memory artifacts between stages.
3. Pipeline config layer: immutable Pydantic settings merged from CLI/env/.env.
   Every preset now exposes a shared `semantic_chunking` nested config.
4. Pipeline execution layer: per-symbol phase execution with run metadata.
5. IO/export layer: run-scoped artifacts written in CSV/JSON/YAML.
6. Observability layer: run registry (SQLite) + optional metrics/tracing.

## Pipeline Families

The `invest` command is a separate application workflow, outside the pipeline
lifecycle. It uses an independent frozen profile so a daily brief does not need
SEC contact settings, filing downloads, embeddings, or model configuration.
Existing filing pipelines remain the deeper research entry points.

- LLM-centric: `analyze`, `chat`
- Retrieval/indexing: `retrieve`, `exb`
- Deterministic SEC extraction: `warranty`, `financials`, `holdings`, `insider`
- Timeline/correlation: `news`, `events`

`retrieve` is EFTS-first and uses lexical ranking/pruning (stopword-aware by default) with selective chunk hydration before optional embedding rerank/index.

## Investing Workspace

`invest init/brief/note/review` provides a daily observation path alongside the
SEC pipelines. The CLI reads a frozen `InvestingSettings` profile, and the
application service calls `core.market` once per symbol and `core.news` once
per feed. Retrieval failures are recorded independently. Dates, phrase matches,
deduplication, adjusted-session returns, and research prompts are computed in
Python without an LLM, filing downloads, or vector infrastructure.

Each report stores the exact profile, dated observations, source statuses, and
journal entries in `brief.json`, plus Markdown and a self-contained HTML view.
These files live under the chosen investing workspace rather than the pipeline
output root or SQLite run registry. Notes are immutable individual JSON files;
configuration remains explicitly editable. Files are published atomically
without overwriting existing records, and report JSON is published last.

Offline snapshot rendering writes separate exports and does not enter live
history. Synthetic demos are flagged throughout their artifacts. Only an earlier
live report with an identical profile is eligible for headline comparisons.
No news article or document content is interpreted as executable instructions.

Reference: [Investing workflow](INVESTING.md)

## Retrieve->Chat Flow Runtime

The `flow` CLI command supports deterministic single-run multi-stage execution.

Current phase supports `retrieve -> chat` with typed handoff:

- Retrieve stage emits `RetrieveChatSeedBundle` in memory.
- Chat stage can accept `seed_context` and skip Qdrant collection search.
- Artifact handoff avoids JSON round-trip serialization loops.

References:

- `src/sec_nlp/app/flows/models.py`
- `src/sec_nlp/app/flows/artifacts.py`
- `src/sec_nlp/app/flows/runner.py`
- `src/sec_nlp/app/flows/compiled.py`
- `src/sec_nlp/app/flows/contracts/`

## Analyze Flow

1. Load filings (optionally with EFTS expansion).
2. Chunk/filter/dedupe content (semantic mode uses LangChain Experimental `SemanticChunker` plus local sentence/token caps).
3. Optional vector indexing/search retrieval.
4. LLM analysis for retrieved chunks.
5. Aggregate, enrich (market correlation optional), and export.

Reference: `src/sec_nlp/pipelines/presets/analyze/README.md`

## Deterministic Pipeline Pattern

Most non-LLM presets follow:

1. Download filings or external source records.
2. Parse/normalize structured entities.
3. Compute diffs, clusters, correlations, or timeline rollups.
4. Export symbol-scoped run artifacts.

## Output Conventions

All pipelines use run-scoped output roots:

```text
outputs/<run_timestamp>/<pipeline_type>/<SYMBOL>/...
```

File names usually include `<run_id>` and pipeline-specific suffixes (for example: `_summary`, `_timeline`, `_ledger`, `_snapshot`, `_ranked`).

Analyze keeps per-accession directories:

```text
outputs/<run_timestamp>/analyze/<SYMBOL>/<accession>/analysis.{yaml,json,csv}
outputs/<run_timestamp>/analyze/<SYMBOL>/search/summary.yaml
```

## Run Registry

- SQLite registry path: `.cache/sec-nlp/runs.db`
- Tracks run id, short id, pipeline type, status, timestamps, and metadata
- Managed via `sec-nlp runs ...`

## Design Priorities

- Repeatable run-scoped outputs with provenance fields.
- Clear separation between config, execution, and serialization.
- Fast-path native integrations through Rust extensions.
- Optional infrastructure dependencies (Qdrant, Docker) instead of mandatory services.
- Vector connectivity fallback for pipelines: configured endpoint → best-effort `colima start` + `sec-nlp qdrant up` for localhost Docker → local `.qdrant` path → embedded `:memory:` when Docker/Qdrant remains unavailable.

## Tool Wrappers (LangChain)

The wrappers-first tool package exposes deterministic helpers without enabling autonomous tool-calling in `chat`.

- `market_context_tool`: derive market metrics bundle for symbols.
- `retrieve_hits_tool`: run deterministic EFTS candidate search + ranking.
- `qdrant_search_tool`: direct semantic query against a Qdrant collection.
- `news_context_tool`: recent deduped headline retrieval.

Example LCEL composition:

```python
from langchain_core.runnables import RunnableParallel, RunnableLambda
from sec_nlp.pipelines.tools import (
    market_context_tool,
    qdrant_search_tool,
)

chain = RunnableParallel(
    market=RunnableLambda(
        lambda x: market_context_tool.invoke(
            {
                "symbols": x["symbols"],
                "start_date": x["start_date"],
                "end_date": x["end_date"],
                "benchmark": "SPY",
                "profile": "compact",
            }
        )
    ),
    filings=RunnableLambda(
        lambda x: qdrant_search_tool.invoke(
            {
                "collection": x["collection"],
                "query": x["query"],
                "top_k": 20,
                "symbols": x["symbols"],
                "forms": ["10-K", "10-Q", "8-K", "6-K"],
            }
        )
    ),
)
```
