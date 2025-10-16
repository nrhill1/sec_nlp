SHELL := /bin/bash
.DEFAULT_GOAL := test

# Python
LOG_DIR := src/sec_nlp/tests/test_logs
PYTEST_FLAGS := -v --maxfail=1 --tb=short --color=yes --basetemp .pytest_tmp --cache-clear

# Rust
CARGO ?= cargo
RUST_CRATE := edgars
RUST_PKG_FLAG := -p $(RUST_CRATE)
CLIPPY_FLAGS ?= -D warnings

# Maturin (PyO3)
MATURIN := uvx maturin
MATURIN_FLAGS ?= --release
MATURIN_MANIFEST := crates/$(RUST_CRATE)/Cargo.toml
WHEELS_DIR := target/wheels

# Cache control
UV_DEPS := $(wildcard pyproject.toml uv.lock)
BOOTSTRAP_DEPS := Makefile pyproject.toml
STAMP_BOOTSTRAP := .bootstrap.stamp
STAMP_UVSYNC := .uvsync.stamp

# -------------------------
# Meta / setup targets
# -------------------------

.PHONY: help
help:
	@echo "Setup:"
	@echo "  bootstrap              Install/upgrade dev tools (ruff, mypy, pytest, coverage)"
	@echo "  install-dev            Sync project dependencies (uv sync --dev)"
	@echo "  preflight              bootstrap + install-dev (cached)"
	@echo ""
	@echo "Development:"
	@echo "  lint                   Run all linters (Rust + Python)"
	@echo "  typecheck              Run mypy type checking"
	@echo "  format                 Auto-format all code (Rust + Python)"
	@echo "  fix                    Auto-fix all issues + format"
	@echo "  test                   Run all tests (Rust + Python)"
	@echo "  coverage               Run Python tests with coverage"
	@echo "  coverage-report        Show coverage report"
	@echo ""
	@echo "CI/CD:"
	@echo "  verify                 preflight + lint (for CI)"
	@echo "  ci                     verify + test (full CI pipeline)"
	@echo ""
	@echo "Python specific:"
	@echo "  python-lint            ruff check"
	@echo "  python-test            pytest"
	@echo "  python-format          ruff format"
	@echo ""
	@echo "Rust specific:"
	@echo "  rust-lint              rustfmt + clippy"
	@echo "  rust-test              cargo test"
	@echo "  rust-fmt               cargo fmt"
	@echo ""
	@echo "Maturin:"
	@echo "  py-ext-develop         Build PyO3 extension in dev mode"
	@echo "  py-ext-build           Build PyO3 wheels"
	@echo "  py-ext-sdist           Build source distribution"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean                  Remove build artifacts and stamps"

.PHONY: .uv
.uv:
	@if ! command -v uv >/dev/null 2>&1; then \
		echo "Installing uv..."; \
		python3 -m pip install --upgrade uv; \
	fi

.PHONY: bootstrap
bootstrap: .uv $(STAMP_BOOTSTRAP)

$(STAMP_BOOTSTRAP): $(BOOTSTRAP_DEPS)
	@echo "==> Bootstrapping dev tools..."
	@uv tool list | grep -qE '(^|[[:space:]])ruff([[:space:]]|@)' || uv tool install ruff
	@uv tool list | grep -qE '(^|[[:space:]])mypy([[:space:]]|@)' || uv tool install mypy
	@uv tool list | grep -qE '(^|[[:space:]])pytest([[:space:]]|@)' || uv tool install pytest
	@uv tool list | grep -qE '(^|[[:space:]])coverage([[:space:]]|@)' || uv tool install coverage
	@uv tool upgrade --all || true
	@touch $(STAMP_BOOTSTRAP)

.PHONY: install-dev
install-dev: $(STAMP_UVSYNC)

$(STAMP_UVSYNC): $(UV_DEPS)
	@echo "==> Syncing dev dependencies..."
	@uv sync --dev
	@touch $(STAMP_UVSYNC)

.PHONY: preflight
preflight: bootstrap install-dev

.PHONY: verify
verify: preflight lint

# -------------------------
# Maturin (PyO3)
# -------------------------

.PHONY: py-ext-develop
py-ext-develop:
	@$(MATURIN) develop $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

.PHONY: py-ext-build
py-ext-build:
	@$(MATURIN) build $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

.PHONY: py-ext-sdist
py-ext-sdist:
	@$(MATURIN) sdist -m $(MATURIN_MANIFEST)

# -------------------------
# Python
# -------------------------

.PHONY: python-lint
python-lint: preflight
	@echo "==> Ruff lint..."
	@uvx ruff check .

.PHONY: python-typecheck
python-typecheck: preflight
	@echo "==> Mypy type check..."
	@uv run mypy .

.PHONY: python-format
python-format: preflight
	@echo "==> Ruff format..."
	@uv run ruff format .

.PHONY: python-test
python-test: py-ext-develop
	@mkdir -p $(LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/test_$${ts}.log"; \
	echo "==> Running Python tests (log: $$log)..."; \
	set -o pipefail; \
	uv run pytest $(PYTEST_FLAGS) 2>&1 | tee "$$log"

.PHONY: python-coverage
python-coverage: py-ext-develop
	@mkdir -p $(LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/coverage_$${ts}.log"; \
	echo "==> Running coverage (log: $$log)..."; \
	set -o pipefail; \
	uv run coverage run -m pytest -q --basetemp .pytest_tmp --cache-clear 2>&1 | tee "$$log"

# -------------------------
# Rust
# -------------------------

.PHONY: rust-lint
rust-lint: preflight
	@echo "==> rustfmt check..."
	@$(CARGO) fmt --all -- --check
	@echo "==> cargo clippy..."
	@$(CARGO) clippy $(RUST_PKG_FLAG) -- $(CLIPPY_FLAGS)

.PHONY: rust-test
rust-test: preflight
	@echo "==> Rust tests..."
	@$(CARGO) test $(RUST_PKG_FLAG) -- --nocapture

.PHONY: rust-fmt
rust-fmt: preflight
	@echo "==> cargo fmt..."
	@$(CARGO) fmt --all

# -------------------------
# Combined commands
# -------------------------

.PHONY: lint
lint: rust-lint python-lint

.PHONY: typecheck
typecheck: python-typecheck

.PHONY: format
format: rust-fmt python-format

.PHONY: test
test: rust-test python-test

.PHONY: coverage
coverage: rust-test python-coverage

.PHONY: coverage-report
coverage-report: preflight
	@uv run coverage report -m

.PHONY: fix
fix: preflight
	@echo "==> Auto-fixing Python..."
	@uvx ruff check --fix .
	@uv run ruff format .
	@echo "==> Auto-fixing Rust..."
	@$(CARGO) fmt --all
	@cargo +nightly clippy --fix --workspace --allow-dirty --allow-staged 2>/dev/null || $(CARGO) clippy $(RUST_PKG_FLAG) --fix --allow-dirty --allow-staged

.PHONY: ci
ci: verify test

.PHONY: clean
clean:
	@echo "==> Cleaning build artifacts..."
	@rm -rf $(WHEELS_DIR) ./*.egg-info ./**/.eggs target/
	@rm -f $(STAMP_BOOTSTRAP) $(STAMP_UVSYNC)
	@rm -rf .pytest_tmp .pytest_cache .ruff_cache .mypy_cache
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true