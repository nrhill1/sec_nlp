# Project Rules

## Project Overview

**sec-nlp** — NLP tools for SEC filings. Python 3.13+ with Rust extensions via PyO3/maturin.

Source layout:

- `src/sec_nlp/` — Python package (cli, core, pipelines, prompts subpackages)
- `crates/` — Rust extensions (market, efts, corr, xbrl, entity, newswatch)
- `tests/` — mirrors `src/sec_nlp/` layout
- `docs/` — architecture docs, pipeline docs, crate READMEs
- `scripts/` — build and profiling utilities

## Planning

Before implementing non-trivial changes:

1. Read relevant source files to understand existing patterns and conventions.
2. Check `docs/ARCHITECTURE.md` for system-level context.
3. Plans should reference concrete file paths and line ranges — no vague descriptions.
4. Identify all downstream callers of any function or type you intend to change.
5. If a change touches pipelines, verify it against all three presets (analyze, exb, warranty) in `src/sec_nlp/pipelines/presets/`.
6. If a change touches Rust crates, note which Python modules import the extension and whether `make build-ext` is needed before tests.

## Python

### Guidelines

[`ty`](https://docs.astral.sh/ty/) is the type checker for this project.
When fixing type errors, writing any new code, or modifying existing code:

1. No `Any` typing — if absolutely necessary, ensure the case for its use is presented to the user.
2. No use of `cast()`.
3. No use of `object` as a type.
4. No use of `object.__setattr__` or `__dict__`.
5. No use of `hasattr`.
6. Use `getattr` only when necessary — prefer accessing using dot notation or `.get()`.
7. Whenever possible, use dot notation instead of square brackets to access attributes.
8. No string/byte type annotations.
9. For Pydantic `model_config`, use `frozen=True` and `extra="forbid"` or `"ignore"` whenever possible.
10. For Pydantic, never use `SkipValidation`.
11. Do not create new `Protocol` types.
12. Do not use reserved Python keywords or function names for any variable, key, or class names.
13. Type annotations, generics, and aliases should follow guidelines for Python v3.13.9.
14. Use the `type` statement for type aliases (e.g. `type JsonDict = dict[str, JsonValue]`).
15. Import from `collections.abc` (not `typing`) for `Sequence`, `Mapping`, `Callable`, etc.
16. Use `from __future__ import annotations` only when needed for forward references.

### File Headers

Every Python source file (including all `__init__.py` files and tests) must start with a repo-relative path comment followed by a module docstring:

```python
# src/sec_nlp/pipelines/utils.py
"""Utility functions for pipelines."""
```

The path comment must use the exact repo-relative path of the file.

### Docstrings

All docstrings use [Google style](https://google.github.io/styleguide/pyguide.html#38-comments-and-docstrings) with triple double-quotes.

#### Module Docstrings

Every module must have a docstring immediately after the path comment.

- **Summary line** (required): One sentence describing the module's purpose. Must end with a period.
- **Extended description** (required for non-trivial modules): What the module provides, its role in the system, and key design decisions. Use paragraph prose, not bullet lists.
- **`__init__.py` files**: One sentence describing what the package exposes or aggregates.

Good example:

```python
# src/sec_nlp/app/flows/runner.py
"""Executor for compiled flow stages and in-memory artifact handoff.

The runner consumes typed compiled stages, dispatches each pipeline, and
records stage-level envelopes. It avoids config re-validation by relying on
compile-time guarantees and only operating on compiled stage types.
"""
```

Bad example:

```python
# src/sec_nlp/pipelines/base/pipeline.py
"""Abstract base classes for all pipelines."""  # Too vague — says nothing about what the base provides
```

#### Class Docstrings

Every class must have a docstring.

- **Summary line** (required): Describes what the class *represents* or *does*, in a full sentence.
- **Extended description** (required for public classes; recommended for private): Responsibilities, design rationale, and relationship to collaborating classes.
- **Attributes section** (required for dataclasses and plain classes with public attributes): List each attribute with type and purpose.
- **Example section** (optional): Include for primary API entry points.

Good example:

```python
class FlowArtifactStore:
    """In-memory artifact registry keyed by flow stage ID.

    Stores typed handoff bundles and seed chunks produced by upstream stages
    so that downstream stages can consume them by reference within a single
    process run. Designed for local execution where serialization overhead
    should be avoided.

    Attributes:
        _seed_by_stage: Maps stage IDs to retrieve-produced seed bundles.
        _seed_chunks_by_stage: Maps stage IDs to immutable chunk tuples.
        _contract_evidence_by_stage: Maps stage IDs to EXB evidence bundles.
    """
```

Bad example:

```python
class AnalyzePipeline(BasePipeline):
    """Generalized pipeline for semantic search and confidence analysis."""  # Missing responsibilities, design context
```

#### Function and Method Docstrings

Every public function and method must have a docstring. Private methods (`_name`) should have at least a summary line.

- **Summary line** (required): Imperative mood ("Return...", "Build...", "Validate..."). Must end with a period.
- **Args section** (required when ≥ 2 non-self parameters or when semantics are not obvious): Each parameter on its own indented line with type and purpose.
- **Returns section** (required when the return type is non-trivial or non-obvious): Describe what is returned and its structure.
- **Raises section** (required when the function raises exceptions as part of its contract): List each exception type and when it occurs.

Special cases:

- **`__init__`**: Describe what is being constructed and the role of key parameters. Never write just `"Initialize the object."`.
- **Pydantic validators**: Describe what constraint is enforced and why.
- **Properties**: One-liner summary is sufficient.
- **Trivial delegating methods** (< 3 lines, obvious behavior): One-liner summary is sufficient.
- **`__repr__` / `__str__`**: One-liner summary is sufficient.

Good example:

```python
def compile_stage(
    *,
    stage: FlowStageSpec,
    defaults: FlowDefaults,
) -> CompiledStage:
    """Compile one flow stage into a prevalidated, typed pipeline config.

    Merges flow-level defaults with stage overrides, resolves the settings
    model from the pipeline registry, and returns a frozen compiled stage
    that the runner can dispatch without further validation.

    Args:
        stage: Raw stage definition from the user-authored flow spec.
        defaults: Shared flow defaults (currently just email).

    Returns:
        A typed compiled stage variant (e.g. ``CompiledRetrieveStage``) with
        pre-validated settings and deterministic run identifiers.

    Raises:
        ValueError: If the stage references an unsupported pipeline name.
    """
```

Bad example:

```python
def _run_analyze_stage(cls, stage, artifacts):
    """Run analyze stage."""  # Just restates the function name
```

#### Test File Docstrings

Test module docstrings should state what module, class, or behavior is under test:

```python
# tests/app/flows/test_artifacts.py
"""Tests for FlowArtifactStore seed/chunk/evidence storage and retrieval."""
```

### Pydantic Models

- Always set `model_config = ConfigDict(frozen=True, extra="forbid")` unless mutability is required.
- Prefer Pydantic `Field()` with explicit descriptions over bare defaults.
- Use `TypedDict` (from `typing`) for structured dicts that do not need validation.
- Centralize shared type aliases in `src/sec_nlp/types.py` or `src/sec_nlp/pipelines/types.py`.

### Console Output

- Use `rich` for all user-facing console output (progress bars, tables, panels).
- Do not use bare `print()` in library or CLI code.
- Loggers (`logging.getLogger(__name__)`) for debug/info messages in library code.

### Error Handling

- Never silently swallow exceptions. At minimum, log with `logger.debug(..., exc_info=True)`.
- Use specific exception types — avoid bare `except Exception`.
- Pipeline-level errors should be handled gracefully and surfaced in output summaries.

## Rust Extensions

The project has six Rust crates in `crates/`, each built as a Python extension via maturin + PyO3:

- `market` — Yahoo Finance market data
- `efts` — EDGAR full-text search
- `corr` — correlation computations
- `xbrl` — XBRL parsing
- `entity` — entity resolution
- `newswatch` — news monitoring

### Build Commands

- `make build-ext` — build and install all six extensions (dev mode)
- `make rs-m-dev`, `make rs-sg-dev`, etc. — build individual crates
- `make rs-m-test`, `make rs-sg-test`, etc. — test individual crates
- `make rs-m-clippy`, `make rs-sg-clippy`, etc. — lint individual crates

### Rust Guidelines

- After modifying Rust code, always run `make build-ext` before running Python tests.
- Each crate has its own `Cargo.toml` and `Makefile`.
- Clippy and rustfmt are enforced via pre-commit hooks for market and efts crates.

## Testing

### Rules

1. No network use during testing. All HTTP/socket calls must be mocked (`pytest-socket` enforces this).
2. Tests should be deterministic and not depend on external services.
3. Test files mirror the source layout: `tests/core/` tests `src/sec_nlp/core/`, etc.
4. Shared fixtures live in `tests/conftest.py`. Subpackage-specific fixtures go in `tests/<subpackage>/conftest.py`.
5. Use factory functions (e.g. `create_mock_documents()`) from conftest for creating test data.
6. Use `tmp_path` or `tempfile.TemporaryDirectory` for any file I/O in tests.
7. Mock LLM calls with `MagicMock` — never call real models in tests.

### Running Tests

```shell
uv run pytest -x               # stop on first failure
uv run pytest -x -q            # quiet output
make test                      # full test suite (builds Rust extensions first)
make py-test                   # Python tests only (no Rust rebuild)
make py-cov-html               # coverage report
```

### Performance Tests

- Benchmarks live in `tests/benchmarks/` and use `pytest-benchmark`.
- Memory tracking uses the `track_memory` fixture from conftest.
- Run benchmarks: `make py-test-benchmarks`.

## Linting, Formatting, and Type Checking

### Commands

```shell
make py-fmt                   # ruff format
make py-lint                  # ruff format + ruff check --fix
make py-types                 # ty check (src + tests)
make pre-commit               # run all pre-commit hooks
make validate                 # full pipeline: build-ext → imports → types → tests
```

### Pre-commit Hooks

Configured in `.pre-commit-config.yaml` with `fail_fast: true`:

- YAML/TOML validation, trailing whitespace, EOF fixer, large file check, merge conflict check
- `make py-lint` on all Python files
- `make py-types` on `src/` and `tests/` Python files
- rustfmt + clippy for market and efts crates

Always run `make pre-commit` or `uv run pre-commit run --all-files` before committing.

## Documentation

- `docs/ARCHITECTURE.md` — system architecture and design decisions
- `src/sec_nlp/pipelines/presets/` — per-pipeline README docs
- `crates/` — per-crate READMEs
- `src/sec_nlp/pipelines/presets/analyze/OUTPUTS_ANALYZE.md`, `src/sec_nlp/pipelines/presets/analyze/OUTPUTS_SEARCH_SUMMARY.md` — analyze output format specs

When modifying pipelines or adding features:

1. Update the relevant pipeline doc in `src/sec_nlp/pipelines/presets/<pipeline>/README.md` if behavior changes.
2. Update `docs/ARCHITECTURE.md` if adding new components or changing data flow.
3. Keep docstrings current — every public function and class should have one.

## Commits

- Use concise, imperative commit messages (e.g. `"Fix confidence calibration double-penalty"`).
- Do not commit unless explicitly asked to.
