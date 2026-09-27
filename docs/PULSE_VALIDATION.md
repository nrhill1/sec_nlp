# Pulse daily review validation

Verified September 27, 2026, on the current macOS machine with Python 3.13.9.
Pulse now shares activity, watchlist, acknowledgement, and review services between
the terminal and CLI. These results cover the implemented daily-review release.

## Correctness and installation

| Check | Result |
| --- | --- |
| Full offline Python suite, including optional research paths with mocked providers | 901 passed in 47.33 seconds |
| Changed market native crate | 22 tests, rustfmt, and strict Clippy passed |
| Changed newswatch native crate | 3 tests, rustfmt, and strict Clippy passed |
| `make build-ext` | All six native wheels rebuilt before Python tests |
| Full Ruff, formatting, and `ty check src tests` | Passed |
| Pre-commit hooks | Passed, including native market/EFTS checks |
| Isolated base installation outside the checkout | Passed with 85 compatible distributions and no AI/vector extras |
| Application wheel contents | All 283 application Python files byte-match source; native typing and five prompt resources present |

Migration fixtures verify v1-to-v2 rollback on corrupt history and interruption,
repeat opening without historical replay, existing payload preservation, and
saved-scan provenance. Profile edits recompute relevance offline. Review tests
cover keyset pagination, concurrent headline ingestion, duplicate bridges,
independent acknowledgements and Undo, immutable journal history, rescheduling,
and retained source dates. Market projections retain usable quotes across empty,
failed, news-only, demo, and older observations.

Refresh fixtures exercise four shared source slots, transient retries, source
deadlines, incremental persistence, and cancellation. A native bridge regression
proves that cancellation drops the Rust future and that cleanup acknowledgement
finishes before returning. New requests wait while a shared market session drains;
the 20-second request deadline includes retries, and required cleanup is awaited
before the job is marked cancelled. SEC registry failure status survives restart.

Headless terminal tests exercise activity filters, pagination, selection,
acknowledgement, rapid edits, preserved drafts, watchlists, due reviews, and
evidence-to-journal/research navigation. Cached startup blocks network access,
creates no jobs, and imports no AI, vector, parser, or native provider runtime.
The installed base also executes deterministic EXB evidence conversion, warranty
fact extraction, Pulse acknowledgement/Undo, and Markdown/JSON export.

## Local performance

The query fixture contains **50,000 filings, 10,000 headlines, and 1,000 briefs**.
Measurements are medians of five runs. The inbox requests 500 rows and activity
requests 50 rows. Startup uses fresh isolated processes outside the checkout.

| Operation | Median | Target |
| --- | ---: | ---: |
| Inbox query | 6.11 ms | <50 ms |
| Focused Pulse page | 1.33 ms | <100 ms |
| All-activity Pulse page | 1.20 ms | <100 ms |
| Missing-symbol Pulse filter | 6.72 ms | <100 ms |
| Deduplicate 10,000 overlapping headlines | 156.18 ms | <250 ms |
| Top-level help, whole process | 97.36 ms | <500 ms |
| Version, whole process | 83.69 ms | <500 ms |
| Cached terminal first paint | 537.20 ms | <1,000 ms |

The indexed inbox replaces an approximately 1.58-second query from planning.
Pulse reads compact projections rather than decoding historical reports.
CI checks query indexes, bounded decoding, deterministic behavior, and import
boundaries; timing thresholds remain local measurements. A concurrent full test
run increased one first-paint sample to 1.58 seconds; idle measurements are used
for the ordinary-startup target.
The final wheel's five idle first-paint samples were 535.58, 531.73, 550.34,
537.20, and 538.05 ms. First paint includes application imports and waits for the
500-row inbox worker to populate the table in Textual's headless test context.

Reproduce the large-cache query measurements offline with:

```bash
PYTHONPATH=src .venv/bin/python -m scripts.profile.pulse
```

## Size accounting

Counts are physical Python lines, including required comments and docstrings.
The baseline is the original consolidation assessment; the preceding checkpoint
is recorded in [consolidation validation](VALIDATION.md).

| Category | Planning baseline | Before daily review | Current |
| --- | ---: | ---: | ---: |
| Maintained application Python | 64,489 | 58,758 | 62,251 |
| Generated application stubs | 5,884 | 0 | 0 |
| Test Python | 26,922 | 26,059 | 28,137 |
| Developer scripts | 4,018 | 4,007 | 4,159 |
| Direct base Python dependencies | 26 | 14 | 14 |

Daily-review functionality adds 3,493 application lines and 2,078 test lines.
The application remains 2,238 lines below the planning baseline. Current runtime
subsets include 5,626 lines in workspace services/storage, 1,672 in the terminal,
and 2,000 in portable Pulse models/services/rendering; these are included in the
runtime total. Native stubs remain packaged. No new direct Python dependency was
added; the market crate now uses the native asynchronous PyO3 bridge.

Live providers and real model execution are outside these offline checks.
