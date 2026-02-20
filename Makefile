.ONESHELL:
SHELL := /bin/bash
.DEFAULT_GOAL := help
BRANCH := $(shell git rev-parse --abbrev-ref HEAD)

# =========================================================================
# Variables
# =========================================================================

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

# Caching
# Default: no rustc wrapper. Opt in with:
#   RUSTC_WRAPPER=sccache make <target>
export RUSTC_WRAPPER ?=

# Nested Makefile directories
PYTHON_DIR := $(ROOT_DIR)/src
RUST_DIR := $(ROOT_DIR)/crates/market
MARKET_MANIFEST := $(RUST_DIR)/Cargo.toml
EFTS_DIR := $(ROOT_DIR)/crates/efts
EFTS_MANIFEST := $(EFTS_DIR)/Cargo.toml
CORR_DIR := $(ROOT_DIR)/crates/corr
CORR_MANIFEST := $(CORR_DIR)/Cargo.toml
XBRL_DIR := $(ROOT_DIR)/crates/xbrl
XBRL_MANIFEST := $(XBRL_DIR)/Cargo.toml
ENTITY_DIR := $(ROOT_DIR)/crates/entity
ENTITY_MANIFEST := $(ENTITY_DIR)/Cargo.toml
NEWSWATCH_DIR := $(ROOT_DIR)/crates/newswatch
NEWSWATCH_MANIFEST := $(NEWSWATCH_DIR)/Cargo.toml

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
	@echo "  rs-m-<target>          Run Rust target for market (e.g., rs-m-dev)"
	@echo "  rs-sg-<target>         Run Rust target for efts (e.g., rs-sg-dev)"
	@echo "  rs-corr-<target>       Run Rust target for corr (e.g., rs-corr-dev)"
	@echo "  rs-xbrl-<target>       Run Rust target for xbrl (e.g., rs-xbrl-dev)"
	@echo "  rs-ent-<target>        Run Rust target for entity (e.g., rs-ent-dev)"
	@echo "  rs-nw-<target>         Run Rust target for newswatch (e.g., rs-nw-dev)"
	@echo "  rs-clean               Clean Rust build artifacts"
	@echo "  rs-clean-all           Clean Rust artifacts + sccache"
	@echo "  rs-clean-sccache       Clear sccache cache"
	@echo "  maturin-dev            Build + install Rust extension via maturin"
	@echo "  maturin-build          Build release wheels via maturin"
	@echo "  maturin-sdist          Build a source distribution via maturin"
	@echo "  build-ext              Build + install Rust extensions (market + efts + corr + xbrl + entity + newswatch)"
	@echo ""
	@echo "For detailed help on each subsystem, run:"
	@echo "  make -C src help       # Python commands"
	@echo "  make -C crates/market help  # Market (Rust) commands"
	@echo "  make -C crates/efts help  # efts (Rust) commands"
	@echo "  make -C crates/corr help  # corr (Rust) commands"
	@echo "  make -C crates/xbrl help  # xbrl (Rust) commands"
	@echo "  make -C crates/entity help  # entity (Rust) commands"
	@echo "  make -C crates/newswatch help  # newswatch (Rust) commands"
	@echo ""
	@echo "CI/CD:"
	@echo "  ci                     Full CI pipeline"
	@echo "  ci-quick               Quick CI check (lint only)"
	@echo ""
	@echo "Advanced:"
	@echo "  validate               Full validation (imports + types + tests)"
	@echo "  cov-html               Generate coverage reports"
	@echo "  perf-bench             Run chat/retrieve performance suite"
	@echo "  perf-bench-fast        Run one-pass chat/retrieve perf suite"
	@echo "  perf-smoke             Run minimal perf smoke pair"
	@echo "  perf-gate-smoke        Run perf smoke and enforce SLO gate"
	@echo "  perf-compare           Compare latest two performance suite artifacts"
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

.PHONY: rs-m-%
rs-m-%:
	@$(MAKE) -C $(RUST_DIR) $*

.PHONY: rs-sg-%
rs-sg-%:
	@$(MAKE) -C $(EFTS_DIR) $*

.PHONY: rs-corr-%
rs-corr-%:
	@$(MAKE) -C $(CORR_DIR) $*

.PHONY: rs-xbrl-%
rs-xbrl-%:
	@$(MAKE) -C $(XBRL_DIR) $*

.PHONY: rs-ent-%
rs-ent-%:
	@$(MAKE) -C $(ENTITY_DIR) $*

.PHONY: rs-nw-%
rs-nw-%:
	@$(MAKE) -C $(NEWSWATCH_DIR) $*

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

.PHONY: build-ext
build-ext: ready
	@echo "==> Building Rust extensions..."
	@RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(MARKET_MANIFEST) $(MATURIN_FLAGS)
	@RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(EFTS_MANIFEST) $(MATURIN_FLAGS)
	@RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(CORR_MANIFEST) $(MATURIN_FLAGS)
	@RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(XBRL_MANIFEST) $(MATURIN_FLAGS)
	@RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(ENTITY_MANIFEST) $(MATURIN_FLAGS)
	@RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(NEWSWATCH_MANIFEST) $(MATURIN_FLAGS)
	@echo "✓ Rust extensions built"
	@echo ""

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
	@$(MAKE) build-ext
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

.PHONY: verify-py
verify-py: ready
	@$(MAKE) build-ext
	@$(MAKE) py-lint
	@$(MAKE) py-types
	@$(MAKE) py-test

.PHONY: verify-rs
verify-rs: ready
	@$(MAKE) rs-m-test
	@$(MAKE) rs-sg-test
	@$(MAKE) rs-corr-test
	@$(MAKE) rs-xbrl-test
	@$(MAKE) rs-ent-test
	@$(MAKE) rs-nw-test

.PHONY: verify-all
verify-all: ready
	@$(MAKE) verify-py
	@$(MAKE) verify-rs

.PHONY: perf-bench
perf-bench: ready
	@echo "==> Running performance suite..."
	@uv run python src/scripts/profile/perf_suite.py --mode run

.PHONY: perf-bench-fast
perf-bench-fast: ready
	@echo "==> Running one-pass performance suite..."
	@uv run python src/scripts/profile/perf_suite.py --mode run --repeats 1 --chat_model_name "llama3.2:1b" --chat_max_new_tokens 192

.PHONY: perf-smoke
perf-smoke: ready
	@echo "==> Running perf smoke (retrieve/chat mining top_k=40)..."
	@uv run python src/scripts/profile/perf_suite.py --mode run --repeats 1 --chat_model_name "llama3.2:1b" --chat_max_new_tokens 192 --include_cases '["retrieve_mining_topk40","chat_mining_topk40"]'

.PHONY: perf-gate-smoke
perf-gate-smoke: ready
	@echo "==> Running perf smoke with SLO gate..."
	@uv run python src/scripts/profile/perf_suite.py --mode run --repeats 1 --enforce_slo --chat_model_name "llama3.2:1b" --chat_max_new_tokens 192 --include_cases '["retrieve_mining_topk40","chat_mining_topk40"]'

.PHONY: perf-compare
perf-compare: ready
	@echo "==> Comparing performance suite artifacts..."
	@uv run python src/scripts/profile/perf_suite.py --mode compare

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
	@$(MAKE) build-ext
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
	@$(MAKE) rs-clean
	@rm -f $(STAMP_BOOTSTRAP) $(STAMP_UVSYNC)
	@echo "✓ All artifacts cleaned"
	@echo ""

.PHONY: rs-clean
rs-clean:
	@$(MAKE) -C $(RUST_DIR) clean

.PHONY: rs-clean-all
rs-clean-all:
	@$(MAKE) -C $(RUST_DIR) clean-all

.PHONY: rs-clean-sccache
rs-clean-sccache:
	@$(MAKE) -C $(RUST_DIR) clean-sccache


.PHONY: nuclear-clean
nuclear-clean: clean
	@echo "==> Nuclear clean (removing .venv)..."
	@rm -rf .venv
	@$(MAKE) ready
	@echo "✓ Nuclear clean complete"
	@echo ""
