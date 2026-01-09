SHELL := /bin/bash
.DEFAULT_GOAL := help

# =========================================================================
# Variables
# =========================================================================

ROOT_DIR := $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
CARGO_MANIFEST := $(ROOT_DIR)/Cargo.toml
MATURIN_FLAGS ?=
MATURIN_BUILD_FLAGS ?= --release

# =========================================================================
# Help
# =========================================================================

.PHONY: help
help:
	@echo "Market (Rust + pyo3) Commands"
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

# =========================================================================
# Development
# =========================================================================

.PHONY: dev
dev:
	@maturin develop -m $(CARGO_MANIFEST) $(MATURIN_FLAGS)

.PHONY: build
build:
	@maturin build -m $(CARGO_MANIFEST) $(MATURIN_BUILD_FLAGS)

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
	@cargo test --manifest-path $(CARGO_MANIFEST)

# =========================================================================
# Cleanup
# =========================================================================

.PHONY: clean
clean:
	@cargo clean --manifest-path $(CARGO_MANIFEST)
