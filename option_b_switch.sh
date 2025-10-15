#!/usr/bin/env bash
set -euo pipefail

# Switch layout to: Python-first (src/sec_nlp), Rust as subcrate (crates/edga_rs)
# - Moves ./edga_rs -> ./crates/edga_rs
# - Ensures a root Cargo workspace with member "crates/edga_rs"
# - Keeps Python under ./src/sec_nlp (no move)
#
# Usage:
#   ./option_b_switch.sh           # interactive
#   ./option_b_switch.sh -y        # non-interactive
#   ./option_b_switch.sh --dry-run # print actions only
#
PROCEED="ask"
DRY_RUN="false"

for arg in "$@"; do
  case "$arg" in
    -y|--yes) PROCEED="yes" ;;
    --dry-run|-n) DRY_RUN="true" ;;
    -h|--help)
      sed -n '1,80p' "$0"
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

file_has() {
  local file="$1"
  local pattern="$2"
  [[ -f "$file" ]] && grep -Eq "$pattern" "$file"
}

ensure_dir() {
  local d="$1"
  if [[ ! -d "$d" ]]; then
    run "mkdir -p \"$d\""
  fi
}

# --- Git safeguard & backup ---
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ "$DRY_RUN" != "true" ]]; then
    if [[ -n "$(git status --porcelain)" ]]; then
      echo "Tip: Commit or stash first if you want a clean history."
      if ! confirm "Continue with uncommitted changes?"; then
        echo "Aborting."
        exit 1
      fi
    fi
    TS="$(date +"%Y%m%d-%H%M%S")"
    run "git branch backup/option-b-$TS >/dev/null 2>&1 || true"
  fi
else
  echo "Not in a git repo; continuing without git safeguards."
fi

# Tarball backup (exclude .backups to avoid recursion)
if [[ "$DRY_RUN" != "true" ]]; then
  TS="$(date +"%Y%m%d-%H%M%S")"
  ensure_dir ".backups"
  run "tar --exclude='./.backups' -czf .backups/repo-before-option-b-$TS.tgz ."
fi

# --- Step 1: Move Rust crate edga_rs -> crates/edga_rs ---
if [[ -d "edga_rs" ]]; then
  echo "Moving edga_rs -> crates/edga_rs"
  ensure_dir "crates"
  if confirm "Proceed moving Rust crate?"; then
    if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      # Prefer git mv for history
      run "git mv edga_rs crates/edga_rs || mv edga_rs crates/edga_rs"
    else
      run "mv edga_rs crates/edga_rs"
    fi
  fi
else
  echo "No ./edga_rs directory found. Skipping move."
fi

# --- Step 2: Ensure a workspace Cargo.toml at repo root ---
if [[ -f "Cargo.toml" ]]; then
  # If it's already a workspace, ensure member present
  if file_has "Cargo.toml" '^\[workspace\]'; then
    echo "Root Cargo.toml: [workspace] found. Ensuring member crates/edga_rs."
    # Add crates/edga_rs to members if missing
    if ! grep -q 'crates/edga_rs' Cargo.toml; then
      TMP="$(mktemp)"
      if [[ "$DRY_RUN" == "true" ]]; then
        echo "[dry-run] Would insert \"crates/edga_rs\" into workspace.members"
      else
        awk '
          BEGIN{in_ws=0;done=0}
          /^\[workspace\]/{in_ws=1}
          in_ws==1 && /^members\s*=\s*\[/ {
            print;
            print "  \"crates/edga_rs\",";
            in_ws=2; done=1; next
          }
          {print}
          END{
            if(!done){
              print ""
              print "[workspace]"
              print "members = [\"crates/edga_rs\"]"
              print "resolver = \"2\""
            }
          }
        ' Cargo.toml > "$TMP" && mv "$TMP" Cargo.toml
      fi
    fi
    # Ensure resolver = "2"
    if ! grep -Eq '^resolver\s*=\s*"2"' Cargo.toml; then
      if [[ "$DRY_RUN" == "true" ]]; then
        echo "[dry-run] Would append resolver = \"2\" under [workspace]"
      else
        printf '\n# Ensure new feature resolver\nresolver = "2"\n' >> Cargo.toml
      fi
    fi
  else
    # Root Cargo.toml exists but no [workspace]. Append a workspace section.
    echo "Root Cargo.toml: no [workspace] found. Appending one."
    if [[ "$DRY_RUN" == "true" ]]; then
      echo "[dry-run] Would append a [workspace] with member crates/edga_rs"
    else
      cat >> Cargo.toml <<'EOF'

[workspace]
members = ["crates/edga_rs"]
resolver = "2"
EOF
    fi
  fi
else
  # No root Cargo.toml. Create a minimal workspace.
  echo "No root Cargo.toml found. Creating a workspace Cargo.toml."
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[dry-run] Would create Cargo.toml with workspace pointing to crates/edga_rs"
  else
    cat > Cargo.toml <<'EOF'
[workspace]
members = ["crates/edga_rs"]
resolver = "2"
EOF
  fi
fi

# --- Step 3: Python stays primary under src/sec_nlp ---
# Validate that src/sec_nlp exists
if [[ -d "src/sec_nlp" ]]; then
  echo "Python package found at src/sec_nlp (as desired for Option B)."
else
  echo "Warning: src/sec_nlp not found. If your package lives elsewhere, adjust hooks/paths accordingly."
fi

# --- Step 4: Pre-commit YAML sanity for Python globs under src/ ---
if [[ -f ".pre-commit-config.yaml" ]]; then
  # Ensure Python globs still match src/*.py and src/sec_nlp/*.py
  # (No destructive changes; only broaden if needed.)
  if ! grep -Eq '^\s*files:\s*"\^src/.*\\\.py\$"' .pre-commit-config.yaml; then
    echo "Note: Your Python hooks may not target src/*.py. Review .pre-commit-config.yaml if needed."
  fi
  echo "Rust hooks are workspace-aware; no change needed."
fi

echo "Done. Next steps:"
echo "  1) uv sync --dev   # if you use uv"
echo "  2) cargo check     # verify Rust crate builds within workspace"
echo "  3) pre-commit run --all-files"
