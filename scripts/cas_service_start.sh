#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="$(dirname "$SCRIPT_DIR")"
VENV_PYTHON="${CAS_VENV_PYTHON:-$SERVICE_ROOT/.venv/bin/python}"
DOTENVX_BIN="${DOTENVX_BIN:-$(command -v dotenvx || true)}"
ENV_FILE="${CAS_ENV_FILE:-$SERVICE_ROOT/.env}"

# Systemd/manual starts should remain stable even if the encrypted .env still
# contains an obsolete CAS_PORT value. Existing env vars keep precedence.
export CAS_PORT="${CAS_PORT:-8769}"
export CAS_LOG_LEVEL="${CAS_LOG_LEVEL:-INFO}"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "[cas-service] ERROR: python runtime not found at $VENV_PYTHON" >&2
  exit 1
fi

if [[ -n "$DOTENVX_BIN" && -f "$ENV_FILE" ]]; then
  exec "$DOTENVX_BIN" run -f "$ENV_FILE" -- "$VENV_PYTHON" -m cas_service.main
fi

exec "$VENV_PYTHON" -m cas_service.main
