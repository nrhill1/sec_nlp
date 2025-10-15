#!/usr/bin/env bash
set -euo pipefail

# Option B (fast): Python-first, Rust as subcrate.
# - Moves ./edga_rs or ./src/edga_rs -> ./crates/edga_rs
# - Ensures root Cargo.toml is a workspace with member "crates/edga_rs"
# - NO TARBALL BACKUP (fast)
#
# Usage:
#   ./option_b_switch_fast.sh -y      # non-interactive
#   ./option_b_switch_fast.sh         # interactive
#   bash -x ./option_b_switch_fast.sh -y  # verbose
#
PROCEED="ask"

for arg in "$@"; do
  case "$arg" in
    -y|--yes) PROCEED="yes" ;;
    -h|--help)
      sed -n '1,80p' "$0"
      exit 0
      ;;
  esac
done

run() {
  echo "+ $*"
  eval "$@"
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

# --- Git safeguard (no backup tar, just a branch) ---
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Tip: Commit or stash first if you want a clean history."
    if ! confirm "Continue with uncommitted changes?"; then
      echo "Aborting."
      exit 1
    fi
  fi
  TS="$(date +"%Y%m%d-%H%M%S")"
  run "git branch backup/option-b-fast-$TS >/dev/null 2>&1 || true"
else
  echo "Not in a git repo; continuing without git safeguards."
fi

# --- Step 1: Move Rust crate to crates/edga_rs ---
SOURCE_DIR=""
if [[ -d "edga_rs" ]]; then
  SOURCE_DIR="edga_rs"
elif [[ -d "src/edga_rs" ]]; then
  SOURCE_DIR="src/edga_rs"
fi

if [[ -n "$SOURCE_DIR" ]]; then
  echo "Will move \"$SOURCE_DIR\" -> \"crates/edga_rs\""
  ensure_dir "crates"
  if confirm "Proceed moving Rust crate?"; then
    if command -v git >/dev/null 2>&1 && git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
      run "git mv \"$SOURCE_DIR\" crates/edga_rs || mv \"$SOURCE_DIR\" crates/edga_rs"
    else
      run "mv \"$SOURCE_DIR\" crates/edga_rs"
    fi
  fi
else
  echo "No Rust crate found at ./edga_rs or ./src/edga_rs. Skipping move."
fi

# --- Step 2: Ensure a workspace Cargo.toml at repo root ---
if [[ -f "Cargo.toml" ]]; then
  if file_has "Cargo.toml" '^\[workspace\]'; then
    echo "Root Cargo.toml: [workspace] found. Ensuring member crates/edga_rs and resolver=2."
    if ! grep -q 'crates/edga_rs' Cargo.toml; then
      TMP="$(mktemp)"
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
    if ! grep -Eq '^resolver\s*=\s*"2"' Cargo.toml; then
      printf '\nresolver = "2"\n' >> Cargo.toml
    fi
  else
    cat >> Cargo.toml <<'EOF'

[workspace]
members = ["crates/edga_rs"]
resolver = "2"
EOF
  fi
else
  cat > Cargo.toml <<'EOF'
[workspace]
members = ["crates/edga_rs"]
resolver = "2"
EOF
fi

# --- Step 3: Python stays under src/sec_nlp ---
if [[ -d "src/sec_nlp" ]]; then
  echo "Python package confirmed at src/sec_nlp."
else
  echo "Note: src/sec_nlp not found. Adjust your Python paths if your layout is different."
fi

echo "Done. Suggested next commands:"
echo "  cargo check"
echo "  pre-commit run --all-files || true"
echo "  git add -A && git commit -m \"Option B fast: move Rust crate and set workspace\" --no-verify"
