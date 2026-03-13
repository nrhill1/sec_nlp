#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${SEC_NLP_WORKDIR:-/workspace}"
STAMP_DIR="${WORKDIR}/.cache/docker"
SYNC_STAMP="${STAMP_DIR}/uv-sync.stamp"
BUILD_STAMP="${STAMP_DIR}/build-ext.stamp"
READY_MARKER="${STAMP_DIR}/container-ready"
VENV_PYTHON="${WORKDIR}/.venv/bin/python"
CONTAINER_ROLE="${SEC_NLP_CONTAINER_ROLE:-benchmark-runner}"
CONTAINER_LOG_DIR="${SEC_NLP_CONTAINER_LOG_DIR:-${WORKDIR}/logs/container/${CONTAINER_ROLE}}"
BOOTSTRAP_LOG="${CONTAINER_LOG_DIR}/bootstrap.log"
METADATA_FILE="${CONTAINER_LOG_DIR}/metadata.json"
STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

mkdir -p \
  "${STAMP_DIR}" \
  "${WORKDIR}/downloads" \
  "${WORKDIR}/logs" \
  "${WORKDIR}/outputs" \
  "${WORKDIR}/target" \
  "${WORKDIR}/.qdrant" \
  "${CONTAINER_LOG_DIR}"

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

needs_build_ext=0
if [[ ! -f "${BUILD_STAMP}" ]]; then
  needs_build_ext=1
fi

if [[ "${needs_build_ext}" -eq 0 ]]; then
  while IFS= read -r -d '' source_file; do
    if [[ "${source_file}" -nt "${BUILD_STAMP}" ]]; then
      needs_build_ext=1
      break
    fi
  done < <(find crates -type f \( -name '*.rs' -o -name 'Cargo.toml' \) -print0)
fi

if [[ "${needs_build_ext}" -eq 1 ]]; then
  echo "[sec-nlp-container] (${GIT_COMMIT}) building Rust extensions"
  make build-ext
  touch "${BUILD_STAMP}"
fi

touch "${READY_MARKER}"
echo "[sec-nlp-container] (${GIT_COMMIT}) ready"

exec "$@"
