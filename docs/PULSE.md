# Pulse: markets and current events

Pulse brings market observations, related headlines, and research notes into
the terminal workspace alongside new SEC filings and saved searches. Its daily
workflow is to refresh evidence, inspect a filing, follow relevant news, and
record a hypothesis with evidence that could challenge it. The application does
not place trades.

## Install and open

From the repository, create a Python 3.13+ environment and install the complete
local base application with its native providers:

```bash
uv venv --python 3.13
make install-local
.venv/bin/sec-nlp workspace init --user-agent "Your Name you@example.com"
.venv/bin/sec-nlp
```

`install-local` builds the main application wheel with the market extension,
then the EFTS, correlation, XBRL, entity, and newswatch sibling wheels. It removes
the older standalone market distribution before installing the bundled version.
The base application does not require LangChain, Ollama, or Qdrant. Optional
`ai`, `vector`, and `economic` extras enable those related research features.

Without a command, an interactive terminal opens the workspace. Help and version
remain fast and do not initialize providers. The workspace starts from saved
local data; source refreshes happen only when explicitly requested.

The default location is the platform's user-data directory under
`sec-nlp/workspace`. Use `--workspace /path/to/desk` on any workspace command to
select a separate research context. Configuration edits never schedule jobs.

## Set observation goals

```bash
sec-nlp workspace configure --name "My research desk" \
  --goal "Track changes in demand and revisit my investment theses" \
  --symbols AAPL MSFT
sec-nlp workspace status
```

Example symbols demonstrate syntax; replace them with your research targets.
The starter has an empty company watchlist, a SPY reference benchmark, Federal
Reserve and BLS feeds, and questions about rates, inflation, employment, and
company developments. A reference symbol is not a suggested holding. A blank
watchlist supports macro observation; set `benchmarks` to an empty JSON array
for a news-only profile.

Edit `config.json` inside the printed workspace path for detailed settings.
Unknown fields and duplicate symbols, feed names, or themes are rejected.

| Setting | Purpose |
| --- | --- |
| `name`, `goal` | Workspace title and observation objective. |
| `watchlist` | Symbols, company names, headline aliases, theses, invalidation criteria, and review dates. |
| `benchmarks` | Reference market symbols. |
| `themes` | Keyword groups and research questions. |
| `feeds` | Named RSS, Atom, or unauthenticated JSON feeds with optional explicit symbol scope. |
| `company_feeds` | Add Yahoo Finance company feeds for watched symbols. |
| `lookback_days`, `max_headlines` | Bound the current brief's news window and size. |
| `market_days`, `stale_after_days` | Quote-history window and visible staleness threshold. |
| `move_threshold_pct` | One-session move that prompts further research. |
| `user_agent` | Contact identity used for SEC requests. |

## Refresh and inspect

```bash
sec-nlp refresh --source all
sec-nlp workspace inbox --unread
sec-nlp search --query "demand outlook" --symbols AAPL --forms 10-K 10-Q
sec-nlp read ACCESSION --list-documents
sec-nlp read ACCESSION --filename DOCUMENT.htm
sec-nlp read ACCESSION --bookmark
```

Replace `ACCESSION` and `DOCUMENT.htm` with values from the inbox and filing
manifest. Listing documents does not mark a filing read. Opening full document
text explicitly marks it read, and complete text plus available original HTML
is cached for later offline access. Discovery never downloads every filing body.

The inbox merges records by accession and retains every observed entity role,
including reporting owners and issuers. Refreshes preserve read and bookmark
choices. Source coverage distinguishes successful, partial, and failed attempts;
an unavailable index is not treated as an empty day. Successfully parsed index
contents and their checkpoint enter the ledger in the same transaction.

Periodic full-index reconciliation can identify an accession no longer present
in a previously observed index. `source_withdrawn` is a provenance warning about
that index membership. The filing, cached documents, notes, and user choices
remain available; the flag does not assert that the SEC deleted the submission.

For a bounded historical refresh, supply explicit dates:

```bash
sec-nlp refresh --source sec --start 2026-01-01 --end 2026-03-31
```

Large requests can require additional explicit refreshes. Inspect coverage and
job history with `workspace status` and `workspace jobs`.

## Save a search and record research

```bash
sec-nlp scan save "Demand changes" --query "demand outlook" \
  --forms 10-K 10-Q --limit 50 --max-documents 10
sec-nlp scan list
sec-nlp scan run "Demand changes"
sec-nlp journal add "Verify the changed demand outlook in the filing" \
  --symbol AAPL --accession ACCESSION \
  --thesis "Write my interpretation here" \
  --invalidation "Write evidence that would contradict it" \
  --review-on 2026-10-15 --sources https://www.sec.gov/edgar/search/
sec-nlp journal review
```

Use your own dates and exact evidence URLs. Saving a scan does not run it or
create a schedule. Notes are immutable records; add a new note for a revision.
An optional accession link survives ticker changes and keeps the note beside
its source filing. The terminal's research actions use the same application
service as `sec-nlp research`; specialist settings remain available there.

## Interpret observations

Market changes compare adjusted closes across one or five observed sessions;
five-session returns require six quotes. The displayed provider close is
unadjusted and denominated in the asset's unspecified listing currency. A
current-session daily bar may still be provisional. Observation dates, missing
history, source failures, and stale quotes remain explicit.

Headline labels are phrase matches or explicit feed scope, not evidence of
causation. Missing publication dates remain unknown. Future-dated and
out-of-window headlines are excluded from a current brief. RSS lookback filters
the feed's retained history; it does not retrieve a complete historical archive.
Repeated dated releases remain separate. The workspace news ledger records
first-seen identity, so an earlier headline does not become new merely because
a feed failed or a previous brief omitted it.

## Export and migrate

```bash
sec-nlp export --format markdown --destination report.md
sec-nlp export --format json --destination snapshot.json
sec-nlp workspace migrate --from investing
```

Exports use saved evidence without fetching sources. Markdown and JSON are the
supported report formats; standalone HTML reports have been retired in favor of
the terminal workspace. Each brief retains its original profile, observations,
source statuses, and journal snapshot.

Migration validates the old `config.json`, individual journal files, and report
manifests before importing. It initializes only an untouched starter profile,
adds notes and briefs by stable identity, and copies authored jobs into immutable
recipes. SEC full-submission caches with complete headers become selectable
documents for offline reading. Entity CIKs must be declared in the header; they
are never inferred from an accession prefix or ticker folder. Ambiguous cache
files remain external pointers with visible migration warnings. It preserves
every original file. Repeating migration adds only new
records; conflicting identities and corrupt records produce explicit errors.
Legacy HTML files remain untouched but are no longer regenerated.

```text
workspace/
  config.json
  ledger.sqlite3
  documents/<url-hash>.json
  scans/<scan-id>/<job-id>.json
  research/<job-id>/
  recipes/<source-hash>/<recipe-hash>.json
```

The SQLite ledger stores filings, entity roles, review state, source coverage,
news, notes, brief snapshots, and operation history. Document snapshots and
specialist artifacts remain ordinary files alongside it.

## Development

`src/sec_nlp/app/workspace/` owns durable storage and shared actions;
`src/sec_nlp/tui/` and `src/sec_nlp/cli/workspace.py` present those actions.
`src/sec_nlp/app/pulse/` supplies typed profiles, deterministic market/news
briefs, and Markdown rendering. Native stubs ship with their corresponding
wheels. Prompt YAML files and the application typing marker ship in the main
wheel.

```bash
make build-ext
uv run --all-extras pytest -q tests/app/workspace tests/app/pulse
uv run --all-extras ty check src tests
```

Tests use local fixtures and mocked providers; they do not contact external
services. Rebuild all native extensions before Python tests after Rust changes.
