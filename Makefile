SHELL := /bin/bash
.DEFAULT_GOAL := test

# Python
PYTHON_DIR := sec_nlp/
LOG_DIR := sec_nlp/tests/test_logs
PYTEST_FLAGS := -v --maxfail=1 --tb=short --color=yes --basetemp .pytest_tmp --cache-clear
MYPY := uv run mypy .

# Rust
CARGO ?= cargo
RUST_CRATE := sec_o3
RUST_PKG_FLAG := -p $(RUST_CRATE)
CLIPPY_FLAGS ?= -D warnings

# Maturin (PyO3)
MATURIN := uv run maturin
MATURIN_FLAGS ?= --uv --release
MATURIN_MANIFEST := crates/$(RUST_CRATE)/Cargo.toml
WHEELS_DIR := target/wheels

# Cache control
UV_DEPS := $(wildcard pyproject.toml uv.lock)
BOOTSTRAP_DEPS := Makefile pyproject.toml
STAMP_BOOTSTRAP := .bootstrap.stamp
STAMP_UVSYNC := .uvsync.stamp

# -------------------------
# Environment Setup
# -------------------------

.PHONY: help
help:
	@echo "Setup:"
	@echo "  setup                  Install/upgrade dev tools"
	@echo "  sync                   Sync project dependencies"
	@echo "  ready                  setup + sync (cached)"
	@echo "  update                 Update all dependencies"
	@echo ""
	@echo "Development:"
	@echo "  lint                   Run all linters"
	@echo "  types                  Run type checking"
	@echo "  fmt                    Auto-format all code"
	@echo "  fix                    Auto-fix all issues + format"
	@echo "  test                   Run all tests"
	@echo "  test-rs                Run Rust tests only"
	@echo "  test-py                Run Python tests only"
	@echo "  watch                  Run tests on file changes (requires cargo-watch)"
	@echo ""
	@echo "Quality:"
	@echo "  check                  ready + lint (pre-commit)"
	@echo "  cov                    Run tests with coverage"
	@echo "  cov-html               Generate HTML coverage report"
	@echo "  bench                  Run benchmarks"
	@echo ""
	@echo "Build & Release:"
	@echo "  build                  Build everything (lib + extension + wheels)"
	@echo "  build-rs               Build Rust library only"
	@echo "  build-ext              Build Python extension"
	@echo "  build-wheel            Build distribution wheels"
	@echo "  build-sdist            Build source distribution"
	@echo ""
	@echo "Language-specific:"
	@echo "  py-lint                Python: ruff check"
	@echo "  py-fmt                 Python: ruff format"
	@echo "  py-types               Python: mypy type check"
	@echo "  python-al 				Python: all language-specific Python commands."
	@echo "  rs-lint                Rust: fmt + clippy"
	@echo "  rs-fmt                 Rust: cargo fmt"
	@echo "  rs-clippy              Rust: cargo clippy"
	@echo "  rust-all				Rust: all language-specific Rust commands"
	@echo ""
	@echo "CI/CD:"
	@echo "  ci                     Full CI pipeline (check + test)"
	@echo "  ci-quick               Quick CI check (lint only)"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean                  Remove build artifacts"
	@echo "  clean-all              Deep clean (including caches)"

.PHONY: .uv
.uv:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		python3 -m pip install --upgrade uv; \
	fi

.PHONY: setup
setup: .uv $(STAMP_BOOTSTRAP)

$(STAMP_BOOTSTRAP): $(BOOTSTRAP_DEPS)
	@echo "==> Bootstrapping dev tools..."
	@uv tool list | grep -qE '(^|[[:space:]])maturin([[:space:]]|@)' || uv tool install maturin
	@uv tool list | grep -qE '(^|[[:space:]])ruff([[:space:]]|@)' || uv tool install ruff
	@uv tool list | grep -qE '(^|[[:space:]])mypy([[:space:]]|@)' || uv tool install mypy
	@uv tool list | grep -qE '(^|[[:space:]])pytest([[:space:]]|@)' || uv tool install pytest
	@uv tool list | grep -qE '(^|[[:space:]])coverage([[:space:]]|@)' || uv tool install coverage
	@uv tool upgrade --all || true
	@touch $(STAMP_BOOTSTRAP)

.PHONY: sync
sync: $(STAMP_UVSYNC)

$(STAMP_UVSYNC): $(UV_DEPS)
	@echo "==> Syncing dev dependencies..."
	@uv sync
	@touch $(STAMP_UVSYNC)

.PHONY: ready
ready: setup sync

.PHONY: update
update: setup
	@echo "==> Updating dependencies..."
	@uv sync --upgrade
	@$(CARGO) update
	@rm -f $(STAMP_UVSYNC)

.PHONY: check
check: ready lint

# -------------------------
# Build Targets
# -------------------------

.PHONY: build
build: build-rs build-ext build-wheel

.PHONY: build-rs
build-rs: ready
	@echo "==> Building Rust library..."
	@$(CARGO) build --release $(RUST_PKG_FLAG)

.PHONY: build-ext
build-ext:
	@$(MATURIN) develop $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

.PHONY: build-wheel
build-wheel:
	@$(MATURIN) build $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

.PHONY: build-sdist
build-sdist:
	@$(MATURIN) sdist -m $(MATURIN_MANIFEST)

# -------------------------
# Python
# -------------------------

.PHONY: py-lint
py-lint: ready
	@echo "==> Ruff lint..."
	@uv run ruff check .

.PHONY: py-types
py-types: ready
	@echo "==> Mypy type check..."
	@uv run mypy .

.PHONY: py-fmt
py-fmt: ready
	@echo "==> Ruff format..."
	@uv run ruff format .

.PHONY: test-py
test-py: build-ext
	@mkdir -p $(LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/test_$${ts}.log"; \
	echo "==> Running Python tests (log: $$log)..."; \
	set -o pipefail; \
	uv run pytest $(PYTEST_FLAGS) 2>&1 | tee "$$log"

.PHONY: py-cov
py-cov: build-ext
	@mkdir -p $(LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/coverage_$${ts}.log"; \
	echo "==> Running coverage (log: $$log)..."; \
	set -o pipefail; \
	uv run coverage run -m pytest -q --basetemp .pytest_tmp --cache-clear 2>&1 | tee "$$log"

.PHONY: python-all
python-all: py-lint py-types py-fmt test-py py-cov

# -------------------------
# Rust
# -------------------------

.PHONY: rs-lint
rs-lint: rs-fmt rs-clippy

.PHONY: rs-fmt
rs-fmt: ready
	@echo "==> cargo fmt check..."
	@$(CARGO) fmt --all -- --check

.PHONY: rs-clippy
rs-clippy: ready
	@echo "==> cargo clippy..."
	@$(CARGO) clippy $(RUST_PKG_FLAG) -- $(CLIPPY_FLAGS)

.PHONY: test-rs
test-rs: ready
	@echo "==> Rust tests..."
	@$(CARGO) test $(RUST_PKG_FLAG)

.PHONY: rs-bench
rs-bench: ready
	@echo "==> Running benchmarks..."
	@$(CARGO) bench $(RUST_PKG_FLAG)

.PHONY: rust-all
rust-all: rs-lint test-rs rs-bench

# -------------------------
# Combined Commands
# -------------------------

.PHONY: lint
lint: rs-lint py-lint

.PHONY: types
types: py-types

.PHONY: fmt
fmt: ready
	@echo "==> Formatting Rust..."
	@$(CARGO) fmt --all
	@echo "==> Formatting Python..."
	@uv run ruff format .

.PHONY: test
test: test-rs test-py

.PHONY: cov
cov: test-rs py-cov

.PHONY: cov-html
cov-html: cov
	@echo "==> Generating HTML coverage report..."
	@uv run coverage html
	@echo "==> Coverage report: htmlcov/index.html"

.PHONY: cov-report
cov-report: ready
	@uv run coverage report -m

.PHONY: fix
fix: ready
	@echo "==> Auto-fixing Python..."
	@uv run ruff check --fix .
	@uv run ruff format .
	@echo "==> Auto-fixing Rust..."
	@$(CARGO) fmt --all
	@cargo +nightly clippy --fix --workspace --allow-dirty --allow-staged 2>/dev/null || $(CARGO) clippy $(RUST_PKG_FLAG) --fix --allow-dirty --allow-staged

.PHONY: watch
watch:
	@if command -v cargo-watch >/dev/null 2>&1; then \
		$(CARGO) watch -x 'test $(RUST_PKG_FLAG)'; \
	else \
		echo "cargo-watch not installed. Run: cargo install cargo-watch"; \
		exit 1; \
	fi

# -------------------------
# CI/CD
# -------------------------

.PHONY: ci
ci: check test

.PHONY: ci-quick
ci-quick: check

# -------------------------
# Cleanup
# -------------------------

.PHONY: clean
clean:
	@echo "==> Cleaning build artifacts..."
	@rm -rf $(WHEELS_DIR) ./*.egg-info ./**/.eggs target/release target/debug
	@rm -f $(STAMP_BOOTSTRAP) $(STAMP_UVSYNC)
	@rm -rf .pytest_tmp .pytest_cache
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true

.PHONY: clean-all
clean-all: clean
	@echo "==> Deep cleaning caches..."
	@rm -rf .ruff_cache .mypy_cache htmlcov .coverage
	@$(CARGO) clean
