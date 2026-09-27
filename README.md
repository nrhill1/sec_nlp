# sec-nlp

A terminal research workspace for SEC filings, related headlines, market observations, and investment research. Discover filings across the market, save topic scans, read source evidence, and keep watchlists and notes together. AI and vector research are optional.

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

## Open your workspace

```shell
.venv/bin/sec-nlp workspace init --workspace ./research \
  --user-agent 'Your Name your-email@example.com' --symbols AAPL MSFT
.venv/bin/sec-nlp workspace open --workspace ./research
```

Bare `sec-nlp` opens the platform-default workspace when attached to a terminal; it displays help with non-interactive input. The default path follows `platformdirs`. Use `--workspace` to keep a project in a chosen directory.

The terminal provides:

- **Inbox:** cached market-wide filings, unread and bookmark filters, source coverage, Refresh, and Continue SEC. `Ctrl+R` refreshes SEC; Enter reads a selected filing.
- **Search & scans:** retrospective SEC keyword/form/date searches and saved scans with explicit evidence downloads.
- **Reader:** document selection, section navigation, local text search, original source links, matched headlines, and attached notes.
- **Pulse:** cached headlines and market observations with publisher, publication time, source links, and match reasons; explicit news and market refreshes.
- **Research:** deterministic specialists and optional AI/vector actions with saved outputs.
- **Journal and settings:** observations, theses, review dates, watchlist membership, contact identity, and profile settings.

Escape cancels active work. Completed evidence remains available. Source failures and incomplete coverage remain visible; refresh time is not a claim that history is complete. A `!` marker means a later full index no longer lists a previously observed filing; its evidence and notes remain saved.

## Scriptable actions

```shell
sec-nlp refresh --workspace ./research
sec-nlp refresh --workspace ./research --source news
sec-nlp refresh --workspace ./research --source market
sec-nlp refresh --workspace ./research --start 2026-01-01 --end 2026-03-31

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

Add `--json` to discovery/reading commands for machine-readable results. Inspect `workspace status`, `workspace inbox`, and `workspace jobs` offline. Exports preserve source provenance and do not overwrite existing files.

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
```

Run `research CAPABILITY --help` for its settings. `--settings FILE.json` supplies a saved specialist configuration; CLI flags override it. Existing specialist serializers remain in use. Exhibit extraction/export works without vector infrastructure.

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

Tests block network access. Model calls and SEC responses are mocked. Headless Textual tests exercise cached startup, reader navigation, notes, and cancellation; fresh-process tests enforce import boundaries.

Read [architecture](docs/ARCHITECTURE.md), [Pulse workflow](docs/PULSE.md), [migration](docs/MIGRATION.md), [validation results](docs/VALIDATION.md), and the [documentation index](docs/README.md).
