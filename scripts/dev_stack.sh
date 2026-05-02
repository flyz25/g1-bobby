#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."

echo "[stack] API dashboard on http://127.0.0.1:8010/dashboard"
echo "[stack] use make unitree-report or make unitree-sim-trace for container diagnostics"

exec ./scripts/dev_up.sh
