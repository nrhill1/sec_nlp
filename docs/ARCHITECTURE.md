# Architecture Overview

`sec-nlp` is a local terminal application for discovering SEC filings, reading
source evidence, tracking related headlines, and running specialist research.
The interactive terminal and explicit CLI commands call the same application
services. Refreshing remote sources and starting research require a user action.

## Application boundaries

- `src/sec_nlp/cli/` parses the selected command without importing every specialist.
- `src/sec_nlp/tui/` renders workspace panes and owns progress and cancellation.
- `src/sec_nlp/app/workspace/` stores filings, saved scans, jobs, source status,
  and journal entries; its services implement refresh, search, read, and export.
- `app/workspace/research.py` imports the selected specialist and executes it in a
  cancellable child process. Specialist result files keep their existing schemas.
- `app/workspace/recipes.py` validates saved recipes and directly invokes supported
  specialists. `app/workspace/evidence/` contains the retained retrieval seeds and
  exhibit evidence contracts. There is no separate compiled graph executor.
- `src/sec_nlp/app/pulse/` provides Pulse's portable profile, observation, and
  report models used by workspace market context and migration of prior investing
  data. The terminal's Pulse pane presents cached headlines and market context.

Workspace persistence and migrations live in `app/workspace/store.py` and
`migrate.py`. Historical evidence is kept separate from newly requested refresh
results so a failed provider cannot silently replace prior observations with
fresh-looking empty data. The default filing feed covers the market; saved scans
and explicit symbol filters narrow it.

## SEC and headline providers

`core/edgar/transport.py` owns the Python HTTPX transport and shared SEC request
budget. Filing discovery, EFTS requests, downloads, and document reads use this
boundary. `core/ingest/downloader.py` adapts the retained specialist download calls
to it. Source metadata and document URLs remain available for review.

`core/news/normalization.py` handles common headline normalization. Provider
statuses distinguish successful, partial, and failed refreshes. Retrieval does
not execute instructions found in news articles or filing text.

Six native capabilities remain: market data, EFTS ranking, XBRL parsing,
correlation, entity extraction, and news retrieval. The `efts` extension no longer
owns SEC HTTP requests. Python callers use its retained ranking functions.

## Deterministic records and optional AI

`core/documents.py` defines `DocumentRecord`: source text, JSON metadata, and an
optional identifier. Attributes are frozen, and each record owns its metadata
dictionary for explicit enrichment. Parsing, lexical ranking, deduplication,
financial extraction, and specialist serializers use this internal model.

`adapters/documents.py` converts records only where optional LangChain/vector
operations are requested. LangChain document and Runnable types are confined to
those integrations. Package `__init__.py` modules remain lightweight; consumers
import a symbol from its defining module.

The base application includes deterministic ingestion and lazy direct
`unstructured` HTML parsing. The pinned parser is invoked only after its existing
local spaCy model loads successfully; absent or broken models use a logged local
text fallback that retains source metadata. Filing extraction never downloads or
installs NLP models. The base does not require LangChain/vector packages. Optional
extras are:

- `ai`: model integration through LangChain Core and Ollama, plus NumPy helpers.
- `vector`: embeddings, Qdrant integration, and semantic chunking.
- `economic`: FRED economic context.

Semantic chunking defaults to disabled. Sentence/section chunking works without
embedding services; users explicitly enable semantic chunking when the `vector`
extra and embedding model are available. EXB extraction and exports likewise run
without vectors; `index_results` explicitly enables indexing. Analyze and chat
require their optional model/vector capabilities.

The library never starts Docker, Colima, Qdrant, or a model daemon. Optional
Qdrant clients can fall back from their configured endpoint to a local store and
then an in-memory store, with the chosen target reported in diagnostic logs.

## Specialist execution

Retained specialists live under `pipelines/presets/`: analyze, exb, warranty,
financials, holdings, insider, news, events, retrieve, and chat. The terminal
selects these behind `research`, `search`, and refresh actions.

`BasePipelineSettings` is a frozen Pydantic configuration. Parsing, displaying,
and serializing settings does not register a run or create output directories.
An explicitly constructed execution service starts registry bookkeeping and
builds its components. `run()` performs the selected operation.

`pipelines/base/stages.py` uses an ordinary ordered loop over typed extraction
steps. `RunContext` supplies identifiers for diagnostic logging, while each
specialist keeps its typed state and existing extraction/export routines. The
application owns interruption and console rendering. This replaces generic
Runnable stage composition without duplicating the specialist implementations.

Typical deterministic execution downloads selected filings, parses facts or text,
computes aggregates/diffs, and exports evidence. Analyze additionally retrieves
relevant chunks and invokes optional model analysis. Saved recipes hand retained
evidence records directly from one selected specialist to the next.

## Outputs and installed paths

Specialist artifacts retain their existing layout:

```text
<out_path>/<run_timestamp>/<pipeline_type>/<SYMBOL>/...
```

Analyze retains per-accession `analysis.{yaml,json,csv}` and symbol-level
`search/summary.yaml`. EXB, warranty, financials, holdings, and insider retain their
existing summary, fact, ledger, and snapshot serializers.

`core/infra/settings.py` obtains application cache/data locations from
`platformdirs`, with `SEC_NLP_CACHE_DIR` and `SEC_NLP_DATA_DIR` overrides. Importing
settings does not create directories. The specialist run registry lives at
`<cache_dir>/runs.db`; user workspace storage is selected separately. Developer
scripts discover the checkout only when needed, so installed runtime code does
not require a repository root.

## Local packaging and verification

The root maturin distribution includes the Python application and `market`.
`make build-wheels` builds it plus the five sibling extension wheels;
`make install-local` installs that complete local base into the selected Python
environment. Native capability stubs ship beside their corresponding modules.
No second Python application distribution or permanent compatibility package is
maintained.

Offline tests mock remote providers. Import-boundary tests run deterministic
specialists with AI/vector modules blocked, and adapter tests preserve filing
provenance. Use `ty check src tests` for the full source/type check. Native edits
require `make build-ext` before Python tests.
