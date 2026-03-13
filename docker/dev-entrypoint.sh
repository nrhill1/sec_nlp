#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${SEC_NLP_WORKDIR:-/workspace}"
STAMP_DIR="${WORKDIR}/.cache/docker"
SYNC_STAMP="${STAMP_DIR}/uv-sync.stamp"
WHEEL_INSTALL_STAMP="${STAMP_DIR}/rust-wheels.stamp"
READY_MARKER="${STAMP_DIR}/container-ready"
VENV_PYTHON="${WORKDIR}/.venv/bin/python"
CONTAINER_ROLE="${SEC_NLP_CONTAINER_ROLE:-benchmark-runner}"
CONTAINER_LOG_DIR="${SEC_NLP_CONTAINER_LOG_DIR:-${WORKDIR}/logs/container/${CONTAINER_ROLE}}"
BOOTSTRAP_LOG="${CONTAINER_LOG_DIR}/bootstrap.log"
METADATA_FILE="${CONTAINER_LOG_DIR}/metadata.json"
PREBUILT_WHEEL_DIR="${SEC_NLP_PREBUILT_WHEEL_DIR:-/opt/sec-nlp/wheels}"
PREBUILT_WHEEL_MANIFEST="${PREBUILT_WHEEL_DIR}/manifest.txt"
STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

mkdir -p \
  "${STAMP_DIR}" \
  "${WORKDIR}/downloads" \
  "${WORKDIR}/logs" \
  "${WORKDIR}/outputs" \
  "${WORKDIR}/target" \
  "${WORKDIR}/.qdrant" \
  "${CONTAINER_LOG_DIR}"

rm -f "${READY_MARKER}"

exec > >(tee -a "${BOOTSTRAP_LOG}") 2>&1

cd "${WORKDIR}"

GIT_COMMIT="${SEC_NLP_CONTAINER_GIT_COMMIT:-unknown}"
if [[ "${GIT_COMMIT}" == "unknown" ]] && git rev-parse --short=12 HEAD >/dev/null 2>&1; then
  GIT_COMMIT="$(git rev-parse --short=12 HEAD)"
fi

cat > "${METADATA_FILE}" <<EOF
{
  "container_role": "${CONTAINER_ROLE}",
  "git_commit": "${GIT_COMMIT}",
  "started_at": "${STARTED_AT}",
  "bootstrap_log": "${BOOTSTRAP_LOG}",
  "prebuilt_wheel_manifest": "${PREBUILT_WHEEL_MANIFEST}",
  "workdir": "${WORKDIR}"
}
EOF

needs_sync=0
if [[ ! -x "${VENV_PYTHON}" ]] || [[ ! -f "${SYNC_STAMP}" ]]; then
  needs_sync=1
fi
if [[ -f pyproject.toml && pyproject.toml -nt "${SYNC_STAMP}" ]]; then
  needs_sync=1
fi
if [[ -f uv.lock && uv.lock -nt "${SYNC_STAMP}" ]]; then
  needs_sync=1
fi

if [[ "${needs_sync}" -eq 1 ]]; then
  echo "[sec-nlp-container] (${GIT_COMMIT}) syncing Python dependencies"
  uv sync --frozen
  touch "${SYNC_STAMP}"
fi

needs_rust_wheels=0
if [[ ! -f "${WHEEL_INSTALL_STAMP}" ]]; then
  needs_rust_wheels=1
fi

if [[ "${needs_sync}" -eq 1 ]]; then
  needs_rust_wheels=1
fi

if [[ ! -f "${PREBUILT_WHEEL_MANIFEST}" ]]; then
  echo "[sec-nlp-container] (${GIT_COMMIT}) missing prebuilt Rust wheel manifest at ${PREBUILT_WHEEL_MANIFEST}"
  exit 1
fi

if [[ "${needs_rust_wheels}" -eq 0 ]] && [[ "${PREBUILT_WHEEL_MANIFEST}" -nt "${WHEEL_INSTALL_STAMP}" ]]; then
  needs_rust_wheels=1
fi

if [[ "${needs_rust_wheels}" -eq 1 ]]; then
  mapfile -t prebuilt_wheels < <(find "${PREBUILT_WHEEL_DIR}" -maxdepth 1 -type f -name '*.whl' | sort)
  if [[ "${#prebuilt_wheels[@]}" -eq 0 ]]; then
    echo "[sec-nlp-container] (${GIT_COMMIT}) no prebuilt Rust wheels found under ${PREBUILT_WHEEL_DIR}"
    exit 1
  fi
  echo "[sec-nlp-container] (${GIT_COMMIT}) installing prebuilt Rust extensions"
  "${VENV_PYTHON}" -m pip install --no-deps --force-reinstall "${prebuilt_wheels[@]}"
  touch "${WHEEL_INSTALL_STAMP}"
fi

echo "[sec-nlp-container] (${GIT_COMMIT}) verifying extension imports"
"${VENV_PYTHON}" src/scripts/build/check_imports.py

touch "${READY_MARKER}"
echo "[sec-nlp-container] (${GIT_COMMIT}) ready"

exec "$@"
