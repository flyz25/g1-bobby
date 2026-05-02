#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."

echo "[doctor] local test suite"
.venv/bin/python -m pytest -q

echo "[doctor] local diagnostic report"
.venv/bin/python -m g1_bobby_unitree_bridge.diagnostic_cli --network-interface "${G1_BOBBY_UNITREE_NETWORK_INTERFACE:-eth0}" --transport "${G1_BOBBY_UNITREE_COMMAND_TRANSPORT:-sdk_real}"

echo "[doctor] done"
