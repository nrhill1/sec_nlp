SHELL := /bin/bash
.DEFAULT_GOAL := test

# Python
PYTHON_DIR := src/
TEST_DIR := tests/
LOG_DIR := $(TEST_DIR)/test_logs
PYTEST_FLAGS := --color=yes --basetemp .pytest_tmp --cache-clear --log-cli-level=INFO
MYPY_FLAGS :=  --exclude-gitignore --warn-unreachable
STUBS_DIR := types/
STUBGEN_FLAGS := src/sec_nlp tests -o $(STUBS_DIR) --include-private

# Rust
CARGO ?= cargo
RUST_NIGHTLY = +nightly
CARGO_NIGHTLY = $(CARGO) $(RUST_NIGHTLY)
RUSTFLAGS = -C instrument-coverage
RUST_CRATE := sec_o3
RUST_PKG_FLAG := -p $(RUST_CRATE)
CLIPPY_FLAGS ?= -D warnings
LLVM_COV_DIR := .coverage/llvm/

# Maturin/PyO3
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
	@echo "  types                  Run type checking (including tests)"
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
	@echo "  py-types               Python: mypy type check (src + tests)"
	@echo "  py-stubs               Python: generate type stubs (src + tests)"
	@echo "  python-all             Python: all language-specific Python commands"
	@echo "  rs-lint                Rust: fmt + clippy"
	@echo "  rs-fmt                 Rust: cargo fmt"
	@echo "  rs-clippy              Rust: cargo clippy"
	@echo "  rust-all               Rust: all language-specific Rust commands"
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
	@uv lock --upgrade
	@$(CARGO) update
	@rm -f $(STAMP_UVSYNC)

.PHONY: check
check: ready lint

# -------------------------
# Build Targets
# -------------------------

.PHONY: build
build: build-rs build-ext build-wheel

.PHONY: prebuild
prebuild: ready
	@rm -f src/sec_nlp/**/*.so 2>/dev/null || true

.PHONY: build-rs
build-rs: prebuild
	@echo "==> Building Rust library..."
	@$(CARGO) build --release $(RUST_PKG_FLAG)

.PHONY: build-ext
build-ext: prebuild
	@echo "==> Building Python extension (release)..."
	@$(MATURIN) develop $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

.PHONY: build-ext-dev
build-ext-dev: prebuild
	@echo "==> Building Python extension (debug, faster)..."
	@$(MATURIN) develop -m $(MATURIN_MANIFEST)

.PHONY: build-wheel
build-wheel: prebuild
	@echo "==> Building distribution wheel..."
	@$(MATURIN) build $(MATURIN_FLAGS) -m $(MATURIN_MANIFEST)

.PHONY: build-sdist
build-sdist: prebuild
	@echo "==> Building source distribution..."
	@$(MATURIN) sdist -m $(MATURIN_MANIFEST)

# -------------------------
# Python
# -------------------------

.PHONY: py-lint
py-lint: ready py-fmt
	@echo "==> Ruff check..."
	@uv run ruff check . --fix

.PHONY: py-stubs
py-stubs: ready
	@echo "==> Generating stubs for src + tests into $(STUBS_DIR)..."
	@rm -rf $(STUBS_DIR) && mkdir -p $(STUBS_DIR)
	@uv run stubgen $(STUBGEN_FLAGS)
	@find $(STUBS_DIR) -type f -name "__init__.pyi" -delete
	@uv run ruff check $(STUBS_DIR) --fix --quiet

.PHONY: py-types
py-types: ready
	@echo "==> Installing missing types using Mypy..."
	@uv run mypy --install-types --non-interactive
	@echo "==> Mypy type check (src + tests)..."
	@uv run mypy $(MYPY_FLAGS)

.PHONY: py-fmt
py-fmt: ready
	@echo "==> Ruff format..."
	@uv run ruff format .

.PHONY: test-py
test-py: ready build-ext-dev
	@mkdir -p $(LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/test_$${ts}.log"; \
	echo "==> Running Python tests (log: $$log)..."; \
	set -o pipefail; \
	uv run pytest $(PYTEST_FLAGS) 2>&1 | tee "$$log"

.PHONY: py-cov
py-cov: ready build-ext-dev
	@mkdir -p $(LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/coverage_$${ts}.log"; \
	echo "==> Running coverage (log: $$log)..."; \
	set -o pipefail; \
	uv run coverage run -m pytest -q --basetemp .pytest_tmp --cache-clear 2>&1 | tee "$$log"

.PHONY: python-all
python-all: py-lint py-types py-fmt test-py

# -------------------------
# Rust
# -------------------------

.PHONY: rs-lint
rs-lint: rs-fmt rs-clippy

.PHONY: rs-fmt
rs-fmt-fix: ready
	@echo "==> cargo fmt..."
	@$(CARGO) fmt --all

.PHONY: rs-clippy
rs-clippy-fix: ready
	@echo "==> cargo clippy --fix..."
	@$(CARGO) clippy $(RUST_PKG_FLAG) --fix --allow-staged -- $(CLIPPY_FLAGS)

.PHONY: test-rs
test-rs: ready
	@echo "==> Rust tests..."
	@$(CARGO) test $(RUST_PKG_FLAG) --lib --bins --tests

.PHONY: rs-bench
rs-bench: ready
	@echo "==> Running benchmarks..."
	@$(CARGO) bench $(RUST_PKG_FLAG)

.PHONY: rs-cov
rs-cov: ready
	@mkdir -p $(LLVM_COV_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	cov="$(LLVM_COV_DIR)/coverage_$${ts}.json" \
	echo "==> Running Rust coverage...(cov: $$cov)"; \
	$(CARGO) llvm-cov $(RUST_PKG_FLAG) --json --output-path cov

.PHONY: rust-all
rust-all: rs-lint test-rs rs-bench rs-cov

# -------------------------
# Combined Commands
# -------------------------

.PHONY: lint
lint: rs-lint py-lint

.PHONY: types
types: py-stubs py-types

.PHONY: fmt
fmt: ready
	@echo "==> Formatting Rust..."
	@$(CARGO) fmt --all
	@echo "==> Formatting Python..."
	@uv run ruff format .

.PHONY: test
test: test-rs test-py

.PHONY: cov
cov: rs-cov py-cov

.PHONY: cov-html
cov-html: cov
	@echo "==> Generating HTML coverage reports..."
	@uv run coverage html
	@echo "==> Python coverage report: htmlcov/index.html"
	@$(CARGO) llvm-cov $(RUST_PKG_FLAG) --html
	@echo "==> Rust coverage report: target/llvm-cov/html/index.html"

.PHONY: cov-report
cov-report: ready
	@uv run coverage report -m

.PHONY: fix
fix: ready py-lint
	@echo "==> Auto-fixing Rust..."
	@$(CARGO) fmt --all
	@$(CARGO_NIGHTLY) clippy --fix $(RUST_PKG_FLAG) --allow-dirty --allow-staged 2>/dev/null || \
		$(CARGO) clippy --fix $(RUST_PKG_FLAG) --allow-dirty --allow-staged

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
# Development Workflow
# -------------------------

.PHONY: dev
dev: setup sync build-ext-dev
	@echo "==> Development environment ready!"
	@echo "    Rust extension built in debug mode for faster iteration"

.PHONY: dev-full
dev-full: setup sync build
	@echo "==> Full development build complete!"

# -------------------------
# Cleanup
# -------------------------

.PHONY: clean
clean:
	@echo "==> Cleaning build artifacts..."
	@rm -rf $(WHEELS_DIR) ./*.egg-info ./**/.eggs target/release target/debug dist/
	@rm -f $(STAMP_BOOTSTRAP) $(STAMP_UVSYNC)
	@rm -f src/sec_nlp/**/*.so 2>/dev/null || true
	@echo "==> Removing Pytest cache/temp files..."
	@rm -rf .pytest_tmp .pytest_cache
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*~" -delete 2>/dev/null || true
	@find . -type f -name ".*~" -delete 2>/dev/null || true

.PHONY: deep-clean
deep-clean: clean
	@echo "==> Deep cleaning caches..."
	@rm -rf .ruff_cache htmlcov .coverage .mypy_cache $(STUBS_DIR)
	@$(CARGO) clean
	@$(CARGO) llvm-cov clean --workspace 2>/dev/null || true

.PHONY: clean-all
clean-all: deep-clean
	@echo "==> Cleaning .venv..."
	@rm -rf .venv
	@make ready
