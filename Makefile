SHELL := /bin/bash
.DEFAULT_GOAL := test

# -------------------------
# Python: paths & commands
# -------------------------
LOG_DIR := src/sec_nlp/tests/test_logs
PYTEST := uv run pytest
COVERAGE := uv run coverage
PYTEST_FLAGS := -v --maxfail=1 --tb=short --color=yes --basetemp .pytest_tmp --cache-clear

# -------------------------
# Rust: workspace settings
# -------------------------
CARGO ?= cargo
RUST_CRATE := edga_rs
RUST_PKG_FLAG := -p $(RUST_CRATE)

# -------------------------
# Lint/Clippy config
# -------------------------
CLIPPY_FLAGS ?= -D warnings

# -------------------------
# Maturin (PyO3) build config
# -------------------------
MATURIN := uvx maturin
MATURIN_FLAGS ?= --release
# Path to the Rust crate manifest for the Python extension
MATURIN_MANIFEST := $(RUST_CRATE)/Cargo.toml
WHEELS_DIR := target/wheels

# -------------------------
# Cache control
# -------------------------
UV_DEPS := $(wildcard pyproject.toml uv.lock)
BOOTSTRAP_DEPS := Makefile pyproject.toml
STAMP_BOOTSTRAP := .bootstrap.stamp
STAMP_UVSYNC := .uvsync.stamp

# -------------------------
# Meta / setup targets
# -------------------------

.PHONY: help
help:
	@echo "Targets:"
	@echo "  .uv                    Ensure 'uv' is installed (idempotent)"
	@echo "  bootstrap              Install/upgrade global dev tools via uv (ruff, mypy, pytest, coverage)"
	@echo "  install-dev            Install project dev deps (uv sync --dev)"
	@echo "  preflight              Cached: ensures bootstrap + install-dev are done"
	@echo ""
	@echo "Maturin (PyO3) targets:"
	@echo "  py-ext-develop         Build & install the Rust extension into the current venv (maturin develop)"
	@echo "  py-ext-build           Build a wheel into $(WHEELS_DIR) (maturin build)"
	@echo "  py-ext-sdist           Build sdist (maturin sdist)"
	@echo "  py-ext-clean           Remove built wheels and egg-info"
	@echo ""
	@echo "Python-only:"
	@echo "  python-test            Run pytest; logs in $(LOG_DIR)"
	@echo "  python-coverage        Run coverage + pytest; logs in $(LOG_DIR)"
	@echo "  python-coverage-report Show coverage summary"
	@echo "  python-lint            Ruff lint (report + safe fixes)"
	@echo "  python-format          Ruff format"
	@echo "  python-typecheck       mypy"
	@echo "  python-type-stubs      Auto-install missing stubs"
	@echo "  python-fix-all         Format, install stubs, typecheck"
	@echo "  python-clean           Clean Python artifacts"
	@echo "  python-all             Lint, typecheck, test"
	@echo ""
	@echo "Rust-only:"
	@echo "  rust-build             cargo build"
	@echo "  rust-check             cargo check"
	@echo "  rust-test              cargo test"
	@echo "  rust-fmt               cargo fmt --all"
	@echo "  rust-clippy            cargo clippy $(CLIPPY_FLAGS)"
	@echo "  rust-doc               cargo doc --no-deps"
	@echo "  rust-bench             cargo bench"
	@echo "  rust-clean             cargo clean"
	@echo "  ci-rust                fmt, clippy, check, test"
	@echo "  rust-all               alias for ci-rust"
	@echo ""
	@echo "Combined (depend on preflight):"
	@echo "  test, coverage, coverage-report, lint, typecheck, format, clean, ci, fix-all"

# Ensure uv is installed (explicit, reusable)
.PHONY: .uv
.uv:
	@echo "==> Ensuring 'uv' is installed..."
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing uv via pip..."; \
		python3 -m pip install --upgrade pip setuptools wheel || true; \
		pip install --upgrade uv || python3 -m pip install --upgrade uv; \
	else \
		echo "uv already installed: $$(uv --version)"; \
	fi

# Cacheable bootstrap: re-run if Makefile or pyproject.toml changes
.PHONY: bootstrap
bootstrap: .uv $(STAMP_BOOTSTRAP)

$(STAMP_BOOTSTRAP): $(BOOTSTRAP_DEPS)
	@echo "==> Bootstrapping global tools (ruff, mypy, pytest, coverage)..."
	@uv tool list | grep -E '(^|[[:space:]])ruff([[:space:]]|@)' >/dev/null 2>&1 || uv tool install ruff
	@uv tool list | grep -E '(^|[[:space:]])mypy([[:space:]]|@)' >/dev/null 2>&1 || uv tool install mypy
	@uv tool list | grep -E '(^|[[:space:]])pytest([[:space:]]|@)' >/dev/null 2>&1 || uv tool install pytest
	@uv tool list | grep -E '(^|[[:space:]])coverage([[:space:]]|@)' >/dev/null 2>&1 || uv tool install coverage
	@uv tool upgrade --all || true
	@touch $(STAMP_BOOTSTRAP)

# Cacheable uv sync: re-run if pyproject.toml or uv.lock changes
.PHONY: install-dev
install-dev: $(STAMP_UVSYNC)

$(STAMP_UVSYNC): $(UV_DEPS)
	@echo "==> Syncing project dev dependencies with uv..."
	uv sync --dev
	@touch $(STAMP_UVSYNC)

.PHONY: preflight
preflight: bootstrap install-dev

.PHONY: create-log-dir
create-log-dir:
	@mkdir -p $(LOG_DIR)

# -------------------------
# Maturin (PyO3) Targets
# -------------------------

# Build & install extension into the active venv (used by tests)
.PHONY: py-ext-develop
py-ext-develop:
	$(MATURIN) develop $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

# Build wheels
.PHONY: py-ext-build
py-ext-build:
	$(MATURIN) build $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

# Build sdist
.PHONY: py-ext-sdist
py-ext-sdist:
	$(MATURIN) sdist -m $(MATURIN_MANIFEST)

# Clean built artifacts from maturin
.PHONY: py-ext-clean
py-ext-clean:
	rm -rf $(WHEELS_DIR) ./*.egg-info ./**/.eggs

# -------------------------
# Python Targets
# -------------------------

# Build the extension first
.PHONY: python-test
python-test: py-ext-develop create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/test_$${ts}.log"; \
	echo "Writing test log to $$log"; \
	set -o pipefail; \
	$(PYTEST) $(PYTEST_FLAGS) 2>&1 | tee "$$log"

.PHONY: python-coverage
python-coverage: py-ext-develop create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/coverage_$${ts}.log"; \
	echo "Writing coverage log to $$log"; \
	set -o pipefail; \
	$(COVERAGE) run -m pytest -q --basetemp .pytest_tmp --cache-clear 2>&1 | tee "$$log"

.PHONY: python-coverage-report
python-coverage-report:
	$(COVERAGE) report -m

.PHONY: python-lint
python-lint:
	uvx ruff check --unsafe-fixes .
	uvx ruff check --fix --exit-zero-on-fix .

.PHONY: python-typecheck
python-typecheck:
	uv run mypy .

.PHONY: python-format
python-format:
	uv run ruff format .

.PHONY: python-type-stubs
python-type-stubs:
	uv run python -m ensurepip --upgrade || true
	uv run mypy --install-types --non-interactive || true

.PHONY: python-fix-all
python-fix-all: python-format python-type-stubs python-typecheck

.PHONY: python-clean
python-clean:
	rm -rf .pytest_tmp .pytest_cache $(LOG_DIR) .coverage coverage.xml htmlcov

.PHONY: python-all
python-all: python-lint python-typecheck python-test

# -------------------------
# Rust Targets
# -------------------------

.PHONY: rust-build
rust-build:
	$(CARGO) build $(RUST_PKG_FLAG)

.PHONY: rust-check
rust-check:
	$(CARGO) check $(RUST_PKG_FLAG)

.PHONY: rust-test
rust-test:
	$(CARGO) test $(RUST_PKG_FLAG) -- --nocapture

.PHONY: rust-fmt
rust-fmt:
	$(CARGO) fmt --all

.PHONY: rust-clippy
rust-clippy:
	$(CARGO) clippy $(RUST_PKG_FLAG) -- $(CLIPPY_FLAGS)

.PHONY: rust-doc
rust-doc:
	$(CARGO) doc $(RUST_PKG_FLAG) --no-deps

.PHONY: rust-bench
rust-bench:
	$(CARGO) bench $(RUST_PKG_FLAG)

.PHONY: rust-clean
rust-clean:
	$(CARGO) clean $(RUST_PKG_FLAG) || $(CARGO) clean

.PHONY: ci-rust
ci-rust: rust-fmt rust-clippy rust-check rust-test

.PHONY: rust-all
rust-all: ci-rust

# -------------------------
# Combined (Python + Rust)
# -------------------------

.PHONY: test
test: preflight rust-test python-test

.PHONY: coverage
coverage: preflight rust-test python-coverage

.PHONY: coverage-report
coverage-report: preflight python-coverage-report

.PHONY: lint
lint: preflight rust-clippy python-lint

.PHONY: typecheck
typecheck: preflight rust-check python-typecheck

.PHONY: format
format: preflight rust-fmt python-format

.PHONY: clean
clean: preflight rust-clean python-clean py-ext-clean
	@rm -f $(STAMP_BOOTSTRAP) $(STAMP_UVSYNC)

.PHONY: ci
ci: preflight ci-rust python-lint python-typecheck python-test

# -------------------------
# Autofix
# -------------------------

.PHONY: fix-python
fix-python:
	@echo "Running Python auto-fixes..."
	uvx ruff check --fix
	uvx ruff format

.PHONY: fix-rust
fix-rust:
	cargo fmt --all
	# try auto-fix with nightly; fall back to plain clippy
	cargo +nightly clippy --fix --workspace --allow-dirty --allow-staged || cargo clippy --workspace

.PHONY: fix-all
fix-all: preflight fix-python fix-rust
