# Workspace consolidation validation

Verified on September 26, 2026, on the current macOS machine with Python 3.13.
The application now shares discovery, reading, research, and persistence services
between its terminal interface and scriptable commands.

## Checks completed

| Check | Result |
| --- | --- |
| Offline Python suite, including headless terminal interaction | 833 passed in 38.14 seconds |
| `ty check src tests` | Passed |
| `ruff check src tests` | Passed |
| `ruff format --check src tests` | 410 files already formatted |
| `git diff --check` | Passed |
| Changed EFTS native crate | 13 tests; rustfmt and strict Clippy passed |
| Changed newswatch native crate | 3 retained tests; rustfmt and strict Clippy passed |
| `make build-ext` | All six extensions rebuilt before the Python suite |
| Installed base wheels outside the checkout | Passed, with no AI/vector extras |

The native build used the already synchronized development environment and skipped
the Makefile's bootstrap and sync stamps. No commits or publication were performed
as part of this implementation.

Tests cover duplicate entity associations, exact amendment forms, moving feed
pages, missing indexes, retry limits, cancellation and resumed coverage, quarterly
reconciliation, and newer filings after a local cache quota. Reading tests cover
declared document type and sequence, offline content, reading state, and source
provenance. Headline tests preserve recurring titles on different dates and handle
missing dates and failed sources.

Migration tests preserve journals, brief snapshots, authored jobs, readable filing
caches, and unsupported binary document manifests. All 80 authored job definitions
retain their expanded settings, checked against fixture hashes, while repeated
benchmark settings live in compact templates. Specialist tests cover retained
serializers and analyze, EXB, warranty, deterministic research, and evidence handoff.
Optional AI/vector paths are exercised with mocked external services.

## Startup measurements

Five fresh isolated Python processes were measured for each operation, using the
installed wheels from outside the checkout. The cached workspace held 300 filings.
Socket connections and DNS were blocked. Startup created zero jobs and loaded no
AI, vector, parser, or native provider modules.

| Operation | Median operation time | Median whole process time |
| --- | ---: | ---: |
| Import `sec_nlp` | 27 ms | 67 ms |
| Top-level help | 56 ms | 103 ms |
| Version | 48 ms | 92 ms |
| Cached terminal first paint | 468 ms | 599 ms |

First paint measures from before application imports through entry into Textual's
headless `run_test` context with the cached table populated. Whole process time
also includes interpreter setup and shutdown. This is a headless measurement,
not a claim about every terminal emulator or disk. Timing targets pass on this
machine; deterministic import and offline-startup checks enforce the boundaries
without timing thresholds in CI.

Package import loads one `sec_nlp` module; its process contains 155 modules total,
including the standard library and measurement harness. The planning assessment
reported approximately 2.6 seconds and 2,439 modules for package import, and 3.3
seconds for top-level help. Those earlier measurements used the development
environment rather than this isolated base installation.

## Size and dependency accounting

Counts are physical Python lines, including comments and docstrings. Runtime,
generated typing files, scripts, and tests are reported separately.

| Category | Baseline | Current | Change |
| --- | ---: | ---: | ---: |
| Application runtime, including pre-existing investing work | 64,489 | 58,673 | -5,816 |
| Generated application stubs | 5,884 | 0 | -5,884 |
| Developer scripts | 4,018 | 4,007 | -11 |
| Test source | 26,922 | 25,667 | -1,255 |
| Direct base dependencies | 26 | 14 | -12 |

The runtime baseline is the planning snapshot, which includes the existing
uncommitted investing work. For a reproducible Git-only comparison, commit
`8afab23` contains 61,867 runtime lines; the current runtime is 3,194 lines smaller
than that commit. Script, test, and generated-stub baselines use that commit.
Native extension stubs remain packaged and are excluded from the removed-stub
count. Enabling every optional extra yields 21 unique direct dependencies.

New functionality included within the current runtime total comprises 3,783 lines
in the shared workspace package, 753 lines in the terminal package, and 1,108 lines
in the shared SEC transport, filing/discovery models, and headline normalization
modules. These are subsets of the runtime total, not additional lines to add to it.
Authored job YAML shrank from 6,600 to 5,188 lines while preserving all 80 jobs.

## Installation and practical limits

The final root wheel and five sibling native wheels were installed into a separate
virtual environment under `/private/tmp`, with the working directory outside the
repository and isolated Python imports. The root wheel's Python sources matched
the checkout byte for byte. Dependency consistency passed for all 86 installed
base distributions. No LangChain, Qdrant, or Ollama distributions were installed,
and there was no competing standalone `market` distribution.

All six native modules import successfully with their typing files. All five
prompt YAML resources are present. Deterministic EXB classification and warranty
XBRL extraction execute, and EXB, warranty, and retrieval pipelines import without
AI/vector packages.

Live SEC/news responses and real model execution were not used as acceptance
tests. Remote availability and configured model quality are outside these offline
checks. SEC jobs share a five-request-per-second gate within an application
process; separate application processes do not share a global rate limiter.

Direct Unstructured parsing remains lazy. It requires an already available local
spaCy model; absent or broken models use the logged local text fallback rather
than installing anything. Unsupported binary documents retain their source links
and manifests. Ambiguous legacy cache entries are preserved with migration
warnings rather than assigning an issuer from an accession prefix.

See [the command and import migration map](MIGRATION.md) and
[architecture](ARCHITECTURE.md) for the resulting interfaces and service boundaries.
