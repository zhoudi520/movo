#!/usr/bin/env bash
# Copy Docker bootstrap secrets to .movo-dev/runtime.env for host-side backends.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VOLUME_PREFIX="${MOVO_VOLUME_PREFIX:-movo}"
VOLUME_NAME="${VOLUME_PREFIX}_deployment-secrets"
OUT_DIR="${ROOT_DIR}/.movo-dev"
OUT_FILE="${OUT_DIR}/runtime.env"

mkdir -p "${OUT_DIR}"
docker run --rm -v "${VOLUME_NAME}:/run/askai-secrets:ro" alpine:3.21 \
  cat /run/askai-secrets/runtime.env > "${OUT_FILE}"
echo "Wrote ${OUT_FILE} from Docker volume ${VOLUME_NAME}"
