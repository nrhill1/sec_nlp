## Quick context

- Repo: sec_nlp — a hybrid Python + Rust project for downloading, parsing, and summarizing SEC filings.
- Two main parts:
  - Python package `python/sec_nlp/` implements the CLI, pipeline, LLM wrappers, and tests.
  - Rust crate `crates/edgars/` provides a fast EDGAR HTTP client with optional PyO3 bindings (built with maturin).

## What this agent should know (high value)

- The CLI entry is `python -m sec_nlp.cli` (see `python/sec_nlp/cli/__main__.py`). The pipeline is `python/sec_nlp/pipelines/pipeline.py` and instantiates `FlanT5LocalLLM` by default.
- Local LLM wrapper: `python/sec_nlp/llms/local_llm_base.py` and `local_t5_wrapper.py`. Tests use `DummyLLM` factories in `python/sec_nlp/tests/conftest.py` to avoid loading heavy models.
- Rust helper crate: `crates/edgars` — build/test with `cargo` and use maturin for Python extension (see `pyproject.toml` [tool.maturin] and `crates/edgars/Cargo.toml`).
- CI expectations: `.github/workflows/ci.yml` runs rustfmt/clippy, builds PyO3 extension, and runs Python tests under `python/sec_nlp/tests` using `uv` as the preferred task runner.

## Build / dev commands (exact, copy-paste)

- Create strict Python 3.11.3 venv and install editable package (the project expects exact 3.11.3):
  - uv venv --python 3.11.3
  - source .venv/bin/activate
  - uv pip install -e .
- Run CLI: `uv run cli` or `python -m sec_nlp.cli` (examples in top-level `README.md`).
- Run Python tests: `uv run pytest -q` (pytest config in `pyproject.toml` points to `python/sec_nlp/tests`).
- Build Rust crate: `cargo build --release` from repo root or `cd crates/edgars && cargo build`.
- Build & install PyO3 extension for Python: `maturin develop -m crates/edgars/Cargo.toml -F python --release` (Makefile and CI use `uv` wrappers; ensure maturin available).

## Key code patterns & conventions

- Use the `uv` tool (uv/uvx) as the project task runner for reproducible tooling (see `pyproject.toml` and README). Prefer `uv run <task>` over direct pip/pytest when modifying CI-related behavior.
- LLMs are wrapped behind `LocalLLM` (Pydantic base + Runnable). Implementations should: lazy-initialize heavy model objects, expose `invoke()` and `_generate()` hooks, and support a passthrough behaviour used in tests (see `tests/conftest.py`).
- Pipeline wiring uses Pydantic models for configuration (`Pipeline` in `pipelines/pipeline.py`) and PrivateAttr for runtime-only objects (Pinecone client). Avoid persisting runtime-only attrs in serialized models.
- Tests avoid external network/large models by using environment overrides in `tests/conftest.py` (e.g., `TRANSFORMERS_OFFLINE=1`, empty `PINECONE_API_KEY`). Mirror this in new tests.
- Rust crate exposes a `SecClient` with rate limiting and retry policies. When changing network behavior, update both Rust docs and Python wrappers in `crates/edgars/src/client` and `python/sec_nlp/tests/rust/test_edgars.py` which validate Python -> Rust integration.

## Files to reference when making changes

- top-level README: `README.md` (usage and strict Python version)
- Python package: `python/sec_nlp/` (CLI, pipelines, llms, tests)
- Tests & fixtures: `python/sec_nlp/tests/` and `python/sec_nlp/tests/conftest.py` (shows test isolation strategies)
- Rust crate: `crates/edgars/` (client, corp, filings modules) and `crates/edgars/Cargo.toml` (features: `python`).
- Build metadata: `pyproject.toml` (maturin config and dev deps), `.github/workflows/ci.yml` (CI steps).

## Typical small tasks & examples

- To add a new LLM wrapper: copy `local_t5_wrapper.py`, implement `_generate()` to return a string, keep the class lightweight and lazy-load heavy libs inside methods.
- To add a Python integration test that exercises the Rust extension: add tests under `python/sec_nlp/tests/rust/` and ensure CI `maturin develop` step succeeds locally (use `maturin develop -m crates/edgars/Cargo.toml`).

## What to avoid / gotchas

- Do not change the supported Python version range in `pyproject.toml` without CI adjustments (tests and mypy are strict on 3.11.
- Avoid network-dependent tests without using the conftest monkeypatches — tests rely on environment gating and dummy objects.
- When modifying Python <-> Rust surface, run maturin develop and the Python rust tests locally; CI builds the PyO3 extension early and will fail fast on API mismatches.

If anything here is unclear or you need additional examples (e.g., preferred test fixtures, typical PR size, or coding style rules), tell me which area to expand and I will iterate.
