SHELL := /bin/bash
.DEFAULT_GOAL := test

# -------------------------
# Python: paths & commands
# -------------------------
LOG_DIR := src/sec_nlp/tests/test_logs
PYTEST := uv run pytest
COVERAGE := uv run coverage

# Pytest flags (isolated temp dirs; clear cache each run)
PYTEST_FLAGS := -v --maxfail=1 --tb=short --color=yes --basetemp .pytest_tmp --cache-clear

# -------------------------
# Rust: workspace settings
# -------------------------
CARGO ?= cargo
RUST_CRATE := edga_rs
RUST_PKG_FLAG := -p $(RUST_CRATE)
CLIPPY_FLAGS ?= -D warnings

.PHONY: help install-dev create-log-dir \
        python-test python-coverage python-coverage-report python-lint python-typecheck python-format python-type-stubs python-fix-all python-clean python-all \
        rust-build rust-check rust-test rust-fmt rust-clippy rust-doc rust-clean rust-bench ci-rust rust-all \
        test coverage coverage-report lint typecheck format clean ci \
        fix-python fix-rust fix-all

help:
	@echo "Targets:"
	@echo "  install-dev            Install dev deps via uv (pytest, coverage, mypy, autopep8)"
	@echo ""
	@echo "Python-only:"
	@echo "  python-test            Run pytest; tee output to $(LOG_DIR)/test_<timestamp>.log"
	@echo "  python-coverage        Run coverage+pytest; tee to $(LOG_DIR)/coverage_<timestamp>.log"
	@echo "  python-coverage-report Print coverage summary"
	@echo "  python-lint            PEP8 check (autopep8 --diff --exit-code)"
	@echo "  python-typecheck       Run mypy"
	@echo "  python-format          Apply autopep8 fixes in-place"
	@echo "  python-type-stubs      Auto-install missing type stubs via mypy"
	@echo "  python-fix-all         Format, install stubs, then typecheck"
	@echo "  python-clean           Remove Python test artifacts and logs"
	@echo "  python-all             Lint, typecheck, test (Python)"
	@echo ""
	@echo "Rust-only:"
	@echo "  rust-build             cargo build for $(RUST_CRATE)"
	@echo "  rust-check             cargo check for $(RUST_CRATE)"
	@echo "  rust-test              cargo test for $(RUST_CRATE)"
	@echo "  rust-fmt               cargo fmt --all"
	@echo "  rust-clippy            cargo clippy $(CLIPPY_FLAGS) for $(RUST_CRATE)"
	@echo "  rust-doc               cargo doc (no-deps) for $(RUST_CRATE)"
	@echo "  rust-bench             cargo bench $(RUST_PKG_FLAG)"
	@echo "  rust-clean             cargo clean (package only)"
	@echo "  ci-rust                Run rust-fmt, rust-clippy, rust-check, rust-test"
	@echo "  rust-all               Run the main Rust checks (same as ci-rust)"
	@echo ""
	@echo "Combined (Python + Rust):"
	@echo "  test                   rust-test then python-test"
	@echo "  coverage               rust-test then python-coverage (no Rust coverage)"
	@echo "  coverage-report        Alias to python-coverage-report"
	@echo "  lint                   rust-clippy then python-lint"
	@echo "  typecheck              rust-check then python-typecheck"
	@echo "  format                 rust-fmt then python-format"
	@echo "  clean                  rust-clean then python-clean"
	@echo "  ci                     ci-rust then python-lint, python-typecheck, python-test"
	@echo "  fix-all                fix-python then fix-rust (full-stack autofix)"

install-dev:
	uv sync --dev

create-log-dir:
	@mkdir -p $(LOG_DIR)

# -------------------------
# Python targets (prefixed)
# -------------------------
python-test: create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/test_$${ts}.log"; \
	echo "Writing test log to $$log"; \
	set -o pipefail; \
	$(PYTEST) $(PYTEST_FLAGS) 2>&1 | tee "$$log"

python-coverage: create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/coverage_$${ts}.log"; \
	echo "Writing coverage log to $$log"; \
	set -o pipefail; \
	$(COVERAGE) run -m pytest -q --basetemp .pytest_tmp --cache-clear 2>&1 | tee "$$log"

python-coverage-report:
	$(COVERAGE) report -m

python-lint:
	uv run autopep8 -r --diff --exit-code --max-line-length 100 .

python-typecheck:
	uv run mypy .

python-format:
	uv run autopep8 -r -i --max-line-length 100 .

python-type-stubs:
	uv run python -m ensurepip --upgrade || true
	uv run mypy --install-types --non-interactive || true

python-fix-all: python-format python-type-stubs python-typecheck

python-clean:
	rm -rf .pytest_tmp .pytest_cache $(LOG_DIR) .coverage coverage.xml htmlcov

python-all: python-lint python-typecheck python-test

# -------------------------
# Rust targets
# -------------------------
rust-build:
	$(CARGO) build $(RUST_PKG_FLAG)

rust-check:
	$(CARGO) check $(RUST_PKG_FLAG)

rust-test:
	$(CARGO) test $(RUST_PKG_FLAG) -- --nocapture

rust-fmt:
	$(CARGO) fmt --all

rust-clippy:
	$(CARGO) clippy $(RUST_PKG_FLAG) -- $(CLIPPY_FLAGS)

rust-doc:
	$(CARGO) doc $(RUST_PKG_FLAG) --no-deps

rust-bench:
	$(CARGO) bench $(RUST_PKG_FLAG)

rust-clean:
	$(CARGO) clean $(RUST_PKG_FLAG) || $(CARGO) clean

# Run all Rust checks that you'd want on pre-push
ci-rust: rust-fmt rust-clippy rust-check rust-test

rust-all: ci-rust

# -------------------------
# Combined (Python + Rust)
# -------------------------
# Run Rust first so you fail fast on native deps, then Python.
test: rust-test python-test

coverage: rust-test python-coverage

coverage-report: python-coverage-report

lint: rust-clippy python-lint

typecheck: rust-check python-typecheck

format: rust-fmt python-format

clean: rust-clean python-clean

ci: ci-rust python-lint python-typecheck python-test

# -------------------------
# One-shot auto-fix helpers
# -------------------------
fix-python:
	uv run python -m pip install --quiet --upgrade ruff || true
	uv run autopep8 -r -i --max-line-length 100 .
	uv run ruff check --fix
	uv run ruff format

fix-rust:
	cargo fmt --all
	# try auto-fix with nightly; fall back to plain clippy
	cargo +nightly clippy --fix --workspace --allow-dirty --allow-staged || cargo clippy --workspace

# Combined Python + Rust autofix
fix-all: fix-python fix-rust
