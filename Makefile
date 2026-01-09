SHELL := /bin/bash
.DEFAULT_GOAL := help
BRANCH := $(shell git rev-parse --abbrev-ref HEAD)

# =========================================================================
# Variables
# =========================================================================

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

# Nested Makefile directories
PYTHON_DIR := $(ROOT_DIR)/src
MARKET_DIR := $(ROOT_DIR)/crates/market
MARKET_MANIFEST := $(MARKET_DIR)/Cargo.toml

# Maturin
MATURIN_FLAGS ?=
MATURIN_BUILD_FLAGS ?= --release --uv --strip
MATURIN_SDIST_FLAGS ?=
RUSTFLAGS_DEV ?= -C debuginfo=0 -C codegen-units=256 -C opt-level=0
RUSTFLAGS_PROD ?= -C lto=thin -C codegen-units=1 -C opt-level=3

# Cache control
UV_DEPS := $(wildcard pyproject.toml uv.lock)
BOOTSTRAP_DEPS := Makefile pyproject.toml
STAMP_BOOTSTRAP := .bootstrap.stamp
STAMP_UVSYNC := .uvsync.stamp
UV_SYNC_FLAGS ?= --frozen
UV_NO_BUILD_ISOLATION ?= 1

# =========================================================================
# Help
# =========================================================================

.PHONY: help
help:
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║           SEC NLP - Consolidated Build System                  ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "Environment Setup:"
	@echo "  setup                  Install/upgrade dev tools"
	@echo "  sync                   Sync project dependencies"
	@echo "  ready                  setup + sync (cached)"
	@echo "  update                 Update all dependencies"
	@echo ""
	@echo "Quick Commands:"
	@echo "  dev                    Setup dev environment"
	@echo "  stubs                  Generate type stubs (Python)"
	@echo "  test                   Run all tests"
	@echo "  lint                   Run all linters"
	@echo "  fmt                    Format all code"
	@echo "  clean                  Clean all build artifacts"
	@echo ""
	@echo "Language-Specific:"
	@echo "  py-<target>            Run Python target (e.g., py-lint, py-test)"
	@echo "  market-<target>        Run Market (Rust) target (e.g., market-dev)"
	@echo "  maturin-dev            Build + install Rust extension via maturin"
	@echo "  maturin-build          Build release wheels via maturin"
	@echo "  maturin-sdist          Build a source distribution via maturin"
	@echo ""
	@echo "For detailed help on each subsystem, run:"
	@echo "  make -C src help       # Python commands"
	@echo "  make -C crates/market help  # Market (Rust) commands"
	@echo ""
	@echo "CI/CD:"
	@echo "  ci                     Full CI pipeline"
	@echo "  ci-quick               Quick CI check (lint only)"
	@echo ""
	@echo "Advanced:"
	@echo "  validate               Full validation (imports + types + tests)"
	@echo "  cov-html               Generate coverage reports"
	@echo "  pre-commit             Run pre-commit hooks"
	@echo "  stubs                  Generate Python stubs into ./types (uses stubgen)"

# =========================================================================
# Environment Setup
# =========================================================================

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
	@uv tool list | grep -qE '(^|[[:space:]])pre-commit([[:space:]]|@)' || uv tool install pre-commit
	@uv tool list | grep -qE '(^|[[:space:]])ruff([[:space:]]|@)' || uv tool install ruff
	@uv tool list | grep -qE '(^|[[:space:]])ty([[:space:]]|@)' || uv tool install ty
	@uv tool list | grep -qE '(^|[[:space:]])pytest([[:space:]]|@)' || uv tool install pytest
	@uv tool list | grep -qE '(^|[[:space:]])coverage([[:space:]]|@)' || uv tool install coverage
	@uv tool list | grep -qE '(^|[[:space:]])maturin([[:space:]]|@)' || uv tool install maturin
	@uv tool upgrade --all || true
	@touch $(STAMP_BOOTSTRAP)
	@echo "✓ Dev tools ready"
	@echo ""

.PHONY: sync
sync: $(STAMP_UVSYNC)
$(STAMP_UVSYNC): $(UV_DEPS)
	@echo "==> Syncing dependencies..."
	@UV_NO_BUILD_ISOLATION=$(UV_NO_BUILD_ISOLATION) uv sync $(UV_SYNC_FLAGS)
	@touch $(STAMP_UVSYNC)
	@echo "✓ Dependencies synced"
	@echo ""

.PHONY: ready
ready: setup sync

.PHONY: update
update: setup
	@echo "==> Updating dependencies..."
	@uv sync --upgrade
	@uv lock --upgrade
	@rm -f $(STAMP_UVSYNC)
	@echo "✓ All dependencies updated"
	@echo ""

# =========================================================================
# Python Targets (delegate to python/Makefile)
# =========================================================================

.PHONY: py-%
py-%: ready
	@$(MAKE) -C $(PYTHON_DIR) $*

# =========================================================================
# Rust Targets (delegate to crates/market/Makefile)
# =========================================================================

.PHONY: market-%
market-%:
	@$(MAKE) -C $(MARKET_DIR) $*

# =========================================================================
# Maturin Targets
# =========================================================================

.PHONY: maturin-dev
maturin-dev:
	@RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(MARKET_MANIFEST) $(MATURIN_FLAGS)

.PHONY: maturin-build
maturin-build:
	@RUSTFLAGS="$(RUSTFLAGS_PROD)" maturin build -m $(MARKET_MANIFEST) $(MATURIN_BUILD_FLAGS)

.PHONY: maturin-sdist
maturin-sdist:
	@maturin sdist -m $(MARKET_MANIFEST) $(MATURIN_SDIST_FLAGS)

# =========================================================================
# Combined Commands
# =========================================================================

.PHONY: dev
dev: setup sync
	@echo "✓ Development environment ready!"
	@echo ""

.PHONY: test
test: ready
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║                    Running Tests                               ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@$(MAKE) py-test
	@echo ""
	@echo "✓ All tests passed!"
	@echo ""

.PHONY: lint
lint: ready
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║                    Running Linters                             ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@$(MAKE) py-lint
	@echo "✓ All linters passed!"
	@echo ""

.PHONY: fmt
fmt: ready
	@echo "==> Formatting all code..."
	@$(MAKE) py-fmt
	@echo "✓ All code formatted"
	@echo ""

.PHONY: types
types: ready
	@echo "==> Running type checks..."
	@$(MAKE) py-types
	@printf '\033[1;32m✓ Type checking complete\033[0m\n'

.PHONY: validate
validate: ready
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║                  Full Validation Pipeline                      ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@$(MAKE) py-check-imports
	@$(MAKE) types
	@$(MAKE) test
	@echo ""
	@echo "✓ All validation checks passed!"
	@echo ""

.PHONY: cov-html
cov-html: ready
	@echo "==> Generating coverage reports..."
	@$(MAKE) py-cov-html
	@echo ""
	@echo "Coverage reports:"
	@echo "  Python: $(ROOT_DIR)/htmlcov/index.html"
	@echo ""

.PHONY: stubs
stubs:
	@echo "==> Generating Python stubs into ./types ..."
	@mkdir -p types
	@stubgen -p sec_nlp -o types >/dev/null
	@echo "✓ Stubs generated in ./types"

# =========================================================================
# Pre-commit
# =========================================================================

.PHONY: pre-commit
pre-commit: ready
	@echo "==> Running pre-commit checks..."
	@pre-commit run --all-files --show-diff-on-failure --color always
	@echo "✓ Pre-commit checks passed"
	@echo ""

# =========================================================================
# CI/CD
# =========================================================================

.PHONY: ci
ci: validate test

.PHONY: ci-quick
ci-quick: lint

# =========================================================================
# Cleanup
# =========================================================================

.PHONY: clean
clean:
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║                    Cleaning All Artifacts                      ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@$(MAKE) py-clean
	@rm -f $(STAMP_BOOTSTRAP) $(STAMP_UVSYNC)
	@echo "✓ All artifacts cleaned"
	@echo ""

.PHONY: nuclear-clean
nuclear-clean: clean
	@echo "==> Nuclear clean (removing .venv)..."
	@rm -rf .venv
	@$(MAKE) ready
	@echo "✓ Nuclear clean complete"
	@echo ""
