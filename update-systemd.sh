#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_ROOT="${CAS_SERVICE_ROOT:-$SCRIPT_DIR}"
SERVICE_USER="${CAS_SERVICE_USER:-$(whoami)}"
ENV_FILE="${CAS_ENV_FILE:-$SERVICE_ROOT/.env}"
CAS_PORT_VALUE="${CAS_PORT:-8769}"
CAS_LOG_LEVEL_VALUE="${CAS_LOG_LEVEL:-INFO}"
START_SCRIPT="$SERVICE_ROOT/scripts/cas_service_start.sh"

if [[ ! -x "$START_SCRIPT" ]]; then
  echo "[cas-service] ERROR: start script not found at $START_SCRIPT" >&2
  exit 1
fi

cat > /etc/systemd/system/cas-service.service <<EOF
[Unit]
Description=CAS Microservice (Sage + SymPy + MATLAB + WolframAlpha)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${SERVICE_ROOT}
ExecStart=${START_SCRIPT}
Restart=on-failure
RestartSec=5
Environment=CAS_PORT=${CAS_PORT_VALUE}
Environment=CAS_LOG_LEVEL=${CAS_LOG_LEVEL_VALUE}
Environment=CAS_ENV_FILE=${ENV_FILE}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now cas-service
sleep 3
systemctl status cas-service --no-pager || true

echo ""
echo "=== Health check ==="
curl -fsS "http://localhost:${CAS_PORT_VALUE}/health" | python3 -m json.tool
