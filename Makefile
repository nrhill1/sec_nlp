# Makefile
SHELL := /bin/bash
.DEFAULT_GOAL := test

LOG_DIR := test_logs
PYTEST := uv run pytest
COVERAGE := uv run coverage

PYTEST_FLAGS := -v --maxfail=1 --tb=short --color=yes --basetemp .pytest_tmp --cache-clear

.PHONY: help install-dev test coverage coverage-report clean create-log-dir

help:
	@echo "Targets:"
	@echo "  install-dev       Install dev deps (pytest, coverage) via uv"
	@echo "  test              Run pytest and tee output to test_logs/test_<timestamp>.log"
	@echo "  coverage          Run coverage + pytest and tee to test_logs/coverage_<timestamp>.log"
	@echo "  coverage-report   Show coverage summary"
	@echo "  clean             Remove .pytest_tmp, .pytest_cache, and test_logs"

install-dev:
	uv sync --dev

create-log-dir:
	@mkdir -p $(LOG_DIR)

test: create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/test_$${ts}.log"; \
	echo "Writing test log to $$log"; \
	bash -o pipefail -c '$(PYTEST) $(PYTEST_FLAGS) | tee "$$log"'

coverage: create-log-dir
	@ts=$$(date +"%Y-%m-%dT%H-%M-%S"); \
	log="$(LOG_DIR)/coverage_$${ts}.log"; \
	echo "Writing coverage log to $$log"; \
	bash -o pipefail -c '$(COVERAGE) run -m pytest -q --basetemp .pytest_tmp --cache-clear | tee "$$log"'

coverage-report:
	$(COVERAGE) report -m

clean:
	rm -rf .pytest_tmp .pytest_cache $(LOG_DIR)


.PHONY: lint typecheck format

install-dev:
	uv sync --dev

lint:
	uv run autopep8 -r --diff --exit-code .

typecheck:  ## Mypy type checking
	uv run mypy .

format:  ## Apply PEP8 fixes in-place
	uv run autopep8 -r -i .
