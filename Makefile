# Makefile
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
RUST_CRATE := edga_rs                 # package name in Cargo.toml
RUST_PKG_FLAG := -p $(RUST_CRATE)     # limit actions to the crate (still uses workspace)
CLIPPY_FLAGS ?= -D warnings

# If you want to run on the whole workspace instead of a single crate, set:
#   RUST_PKG_FLAG :=
# to allow e.g. cargo test to run for all members.

.PHONY: help install-dev create-log-dir \
        test coverage coverage-report lint typecheck format clean ci type-stubs fix-all \
        rust-build rust-check rust-test rust-fmt rust-clippy rust-doc rust-clean rust-bench ci-rust

help:
	@echo "Targets:"
	@echo "  install-dev       Install dev deps via uv (pytest, coverage, mypy, autopep8)"
	@echo "  test              Run pytest; tee output to $(LOG_DIR)/test_<timestamp>.log"
	@echo "  coverage          Run coverage+pytest; tee to $(LOG_DIR)/coverage_<timestamp>.log"
	@echo "  coverage-report   Print coverage summary"
	@echo "  lint              PEP8 check (autopep8 --diff --exit-code)"
	@echo "  typecheck         Run mypy"
	@echo "  format            Apply autopep8 fixes in-place"
	@echo "  type-stubs        Auto-install missing type stubs via mypy"
	@echo "  fix-all           Format, install stubs, then typecheck"
	@echo "  clean             Remove test artifacts and logs"
	@echo "  ci                Run Rust + Python checks (pre-push style)"
	@echo ""
	@echo "Rust:"
	@echo "  rust-build        cargo build for $(RUST_CRATE)"
	@echo "  rust-check        cargo check for $(RUST_CRATE)"
	@echo "  rust-test         cargo test for $(RUST_CRATE)"
	@echo "  rust-fmt          cargo fmt --all (check and fix)"
	@echo "  rust-clippy       cargo clippy $(CLIPPY_FLAGS) for $(RUST_CRATE)"
	@echo "  rust-doc          cargo doc (no-deps) for $(RUST_CRATE)"
	@echo "  rust-bench        cargo bench for $(RUST_CRATE)"
	@echo "  rust-clean        cargo clean (package only)"
	@echo "  ci-rust           Run rust-fmt, rust-clippy, rust-check, rust-test"

install-dev:
	uv sync --dev

create-log-dir:
	@mkdir -p $(LOG_DIR)

# -------------------------
# Python targets
# -------------------------
test: create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/test_$${ts}.log"; \
	echo "Writing test log to $$log"; \
	set -o pipefail; \
	$(PYTEST) $(PYTEST_FLAGS) 2>&1 | tee "$$log"

coverage: create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/coverage_$${ts}.log"; \
	echo "Writing coverage log to $$log"; \
	set -o pipefail; \
	$(COVERAGE) run -m pytest -q --basetemp .pytest_tmp --cache-clear 2>&1 | tee "$$log"

coverage-report:
	$(COVERAGE) report -m

lint:
	uv run autopep8 -r --diff --exit-code --max-line-length 100 .

typecheck:
	uv run mypy .

format:
	uv run autopep8 -r -i --max-line_length 100 .

# Auto-install missing type stubs, then re-run mypy install (non-fatal) to capture all
type-stubs:
	uv run python -m ensurepip --upgrade || true
	uv run mypy --install-types --non-interactive || true

# One-shot: format code, install stubs, then typecheck
fix-all: format type-stubs typecheck

clean:
	rm -rf .pytest_tmp .pytest_cache $(LOG_DIR) .coverage coverage.xml htmlcov

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

# -------------------------
# Combined CI
# -------------------------
# Run Rust checks first so you fail fast on native deps, then Python.
ci: ci-rust lint typecheck test
