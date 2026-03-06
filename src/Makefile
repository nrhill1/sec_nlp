SHELL := /bin/bash
.DEFAULT_GOAL := help

# =========================================================================
# Variables
# =========================================================================

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
REPO_ROOT := $(shell cd $(ROOT_DIR)/.. && pwd)

PYTHON_DIR := $(ROOT_DIR)
TEST_DIR := $(REPO_ROOT)/tests
TEST_LOG_DIR := $(TEST_DIR)/test_logs
STUBS_DIR := $(REPO_ROOT)/types
PROFILE_DIR := $(REPO_ROOT)/profiling
PY_SCRIPTS_DIR := $(REPO_ROOT)/src/scripts

PYTEST_FLAGS := -q --color=yes --basetemp $(REPO_ROOT)/.pytest_tmp
STUBGEN_FLAGS := \
	$(PYTHON_DIR)/sec_nlp \
	$(TEST_DIR) \
	-o $(STUBS_DIR) \
	--include-private \
	--exclude market \
	--exclude sec_nlp/core/market.py \
	--exclude sec_nlp/cli/commands/market.py

# =========================================================================
# Help
# =========================================================================

.PHONY: help
help:
	@echo "Python Development Commands"
	@echo ""
	@echo "Development:"
	@echo "  fmt                Format Python code"
	@echo "  lint               Run ruff check with fixes"
	@echo "  stubs              Generate type stubs"
	@echo "  types              Run ty type checking"
	@echo "  fix                Auto-fix all issues"
	@echo ""
	@echo "Testing:"
	@echo "  test               Run Python tests"
	@echo "  test-comparison    Run downloader comparison tests"
	@echo "  test-benchmarks    Run performance benchmarks"
	@echo ""
	@echo "Coverage:"
	@echo "  cov                Run tests with coverage"
	@echo "  cov-html           Generate HTML coverage report"
	@echo "  cov-report         Show coverage report"
	@echo "  cov-check          Check coverage meets 80% threshold"
	@echo ""
	@echo "Profiling:"
	@echo "  profile            Profile pipeline execution"
	@echo "  profile-breakdown  Profile component breakdown"
	@echo "  profile-memory     Profile memory usage"
	@echo "  profile-verbose    Profile with verbose output"
	@echo ""
	@echo "Import Checking:"
	@echo "  check-imports      Check Python imports (including Rust extension)"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean              Clean Python artifacts"

# =========================================================================
# Development
# =========================================================================

.PHONY: fmt
fmt:
	@echo "==> Ruff format..."
	@cd $(REPO_ROOT) && uv run ruff format .
	@echo "✓ Formatting complete"
	@echo ""

.PHONY: lint
lint: fmt
	@echo "==> Ruff check..."
	@cd $(REPO_ROOT) && uv run ruff check . --fix
	@echo "✓ Linting complete"
	@echo ""

.PHONY: stubs
stubs:
	@echo "==> Generating stubs for src + tests into $(STUBS_DIR)..."
	@# Generate Python code stubs
	@mkdir -p $(STUBS_DIR)
	@cd $(REPO_ROOT) && uv run stubgen $(STUBGEN_FLAGS)
	@find $(STUBS_DIR) -type f -name "__init__.pyi"
	@cd $(REPO_ROOT) && uv run ruff check $(STUBS_DIR) --fix --quiet && \
	uv run ruff check $(STUBS_DIR) --select I --fix --quiet && \
	uv run ruff format $(STUBS_DIR)
	@echo "✓ Stubs generated"
	@echo ""

.PHONY: types
types:
	@echo "==> Ty type check (src + tests)..."
	@echo ""
	@cd $(REPO_ROOT) && \
		set -o pipefail; \
		uv run ty check src tests --output-format github --no-progress --color=never 2>&1 | \
		{ grep -E '^::(error|warning|notice|info)' || true; } | \
		uv run python $(PY_SCRIPTS_DIR)/format_ty_output.py

.PHONY: fix
fix: lint
	@echo "✓ Python fixes applied"
	@echo ""

# =========================================================================
# Testing
# =========================================================================

.PHONY: test
test:
	@mkdir -p $(TEST_LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(TEST_LOG_DIR)/test_$${ts}.log"; \
	echo "==> Running Python tests (log: $$log)..."; \
	set -o pipefail; \
	cd $(REPO_ROOT) && uv run pytest $(PYTEST_FLAGS) 2>&1 | tee "$$log"

.PHONY: test-comparison
test-comparison:
	@echo "==> Running downloader comparison tests..."
	@cd $(REPO_ROOT) && uv run pytest $(TEST_DIR)/core/test_downloader_comparison.py -v

.PHONY: test-benchmarks
test-benchmarks:
	@echo "==> Running performance benchmarks..."
	@cd $(REPO_ROOT) && uv run pytest $(TEST_DIR)/benchmarks/test_downloader_benchmarks.py -v -s

# =========================================================================
# Coverage
# =========================================================================

.PHONY: cov
cov:
	@mkdir -p $(TEST_LOG_DIR)
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(TEST_LOG_DIR)/coverage_$${ts}.log"; \
	echo "==> Running coverage (log: $$log)..."; \
	set -o pipefail; \
	cd $(REPO_ROOT) && uv run coverage run -m pytest -q --basetemp .pytest_tmp --cache-clear 2>&1 | tee "$$log"

.PHONY: cov-html
cov-html: cov
	@echo "==> Generating HTML coverage report..."
	@cd $(REPO_ROOT) && uv run coverage html
	@echo "==> Python coverage report: htmlcov/index.html"
	@echo ""

.PHONY: cov-report
cov-report:
	@cd $(REPO_ROOT) && uv run coverage report -m

.PHONY: cov-check
cov-check: cov
	@echo "==> Checking coverage threshold (80%)..."
	@cd $(REPO_ROOT) && uv run coverage report --fail-under=80
	@echo "✓ Coverage threshold check complete"
	@echo ""

# =========================================================================
# Profiling
# =========================================================================

.PHONY: profile
profile:
	@mkdir -p $(PROFILE_DIR)
	@echo "==> Running pipeline profiler..."
	@cd $(REPO_ROOT) && uv run python $(PY_SCRIPTS_DIR)/profile/run.py --output_dir $(PROFILE_DIR)
	@echo "✓ Pipeline profile complete"
	@echo ""

.PHONY: profile-breakdown
profile-breakdown:
	@echo "==> Running component breakdown profiler..."
	@cd $(REPO_ROOT) && uv run python $(PY_SCRIPTS_DIR)/profile/run.py --breakdown
	@echo "✓ Profile breakdown complete"
	@echo ""

.PHONY: profile-memory
profile-memory:
	@echo "==> Running memory profiler..."
	@cd $(REPO_ROOT) && uv run python $(PY_SCRIPTS_DIR)/profile/run_memory.py
	@echo "✓ Memory profiler complete"
	@echo ""

.PHONY: profile-verbose
profile-verbose:
	@mkdir -p $(PROFILE_DIR)
	@echo "==> Running profiler (verbose)..."
	@cd $(REPO_ROOT) && uv run python $(PY_SCRIPTS_DIR)/profile/run.py --verbose --log-level DEBUG --output-dir $(PROFILE_DIR)
	@echo "✓ Profiler (verbose) complete"
	@echo ""

# =========================================================================
# Import Checking
# =========================================================================

.PHONY: check-imports
check-imports:
	@echo "==> Checking Python imports (including Rust extension)..."
	@cd $(REPO_ROOT) && uv run python $(PY_SCRIPTS_DIR)/build/check_imports.py
	@echo "✓ Import checks complete"
	@echo ""

.PHONY: check-imports-verbose
check-imports-verbose:
	@echo "==> Checking Python imports (verbose)..."
	@cd $(REPO_ROOT) && uv run python $(PY_SCRIPTS_DIR)/build/check_imports.py --verbose
	@echo "✓ Import checks (verbose) complete"
	@echo ""

.PHONY: check-imports-no-rust
check-imports-no-rust:
	@echo "==> Checking Python imports (skipping Rust check)..."
	@cd $(REPO_ROOT) && uv run python $(PY_SCRIPTS_DIR)/build/check_imports.py --no-check-rust
	@echo "✓ Import checks (sans Rust) complete"
	@echo ""

# =========================================================================
# Cleanup
# =========================================================================

.PHONY: clean
clean:
	@echo "==> Cleaning Python artifacts..."
	@rm -rf $(REPO_ROOT)/.pytest_tmp $(REPO_ROOT)/.pytest_cache
	@find $(REPO_ROOT) -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find $(REPO_ROOT) -type f -name "*.pyc" -delete 2>/dev/null || true
	@find $(REPO_ROOT) -type f -name "*~" -delete 2>/dev/null || true
	@find $(REPO_ROOT) -type f -name ".*~" -delete 2>/dev/null || true
	@cd $(REPO_ROOT) && uv cache clean
	@rm -rf $(PROFILE_DIR)
	@rm -rf $(REPO_ROOT)/.ruff_cache $(REPO_ROOT)/htmlcov $(REPO_ROOT)/.coverage
	@if [ -d $(STUBS_DIR) ]; then \
		find $(STUBS_DIR) -mindepth 1 -maxdepth 1 ! -name "market" -exec rm -rf {} +; \
	fi
	@echo "✓ Python artifacts cleaned"
	@echo ""
