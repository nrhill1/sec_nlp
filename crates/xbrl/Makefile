SHELL := /bin/bash
.DEFAULT_GOAL := help

# =========================================================================
# Variables
# =========================================================================

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
REPO_ROOT := $(shell cd $(ROOT_DIR)/../.. && pwd)
CARGO_MANIFEST := $(ROOT_DIR)/Cargo.toml
ifneq ("$(wildcard $(REPO_ROOT)/.env)","")
	include $(REPO_ROOT)/.env
	export
endif
ifeq ("$(wildcard $(REPO_ROOT)/.venv/bin/python)","")
PYTHON_SYS_EXECUTABLE ?= $(shell if command -v python3.13 >/dev/null 2>&1; then python3.13 -c 'import sys; print(sys.executable)'; else python3 -c 'import sys; print(sys.executable)'; fi)
else
PYTHON_SYS_EXECUTABLE ?= $(REPO_ROOT)/.venv/bin/python
endif
PYO3_PYTHON ?= $(PYTHON_SYS_EXECUTABLE)
MATURIN_FLAGS ?=
MATURIN_BUILD_FLAGS ?= --release --uv
RUSTFLAGS_DEV ?=
RUSTFLAGS_PROD ?=

# =========================================================================
# Help
# =========================================================================

.PHONY: help
help:
	@echo "xbrl (Rust + pyo3) Commands"
	@echo ""
	@echo "Development:"
	@echo "  dev            Build and install into current Python environment"
	@echo "  build          Build wheels (release by default)"
	@echo "  fmt            Format Rust code"
	@echo "  clippy         Lint with clippy"
	@echo ""
	@echo "Testing:"
	@echo "  test           Run cargo test"
	@echo ""
	@echo "Cleanup:"
	@echo "  clean          Remove Rust build artifacts"
	@echo "  clean-all      Remove Rust artifacts + maturin outputs + sccache"
	@echo "  clean-sccache  Clear sccache cache (if installed)"

# =========================================================================
# Development
# =========================================================================

.PHONY: dev
dev:
	@cd $(REPO_ROOT) && RUSTFLAGS="$(RUSTFLAGS_DEV)" maturin develop -m $(CARGO_MANIFEST) $(MATURIN_FLAGS)

.PHONY: build
build:
	@cd $(REPO_ROOT) && RUSTFLAGS="$(RUSTFLAGS_PROD)" maturin build -m $(CARGO_MANIFEST) $(MATURIN_BUILD_FLAGS)

.PHONY: fmt
fmt:
	@cargo fmt --manifest-path $(CARGO_MANIFEST)

.PHONY: clippy
clippy:
	@cargo clippy --manifest-path $(CARGO_MANIFEST) --all-targets --all-features -- -D warnings

# =========================================================================
# Testing
# =========================================================================

.PHONY: test
test:
	@PYTHON_SYS_EXECUTABLE=$(PYTHON_SYS_EXECUTABLE) \
	PYTHONHOME=$$($(PYTHON_SYS_EXECUTABLE) -c 'import sys; print(getattr(sys, "base_prefix", sys.prefix))') \
	PYO3_PYTHON=$(PYO3_PYTHON) \
	cargo test --manifest-path $(CARGO_MANIFEST)

# =========================================================================
# Cleanup
# =========================================================================

.PHONY: clean
clean:
	@cargo clean --manifest-path $(CARGO_MANIFEST)

.PHONY: clean-sccache
clean-sccache:
	@if command -v sccache >/dev/null 2>&1; then \
		echo "==> Clearing sccache..."; \
		sccache --stop-server >/dev/null 2>&1 || true; \
		sccache --clear || true; \
	else \
		echo "sccache not installed; skipping"; \
	fi

.PHONY: clean-all
clean-all: clean
	@echo "==> Removing maturin build artifacts..."
	@rm -rf $(REPO_ROOT)/target/wheels $(REPO_ROOT)/target/sdist $(REPO_ROOT)/dist $(REPO_ROOT)/.maturin
	@$(MAKE) clean-sccache
	@echo "✓ Rust artifacts cleaned"
