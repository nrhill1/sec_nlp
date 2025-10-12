# Makefile
SHELL := /bin/bash
.DEFAULT_GOAL := test

# Paths & commands
LOG_DIR := src/sec_nlp/tests/test_logs
PYTEST := uv run pytest
COVERAGE := uv run coverage

# Pytest flags (isolated temp dirs; clear cache each run)
PYTEST_FLAGS := -v --maxfail=1 --tb=short --color=yes --basetemp .pytest_tmp --cache-clear

.PHONY: help install-dev create-log-dir test coverage coverage-report lint typecheck format clean ci

help:
	@echo "Targets:"
	@echo "  install-dev       Install dev deps via uv (pytest, coverage, mypy, autopep8)"
	@echo "  test              Run pytest; tee output to $(LOG_DIR)/test_<timestamp>.log"
	@echo "  coverage          Run coverage+pytest; tee to $(LOG_DIR)/coverage_<timestamp>.log"
	@echo "  coverage-report   Print coverage summary"
	@echo "  lint              PEP8 check (autopep8 --diff --exit-code)"
	@echo "  typecheck         Run mypy"
	@echo "  format            Apply autopep8 fixes in-place"
	@echo "  clean             Remove test artifacts and logs"
	@echo "  ci                Run lint, typecheck, tests (for local pre-push)"

install-dev:
	uv sync --dev

create-log-dir:
	@mkdir -p $(LOG_DIR)

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
	uv run autopep8 -r -i --max-line-length 100 .

clean:
	rm -rf .pytest_tmp .pytest_cache $(LOG_DIR) .coverage coverage.xml htmlcov

ci: lint typecheck test
