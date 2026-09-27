# sec-nlp

A terminal research workspace for SEC filings, related headlines, market observations, and investment research. Ordinary shell commands show styled tables and readable text, then return to your prompt. Discover filings across the market, save topic scans, read source evidence, and keep watchlists and notes together. AI and vector research are optional.

Launching the workspace uses cached data. Refresh, search, evidence downloads, and research run only when requested.

## Install locally

Requires Python 3.13+, `uv`, and Rust with `maturin` when building from source.

```shell
uv sync --all-extras --group dev
make build-ext
.venv/bin/sec-nlp --help
```

For a complete base installation into a separate virtual environment, without AI/vector extras:

```shell
uv venv /path/to/environment --python 3.13
make install-local PYTHON_BIN=/path/to/environment/bin/python
/path/to/environment/bin/sec-nlp --help
```

The root maturin wheel contains `sec_nlp`, its prompts, and `market`. The installation target also builds and installs the `efts`, `corr`, `xbrl`, `entity`, and `newswatch` wheels. Native typing files ship with their owning wheel.

Use the installed `sec-nlp` executable directly. An exact `uv sync` or ordinary `uv run` can remove the locally installed sibling wheels and unselected extras; use `uv run --no-sync` after building if you prefer that launcher. The repository Makefile's development sync includes extras and preserves sibling wheels.

## Start a terminal workspace

```shell
.venv/bin/sec-nlp workspace init --workspace ./research \
  --user-agent 'Your Name your-email@example.com' --symbols AAPL MSFT
.venv/bin/sec-nlp workspace open --workspace ./research
```

Bare `sec-nlp` displays command help. `workspace open` prints a cached overview in your terminal; it does not enter a full-screen interface. The default path follows `platformdirs`. Use `--workspace` to keep a project in a chosen directory.

The core workflow stays in ordinary terminal output:

- `workspace inbox` lists cached market-wide filings with unread and bookmark filters.
- `workspace pulse` lists new watchlist/topic evidence; `workspace pulse overview` shows market observations and source outcomes.
- `search` and `scan` discover filings and explicitly download selected evidence.
- `read` lists filing documents or prints readable evidence with its source link.
- `workspace watchlist` and `journal` maintain theses, notes, and review schedules.
- `research` runs deterministic specialists or optional AI/vector actions and reports saved output paths.
- `workspace status`, `workspace jobs`, and `export` expose coverage, operation history, and portable reports.

Use `Ctrl+C` to interrupt active command work. Completed evidence remains available. Source failures and incomplete coverage remain visible; refresh time is not a claim that history is complete. A withdrawn-source state means a later full index no longer lists a previously observed filing; its evidence and notes remain saved.

The existing keyboard-driven full-screen interface remains available explicitly with `sec-nlp workspace ui --workspace ./research`. It uses the same data and services. Ordinary commands do not launch it or open browser windows.

## Scriptable actions

```shell
sec-nlp refresh --workspace ./research
sec-nlp refresh --workspace ./research --source news
sec-nlp refresh --workspace ./research --source market
sec-nlp refresh --workspace ./research --start 2026-01-01 --end 2026-03-31

sec-nlp workspace pulse --workspace ./research
sec-nlp workspace pulse overview --workspace ./research
sec-nlp workspace pulse list --workspace ./research --scope all --all --form 8-K
sec-nlp workspace watchlist list --workspace ./research

sec-nlp search --workspace ./research --query 'supply agreement' --forms 8-K
sec-nlp scan save 'Supplier changes' --workspace ./research \
  --query 'supply agreement' --forms 8-K --max-documents 10
sec-nlp scan run 'Supplier changes' --workspace ./research
sec-nlp read ACCESSION --workspace ./research --list-documents
sec-nlp read ACCESSION --workspace ./research --filename DOCUMENT.html

sec-nlp journal add 'Review customer concentration' --workspace ./research \
  --symbol AAPL --thesis 'Demand remains durable' --review-on 2026-10-15
sec-nlp journal review --workspace ./research
sec-nlp export --workspace ./research --format markdown --destination ./review.md
sec-nlp export --workspace ./research --format json --destination ./review.json
```

Use the default tables and text for interactive work; add `--json` to result listings and actions for machine-readable output. For example, `sec-nlp workspace pulse --workspace ./research --json` returns evidence identities and a continuation cursor. Inspect `workspace status`, `workspace inbox`, and `workspace jobs` offline. Exports preserve source provenance and do not overwrite existing files.

The first SEC refresh imports the latest feed and up to five published daily indexes. Each refresh is bounded to 1,000 feed entries and 20 daily indexes or two quarterly indexes. Subsequent refreshes resume gaps. Explicit history actions require a date range; rerun the same range to continue a capped import. Corrections are reconciled on later manual refreshes. The transport defaults to five SEC requests per second within an application process. See the SEC's [access guidance](https://www.sec.gov/about/developer-resources) and [filing index documentation](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

## Deeper research

```shell
sec-nlp research financials AAPL --periods 4 --workspace ./research
sec-nlp research insider AAPL --workspace ./research
sec-nlp research holdings AAPL --workspace ./research
sec-nlp research warranty AAPL --workspace ./research
sec-nlp research exb AAPL --workspace ./research
sec-nlp research events AAPL --workspace ./research
sec-nlp research retrieve AAPL --queries 'supply agreement' --workspace ./research
sec-nlp research analyze AAPL --preset quick --workspace ./research
sec-nlp research ask --question 'What changed in liquidity risk?' --workspace ./research
sec-nlp research index AAPL --queries 'liquidity risk' --workspace ./research
sec-nlp research recipe --settings jobs/benchmark_matrix_flows/01_rems_large_merged_aligned.yaml \
  --workspace ./research
sec-nlp research report /path/to/saved/summary.json
```

Run `research CAPABILITY --help` for its settings. `--settings FILE.json` supplies a saved specialist configuration; CLI flags override it. Existing specialist serializers remain in use. Exhibit extraction/export works without vector infrastructure.

`research report PATH` reads an existing JSON or YAML report into terminal sections and tables. It uses the saved file without running research or fetching sources. Add `--json` to emit its structured contents.

Install the `ai` extra for model execution and the `vector` extra for embeddings, Qdrant, and semantic chunking. Configure running model/vector services explicitly. Research does not start Docker or model services. The base reader works without either extra. Direct Unstructured parsing remains lazy; see the architecture guide for local parser resource requirements and fallback behavior.

## Migrate existing work

```shell
sec-nlp workspace migrate --workspace ./research --from ./investing
```

Migration preserves original profiles, journals, brief snapshots, filing caches, authored jobs, and specialist output files. It is repeatable and rejects conflicting identities. See [the migration map](docs/MIGRATION.md) for command/import replacements and cache handling.

## Development checks

```shell
make build-ext
.venv/bin/pytest -x
.venv/bin/ty check src tests
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

Tests block network access. Model calls and SEC responses are mocked. CLI tests cover terminal reports and JSON output; headless Textual tests exercise the optional interface's reader navigation, notes, and cancellation. Fresh-process tests enforce import boundaries.

Read [architecture](docs/ARCHITECTURE.md), [Pulse workflow](docs/PULSE.md), [migration](docs/MIGRATION.md), [validation results](docs/VALIDATION.md), and the [documentation index](docs/README.md).
