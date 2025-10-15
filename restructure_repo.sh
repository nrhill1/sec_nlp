#!/usr/bin/env bash
set -euo pipefail

# Restructure a combined Python+Rust repo by:
#   1) Moving Python package from src/sec_nlp -> sec_nlp/
#   2) Updating pyproject.toml, pre-commit config, Makefile paths, and mypy/pytest settings
#   3) (Optional) Moving Rust crate "edga_rs" to crates/edga_rs and setting up a Cargo workspace
# Usage:
#   ./restructure_repo.sh              # interactive (will prompt before changes)
#   ./restructure_repo.sh -y           # non-interactive, proceed
#   ./restructure_repo.sh --dry-run    # print actions only
#
# Idempotent(ish): safe to re-run; will skip steps that are already applied.
#
# Notes:
# - Assumes current working directory is the repo root shown in the screenshot.
# - Creates a backup branch and a tarball before making changes.
#
PROCEED="ask"
DRY_RUN="false"

for arg in "$@"; do
  case "$arg" in
    -y|--yes) PROCEED="yes" ;;
    --dry-run|-n) DRY_RUN="true" ;;
    -h|--help)
      sed -n '1,60p' "$0"
      exit 0
      ;;
  esac
done

run() {
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] $*"
  else
    echo "+ $*"
    eval "$@"
  fi
}

confirm() {
  if [[ "$PROCEED" == "yes" ]]; then
    return 0
  fi
  read -r -p "$1 [y/N]: " ans
  [[ "${ans:-N}" =~ ^[Yy]$ ]]
}

# --- helpers ---
# Cross-platform sed -i (BSD/mac vs GNU)
do_sed() {
  local expr="$1"
  local file="$2"
  if sed --version >/dev/null 2>&1; then
    run "sed -i -E \"$expr\" \"$file\""
  else
    run "sed -i '' -E \"$expr\" \"$file\""
  fi
}

ensure_dir() {
  local d="$1"
  if [[ ! -d "$d" ]]; then
    run "mkdir -p \"$d\""
  fi
}

file_has() {
  local file="$1"
  local pattern="$2"
  [[ -f "$file" ]] && grep -Eq "$pattern" "$file"
}

# --- sanity checks ---
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ "$DRY_RUN" != "true" ]]; then
    if [[ -n "$(git status --porcelain)" ]]; then
      echo "Warning: you have uncommitted changes."
      if ! confirm "Continue anyway?"; then
        echo "Aborting."
        exit 1
      fi
    fi
    TS="$(date +"%Y%m%d-%H%M%S")"
    run "git branch backup/restructure-$TS >/dev/null 2>&1 || true"
  fi
else
  echo "Not in a git repo; continuing without git safeguards."
fi

# Create a tarball backup
if [[ "$DRY_RUN" != "true" ]]; then
  TS="$(date +"%Y%m%d-%H%M%S")"
  ensure_dir ".backups"
  run "tar --exclude='./.backups' -czf .backups/repo-before-restructure-$TS.tgz ."
fi

# --- Step 1: Move Python package from src/sec_nlp -> sec_nlp/ ---
if [[ -d "src/sec_nlp" ]]; then
  echo "Found Python package at src/sec_nlp"
  if confirm "Move src/sec_nlp -> sec_nlp/?"; then
    ensure_dir "sec_nlp"
    run "rsync -a --remove-source-files src/sec_nlp/ sec_nlp/"
    # Clean up empty dirs
    run "find src -type d -empty -delete || true"
  fi
else
  echo "No src/sec_nlp directory; assuming already moved."
fi

# --- Step 2: Update pyproject.toml and configs ---
if [[ -f "pyproject.toml" ]]; then
  echo "Updating pyproject.toml"
  # Change uv_build src-dir from "src" to "." if present
  if file_has "pyproject.toml" '^\s*src-dir\s*=\s*"src"'; then
    do_sed 's/^\s*src-dir\s*=\s*"src"/src-dir = "."/' "pyproject.toml"
  fi
  # pytest testpaths -> ["sec_nlp/tests"]
  if file_has "pyproject.toml" '\[tool.pytest.ini_options\]'; then
    do_sed 's#(^\s*testpaths\s*=\s*)\[[^]]*\]#\1\["sec_nlp/tests"\]#' "pyproject.toml"
  fi
  # mypy exclude: ^src/sec_nlp/tests/.* -> ^sec_nlp/tests/.*
  do_sed 's#\^src/sec_nlp/tests/\\.\\*#^sec_nlp/tests/.*#' "pyproject.toml"
  # Ruff/mypy "files" globs are in .pre-commit-config.yaml; not here.
fi

# --- Step 3: Update .pre-commit-config.yaml globs ---
if [[ -f ".pre-commit-config.yaml" ]]; then
  echo "Updating .pre-commit-config.yaml"
  # Replace '^src/.*\.py$' with '^(sec_nlp|tests)/.*\.py$'
  do_sed 's#\^src/\\.\\*\\\.py\\$#^(sec_nlp|tests)/.*\\.py$#' ".pre-commit-config.yaml"
  # For autopep8 hook limited to "^src/sec_nlp/.*\.py$", broaden to "^(sec_nlp|tests)/.*\.py$"
  do_sed 's#\^src/sec_nlp/\\.\\*\\\.py\\$#^(sec_nlp|tests)/.*\\.py$#' ".pre-commit-config.yaml"
fi

# --- Step 4: Update Makefile paths ---
if [[ -f "Makefile" ]]; then
  echo "Updating Makefile LOG_DIR and path globs"
  do_sed 's#^LOG_DIR\s*:=\s*src/sec_nlp/tests/test_logs#LOG_DIR := sec_nlp/tests/test_logs#' "Makefile"
fi

# --- Step 5: Clean up empty top-level src if it only contained Python ---
if [[ -d "src" ]]; then
  # If src is empty, remove it
  if [[ -z "$(ls -A src)" ]]; then
    echo "Removing empty src/ directory"
    run "rmdir src"
  else
    echo "Keeping src/ (not empty)."
  fi
fi

# --- Step 6 (optional): Move Rust crate edga_rs to crates/edga_rs and create workspace ---
RUST_SRC_DIR="edga_rs"
if [[ -d "$RUST_SRC_DIR" ]]; then
  echo "Detected Rust crate at $RUST_SRC_DIR/"
  if confirm "Move $RUST_SRC_DIR -> crates/edga_rs and setup a Cargo workspace?"; then
    ensure_dir "crates"
    if [[ ! -d "crates/edga_rs" ]]; then
      run "git mv \"$RUST_SRC_DIR\" crates/edga_rs || mv \"$RUST_SRC_DIR\" crates/edga_rs"
    fi
    # Ensure a workspace Cargo.toml at repo root
    if [[ -f "Cargo.toml" ]]; then
      # If it's not already a workspace, append one
      if ! file_has "Cargo.toml" '^\[workspace\]'; then
        echo "Adding [workspace] to Cargo.toml"
        if [[ "$DRY_RUN" == "true" ]]; then
          echo "[dry-run] Would append workspace members to Cargo.toml"
        else
          cat >> Cargo.toml <<'EOF'

[workspace]
members = ["crates/edga_rs"]
resolver = "2"
EOF
        fi
      else
        # Ensure member exists
        if ! grep -q 'crates/edga_rs' Cargo.toml; then
          echo "Adding crates/edga_rs to workspace members"
          TMPFILE="$(mktemp)"
          if [[ "$DRY_RUN" == "true" ]]; then
            echo "[dry-run] Would insert crates/edga_rs into Cargo.toml workspace.members"
          else
            awk '
              BEGIN{in_ws=0}
              /^\[workspace\]/{in_ws=1}
              in_ws==1 && /^members\s*=\s*\[/ {print; print "  \"crates/edga_rs\","; in_ws=2; next}
              {print}
            ' Cargo.toml > "$TMPFILE" && mv "$TMPFILE" Cargo.toml
          fi
        fi
      fi
    else
      echo "No root Cargo.toml found; skipping workspace setup."
    fi
  fi
else
  echo "No top-level edga_rs crate found; skipping Rust move."
fi

echo "Done. Suggested follow-ups:"
echo "  - Run: uv sync --dev"
echo "  - Run: pre-commit run --all-files"
echo "  - Run: make ci"
